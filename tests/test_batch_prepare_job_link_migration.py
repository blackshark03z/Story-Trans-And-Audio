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
from tests.test_batch_prepare_migration import load_schema_13_migration, schema_13_runner


DORMANT_LINK_MIGRATION_PATH = Path("story_audio/migrations/dormant/0014_batch_prepare_job_links.sql")


def load_schema_14_migration(sql: str | None = None) -> Migration:
    migration_sql = sql if sql is not None else DORMANT_LINK_MIGRATION_PATH.read_text(encoding="utf-8")
    return Migration(
        version=14,
        name="batch_prepare_job_links",
        path=DORMANT_LINK_MIGRATION_PATH,
        checksum=hashlib.sha256(migration_sql.encode("utf-8")).hexdigest(),
        sql=migration_sql,
    )


def schema_14_runner(sql: str | None = None) -> MigrationRunner:
    return MigrationRunner([*MIGRATIONS, load_schema_13_migration(), load_schema_14_migration(sql)])


def _canonical_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _assert_not_canonical(path: Path) -> None:
    if _canonical_key(path) == _canonical_key(canonical_production_db_path()):
        raise AssertionError("schema-14 migration tests must not target canonical production DB")


class BatchPrepareJobLinkMigrationTests(unittest.TestCase):
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

    def _fixture(self, database: Database) -> dict[str, int | str]:
        now = utcnow()
        with database.transaction() as connection:
            book_id = int(connection.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                ("Link Migration", "synthetic.epub", "1" * 64, 2, now, now),
            ).lastrowid)
            chapter_ids = []
            for number in (1, 2):
                chapter_ids.append(int(connection.execute(
                    "INSERT INTO chapters(book_id,chapter_number,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (book_id, number, f"Chapter {number}", now, now),
                ).lastrowid))
            job_id = int(connection.execute(
                """INSERT INTO jobs(
                    book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                    settings_json,total_chapters,scheduled_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (book_id, "prepared", 1, 2, "custom:26", "off", "m4a", "{}", 2, now, now, now),
            ).lastrowid)
            for index, chapter_id in enumerate(chapter_ids, start=1):
                connection.execute(
                    "INSERT INTO job_chapters(job_id,chapter_id,sequence,status) VALUES(?,?,?,?)",
                    (job_id, chapter_id, index, "pending"),
                )
            request_id = int(connection.execute(
                """INSERT INTO batch_prepare_requests(
                    client_request_id,request_identity,book_id,from_chapter,to_chapter,
                    target_phase,plan_fingerprint,state,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                ("request-1", "a" * 64, book_id, 1, 2, "PREPARE", "b" * 64, "APPLYING", now, now),
            ).lastrowid)
        return {
            "book_id": book_id,
            "job_id": job_id,
            "request_id": request_id,
            "request_identity": "a" * 64,
            "plan_fingerprint": "b" * 64,
            "chapter_snapshot_digest": "c" * 64,
            "now": now,
        }

    def _insert_link(self, connection: sqlite3.Connection, fixture: dict[str, int | str], **overrides: object) -> int:
        values = {
            "batch_prepare_request_id": fixture["request_id"],
            "request_identity": fixture["request_identity"],
            "job_id": fixture["job_id"],
            "plan_fingerprint": fixture["plan_fingerprint"],
            "chapter_snapshot_digest": fixture["chapter_snapshot_digest"],
            "expected_chapter_count": 2,
            "actual_chapter_count": 2,
            "prepared_status": "prepared",
            "transaction_evidence_version": 1,
            "transaction_committed_at": fixture["now"],
            "worker_woken": 0,
            "render_started": 0,
            "result_schema_version": 1,
            "transaction_reference": None,
            "evidence_source": "migration-test",
            "created_at": fixture["now"],
            "updated_at": fixture["now"],
        }
        values.update(overrides)
        return int(connection.execute(
            """INSERT INTO batch_prepare_job_links(
                batch_prepare_request_id,request_identity,job_id,plan_fingerprint,
                chapter_snapshot_digest,expected_chapter_count,actual_chapter_count,
                prepared_status,transaction_evidence_version,transaction_committed_at,
                worker_woken,render_started,result_schema_version,transaction_reference,
                evidence_source,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                values["batch_prepare_request_id"],
                values["request_identity"],
                values["job_id"],
                values["plan_fingerprint"],
                values["chapter_snapshot_digest"],
                values["expected_chapter_count"],
                values["actual_chapter_count"],
                values["prepared_status"],
                values["transaction_evidence_version"],
                values["transaction_committed_at"],
                values["worker_woken"],
                values["render_started"],
                values["result_schema_version"],
                values["transaction_reference"],
                values["evidence_source"],
                values["created_at"],
                values["updated_at"],
            ),
        ).lastrowid)

    def test_dormant_schema_14_is_not_auto_discovered(self) -> None:
        self.assertTrue(DORMANT_LINK_MIGRATION_PATH.exists())
        self.assertEqual(LATEST_SCHEMA_VERSION, 12)
        self.assertEqual(MIGRATIONS[-1].version, 12)
        self.assertFalse(Path("story_audio/migrations/0014_batch_prepare_job_links.sql").exists())

    def test_explicit_schema_13_to_14_migration_preserves_legacy_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schema14.db"
            _assert_not_canonical(path)
            database = Database(path, migration_runner=schema_13_runner())
            self.assertEqual(database.initialize(), 13)
            fixture = self._fixture(database)
            before = {
                table: database.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]
                for table in ["batch_prepare_requests", "jobs", "job_chapters"]
            }
            database_14 = Database(path, migration_runner=schema_14_runner())
            self.assertEqual(database_14.initialize(), 14)
            self.assertIsNotNone(database_14.fetch_one(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='batch_prepare_job_links'"
            ))
            after = {
                table: database_14.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]
                for table in before
            }
            self.assertEqual(before, after)
            self.assertEqual(fixture["job_id"], 1)

    def test_full_explicit_12_to_13_to_14_chain_and_reopen_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chain.db"
            _assert_not_canonical(path)
            database = Database(path)
            self.assertEqual(database.initialize(), 12)
            database_14 = Database(path, migration_runner=schema_14_runner())
            self.assertEqual(database_14.initialize(), 14)
            self.assertEqual(database_14.schema_version(), 14)
            reopened = Database(path, migration_runner=schema_14_runner())
            self.assertEqual(reopened.schema_version(), 14)
            self.assertIsNotNone(reopened.fetch_one(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='batch_prepare_requests'"
            ))
            self.assertIsNotNone(reopened.fetch_one(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='batch_prepare_job_links'"
            ))

    def test_required_columns_constraints_indexes_and_foreign_keys_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shape.db"
            _assert_not_canonical(path)
            database = Database(path, migration_runner=schema_14_runner())
            database.initialize()
            columns = {row["name"] for row in database.fetch_all("PRAGMA table_info(batch_prepare_job_links)")}
            self.assertTrue({
                "id",
                "batch_prepare_request_id",
                "request_identity",
                "job_id",
                "plan_fingerprint",
                "chapter_snapshot_digest",
                "expected_chapter_count",
                "actual_chapter_count",
                "prepared_status",
                "transaction_evidence_version",
                "transaction_committed_at",
                "worker_woken",
                "render_started",
                "result_schema_version",
                "transaction_reference",
                "evidence_source",
                "created_at",
                "updated_at",
            }.issubset(columns))
            indexes = {row["name"] for row in database.fetch_all(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name IN ('batch_prepare_job_links','batch_prepare_requests')"
            )}
            self.assertTrue({
                "ux_batch_prepare_requests_id_identity",
                "ux_batch_prepare_job_links_request",
                "ux_batch_prepare_job_links_identity",
                "ux_batch_prepare_job_links_job",
                "idx_batch_prepare_job_links_committed",
            }.issubset(indexes))
            fks = [dict(row) for row in database.fetch_all("PRAGMA foreign_key_list(batch_prepare_job_links)")]
            self.assertEqual({row["table"] for row in fks}, {"batch_prepare_requests", "jobs"})
            self.assertTrue(all(row["on_delete"] == "RESTRICT" for row in fks))

    def test_database_constraints_enforce_linkage_evidence_and_uniqueness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "constraints.db"
            _assert_not_canonical(path)
            database = Database(path, migration_runner=schema_14_runner())
            database.initialize()
            fixture = self._fixture(database)
            with database.transaction() as connection:
                self._insert_link(connection, fixture)
                for overrides in [
                    {"batch_prepare_request_id": fixture["request_id"], "job_id": 999},
                    {"request_identity": fixture["request_identity"], "batch_prepare_request_id": 999},
                    {"job_id": fixture["job_id"], "request_identity": "d" * 64},
                    {"expected_chapter_count": 0},
                    {"actual_chapter_count": 3},
                    {"prepared_status": "scheduled"},
                    {"transaction_evidence_version": 2},
                    {"transaction_committed_at": ""},
                    {"worker_woken": 1},
                    {"render_started": 1},
                    {"request_identity": "e" * 64},
                ]:
                    with self.subTest(overrides=overrides):
                        with self.assertRaises(sqlite3.IntegrityError):
                            self._insert_link(connection, fixture, **overrides)

    def test_conservative_delete_behavior_restricts_parent_removal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "restrict.db"
            _assert_not_canonical(path)
            database = Database(path, migration_runner=schema_14_runner())
            database.initialize()
            fixture = self._fixture(database)
            with database.transaction() as connection:
                self._insert_link(connection, fixture)
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute("DELETE FROM batch_prepare_requests WHERE id=?", (fixture["request_id"],))
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute("DELETE FROM jobs WHERE id=?", (fixture["job_id"],))

    def test_migration_failure_rolls_back_without_false_schema_14_or_partial_table(self) -> None:
        bad_sql = DORMANT_LINK_MIGRATION_PATH.read_text(encoding="utf-8") + "\nCREATE TABLE broken_link(\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rollback.db"
            _assert_not_canonical(path)
            database = Database(path, migration_runner=schema_13_runner())
            database.initialize()
            self._fixture(database)
            before = {
                table: database.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]
                for table in ["batch_prepare_requests", "jobs", "job_chapters"]
            }
            broken = Database(path, migration_runner=schema_14_runner(bad_sql))
            with self.assertRaises(SchemaMigrationError):
                broken.initialize()
            self.assertEqual(database.schema_version(), 13)
            self.assertIsNone(database.fetch_one(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='batch_prepare_job_links'"
            ))
            self.assertFalse(database.fetch_all(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE '%job_links%'"
            ))
            after = {
                table: database.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]
                for table in before
            }
            self.assertEqual(before, after)

    def test_canonical_path_guard_variants(self) -> None:
        canonical = canonical_production_db_path()
        variants = [canonical, canonical.resolve(), Path.cwd() / canonical.relative_to(Path.cwd())]
        if canonical.drive:
            variants.append(Path(canonical.drive.lower() + str(canonical)[len(canonical.drive):]))
        for variant in variants:
            with self.subTest(variant=variant):
                with self.assertRaises(AssertionError):
                    _assert_not_canonical(variant)

    def test_migration_does_not_create_job_or_job_chapter_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "no-job-create.db"
            _assert_not_canonical(path)
            database = Database(path, migration_runner=schema_13_runner())
            database.initialize()
            before = {table: database.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"] for table in ["jobs", "job_chapters"]}
            Database(path, migration_runner=schema_14_runner()).initialize()
            after = {table: database.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"] for table in before}
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
