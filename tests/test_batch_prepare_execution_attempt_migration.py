from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from story_audio.batch_prepare_transaction_manager import CanonicalDatabaseRejected, assert_isolated_database_path
from story_audio.config import canonical_production_db_path
from story_audio.db import Database, utcnow
from story_audio.migrations import LATEST_SCHEMA_VERSION, MIGRATIONS, MigrationRunner, SchemaMigrationError
from tests.phase9_fixture import (
    DORMANT_EXECUTION_MIGRATION_PATH,
    Phase9FixtureMixin,
    load_schema_15_migration,
    schema_15_runner,
)
from tests.test_batch_prepare_job_link_migration import schema_14_runner


class BatchPrepareExecutionAttemptMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_testing = os.environ.get("STORY_AUDIO_TESTING")
        os.environ["STORY_AUDIO_TESTING"] = "1"

    def tearDown(self) -> None:
        if self._original_testing is None:
            os.environ.pop("STORY_AUDIO_TESTING", None)
        else:
            os.environ["STORY_AUDIO_TESTING"] = self._original_testing

    def test_dormant_migration_is_not_auto_discovered(self) -> None:
        self.assertTrue(DORMANT_EXECUTION_MIGRATION_PATH.exists())
        self.assertEqual(LATEST_SCHEMA_VERSION, 12)
        self.assertEqual(MIGRATIONS[-1].version, 12)
        self.assertFalse(Path("story_audio/migrations/0015_batch_prepare_execution_attempts.sql").exists())

    def test_explicit_14_to_15_and_full_12_to_15_chain_preserve_legacy_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "migration.db"
            database_14 = Database(path, migration_runner=schema_14_runner())
            self.assertEqual(database_14.initialize(), 14)
            now = utcnow()
            with database_14.transaction() as connection:
                book = int(connection.execute(
                    "INSERT INTO books(title,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?)",
                    ("Legacy", "legacy.epub", "1" * 64, now, now),
                ).lastrowid)
                chapter = int(connection.execute(
                    "INSERT INTO chapters(book_id,chapter_number,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (book, 1, "One", now, now),
                ).lastrowid)
                job = int(connection.execute(
                    """INSERT INTO jobs(book_id,status,from_chapter,to_chapter,voice_name,repair_mode,
                    output_format,settings_json,total_chapters,scheduled_at,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (book, "prepared", 1, 1, "voice", "off", "m4a", "{}", 1, now, now, now),
                ).lastrowid)
                connection.execute(
                    "INSERT INTO job_chapters(job_id,chapter_id,sequence,status) VALUES(?,?,?,?)",
                    (job, chapter, 1, "pending"),
                )
                request = int(connection.execute(
                    """INSERT INTO batch_prepare_requests(
                    client_request_id,request_identity,book_id,from_chapter,to_chapter,target_phase,
                    plan_fingerprint,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    ("legacy-request", "a" * 64, book, 1, 1, "PREPARE", "b" * 64, "APPLYING", now, now),
                ).lastrowid)
                connection.execute(
                    """INSERT INTO batch_prepare_job_links(
                    batch_prepare_request_id,request_identity,job_id,plan_fingerprint,
                    chapter_snapshot_digest,expected_chapter_count,actual_chapter_count,
                    prepared_status,transaction_evidence_version,transaction_committed_at,
                    worker_woken,render_started,result_schema_version,evidence_source,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (request, "a" * 64, job, "b" * 64, "c" * 64, 1, 1, "prepared", 1, now, 0, 0, 1, "migration-test", now, now),
                )
            before = {name: database_14.fetch_one(f"SELECT COUNT(*) AS n FROM {name}")["n"] for name in [
                "books", "chapters", "jobs", "job_chapters", "batch_prepare_requests", "batch_prepare_job_links"
            ]}
            database_15 = Database(path, migration_runner=schema_15_runner())
            self.assertEqual(database_15.initialize(), 15)
            self.assertEqual(database_15.schema_version(), 15)
            self.assertEqual(before, {name: database_15.fetch_one(f"SELECT COUNT(*) AS n FROM {name}")["n"] for name in before})
            self.assertIsNotNone(database_15.fetch_one(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='batch_prepare_execution_attempts'"
            ))
            reopened = Database(path, migration_runner=schema_15_runner())
            self.assertEqual(reopened.schema_version(), 15)

    def test_shape_constraints_foreign_keys_and_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "shape.db", migration_runner=schema_15_runner())
            database.initialize()
            columns = {row["name"] for row in database.fetch_all("PRAGMA table_info(batch_prepare_execution_attempts)")}
            self.assertTrue({
                "batch_prepare_request_id", "request_identity", "attempt_generation", "owner_token_hash",
                "lease_acquired_at", "lease_expires_at", "transaction_reference", "state",
                "plan_fingerprint", "chapter_snapshot_digest", "committed_job_link_id",
                "committed_at", "rolled_back_at", "ambiguity_reason_code", "created_at", "updated_at",
            }.issubset(columns))
            indexes = {row["name"] for row in database.fetch_all(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='batch_prepare_execution_attempts'"
            )}
            self.assertTrue({
                "ux_batch_prepare_execution_attempts_live_owner",
                "idx_batch_prepare_execution_attempts_request_generation",
                "idx_batch_prepare_execution_attempts_lease",
                "idx_batch_prepare_execution_attempts_link",
            }.issubset(indexes))
            foreign_keys = database.fetch_all("PRAGMA foreign_key_list(batch_prepare_execution_attempts)")
            self.assertEqual({row["table"] for row in foreign_keys}, {"batch_prepare_requests", "batch_prepare_job_links"})
            sql = database.fetch_one(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='batch_prepare_execution_attempts'"
            )["sql"]
            for fragment in ["attempt_generation > 0", "state IN", "lease_expires_at > lease_acquired_at", "state = 'COMMITTED'", "state = 'ROLLBACK_CONFIRMED'"]:
                self.assertIn(fragment, sql)

    def test_mid_migration_failure_rolls_back_without_false_schema_15(self) -> None:
        broken = load_schema_15_migration(
            DORMANT_EXECUTION_MIGRATION_PATH.read_text(encoding="utf-8") + "\nTHIS IS NOT SQL;"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.db"
            database_14 = Database(path, migration_runner=schema_14_runner())
            database_14.initialize()
            runner = MigrationRunner([*schema_14_runner().migrations, broken])
            with self.assertRaises((sqlite3.Error, SchemaMigrationError)):
                Database(path, migration_runner=runner).initialize()
            self.assertEqual(database_14.schema_version(), 14)
            self.assertIsNone(database_14.fetch_one(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='batch_prepare_execution_attempts'"
            ))

    def test_canonical_path_guard_rejects_normalized_aliases(self) -> None:
        canonical = canonical_production_db_path()
        with self.assertRaises(CanonicalDatabaseRejected):
            assert_isolated_database_path(canonical)
        alias = canonical.parent / "." / canonical.name
        with self.assertRaises(CanonicalDatabaseRejected):
            assert_isolated_database_path(alias)


class BatchPrepareExecutionAttemptConstraintTests(Phase9FixtureMixin):
    def test_database_rejects_invalid_generation_hash_lease_state_and_parent_binding(self) -> None:
        now = utcnow()
        future = "2999-01-01T00:00:00+00:00"
        base = (
            self.fixture["request_id"], self.fixture["request_identity"], 1, "c" * 64,
            now, future, "tx-constraint", "OWNED", self.fixture["plan_fingerprint"], "d" * 64, now, now,
        )
        sql = """INSERT INTO batch_prepare_execution_attempts(
            batch_prepare_request_id,request_identity,attempt_generation,owner_token_hash,
            lease_acquired_at,lease_expires_at,transaction_reference,state,plan_fingerprint,
            chapter_snapshot_digest,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"""
        cases = [
            (base[:2] + (0,) + base[3:], "generation"),
            (base[:3] + ("Z" * 64,) + base[4:], "hash"),
            (base[:5] + ("2000-01-01T00:00:00+00:00",) + base[6:], "lease"),
            (base[:7] + ("FREEFORM",) + base[8:], "state"),
            ((9999,) + base[1:], "parent"),
        ]
        for values, label in cases:
            with self.subTest(label=label), self.assertRaises(sqlite3.IntegrityError):
                with self.database.transaction() as connection:
                    connection.execute(sql, values)
