from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from story_audio.chapter_repair_execution import (
    ChapterRepairInstructionError,
    compile_chapter_repair_instruction,
    materialize_offline_repair_segments,
)
from story_audio.files import sha256_file, sha256_text
from story_audio.pipeline import PipelineWorker
from story_audio.storage import ContentStore
from tests.base import IsolatedTestCase
from tests.test_audio_qa import AudioQaFixture


class ChapterRepairExecutionTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            self.skipTest("ffmpeg/ffprobe are required")
        self.fixture = AudioQaFixture(self)
        first = self.fixture.segments[0]
        first["leading_silence_ms"] = 900
        first["trailing_silence_ms"] = 650
        self.fixture.build()
        self.db = self.fixture.db
        with self.db.transaction() as connection:
            connection.execute(
                """INSERT INTO jobs(
                    id,book_id,status,from_chapter,to_chapter,voice_name,repair_mode,
                    output_format,settings_json,scheduled_at,created_at,updated_at
                ) VALUES(2,1,'prepared',629,629,'ngoc_lan','off','m4a',?,datetime('now'),datetime('now'),datetime('now'))""",
                (json.dumps({"engine_version": "fixture"}),),
            )
            connection.execute(
                """INSERT INTO job_chapters(
                    id,job_id,chapter_id,sequence,status,text_revision_id
                ) VALUES(2,2,1,1,'pending',1)"""
            )
            for source in self.db.fetch_all(
                "SELECT * FROM segments WHERE job_chapter_id=1 ORDER BY segment_index"
            ):
                connection.execute(
                    """INSERT INTO segments(
                        id,job_chapter_id,segment_index,text_path,text_sha256,status,
                        attempt_count,created_at,utterance_sequence,speaker_role,
                        character_id,resolved_voice_id,synthesis_hash
                    ) VALUES(?,?,?, ?,?,'pending',0,datetime('now'),?,?,?,?,?)""",
                    (
                        100 + int(source["id"]),
                        2,
                        int(source["segment_index"]),
                        source["text_path"],
                        source["text_sha256"],
                        source["utterance_sequence"],
                        source["speaker_role"],
                        source["character_id"],
                        source["resolved_voice_id"],
                        source["synthesis_hash"],
                    ),
                )

    def _markers(self) -> list[dict]:
        source = self.db.fetch_one("SELECT * FROM segments WHERE id=1")
        common = {
            "timestamp_seconds": 0.0,
            "segment_id": 1,
            "segment_audio_sha256": source["audio_sha256"],
            "risk_kind": "silence",
        }
        return [
            {**common, "repair_kind": "trim_leading_silence", "machine_finding_key": "lead"},
            {**common, "repair_kind": "trim_trailing_silence", "machine_finding_key": "tail"},
        ]

    def test_compiles_and_executes_all_repairs_in_one_offline_batch(self) -> None:
        instruction = compile_chapter_repair_instruction(
            self.db,
            chapter_id=1,
            artifact_id=3,
            markers=self._markers(),
            repeated_words=False,
            global_speed_target=None,
            local_pacing_adjustment_required=False,
        )
        instruction["replacement_for_artifact_id"] = 3
        self.assertTrue(instruction["execution_ready"])
        self.assertEqual(instruction["machine_action_count"], 2)

        source_hashes = {
            int(row["segment_index"]): str(row["audio_sha256"])
            for row in self.db.fetch_all("SELECT * FROM segments WHERE job_chapter_id=1")
        }
        target_rows = [dict(row) for row in self.db.fetch_all("SELECT * FROM segments WHERE job_chapter_id=2")]
        rendered = materialize_offline_repair_segments(
            self.db,
            self.config,
            chapter_id=1,
            instruction=instruction,
            target_segments=target_rows,
            target_dir=self.config.work_dir / "job_2" / "chapter_0629" / "segments",
        )

        self.assertTrue(all(row["status"] == "verified" for row in rendered))
        self.assertNotEqual(rendered[0]["audio_sha256"], source_hashes[1])
        self.assertEqual(rendered[1]["audio_sha256"], source_hashes[2])
        self.assertTrue(all(Path(row["wav_path"]).is_file() for row in rendered))
        self.assertEqual(
            self.db.fetch_one("SELECT active_audio_artifact_id FROM chapters WHERE id=1")[
                "active_audio_artifact_id"
            ],
            3,
        )
        self.assertEqual(sha256_file(self.fixture.final_path), instruction["source_artifact_sha256"])

    def test_pipeline_creates_one_replacement_without_calling_tts(self) -> None:
        instruction = compile_chapter_repair_instruction(
            self.db,
            chapter_id=1,
            artifact_id=3,
            markers=self._markers(),
            repeated_words=False,
            global_speed_target=None,
            local_pacing_adjustment_required=False,
        )
        instruction.update(
            {
                "schema": "story-audio-repair-instruction/v2",
                "replacement_for_artifact_id": 3,
            }
        )
        store = ContentStore(self.config)
        chapter_text = "\n".join(item["text"] for item in self.fixture.segments)
        chapter_path, chapter_sha = store.put_text(chapter_text)
        with self.db.transaction() as connection:
            connection.execute(
                """UPDATE text_revisions SET content_path=?,content_sha256=?,
                   lexical_sha256=?,char_count=? WHERE id=1""",
                (chapter_path, chapter_sha, sha256_text(chapter_text), len(chapter_text)),
            )
            for item in self.fixture.segments:
                text_path, text_sha = store.put_text(item["text"])
                connection.execute(
                    "UPDATE segments SET text_path=?,text_sha256=? WHERE id IN (?,?)",
                    (text_path, text_sha, int(item["sequence"]), 100 + int(item["sequence"])),
                )
            connection.execute(
                "UPDATE jobs SET status='scheduled',settings_json=? WHERE id=2",
                (json.dumps({"engine_version": "fixture", "repair_instruction": instruction}),),
            )

        class FailingTts:
            calls = 0

            def synthesize(self, **_kwargs):
                self.calls += 1
                raise AssertionError("TTS must not be called for offline chapter repair")

        tts = FailingTts()
        worker = PipelineWorker(self.db, store, tts, self.config)
        job = dict(self.db.fetch_one("SELECT * FROM jobs WHERE id=2"))
        chapter = dict(
            self.db.fetch_one(
                """SELECT jc.*,c.chapter_number,c.book_id,b.title AS book_title
                   FROM job_chapters jc JOIN chapters c ON c.id=jc.chapter_id
                   JOIN books b ON b.id=c.book_id WHERE jc.id=2"""
            )
        )
        worker._process_chapter(job, chapter)

        current = self.db.fetch_one(
            "SELECT active_audio_artifact_id,human_approval_json FROM chapters WHERE id=1"
        )
        self.assertNotEqual(int(current["active_audio_artifact_id"]), 3)
        self.assertIsNone(current["human_approval_json"])
        self.assertEqual(tts.calls, 0)
        self.assertEqual(
            self.db.fetch_one("SELECT artifact_id,status FROM job_chapters WHERE id=2")["status"],
            "completed",
        )

    def test_stale_segment_sha_fails_before_writing_replacement(self) -> None:
        markers = self._markers()
        markers[0]["segment_audio_sha256"] = "0" * 64
        with self.assertRaises(ChapterRepairInstructionError):
            compile_chapter_repair_instruction(
                self.db,
                chapter_id=1,
                artifact_id=3,
                markers=markers,
                repeated_words=False,
                global_speed_target=None,
                local_pacing_adjustment_required=False,
            )
        self.assertFalse((self.config.work_dir / "job_2" / "chapter_0629" / "segments").exists())

    def test_manual_marker_resolves_to_exact_segment_for_resynthesis(self) -> None:
        instruction = compile_chapter_repair_instruction(
            self.db,
            chapter_id=1,
            artifact_id=3,
            markers=[{"timestamp_seconds": 0.4, "risk_kind": "hard_clipping"}],
            repeated_words=False,
            global_speed_target=None,
            local_pacing_adjustment_required=False,
        )
        self.assertTrue(instruction["execution_ready"])
        self.assertEqual(instruction["execution_mode"], "hybrid_segment_batch")
        self.assertTrue(instruction["provider_call_required"])
        self.assertEqual(instruction["resynthesis_segment_count"], 1)
        self.assertEqual(instruction["machine_actions"][0]["segment_id"], 1)

    def test_repeated_words_without_reviewed_location_fails_closed(self) -> None:
        instruction = compile_chapter_repair_instruction(
            self.db,
            chapter_id=1,
            artifact_id=3,
            markers=[],
            repeated_words=True,
            global_speed_target=None,
            local_pacing_adjustment_required=False,
        )
        self.assertFalse(instruction["execution_ready"])
        self.assertEqual(instruction["execution_mode"], "blocked")
        self.assertIn("repeated_words_location_required", instruction["execution_blockers"])

    def test_marker_without_timestamp_or_segment_fails_closed(self) -> None:
        with self.assertRaisesRegex(ChapterRepairInstructionError, "thời điểm nghe"):
            compile_chapter_repair_instruction(
                self.db,
                chapter_id=1,
                artifact_id=3,
                markers=[{"issue": "repeated_words"}],
                repeated_words=True,
                global_speed_target=None,
                local_pacing_adjustment_required=False,
            )

    def test_conflicting_local_paces_for_one_segment_fail_closed(self) -> None:
        with self.assertRaisesRegex(ChapterRepairInstructionError, "hai tốc độ"):
            compile_chapter_repair_instruction(
                self.db,
                chapter_id=1,
                artifact_id=3,
                markers=[
                    {"timestamp_seconds": 0.4, "issue": "too_slow", "local_pace": 1.1},
                    {"timestamp_seconds": 0.5, "issue": "too_fast", "local_pace": 0.9},
                ],
                repeated_words=False,
                global_speed_target=None,
                local_pacing_adjustment_required=True,
            )

    def test_local_pace_overrides_global_speed_for_its_segment(self) -> None:
        instruction = compile_chapter_repair_instruction(
            self.db,
            chapter_id=1,
            artifact_id=3,
            markers=[{"timestamp_seconds": 0.4, "issue": "too_slow", "local_pace": 1.1}],
            repeated_words=False,
            global_speed_target=1.25,
            local_pacing_adjustment_required=True,
        )
        self.assertTrue(instruction["execution_ready"])
        self.assertEqual(instruction["execution_mode"], "offline_segment_batch")
        tempos = {
            int(action["segment_index"]): float(action["tempo"])
            for action in instruction["machine_actions"]
        }
        self.assertEqual(tempos, {1: 1.1, 2: 1.25})

        instruction["replacement_for_artifact_id"] = 3
        source_durations = {
            int(row["segment_index"]): int(row["duration_ms"])
            for row in self.db.fetch_all("SELECT * FROM segments WHERE job_chapter_id=1")
        }
        rendered = materialize_offline_repair_segments(
            self.db,
            self.config,
            chapter_id=1,
            instruction=instruction,
            target_segments=[
                dict(row)
                for row in self.db.fetch_all("SELECT * FROM segments WHERE job_chapter_id=2")
            ],
            target_dir=self.config.work_dir / "job_2" / "chapter_0629" / "segments",
        )
        self.assertLess(int(rendered[0]["duration_ms"]), source_durations[1])
        self.assertLess(int(rendered[1]["duration_ms"]), source_durations[2])

    def test_hybrid_batch_resynthesizes_only_the_exact_segment(self) -> None:
        instruction = compile_chapter_repair_instruction(
            self.db,
            chapter_id=1,
            artifact_id=3,
            markers=[{"timestamp_seconds": 0.4, "issue": "repeated_words"}],
            repeated_words=True,
            global_speed_target=None,
            local_pacing_adjustment_required=False,
        )
        instruction["replacement_for_artifact_id"] = 3
        source_path = Path(self.db.fetch_one("SELECT wav_path FROM segments WHERE id=1")["wav_path"])

        class FakeTts:
            calls = 0

            def synthesize(self, *, synth_input, output_path):
                self.calls += 1
                subprocess.run(
                    ["ffmpeg", "-y", "-v", "error", "-i", str(source_path), "-af", "volume=0.5", str(output_path)],
                    check=True,
                )

        target_rows = [dict(row) for row in self.db.fetch_all("SELECT * FROM segments WHERE job_chapter_id=2")]
        tts = FakeTts()
        with patch(
            "story_audio.chapter_repair_execution.load_segment_synthesis_input",
            return_value=object(),
        ):
            rendered = materialize_offline_repair_segments(
                self.db,
                self.config,
                chapter_id=1,
                instruction=instruction,
                target_segments=target_rows,
                target_dir=self.config.work_dir / "job_2" / "chapter_0629" / "segments",
                store=ContentStore(self.config),
                tts=tts,
            )
        self.assertEqual(tts.calls, 1)
        self.assertNotEqual(rendered[0]["audio_sha256"], sha256_file(source_path))
        self.assertEqual(
            rendered[1]["audio_sha256"],
            self.db.fetch_one("SELECT audio_sha256 FROM segments WHERE id=2")["audio_sha256"],
        )

    def test_failed_resynthesis_removes_partial_replacement_files(self) -> None:
        instruction = compile_chapter_repair_instruction(
            self.db,
            chapter_id=1,
            artifact_id=3,
            markers=[{"timestamp_seconds": 0.4, "issue": "repeated_words"}],
            repeated_words=True,
            global_speed_target=None,
            local_pacing_adjustment_required=False,
        )
        instruction["replacement_for_artifact_id"] = 3
        target_dir = self.config.work_dir / "job_2" / "chapter_0629" / "segments"

        class FailingTts:
            def synthesize(self, *, synth_input, output_path):
                Path(output_path).write_bytes(b"partial")
                raise RuntimeError("fixture failure")

        with patch(
            "story_audio.chapter_repair_execution.load_segment_synthesis_input",
            return_value=object(),
        ), self.assertRaisesRegex(ChapterRepairInstructionError, "Không tái tạo"):
            materialize_offline_repair_segments(
                self.db,
                self.config,
                chapter_id=1,
                instruction=instruction,
                target_segments=[
                    dict(row)
                    for row in self.db.fetch_all("SELECT * FROM segments WHERE job_chapter_id=2")
                ],
                target_dir=target_dir,
                store=ContentStore(self.config),
                tts=FailingTts(),
            )
        self.assertEqual(list(target_dir.glob("*.wav")), [])
        self.assertTrue(
            all(
                row["status"] == "pending" and row["wav_path"] is None
                for row in self.db.fetch_all("SELECT * FROM segments WHERE job_chapter_id=2")
            )
        )


if __name__ == "__main__":
    unittest.main()
