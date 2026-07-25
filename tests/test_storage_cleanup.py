from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from story_audio.storage_cleanup import (
    CONFIRMATION,
    StorageCleanupError,
    build_report,
    execute_cleanup,
)


class StorageCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "data" / "output").mkdir(parents=True)
        (self.root / "data" / "work").mkdir(parents=True)
        (self.root / "data" / "exports" / "youtube_auto").mkdir(parents=True)
        (self.root / "backups").mkdir()
        (self.root / "runs").mkdir()
        (self.root / "experiment_b_transcript").mkdir()
        (self.root / "secrets").mkdir()
        self.db_path = self.root / "data" / "app.db"
        self._create_database()
        self.artifact = self.root / "data" / "output" / "book" / "chapter.m4a"
        self.artifact.parent.mkdir(parents=True)
        self.artifact.write_bytes(b"canonical-audio")
        digest = hashlib.sha256(self.artifact.read_bytes()).hexdigest()
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "INSERT INTO artifacts(id,chapter_id,path,sha256,status) "
                "VALUES(87,1,?,?,?)",
                (str(self.artifact), digest, "stale"),
            )
            connection.execute(
                "INSERT INTO chapters(id,active_audio_artifact_id) VALUES(1,87)"
            )
            connection.execute(
                "INSERT INTO jobs(id,status) VALUES(1,'completed')"
            )
            connection.execute(
                "INSERT INTO jobs(id,status) VALUES(24,'completed')"
            )
            connection.commit()
        self._create_backup("pre", 14)
        self._create_backup("current", 15)
        tracked = self.root / "tracked.txt"
        tracked.write_text("keep", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "tracked.txt"], check=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create_database(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.executescript(
                """
                CREATE TABLE schema_migrations(version INTEGER);
                INSERT INTO schema_migrations(version) VALUES(15);
                CREATE TABLE jobs(id INTEGER PRIMARY KEY,status TEXT);
                CREATE TABLE chapters(
                    id INTEGER PRIMARY KEY,
                    active_audio_artifact_id INTEGER
                );
                CREATE TABLE artifacts(
                    id INTEGER PRIMARY KEY,
                    chapter_id INTEGER,
                    path TEXT,
                    sha256 TEXT,
                    status TEXT
                );
                CREATE TABLE segments(wav_path TEXT);
                CREATE TABLE segment_attempts(wav_path TEXT);
                CREATE TABLE audio_repair_blocks(candidate_wav_path TEXT);
                """
            )
            connection.commit()

    def _create_backup(self, name: str, schema: int) -> None:
        destination = self.root / "backups" / name
        files = destination / "files"
        files.mkdir(parents=True)
        backup_db = files / "app.db"
        with closing(sqlite3.connect(backup_db)) as connection:
            connection.execute("CREATE TABLE schema_migrations(version INTEGER)")
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES(?)", (schema,)
            )
            connection.commit()
        entry = {
            "path": "files/app.db",
            "size": backup_db.stat().st_size,
            "sha256": hashlib.sha256(backup_db.read_bytes()).hexdigest(),
        }
        manifest = {
            "manifest_schema_version": 1,
            "created_at": f"2026-01-{schema:02d}T00:00:00+00:00",
            "app_version": "test",
            "schema_version": schema,
            "source_data_dir": str(self.root / "data"),
            "includes": {
                "database": True,
                "blobs": False,
                "output": False,
                "youtube_exports": False,
                "work": False,
            },
            "file_count": 1,
            "total_size": entry["size"],
            "files": [entry],
        }
        (destination / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    def test_report_preserves_canonical_and_finds_proven_orphans(self) -> None:
        orphan = self.root / "data" / "work" / "job_1"
        orphan.mkdir()
        (orphan / "concat.txt").write_text("temporary", encoding="utf-8")
        protected = self.root / "data" / "work" / "job_24"
        protected.mkdir()
        (protected / "concat.txt").write_text("keep", encoding="utf-8")
        (self.root / "runs" / "__pycache__").mkdir()
        (self.root / "runs" / "__pycache__" / "x.pyc").write_bytes(b"x")

        report = build_report(self.root, include_largest=False)

        paths = {item["path"] for item in report["candidates"]}
        self.assertIn("data/work/job_1", paths)
        self.assertNotIn("data/work/job_24", paths)
        self.assertFalse(any(path.startswith("runs/") for path in paths))
        self.assertTrue(self.artifact.exists())
        self.assertEqual([], report["blockers"])

    def test_duplicate_export_requires_canonical_audio_hash(self) -> None:
        package = (
            self.root
            / "data"
            / "exports"
            / "youtube_auto"
            / "duplicate-package"
        )
        (package / "audio").mkdir(parents=True)
        (package / "audio" / "narration.m4a").write_bytes(self.artifact.read_bytes())
        (package / "handoff.json").write_text("{}", encoding="utf-8")

        report = build_report(self.root, include_largest=False)

        item = next(
            entry
            for entry in report["candidates"]
            if entry["path"].endswith("duplicate-package")
        )
        self.assertEqual("DUPLICATE_EXPORT", item["category"])

    def test_execute_requires_confirmation_and_inactive_runtime(self) -> None:
        with self.assertRaises(StorageCleanupError):
            execute_cleanup(self.root, confirmation="wrong")
        with mock.patch(
            "story_audio.storage_cleanup._runtime_listening", return_value=True
        ):
            with self.assertRaises(StorageCleanupError):
                execute_cleanup(self.root, confirmation=CONFIRMATION)

    def test_execute_rechecks_runtime_immediately_before_deletion(self) -> None:
        orphan = self.root / "data" / "work" / "job_1"
        orphan.mkdir()
        (orphan / "concat.txt").write_text("temporary", encoding="utf-8")

        with mock.patch(
            "story_audio.storage_cleanup._runtime_listening",
            side_effect=[False, True],
        ):
            with self.assertRaisesRegex(
                StorageCleanupError, "runtime started during verification"
            ):
                execute_cleanup(self.root, confirmation=CONFIRMATION)

        self.assertTrue(orphan.exists())
        self.assertTrue(self.artifact.exists())

    def test_in_process_mode_allows_owned_runtime_but_keeps_safety_checks(self) -> None:
        orphan = self.root / "data" / "work" / "job_1"
        orphan.mkdir()
        (orphan / "concat.txt").write_text("temporary", encoding="utf-8")

        with mock.patch(
            "story_audio.storage_cleanup._runtime_listening",
            return_value=True,
        ):
            result = execute_cleanup(
                self.root,
                confirmation=CONFIRMATION,
                allow_running_runtime=True,
            )

        self.assertFalse(orphan.exists())
        self.assertTrue(self.artifact.exists())
        self.assertGreater(result["reclaimed_bytes"], 0)

    def test_nonempty_wal_blocks_but_zero_byte_sidecars_are_reclaimable(self) -> None:
        wal = Path(str(self.db_path) + "-wal")
        shm = Path(str(self.db_path) + "-shm")
        wal.write_bytes(b"not-empty")
        shm.write_bytes(b"sidecar")

        blocked = build_report(self.root, include_largest=False)
        self.assertTrue(
            any("non-empty SQLite WAL" in item for item in blocked["blockers"])
        )

        wal.write_bytes(b"")
        report = build_report(self.root, include_largest=False)
        paths = {item["path"] for item in report["candidates"]}
        self.assertIn("data/app.db-wal", paths)
        self.assertIn("data/app.db-shm", paths)
        self.assertEqual([], report["blockers"])

    def test_readonly_inventory_does_not_create_sqlite_sidecars(self) -> None:
        build_report(self.root, include_largest=False)

        self.assertFalse(Path(str(self.db_path) + "-wal").exists())
        self.assertFalse(Path(str(self.db_path) + "-shm").exists())

    def test_git_tracked_generated_cache_is_not_a_candidate(self) -> None:
        cache = self.root / "scripts" / "__pycache__"
        cache.mkdir(parents=True)
        tracked_cache = cache / "tracked.pyc"
        tracked_cache.write_bytes(b"tracked")
        subprocess.run(
            ["git", "-C", str(self.root), "add", "scripts/__pycache__/tracked.pyc"],
            check=True,
        )

        report = build_report(self.root, include_largest=False)

        self.assertFalse(
            any(item["path"] == "scripts/__pycache__" for item in report["candidates"])
        )

    def test_backup_with_unmanifested_extra_file_is_retained_unknown(self) -> None:
        (self.root / "backups" / "pre" / "unexpected.bin").write_bytes(b"unknown")

        report = build_report(self.root, include_largest=False)

        retained = {
            item["path"]: item["category"] for item in report["retained"]
        }
        self.assertEqual("UNKNOWN_KEEP", retained["backups/pre"])

    def test_unrecognized_data_clone_is_retained_unknown(self) -> None:
        unknown = self.root / "data" / "app-owner.db"
        with closing(sqlite3.connect(unknown)) as connection:
            connection.execute("CREATE TABLE schema_migrations(version INTEGER)")
            connection.execute("INSERT INTO schema_migrations(version) VALUES(15)")
            connection.commit()

        report = build_report(self.root, include_largest=False)

        self.assertFalse(
            any(item["path"] == "data/app-owner.db" for item in report["candidates"])
        )
        retained = {
            item["path"]: item["category"] for item in report["retained"]
        }
        self.assertEqual("UNKNOWN_KEEP", retained["data/app-owner.db"])

    def test_execute_deletes_only_reported_candidate_and_writes_manifest(self) -> None:
        orphan = self.root / "data" / "work" / "job_1"
        orphan.mkdir()
        (orphan / "concat.txt").write_text("temporary", encoding="utf-8")
        manifest = self.root / "data" / "cleanup_reports" / "result.json"

        with mock.patch(
            "story_audio.storage_cleanup._runtime_listening", return_value=False
        ):
            result = execute_cleanup(
                self.root,
                confirmation=CONFIRMATION,
                json_report=manifest,
            )

        self.assertFalse(orphan.exists())
        self.assertTrue(self.artifact.exists())
        self.assertTrue((self.root / "runs").exists())
        self.assertTrue((self.root / "experiment_b_transcript").exists())
        self.assertTrue(manifest.is_file())
        self.assertGreater(result["reclaimed_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
