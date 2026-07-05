from __future__ import annotations

import json
import unittest
from pathlib import Path

from story_audio.db import Database
from story_audio.files import sha256_file, sha256_text
from story_audio.production_runner import (
    TerminalValidationError,
    build_completed_manifest,
    write_manifest,
)
from story_audio.storage import ContentStore
from tests.base import IsolatedTestCase


class ProductionManifestTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        self.config.ensure_dirs()

        with self.db.transaction() as conn:
            self.book_id = int(conn.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,datetime('now'),datetime('now'))",
                ("Test Book", "test://book", "b" * 64, 1),
            ).lastrowid)
            self.chapter_id = int(conn.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at,audio_status) VALUES(?,?,?,?,datetime('now'),datetime('now'),'completed')",
                (self.book_id, 629, "Chapter 629", 120),
            ).lastrowid)
            self.character_id = int(conn.execute(
                """
                INSERT INTO characters(book_id,display_name,default_voice_id,voice_override_id,active,created_at,updated_at)
                VALUES(?,?,?,?,1,datetime('now'),datetime('now'))
                """,
                (self.book_id, "Ati", "duc_tri", None),
            ).lastrowid)

        self.text_one = "Ati noi mot cau."
        self.text_two = "Nguoi ke tiep tuc."
        first_path, first_sha = self.store.put_text(self.text_one)
        second_path, second_sha = self.store.put_text(self.text_two)
        self.segment_text_paths = [first_path, second_path]
        self.segment_text_sha = [first_sha, second_sha]
        chapter_text = self.text_one + "\n" + self.text_two
        revision_path, revision_sha = self.store.put_text(chapter_text)
        with self.db.transaction() as conn:
            self.text_revision_id = int(conn.execute(
                """
                INSERT INTO text_revisions(
                    chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                    processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,datetime('now'))
                """,
                (
                    self.chapter_id,
                    "reflowed",
                    revision_path,
                    revision_sha,
                    sha256_text(chapter_text),
                    len(chapter_text),
                    "v1",
                    "approved",
                ),
            ).lastrowid)
            conn.execute(
                "UPDATE chapters SET active_text_revision_id=?,updated_at=datetime('now') WHERE id=?",
                (self.text_revision_id, self.chapter_id),
            )

        self.render_dir = (
            self.config.output_dir
            / f"{self.book_id}-test-book"
            / "chapter_0629"
            / "job_2"
            / "render_0001"
        )
        self.render_dir.mkdir(parents=True, exist_ok=True)
        self.segment_dir = self.config.work_dir / "job_2" / "chapter_0629" / "segments"
        self.segment_dir.mkdir(parents=True, exist_ok=True)

        self.segment_paths = [
            self.segment_dir / "000001.wav",
            self.segment_dir / "000002.wav",
        ]
        self.segment_paths[0].write_bytes(b"RIFFSEGMENT0001")
        self.segment_paths[1].write_bytes(b"RIFFSEGMENT0002")
        self.segment_audio_sha = [sha256_file(path) for path in self.segment_paths]

        self.master_path = self.render_dir / "chapter_master.wav"
        self.timeline_path = self.render_dir / "segment_timeline.json"
        self.final_path = self.render_dir / "chapter.m4a"
        self.master_path.write_bytes(b"RIFFMASTERWAV")
        self.final_path.write_bytes(b"M4AFINALDATA")
        timeline_payload = {
            "schema_version": 2,
            "chapter_id": self.chapter_id,
            "text_revision_id": self.text_revision_id,
            "sample_rate": 48000,
            "duration_ms": 2000,
            "items": [
                {
                    "index": 1,
                    "text": self.text_one,
                    "start_ms": 0,
                    "end_ms": 1000,
                    "duration_ms": 1000,
                    "segment_sha256": self.segment_audio_sha[0],
                    "utterance_sequence": 1,
                    "speaker_role": "character",
                    "character_id": 81,
                    "character_name": "Ati",
                    "voice_id": "duc_tri",
                    "synthesis_hash": "synth-1",
                },
                {
                    "index": 2,
                    "text": self.text_two,
                    "start_ms": 1000,
                    "end_ms": 2000,
                    "duration_ms": 1000,
                    "segment_sha256": self.segment_audio_sha[1],
                    "utterance_sequence": 2,
                    "speaker_role": "narrator",
                    "character_id": None,
                    "character_name": None,
                    "voice_id": "ngoc_lan",
                    "synthesis_hash": "synth-2",
                },
            ],
        }
        self.timeline_path.write_text(json.dumps(timeline_payload, ensure_ascii=False), encoding="utf-8")

        casting_snapshot = {
            "casting_plan_id": 55,
            "casting_plan_sha256": "plan-sha-55",
            "text_revision_id": self.text_revision_id,
            "narrator_voice_id": "ngoc_lan",
            "book_voice_profile": {
                "id": 9,
                "config_version": 4,
                "narrator_voice_id": "ngoc_lan",
                "male_dialogue_voice_id": "duc_tri",
                "female_dialogue_voice_id": "my_duyen",
                "unknown_fallback": "narrator",
                "unknown_voice_id": None,
            },
            "utterances": [
                {"sequence": 1, "role": "character", "resolved_voice_id": "duc_tri"},
                {"sequence": 2, "role": "narrator", "resolved_voice_id": "ngoc_lan"},
            ],
        }
        with self.db.transaction() as conn:
            plan_blob_path, _plan_blob_sha = self.store.put_text(json.dumps({"utterances": casting_snapshot["utterances"]}, ensure_ascii=False))
            self.casting_plan_id = int(conn.execute(
                """
                INSERT INTO casting_plans(
                    chapter_id,text_revision_id,plan_revision,status,content_path,plan_sha256,
                    narrator_voice_id,created_at,approved_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    self.chapter_id,
                    self.text_revision_id,
                    3,
                    "approved",
                    plan_blob_path,
                    "plan-sha-55",
                    "ngoc_lan",
                    "2026-07-05T00:00:00Z",
                    "2026-07-05T00:00:00Z",
                ),
            ).lastrowid)
            persisted_snapshot = dict(casting_snapshot)
            persisted_snapshot["casting_plan_id"] = self.casting_plan_id
            voice_snapshot = json.dumps(persisted_snapshot, ensure_ascii=False, sort_keys=True)
            self.job_id = int(conn.execute(
                """
                INSERT INTO jobs(
                    book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                    settings_json,skip_completed,total_chapters,scheduled_at,created_at,updated_at,
                    casting_plan_id,casting_snapshot_json,started_at,finished_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    self.book_id,
                    "completed",
                    629,
                    629,
                    "ngoc_lan",
                    "off",
                    "m4a",
                    json.dumps({"engine_version": "vieneu:v3turbo"}, ensure_ascii=False),
                    0,
                    1,
                    "2026-07-05T00:00:00Z",
                    "2026-07-05T00:00:00Z",
                    "2026-07-05T00:01:00Z",
                    self.casting_plan_id,
                    voice_snapshot,
                    "2026-07-05T00:00:01Z",
                    "2026-07-05T00:01:00Z",
                ),
            ).lastrowid)
            self.job_chapter_id = int(conn.execute(
                """
                INSERT INTO job_chapters(
                    job_id,chapter_id,sequence,status,text_revision_id,casting_plan_id,
                    casting_plan_sha256,voice_snapshot_json,started_at,finished_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    self.job_id,
                    self.chapter_id,
                    1,
                    "completed",
                    self.text_revision_id,
                    self.casting_plan_id,
                    "plan-sha-55",
                    voice_snapshot,
                    "2026-07-05T00:00:01Z",
                    "2026-07-05T00:01:00Z",
                ),
            ).lastrowid)
            for index, path in enumerate(self.segment_paths, start=1):
                conn.execute(
                    """
                    INSERT INTO segments(
                        job_chapter_id,segment_index,text_path,text_sha256,status,attempt_count,created_at,
                        utterance_sequence,speaker_role,character_id,resolved_voice_id,synthesis_hash,
                        wav_path,audio_sha256,duration_ms,verified_at,casting_plan_id
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        self.job_chapter_id,
                        index,
                        self.segment_text_paths[index - 1],
                        self.segment_text_sha[index - 1],
                        "verified",
                        1,
                        "2026-07-05T00:00:01Z",
                        index,
                        "character" if index == 1 else "narrator",
                        self.character_id if index == 1 else None,
                        "duc_tri" if index == 1 else "ngoc_lan",
                        f"synth-{index}",
                        str(path),
                        self.segment_audio_sha[index - 1],
                        1000,
                        "2026-07-05T00:00:10Z",
                        self.casting_plan_id,
                    ),
                )
            self.master_artifact_id = int(conn.execute(
                """
                INSERT INTO artifacts(
                    chapter_id,job_chapter_id,text_revision_id,artifact_type,synthesis_hash,export_hash,
                    path,sha256,size_bytes,duration_ms,status,created_at,verified_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    self.chapter_id,
                    self.job_chapter_id,
                    self.text_revision_id,
                    "chapter_master_wav",
                    "job-synth",
                    None,
                    str(self.master_path),
                    sha256_file(self.master_path),
                    self.master_path.stat().st_size,
                    2000,
                    "verified",
                    "2026-07-05T00:01:00Z",
                    "2026-07-05T00:01:00Z",
                ),
            ).lastrowid)
            self.timeline_artifact_id = int(conn.execute(
                """
                INSERT INTO artifacts(
                    chapter_id,job_chapter_id,text_revision_id,artifact_type,synthesis_hash,export_hash,
                    path,sha256,size_bytes,duration_ms,status,created_at,verified_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    self.chapter_id,
                    self.job_chapter_id,
                    self.text_revision_id,
                    "segment_timeline_json",
                    "job-synth",
                    None,
                    str(self.timeline_path),
                    sha256_file(self.timeline_path),
                    self.timeline_path.stat().st_size,
                    2000,
                    "verified",
                    "2026-07-05T00:01:00Z",
                    "2026-07-05T00:01:00Z",
                ),
            ).lastrowid)
            self.final_artifact_id = int(conn.execute(
                """
                INSERT INTO artifacts(
                    chapter_id,job_chapter_id,text_revision_id,artifact_type,synthesis_hash,export_hash,
                    path,sha256,size_bytes,duration_ms,status,created_at,verified_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    self.chapter_id,
                    self.job_chapter_id,
                    self.text_revision_id,
                    "chapter_m4a",
                    "job-synth",
                    "job-export",
                    str(self.final_path),
                    sha256_file(self.final_path),
                    self.final_path.stat().st_size,
                    2000,
                    "active",
                    "2026-07-05T00:01:00Z",
                    "2026-07-05T00:01:00Z",
                ),
            ).lastrowid)
            conn.execute(
                "UPDATE chapters SET active_audio_artifact_id=?,updated_at=datetime('now') WHERE id=?",
                (self.final_artifact_id, self.chapter_id),
            )

        self.preflight = {
            "runtime_identity": {
                "data_root": str(self.config.data_dir.resolve()),
                "db_path": str(self.config.db_path.resolve()),
                "schema_version": self.db.schema_version(),
            },
            "book": {"id": self.book_id},
            "chapter": {"id": self.chapter_id, "number": 629, "title": "Chapter 629"},
            "text_revision": {"id": self.text_revision_id, "content_sha256": revision_sha},
            "casting_plan": {"id": self.casting_plan_id, "revision": 3, "sha256": "plan-sha-55", "character_bible_fingerprint": None},
            "book_voice_profile": {"id": 9, "config_version": 4},
            "derived_default_voice": {"voice_id": "ngoc_lan"},
            "request_preview": {"payload": {"output_format": "m4a", "repair_mode": "off"}},
        }

    def test_valid_completed_job_creates_manifest_payload(self):
        manifest = build_completed_manifest(
            data_root=self.config.data_dir.resolve(),
            db_path=self.config.db_path.resolve(),
            preflight=self.preflight,
            job_id=self.job_id,
        )
        self.assertEqual(manifest["schema"], "story-audio-production-manifest/v1")
        self.assertEqual(manifest["identity"]["job_id"], self.job_id)
        self.assertEqual(manifest["identity"]["render_generation"], "render_0001")
        self.assertEqual(manifest["terminal_state"]["verified_segments"], 2)
        self.assertEqual(manifest["segment_integrity_summary"]["timeline_entry_count"], 2)

    def test_null_segment_casting_plan_ids_reuse_job_chapter_binding(self):
        with self.db.transaction() as conn:
            conn.execute("UPDATE segments SET casting_plan_id=NULL WHERE job_chapter_id=?", (self.job_chapter_id,))
        manifest = build_completed_manifest(
            data_root=self.config.data_dir.resolve(),
            db_path=self.config.db_path.resolve(),
            preflight=self.preflight,
            job_id=self.job_id,
        )
        self.assertEqual(manifest["identity"]["job_id"], self.job_id)
        self.assertEqual(manifest["immutable_bindings"]["casting_plan_id"], self.casting_plan_id)

    def test_missing_segment_sequence_fails_validation(self):
        with self.db.transaction() as conn:
            conn.execute("UPDATE segments SET segment_index=3 WHERE job_chapter_id=? AND segment_index=2", (self.job_chapter_id,))
        with self.assertRaisesRegex(TerminalValidationError, "Segment sequence continuity failed"):
            build_completed_manifest(
                data_root=self.config.data_dir.resolve(),
                db_path=self.config.db_path.resolve(),
                preflight=self.preflight,
                job_id=self.job_id,
            )

    def test_missing_artifact_file_fails_validation(self):
        self.final_path.unlink()
        with self.assertRaisesRegex(TerminalValidationError, "Artifact file is missing"):
            build_completed_manifest(
                data_root=self.config.data_dir.resolve(),
                db_path=self.config.db_path.resolve(),
                preflight=self.preflight,
                job_id=self.job_id,
            )

    def test_timeline_count_mismatch_fails_validation(self):
        payload = json.loads(self.timeline_path.read_text(encoding="utf-8"))
        payload["items"] = payload["items"][:-1]
        self.timeline_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE artifacts SET sha256=?,size_bytes=? WHERE id=?",
                (sha256_file(self.timeline_path), self.timeline_path.stat().st_size, self.timeline_artifact_id),
            )
        with self.assertRaisesRegex(TerminalValidationError, "Timeline entry count does not match segment count"):
            build_completed_manifest(
                data_root=self.config.data_dir.resolve(),
                db_path=self.config.db_path.resolve(),
                preflight=self.preflight,
                job_id=self.job_id,
            )

    def test_manifest_write_reuses_identical_existing_file(self):
        manifest = build_completed_manifest(
            data_root=self.config.data_dir.resolve(),
            db_path=self.config.db_path.resolve(),
            preflight=self.preflight,
            job_id=self.job_id,
        )
        first = write_manifest(manifest, data_root=self.config.data_dir.resolve(), manifest_out=None)
        second = write_manifest(manifest, data_root=self.config.data_dir.resolve(), manifest_out=None)
        self.assertFalse(first["reused_existing"])
        self.assertTrue(second["reused_existing"])
        self.assertEqual(first["sha256"], second["sha256"])

    def test_manifest_write_conflict_does_not_overwrite(self):
        manifest = build_completed_manifest(
            data_root=self.config.data_dir.resolve(),
            db_path=self.config.db_path.resolve(),
            preflight=self.preflight,
            job_id=self.job_id,
        )
        target = self.config.data_dir / "manifests" / f"job_{self.job_id}_chapter_629.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"different":true}\n', encoding="utf-8")
        with self.assertRaisesRegex(TerminalValidationError, "Manifest already exists with different content"):
            write_manifest(manifest, data_root=self.config.data_dir.resolve(), manifest_out=None)


if __name__ == "__main__":
    unittest.main()
