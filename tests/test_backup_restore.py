from __future__ import annotations

import tempfile
import os
import unittest
from dataclasses import replace
from pathlib import Path

from story_audio.backup import (
    BackupError,
    BackupVerificationError,
    create_backup,
    restore_backup,
    verify_backup,
)
from story_audio.config import settings
from story_audio.db import Database, utcnow
from story_audio.files import sha256_file
from story_audio.migrations import LATEST_SCHEMA_VERSION
from story_audio.storage import ContentStore


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


def seed_data(config) -> tuple[Database, Path]:
    config.ensure_dirs()
    database = Database(config.db_path)
    database.initialize()
    store = ContentStore(config)
    content_path, content_sha = store.put_text("Nội dung chương được lưu ngoài SQLite.")
    now = utcnow()
    artifact_path = config.output_dir / "book" / "chapter_0001" / "chapter.m4a"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"fake-audio-for-backup")
    with database.transaction() as connection:
        book_id = int(
            connection.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?)",
                ("Book", "book.epub", "book-sha", 1, now, now),
            ).lastrowid
        )
        chapter_id = int(
            connection.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?)",
                (book_id, 1, "Chương 1", 40, now, now),
            ).lastrowid
        )
        revision_id = int(
            connection.execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                    processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    chapter_id,
                    "reflowed",
                    content_path,
                    content_sha,
                    "lexical",
                    40,
                    "test",
                    "approved",
                    now,
                ),
            ).lastrowid
        )
        artifact_id = int(
            connection.execute(
                """INSERT INTO artifacts(
                    chapter_id,text_revision_id,artifact_type,path,sha256,size_bytes,
                    duration_ms,status,created_at,verified_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    chapter_id,
                    revision_id,
                    "chapter_m4a",
                    str(artifact_path),
                    sha256_file(artifact_path),
                    artifact_path.stat().st_size,
                    1000,
                    "active",
                    now,
                    now,
                ),
            ).lastrowid
        )
        connection.execute(
            "UPDATE chapters SET active_text_revision_id=?,active_audio_artifact_id=?,audio_status='completed' WHERE id=?",
            (revision_id, artifact_id, chapter_id),
        )
    work_file = config.work_dir / "job_1" / "segments" / "000001.wav"
    work_file.parent.mkdir(parents=True, exist_ok=True)
    work_file.write_bytes(b"checkpoint-wave")
    return database, artifact_path


class BackupRestoreTests(unittest.TestCase):

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

    def test_backup_manifest_and_restore_to_new_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root / "source")
            seed_data(config)
            backup_dir = root / "backup"
            manifest = create_backup(config, backup_dir)
            self.assertEqual(manifest["schema_version"], LATEST_SCHEMA_VERSION)
            self.assertGreater(manifest["file_count"], 2)
            self.assertEqual(verify_backup(backup_dir)["total_size"], manifest["total_size"])

            restored_data = root / "restored" / "data"
            report = restore_backup(backup_dir, restored_data)
            self.assertGreaterEqual(report["rewritten_paths"], 1)
            restored_db = Database(restored_data / "app.db")
            self.assertEqual(restored_db.schema_version(), LATEST_SCHEMA_VERSION)
            revision = restored_db.fetch_one("SELECT content_path FROM text_revisions")
            self.assertTrue((restored_data / "blobs" / revision["content_path"]).exists())
            artifact = restored_db.fetch_one("SELECT path,sha256 FROM artifacts WHERE status='active'")
            restored_artifact = Path(artifact["path"])
            self.assertTrue(restored_artifact.is_relative_to(restored_data))
            self.assertTrue(restored_artifact.exists())
            self.assertEqual(sha256_file(restored_artifact), artifact["sha256"])
            with self.assertRaises(BackupError):
                restore_backup(backup_dir, restored_data)

    def test_verify_detects_corrupted_backup_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root / "source")
            seed_data(config)
            backup_dir = root / "backup"
            create_backup(config, backup_dir)
            artifact = next((backup_dir / "files" / "output").rglob("*.m4a"))
            artifact.write_bytes(b"corrupted")
            with self.assertRaises(BackupVerificationError):
                verify_backup(backup_dir)

    def test_backup_refuses_active_job_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root / "source")
            database, _ = seed_data(config)
            now = utcnow()
            book_id = database.fetch_one("SELECT id FROM books")["id"]
            with database.connect() as connection:
                connection.execute(
                    """INSERT INTO jobs(
                        book_id,status,from_chapter,to_chapter,voice_name,repair_mode,
                        output_format,settings_json,total_chapters,scheduled_at,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (book_id, "synthesizing", 1, 1, "Voice", "off", "m4a", "{}", 1, now, now, now),
                )
            with self.assertRaises(BackupError):
                create_backup(config, root / "backup")


if __name__ == "__main__":
    unittest.main()
