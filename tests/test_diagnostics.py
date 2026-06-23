from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from story_audio.db import utcnow
from story_audio.diagnostics import (
    RetryConflict,
    get_job_chapter_diagnostics,
    get_job_diagnostics,
    get_segment_diagnostics,
    retry_job_chapter,
    retry_segment,
)
from story_audio.files import sha256_file

from tests.test_recovery import make_config, seed_recovery


def seed_diagnostics(root: Path):
    config = make_config(root)
    database, store, job, chapter, verified_wav = seed_recovery(config)
    failed_segment = database.fetch_one(
        "SELECT id FROM segments WHERE job_chapter_id=? AND segment_index=2",
        (chapter["id"],),
    )
    source_path, source_sha = store.put_text("Câu cần sửa dấu.")
    artifact = config.output_dir / "chapter_0001.m4a"
    artifact.write_bytes(b"assembled-audio")
    now = utcnow()
    with database.connect() as connection:
        connection.execute(
            "UPDATE jobs SET status='completed_with_errors' WHERE id=?", (job["id"],)
        )
        connection.execute(
            "UPDATE job_chapters SET status='failed',error_message='chapter failed' WHERE id=?",
            (chapter["id"],),
        )
        connection.execute(
            "UPDATE segments SET status='failed',attempt_count=3,error_message='tts failed' WHERE id=?",
            (failed_segment["id"],),
        )
        connection.execute(
            """INSERT INTO repair_blocks(
                job_chapter_id,block_index,source_path,source_sha256,lexical_sha256,
                model_id,prompt_version,status,attempt_count,error_message
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                chapter["id"], 1, source_path, source_sha, "lexical", "fake-gemini",
                "test-v1", "failed", 2, "repair failed",
            ),
        )
        connection.execute(
            """INSERT INTO artifacts(
                chapter_id,job_chapter_id,text_revision_id,artifact_type,path,sha256,
                size_bytes,status,created_at,verified_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                chapter["chapter_id"], chapter["id"], chapter["text_revision_id"],
                "chapter_m4a", str(artifact), sha256_file(artifact), artifact.stat().st_size,
                "active", now, now,
            ),
        )
    return config, database, store, job, chapter, verified_wav, int(failed_segment["id"]), artifact


class DiagnosticTests(unittest.TestCase):
    def test_job_diagnostics_aggregates_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, database, _store, job, _chapter, *_rest = seed_diagnostics(Path(directory))
            result = get_job_diagnostics(database, job["id"])
            self.assertEqual(result["summary"]["chapter_total"], 1)
            self.assertEqual(result["summary"]["segment_verified"], 1)
            self.assertEqual(result["summary"]["segment_failed"], 1)
            self.assertEqual(result["summary"]["repair_failed"], 1)
            self.assertEqual(result["job"]["settings"]["max_chars"], 256)

    def test_chapter_diagnostics_reports_files_without_full_chapter_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, database, store, _job, chapter, *_rest = seed_diagnostics(Path(directory))
            result = get_job_chapter_diagnostics(database, store, chapter["id"])
            self.assertNotIn("content_path", result["text_revision"])
            self.assertEqual([item["status"] for item in result["segments"]], ["verified", "failed"])
            self.assertTrue(result["segments"][0]["file_exists"])
            self.assertTrue(result["repair_blocks"][0]["source_file_exists"])
            self.assertTrue(result["artifacts"][0]["hash_matches"])

    def test_segment_diagnostics_detects_audio_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, database, store, _job, chapter, verified_wav, *_rest = seed_diagnostics(Path(directory))
            segment_id = database.fetch_one(
                "SELECT id FROM segments WHERE job_chapter_id=? AND status='verified'", (chapter["id"],)
            )["id"]
            self.assertTrue(get_segment_diagnostics(database, store, segment_id)["audio_file"]["hash_matches"])
            verified_wav.write_bytes(b"corrupted")
            self.assertFalse(get_segment_diagnostics(database, store, segment_id)["audio_file"]["hash_matches"])

    def test_chapter_retry_reuses_verified_and_resets_only_failed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, database, _store, job, chapter, _wav, failed_id, _artifact = seed_diagnostics(Path(directory))
            result = retry_job_chapter(database, chapter["id"])
            self.assertEqual(result, {"verified_segments_reused": 1, "segments_reset": 1})
            statuses = database.fetch_all("SELECT id,status,attempt_count FROM segments ORDER BY segment_index")
            self.assertEqual(statuses[0]["status"], "verified")
            self.assertEqual(statuses[1]["id"], failed_id)
            self.assertEqual((statuses[1]["status"], statuses[1]["attempt_count"]), ("pending", 0))
            self.assertEqual(database.fetch_one("SELECT status FROM jobs WHERE id=?", (job["id"],))["status"], "queued")

    def test_segment_retry_rejects_verified_and_requeues_failed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, database, _store, job, chapter, _wav, failed_id, _artifact = seed_diagnostics(Path(directory))
            verified_id = database.fetch_one(
                "SELECT id FROM segments WHERE job_chapter_id=? AND status='verified'", (chapter["id"],)
            )["id"]
            with self.assertRaises(RetryConflict):
                retry_segment(database, verified_id)
            result = retry_segment(database, failed_id)
            self.assertEqual(result["segment_id"], failed_id)
            self.assertEqual(database.fetch_one("SELECT status FROM segments WHERE id=?", (failed_id,))["status"], "pending")
            self.assertEqual(database.fetch_one("SELECT status FROM jobs WHERE id=?", (job["id"],))["status"], "queued")


if __name__ == "__main__":
    unittest.main()
