from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from story_audio.config import canonical_production_db_path
from story_audio.db import Database, utcnow
from story_audio.migrations import LATEST_SCHEMA_VERSION, MIGRATIONS, Migration, MigrationRunner, SchemaMigrationError


DORMANT_MIGRATION_PATH = Path("story_audio/migrations/dormant/0013_batch_prepare_requests.sql")


def load_schema_13_migration(sql: str | None = None) -> Migration:
    migration_sql = sql if sql is not None else DORMANT_MIGRATION_PATH.read_text(encoding="utf-8")
    return Migration(
        version=13,
        name="batch_prepare_requests",
        path=DORMANT_MIGRATION_PATH,
        checksum=hashlib.sha256(migration_sql.encode("utf-8")).hexdigest(),
        sql=migration_sql,
    )


def schema_13_runner(sql: str | None = None) -> MigrationRunner:
    return MigrationRunner([*MIGRATIONS, load_schema_13_migration(sql)])


class BatchPrepareMigrationTests(unittest.TestCase):
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

    def _assert_not_canonical(self, path: Path) -> None:
        self.assertNotEqual(path.resolve(), canonical_production_db_path().resolve())

    def test_dormant_migration_is_not_auto_discovered_by_default(self) -> None:
        self.assertEqual(LATEST_SCHEMA_VERSION, 12)
        self.assertEqual(MIGRATIONS[-1].version, 12)
        self.assertFalse(Path("story_audio/migrations/0013_batch_prepare_requests.sql").exists())

    def test_temporary_schema_12_database_upgrades_to_schema_13_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schema13.db"
            self._assert_not_canonical(path)
            database = Database(path)
            self.assertEqual(database.initialize(), 12)
            database_13 = Database(path, migration_runner=schema_13_runner())
            self.assertEqual(database_13.initialize(), 13)
            self.assertEqual(database_13.schema_version(), 13)
            table = database_13.fetch_one(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='batch_prepare_requests'"
            )
            self.assertIsNotNone(table)

    def test_legacy_rows_survive_explicit_schema_13_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.db"
            self._assert_not_canonical(path)
            database = Database(path)
            database.initialize()
            now = utcnow()
            with database.transaction() as connection:
                book_id = connection.execute(
                    "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    ("Legacy", "legacy.epub", "1" * 64, 1, now, now),
                ).lastrowid
                chapter_id = connection.execute(
                    "INSERT INTO chapters(book_id,chapter_number,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (book_id, 1, "One", now, now),
                ).lastrowid
                job_id = connection.execute(
                    """INSERT INTO jobs(
                        book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                        settings_json,total_chapters,scheduled_at,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (book_id, "prepared", 1, 1, "voice", "off", "m4a", "{}", 1, now, now, now),
                ).lastrowid
                connection.execute(
                    "INSERT INTO job_chapters(job_id,chapter_id,sequence,status) VALUES(?,?,?,?)",
                    (job_id, chapter_id, 1, "pending"),
                )
            before = {
                table: database.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]
                for table in ["books", "chapters", "jobs", "job_chapters", "segments", "artifacts"]
            }
            database_13 = Database(path, migration_runner=schema_13_runner())
            database_13.initialize()
            after = {
                table: database_13.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]
                for table in ["books", "chapters", "jobs", "job_chapters", "segments", "artifacts"]
            }
            self.assertEqual(before, after)
            self.assertEqual(after["jobs"], 1)
            self.assertEqual(after["job_chapters"], 1)

    def test_required_columns_constraints_and_indexes_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shape.db"
            self._assert_not_canonical(path)
            database = Database(path, migration_runner=schema_13_runner())
            database.initialize()
            columns = {row["name"]: row for row in database.fetch_all("PRAGMA table_info(batch_prepare_requests)")}
            for column in [
                "id",
                "client_request_id",
                "request_identity",
                "book_id",
                "from_chapter",
                "to_chapter",
                "target_phase",
                "plan_fingerprint",
                "state",
                "job_id",
                "result_schema_version",
                "result_payload_json",
                "error_code",
                "error_message",
                "attempt_count",
                "applying_started_at",
                "completed_at",
                "created_at",
                "updated_at",
            ]:
                self.assertIn(column, columns)
            indexes = {row["name"] for row in database.fetch_all(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='batch_prepare_requests'"
            )}
            self.assertTrue(
                {
                    "idx_batch_prepare_requests_client",
                    "idx_batch_prepare_requests_identity",
                    "idx_batch_prepare_requests_state_updated",
                    "idx_batch_prepare_requests_stale_applying",
                    "idx_batch_prepare_requests_job",
                    "idx_batch_prepare_requests_scope",
                }.issubset(indexes)
            )
            sql = database.fetch_one(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='batch_prepare_requests'"
            )["sql"]
            self.assertIn("UNIQUE(client_request_id)", sql)
            self.assertIn("UNIQUE(request_identity)", sql)
            self.assertIn("target_phase IN ('PREPARE')", sql)
            self.assertIn("state IN ('PLANNED','APPLYING','APPLIED','REJECTED','FAILED')", sql)
            self.assertIn("from_chapter <= to_chapter", sql)
            self.assertIn("length(error_message) <= 1000", sql)

    def test_constraints_are_database_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "constraints.db"
            self._assert_not_canonical(path)
            database = Database(path, migration_runner=schema_13_runner())
            database.initialize()
            now = utcnow()
            with database.transaction() as connection:
                book_id = connection.execute(
                    "INSERT INTO books(title,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?)",
                    ("Book", "book.epub", "2" * 64, now, now),
                ).lastrowid
                base = (book_id, 1, 1, "PREPARE", "a" * 64, "PLANNED", now, now)
                connection.execute(
                    """INSERT INTO batch_prepare_requests(
                        client_request_id,request_identity,book_id,from_chapter,to_chapter,
                        target_phase,plan_fingerprint,state,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    ("request-1", "b" * 64, *base),
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """INSERT INTO batch_prepare_requests(
                            client_request_id,request_identity,book_id,from_chapter,to_chapter,
                            target_phase,plan_fingerprint,state,created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        ("request-1", "c" * 64, *base),
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """INSERT INTO batch_prepare_requests(
                            client_request_id,request_identity,book_id,from_chapter,to_chapter,
                            target_phase,plan_fingerprint,state,created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        ("request-2", "b" * 64, *base),
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """INSERT INTO batch_prepare_requests(
                            client_request_id,request_identity,book_id,from_chapter,to_chapter,
                            target_phase,plan_fingerprint,state,created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        ("request-3", "d" * 64, book_id, 2, 1, "PREPARE", "a" * 64, "PLANNED", now, now),
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """INSERT INTO batch_prepare_requests(
                            client_request_id,request_identity,book_id,from_chapter,to_chapter,
                            target_phase,plan_fingerprint,state,created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        ("request-4", "e" * 64, book_id, 1, 1, "START_RENDER", "a" * 64, "PLANNED", now, now),
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """INSERT INTO batch_prepare_requests(
                            client_request_id,request_identity,book_id,from_chapter,to_chapter,
                            target_phase,plan_fingerprint,state,created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        ("request-5", "f" * 64, book_id, 1, 1, "PREPARE", "a" * 64, "RUNNING", now, now),
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """INSERT INTO batch_prepare_requests(
                            client_request_id,request_identity,book_id,from_chapter,to_chapter,
                            target_phase,plan_fingerprint,state,error_message,created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            "request-6",
                            "9" * 64,
                            book_id,
                            1,
                            1,
                            "PREPARE",
                            "a" * 64,
                            "FAILED",
                            "x" * 1001,
                            now,
                            now,
                        ),
                    )

    def test_foreign_keys_follow_existing_conventions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fk.db"
            self._assert_not_canonical(path)
            database = Database(path, migration_runner=schema_13_runner())
            database.initialize()
            fks = [dict(row) for row in database.fetch_all("PRAGMA foreign_key_list(batch_prepare_requests)")]
            self.assertEqual({row["table"] for row in fks}, {"books", "jobs"})

    def test_explicit_migration_rolls_back_on_failure_without_false_schema_13(self) -> None:
        bad_sql = DORMANT_MIGRATION_PATH.read_text(encoding="utf-8") + "\nCREATE TABLE broken_table(\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rollback.db"
            self._assert_not_canonical(path)
            database = Database(path)
            database.initialize()
            broken = Database(path, migration_runner=schema_13_runner(bad_sql))
            with self.assertRaises(SchemaMigrationError):
                broken.initialize()
            connection = sqlite3.connect(path)
            try:
                applied = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
                table = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='batch_prepare_requests'"
                ).fetchone()
                self.assertEqual(applied, 12)
                self.assertIsNone(table)
            finally:
                connection.close()

    def test_reapplying_schema_13_is_idempotent_by_migration_framework(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reapply.db"
            self._assert_not_canonical(path)
            database = Database(path, migration_runner=schema_13_runner())
            self.assertEqual(database.initialize(), 13)
            self.assertEqual(database.initialize(), 13)
            self.assertEqual(
                database.fetch_one("SELECT COUNT(*) AS n FROM schema_migrations WHERE version=13")["n"],
                1,
            )


if __name__ == "__main__":
    unittest.main()
