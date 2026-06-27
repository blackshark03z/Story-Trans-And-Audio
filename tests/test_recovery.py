from __future__ import annotations

import json
import tempfile
import os
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from story_audio.config import settings
from story_audio.db import Database, utcnow
from story_audio.files import sha256_file
from story_audio.integrity import check_data_integrity
from story_audio.pipeline import JobCancelled, PipelineWorker
from story_audio.storage import ContentStore


class FakeTts:
    def __init__(self):
        self.calls: list[str] = []

    def synthesize(self, *, synth_input=None, text: str = None, output_path: Path, **_kwargs):
        # Support both snapshot-based and legacy API
        if synth_input is not None:
            actual_text = synth_input.text
        else:
            actual_text = text

        self.calls.append(actual_text)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(f"audio:{actual_text}".encode("utf-8"))
        return 1000, 48_000


def make_config(root: Path):
    return replace(
        settings,
        root=root,
        data_dir=root / "data",
        db_path=root / "data" / "app.db",
        blobs_dir=root / "data" / "blobs",
        output_dir=root / "data" / "output",
        work_dir=root / "data" / "work",
        log_dir=root / "logs",
        minimum_free_gb=0,
    )


def seed_recovery(config):
    config.ensure_dirs()
    database = Database(config.db_path)
    database.initialize()
    store = ContentStore(config)
    full_path, full_sha = store.put_text("Đoạn thứ nhất. Đoạn thứ hai.")
    first_path, first_sha = store.put_text("Đoạn thứ nhất.")
    second_path, second_sha = store.put_text("Đoạn thứ hai.")
    now = utcnow()
    verified_wav = config.work_dir / "job_1" / "chapter_0001" / "segments" / "000001.wav"
    verified_wav.parent.mkdir(parents=True, exist_ok=True)
    verified_wav.write_bytes(b"already-verified")
    with database.transaction() as connection:
        book_id = int(
            connection.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                ("Book", "book.epub", "sha", 1, now, now),
            ).lastrowid
        )
        chapter_id = int(
            connection.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (book_id, 1, "Chương 1", 30, now, now),
            ).lastrowid
        )
        revision_id = int(
            connection.execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                    processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (chapter_id, "reflowed", full_path, full_sha, "lexical", 30, "test", "approved", now),
            ).lastrowid
        )
        settings_json = json.dumps(
            {
                "temperature": 0.8,
                "top_k": 25,
                "max_chars": 256,
                "target_chars": 230,
                "silence_seconds": 0.15,
                "engine_version": "vieneu:v3turbo"
            }
        )
        job_id = int(
            connection.execute(
                """INSERT INTO jobs(
                    book_id,status,from_chapter,to_chapter,voice_name,repair_mode,
                    output_format,settings_json,total_chapters,scheduled_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (book_id, "running", 1, 1, "Voice", "off", "m4a", settings_json, 1, now, now, now),
            ).lastrowid
        )
        job_chapter_id = int(
            connection.execute(
                "INSERT INTO job_chapters(job_id,chapter_id,sequence,status,text_revision_id) VALUES(?,?,?,?,?)",
                (job_id, chapter_id, 1, "running", revision_id),
            ).lastrowid
        )
        connection.execute(
            """INSERT INTO segments(
                job_chapter_id,segment_index,text_path,text_sha256,status,attempt_count,
                wav_path,audio_sha256,duration_ms,created_at,verified_at,
                voice_snapshot_version,voice_source_type,voice_provider,voice_model,
                logical_voice_ref,effective_voice_ref,synthesis_settings_json,
                voice_resolution_reason,synthesis_hash
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job_chapter_id,
                1,
                first_path,
                first_sha,
                "verified",
                1,
                str(verified_wav),
                sha256_file(verified_wav),
                1000,
                now,
                now,
                1,
                "preset",
                "vieneu",
                "v3turbo",
                "narrator",
                "Voice",
                settings_json,
                "direct",
                "hash1",
            ),
        )
        connection.execute(
            """INSERT INTO segments(
                job_chapter_id,segment_index,text_path,text_sha256,status,created_at,
                voice_snapshot_version,voice_source_type,voice_provider,voice_model,
                logical_voice_ref,effective_voice_ref,synthesis_settings_json,
                voice_resolution_reason,synthesis_hash
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (job_chapter_id, 2, second_path, second_sha, "pending", now,
             1, "preset", "vieneu", "v3turbo", "narrator", "Voice", settings_json, "direct", "hash2"),
        )
    job = dict(database.fetch_one("SELECT * FROM jobs WHERE id=?", (job_id,)))
    chapter = {
        "id": job_chapter_id,
        "job_id": job_id,
        "chapter_id": chapter_id,
        "chapter_number": 1,
        "title": "Chương 1",
        "book_id": book_id,
        "book_title": "Book",
        "text_revision_id": revision_id,
    }
    return database, store, job, chapter, verified_wav


class RecoveryTests(unittest.TestCase):

    def setUp(self) -> None:
        super().setUp()
        self._original_testing = os.environ.get("STORY_AUDIO_TESTING")
        os.environ["STORY_AUDIO_TESTING"] = "1"

    def tearDown(self) -> None:
        if self._original_testing is None:
            os.environ.pop("STORY_AUDIO_TESTING", None)
        else:
            os.environ["STORY_AUDIO_TESTING"] = self._original_testing
        super().tearDown()

    def test_retry_reuses_verified_segment_and_renders_only_pending(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory))
            database, store, job, chapter, verified_wav = seed_recovery(config)
            original_hash = sha256_file(verified_wav)
            fake_tts = FakeTts()
            worker = PipelineWorker(database, store, fake_tts, config)
            with patch.object(worker, "_assemble", return_value=999):
                worker._process_chapter(job, chapter)
            self.assertEqual(fake_tts.calls, ["Đoạn thứ hai."])
            self.assertEqual(sha256_file(verified_wav), original_hash)
            rows = database.fetch_all("SELECT status FROM segments ORDER BY segment_index")
            self.assertEqual([row["status"] for row in rows], ["verified", "verified"])

    def test_cancel_is_observed_before_tts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory))
            database, store, job, _chapter, _verified_wav = seed_recovery(config)
            with database.connect() as connection:
                connection.execute(
                    "UPDATE jobs SET cancel_requested=1 WHERE id=?", (job["id"],)
                )
            fake_tts = FakeTts()
            worker = PipelineWorker(database, store, fake_tts, config)
            with self.assertRaises(JobCancelled):
                worker._control(job["id"])
            self.assertEqual(fake_tts.calls, [])

    def test_integrity_detects_corrupted_active_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory))
            database, _store, _job, chapter, _verified_wav = seed_recovery(config)
            artifact = config.output_dir / "chapter.m4a"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(b"good")
            now = utcnow()
            with database.connect() as connection:
                connection.execute(
                    """INSERT INTO artifacts(
                        chapter_id,artifact_type,path,sha256,size_bytes,status,created_at,verified_at
                    ) VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        chapter["chapter_id"],
                        "chapter_m4a",
                        str(artifact),
                        sha256_file(artifact),
                        artifact.stat().st_size,
                        "active",
                        now,
                        now,
                    ),
                )
            artifact.write_bytes(b"corrupted")
            findings = check_data_integrity(config, deep=True)
            self.assertTrue(
                any(finding.level == "ERROR" and finding.name == "artifact_hash" for finding in findings)
            )


if __name__ == "__main__":
    unittest.main()
