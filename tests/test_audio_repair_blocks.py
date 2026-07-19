import json
import wave
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from story_audio.audio_repair_blocks import (
    AudioRepairBlockValidationError,
    build_active_audio_preview,
    create_audio_repair_block_candidate,
    list_audio_repair_blocks,
    reject_audio_repair_block_candidate,
)
from story_audio.db import Database, utcnow
from story_audio.files import sha256_file, sha256_text
from story_audio.storage import ContentStore
from tests.base import IsolatedTestCase


class AudioRepairBlockTests(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        self.tts = Mock()
        self.tts.synthesize.side_effect = self._synthesize
        self.synth_inputs = []
        self._create_job_with_adjacent_segments()

    def _write_wav(self, path: Path, duration_ms: int = 100):
        path.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = 48000
        samples = duration_ms * sample_rate // 1000
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(b"\0\0" * samples)

    def _synthesize(self, *, synth_input, output_path):
        self.synth_inputs.append(synth_input)
        self._write_wav(output_path, 250)
        return 250, 48000

    def _create_job_with_adjacent_segments(self):
        self.full_text = "Alpha beta gamma. Next sentence."
        self.segment_texts = ["Alpha beta", "gamma."]
        self.settings_json = json.dumps(
            {
                "temperature": 0.8,
                "top_k": 25,
                "max_chars": 256,
                "silence_seconds": 0.15,
                "engine_version": "vieneu:v3turbo",
            },
            sort_keys=True,
        )
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO books(title,author,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                ("Book", "Author", "book.epub", sha256_text("book.epub"), utcnow(), utcnow()),
            )
            self.book_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,char_count,audio_status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (self.book_id, 368, "Chapter 368", len(self.full_text), "completed", utcnow(), utcnow()),
            )
            self.chapter_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            text_path, text_sha = self.store.put_text(self.full_text)
            conn.execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,parent_revision_id,content_path,content_sha256,lexical_sha256,
                    char_count,processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    self.chapter_id,
                    "reflowed",
                    None,
                    text_path,
                    text_sha,
                    text_sha,
                    len(self.full_text),
                    "test",
                    "approved",
                    utcnow(),
                ),
            )
            self.text_revision_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            plan_payload = {
                "utterances": [
                    {
                        "utterance_id": "u1",
                        "sequence": 1,
                        "start_offset": 0,
                        "end_offset": len("Alpha beta"),
                        "speaker_role": "narrator",
                    },
                    {
                        "utterance_id": "u2",
                        "sequence": 2,
                        "start_offset": len("Alpha beta "),
                        "end_offset": len("Alpha beta gamma."),
                        "speaker_role": "narrator",
                    },
                ]
            }
            plan_json = json.dumps(plan_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            plan_path, _plan_content_sha = self.store.put_text(plan_json)
            self.plan_sha = sha256_text(plan_json)
            conn.execute(
                """INSERT INTO casting_plans(
                    chapter_id,text_revision_id,plan_revision,status,content_path,plan_sha256,
                    narrator_voice_id,created_at,approved_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    self.chapter_id,
                    self.text_revision_id,
                    1,
                    "approved",
                    plan_path,
                    self.plan_sha,
                    "preset_voice",
                    utcnow(),
                    utcnow(),
                ),
            )
            self.casting_plan_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            job_settings = json.dumps({"engine_version": "vieneu:v3turbo"}, sort_keys=True)
            conn.execute(
                """INSERT INTO jobs(
                    book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                    settings_json,total_chapters,scheduled_at,created_at,updated_at,finished_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    self.book_id,
                    "completed",
                    368,
                    368,
                    "preset_voice",
                    "off",
                    "m4a",
                    job_settings,
                    1,
                    utcnow(),
                    utcnow(),
                    utcnow(),
                    utcnow(),
                ),
            )
            self.job_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute(
                """INSERT INTO job_chapters(
                    job_id,chapter_id,sequence,status,text_revision_id,finished_at,
                    casting_plan_id,casting_plan_sha256
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    self.job_id,
                    self.chapter_id,
                    1,
                    "completed",
                    self.text_revision_id,
                    utcnow(),
                    self.casting_plan_id,
                    self.plan_sha,
                ),
            )
            self.job_chapter_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            self.segment_ids = []
            for idx, text in enumerate(self.segment_texts, start=1):
                text_path, text_sha = self.store.put_text(text)
                wav_path = self.config.work_dir / f"job_{self.job_id}" / "chapter_0368" / "segments" / f"{idx:06d}.wav"
                self._write_wav(wav_path, 100)
                conn.execute(
                    """INSERT INTO segments(
                        job_chapter_id,segment_index,text_path,text_sha256,status,
                        wav_path,audio_sha256,duration_ms,verified_at,created_at,
                        utterance_sequence,speaker_role,resolved_voice_id,casting_plan_id,
                        voice_snapshot_version,voice_source_type,voice_provider,voice_model,
                        logical_voice_ref,effective_voice_ref,synthesis_settings_json,
                        voice_resolution_reason,synthesis_hash
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        self.job_chapter_id,
                        idx,
                        text_path,
                        text_sha,
                        "verified",
                        str(wav_path),
                        sha256_file(wav_path),
                        100,
                        utcnow(),
                        utcnow(),
                        idx,
                        "narrator",
                        "preset_voice",
                        self.casting_plan_id,
                        1,
                        "preset",
                        "vieneu",
                        "v3turbo",
                        "narrator",
                        "preset_voice",
                        self.settings_json,
                        "direct",
                        sha256_text(self.settings_json + text + "preset_voice"),
                    ),
                )
                self.segment_ids.append(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

            artifact_path = self.config.output_dir / "chapter.m4a"
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_bytes(b"active artifact")
            conn.execute(
                """INSERT INTO artifacts(
                    chapter_id,job_chapter_id,text_revision_id,artifact_type,
                    path,sha256,size_bytes,duration_ms,status,created_at,verified_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    self.chapter_id,
                    self.job_chapter_id,
                    self.text_revision_id,
                    "chapter_final_m4a",
                    str(artifact_path),
                    sha256_file(artifact_path),
                    artifact_path.stat().st_size,
                    200,
                    "active",
                    utcnow(),
                    utcnow(),
                ),
            )
            self.artifact_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute("UPDATE chapters SET active_audio_artifact_id=? WHERE id=?", (self.artifact_id, self.chapter_id))

    def _count(self, table: str) -> int:
        return int(self.db.fetch_one(f"SELECT COUNT(*) AS count FROM {table}")["count"])

    def test_create_candidate_uses_revision_span_and_keeps_active_state(self):
        result = create_audio_repair_block_candidate(
            self.db,
            self.store,
            self.tts,
            self.config,
            job_id=self.job_id,
            first_segment_id=self.segment_ids[0],
            last_segment_id=self.segment_ids[1],
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["reused"])
        self.assertEqual(result["source_text"], "Alpha beta gamma.")
        self.assertEqual(result["source_start_offset"], 0)
        self.assertEqual(result["source_end_offset"], len("Alpha beta gamma."))
        self.assertEqual(self.synth_inputs[0].text, "Alpha beta gamma.")
        self.assertEqual(self._count("jobs"), 1)
        self.assertEqual(self._count("job_chapters"), 1)
        self.assertEqual(self._count("segment_attempts"), 0)
        self.assertEqual(self._count("artifacts"), 1)
        chapter = self.db.fetch_one("SELECT active_audio_artifact_id FROM chapters WHERE id=?", (self.chapter_id,))
        self.assertEqual(chapter["active_audio_artifact_id"], self.artifact_id)

    def test_duplicate_pending_candidate_reuses_existing_without_second_tts_call(self):
        first = create_audio_repair_block_candidate(
            self.db,
            self.store,
            self.tts,
            self.config,
            job_id=self.job_id,
            first_segment_id=self.segment_ids[0],
            last_segment_id=self.segment_ids[1],
        )
        second = create_audio_repair_block_candidate(
            self.db,
            self.store,
            self.tts,
            self.config,
            job_id=self.job_id,
            first_segment_id=self.segment_ids[0],
            last_segment_id=self.segment_ids[1],
        )

        self.assertEqual(second["id"], first["id"])
        self.assertTrue(second["reused"])
        self.assertEqual(self.tts.synthesize.call_count, 1)
        self.assertEqual(self._count("audio_repair_blocks"), 1)

    def test_reject_candidate_does_not_touch_active_artifact(self):
        created = create_audio_repair_block_candidate(
            self.db,
            self.store,
            self.tts,
            self.config,
            job_id=self.job_id,
            first_segment_id=self.segment_ids[0],
            last_segment_id=self.segment_ids[1],
        )

        rejected = reject_audio_repair_block_candidate(self.db, created["id"])

        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(self._count("segment_attempts"), 0)
        chapter = self.db.fetch_one("SELECT active_audio_artifact_id FROM chapters WHERE id=?", (self.chapter_id,))
        self.assertEqual(chapter["active_audio_artifact_id"], self.artifact_id)

    def test_rejects_single_segment_without_synthesis(self):
        with self.assertRaises(AudioRepairBlockValidationError):
            create_audio_repair_block_candidate(
                self.db,
                self.store,
                self.tts,
                self.config,
                job_id=self.job_id,
                first_segment_id=self.segment_ids[1],
                last_segment_id=self.segment_ids[1],
            )

        self.assertEqual(self.tts.synthesize.call_count, 0)
        self.assertEqual(self._count("audio_repair_blocks"), 0)

    def test_rejects_mixed_voice_without_partial_state(self):
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE segments SET effective_voice_ref=?, resolved_voice_id=? WHERE id=?",
                ("other_voice", "other_voice", self.segment_ids[1]),
            )

        with self.assertRaises(AudioRepairBlockValidationError):
            create_audio_repair_block_candidate(
                self.db,
                self.store,
                self.tts,
                self.config,
                job_id=self.job_id,
                first_segment_id=self.segment_ids[0],
                last_segment_id=self.segment_ids[1],
            )

        self.assertEqual(self.tts.synthesize.call_count, 0)
        self.assertEqual(self._count("audio_repair_blocks"), 0)

    def test_rejects_unapproved_or_mismatched_plan_without_partial_state(self):
        with self.db.connect() as conn:
            conn.execute("UPDATE casting_plans SET status='draft' WHERE id=?", (self.casting_plan_id,))

        with self.assertRaises(AudioRepairBlockValidationError):
            create_audio_repair_block_candidate(
                self.db,
                self.store,
                self.tts,
                self.config,
                job_id=self.job_id,
                first_segment_id=self.segment_ids[0],
                last_segment_id=self.segment_ids[1],
            )

        self.assertEqual(self.tts.synthesize.call_count, 0)
        self.assertEqual(self._count("audio_repair_blocks"), 0)

    def test_rejects_wrong_job_id_without_partial_state(self):
        with self.assertRaises(AudioRepairBlockValidationError):
            create_audio_repair_block_candidate(
                self.db,
                self.store,
                self.tts,
                self.config,
                job_id=self.job_id + 1,
                first_segment_id=self.segment_ids[0],
                last_segment_id=self.segment_ids[1],
            )

        self.assertEqual(self.tts.synthesize.call_count, 0)
        self.assertEqual(self._count("audio_repair_blocks"), 0)

    def test_uses_job_chapter_pin_when_segment_pin_is_missing(self):
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE segments SET casting_plan_id=NULL WHERE id IN (?, ?)",
                (self.segment_ids[0], self.segment_ids[1]),
            )

        result = create_audio_repair_block_candidate(
            self.db,
            self.store,
            self.tts,
            self.config,
            job_id=self.job_id,
            first_segment_id=self.segment_ids[0],
            last_segment_id=self.segment_ids[1],
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["casting_plan_id"], self.casting_plan_id)
        self.assertEqual(self.tts.synthesize.call_count, 1)

    def test_list_repair_blocks_returns_candidate_identity(self):
        created = create_audio_repair_block_candidate(
            self.db,
            self.store,
            self.tts,
            self.config,
            job_id=self.job_id,
            first_segment_id=self.segment_ids[0],
            last_segment_id=self.segment_ids[1],
        )

        listed = list_audio_repair_blocks(self.db, self.job_chapter_id)

        self.assertEqual(listed["repair_blocks"][0]["id"], created["id"])
        self.assertEqual(listed["repair_blocks"][0]["covered_segment_ids"], self.segment_ids)

    def test_active_preview_builds_without_mutating_state(self):
        created = create_audio_repair_block_candidate(
            self.db,
            self.store,
            self.tts,
            self.config,
            job_id=self.job_id,
            first_segment_id=self.segment_ids[0],
            last_segment_id=self.segment_ids[1],
        )

        def fake_run(command, check, capture_output, text):
            temp_path = Path(command[-1])
            self._write_wav(temp_path, 150)
            return Mock()

        with patch("story_audio.audio_repair_blocks.subprocess.run", side_effect=fake_run):
            preview_path = build_active_audio_preview(self.db, self.config, created["id"])

        self.assertTrue(preview_path.exists())
        self.assertIn("active_preview.wav", str(preview_path))
        self.assertEqual(self._count("audio_repair_blocks"), 1)

    def test_api_ignores_client_text_and_voice_overrides(self):
        import story_audio.api as api_module

        original_db = api_module.db
        original_store = api_module.store
        original_tts = api_module.tts_service
        original_settings = api_module.settings
        try:
            api_module.db = self.db
            api_module.store = self.store
            api_module.tts_service = self.tts
            api_module.settings = self.config
            client = TestClient(api_module.app)
            response = client.post(
                f"/api/jobs/{self.job_id}/repair-blocks",
                json={
                    "first_segment_id": self.segment_ids[0],
                    "last_segment_id": self.segment_ids[1],
                    "text": "client supplied text",
                    "effective_voice_ref": "client_voice",
                },
            )
        finally:
            api_module.db = original_db
            api_module.store = original_store
            api_module.tts_service = original_tts
            api_module.settings = original_settings

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source_text"], "Alpha beta gamma.")
        self.assertEqual(self.synth_inputs[0].effective_voice_ref, "preset_voice")


class AudioRepairBlockUiTests(IsolatedTestCase):
    def test_ui_exposes_ab_review_without_enabled_accept(self):
        ui_source = (Path(__file__).resolve().parents[1] / "ui" / "app.js").read_text(encoding="utf-8")

        self.assertIn("Original active range", ui_source)
        self.assertIn("/api/audio-repair-blocks/${block.id}/active-audio", ui_source)
        self.assertIn("Repair-block candidate", ui_source)
        self.assertIn("rejectRepairBlock", ui_source)
        self.assertIn("disabled title=\"Repair-block acceptance is handled in a later reviewed workflow\"", ui_source)
