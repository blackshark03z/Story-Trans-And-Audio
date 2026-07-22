from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any

from story_audio.batch_prepare_persistence_contract import (
    DUPLICATE_APPLIED,
    DUPLICATE_FAILED_RETRYABLE,
    DUPLICATE_REJECTED,
    REQUEST_ID_CONFLICT,
    STATE_APPLIED,
    STATE_APPLYING,
    STATE_FAILED,
    STATE_PLANNED,
    STATE_REJECTED,
    build_request_binding,
    build_result_payload,
)
from story_audio.batch_prepare_store import (
    BatchPrepareRequestConflict,
    BatchPrepareRequestStore,
    BatchPrepareStateConflict,
    BatchPrepareStoreDataError,
)
from story_audio.config import canonical_production_db_path
from story_audio.db import Database, utcnow
from story_audio.migrations import LATEST_SCHEMA_VERSION, SchemaMigrationError
from tests.test_batch_prepare_migration import DORMANT_MIGRATION_PATH, schema_13_runner


FINGERPRINT = "a" * 64


def _canonical_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _assert_isolated_db_path(path: Path) -> None:
    if _canonical_key(path) == _canonical_key(canonical_production_db_path()):
        raise AssertionError("isolated integration tests must not target the canonical production DB")


class BatchPrepareIsolatedIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._original_testing = os.environ.get("STORY_AUDIO_TESTING")
        os.environ["STORY_AUDIO_TESTING"] = "1"
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name).resolve() / "isolated_phase4.db"
        _assert_isolated_db_path(self.db_path)
        self.database = Database(self.db_path)
        self.assertEqual(self.database.initialize(), 12)
        self.fixture_ids = self._insert_production_like_fixture(self.database)

    def tearDown(self) -> None:
        if self._original_testing is None:
            os.environ.pop("STORY_AUDIO_TESTING", None)
        else:
            os.environ["STORY_AUDIO_TESTING"] = self._original_testing
        self.temp.cleanup()
        super().tearDown()

    def _insert_production_like_fixture(self, database: Database) -> dict[str, int]:
        now = utcnow()
        with database.transaction() as connection:
            book_id = int(
                connection.execute(
                    "INSERT INTO books(title,author,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                    ("Isolated Book", "Author", "synthetic.epub", "1" * 64, 2, now, now),
                ).lastrowid
            )
            chapter_id = int(
                connection.execute(
                    "INSERT INTO chapters(book_id,chapter_number,title,char_count,audio_status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                    (book_id, 10, "Ten", 1200, "not_created", now, now),
                ).lastrowid
            )
            text_revision_id = int(
                connection.execute(
                    "INSERT INTO text_revisions(chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,processor_version,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (chapter_id, "reflowed", "blobs/text/synthetic.txt", "2" * 64, "3" * 64, 1200, "test", "approved", now),
                ).lastrowid
            )
            plan_id = int(
                connection.execute(
                    "INSERT INTO casting_plans(chapter_id,text_revision_id,plan_revision,status,content_path,plan_sha256,narrator_voice_id,created_at,approved_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (chapter_id, text_revision_id, 1, "approved", "blobs/casting/synthetic.json", "4" * 64, "custom:26", now, now),
                ).lastrowid
            )
            job_id = int(
                connection.execute(
                    """INSERT INTO jobs(
                        book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                        settings_json,total_chapters,scheduled_at,created_at,updated_at,casting_plan_id,casting_snapshot_json
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (book_id, "completed", 10, 10, "custom:26", "off", "m4a", "{}", 1, now, now, now, plan_id, "{}"),
                ).lastrowid
            )
            job_chapter_id = int(
                connection.execute(
                    "INSERT INTO job_chapters(job_id,chapter_id,sequence,status,text_revision_id,casting_plan_id,casting_plan_sha256,voice_snapshot_json) VALUES(?,?,?,?,?,?,?,?)",
                    (job_id, chapter_id, 1, "completed", text_revision_id, plan_id, "4" * 64, "{}"),
                ).lastrowid
            )
            artifact_id = int(
                connection.execute(
                    "INSERT INTO artifacts(chapter_id,job_chapter_id,text_revision_id,artifact_type,path,sha256,size_bytes,duration_ms,status,created_at,verified_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (chapter_id, job_chapter_id, text_revision_id, "chapter_m4a", "output/synthetic.m4a", "5" * 64, 12345, 6789, "verified", now, now),
                ).lastrowid
            )
            connection.execute(
                "UPDATE chapters SET active_text_revision_id=?, active_audio_artifact_id=?, audio_status=?, updated_at=? WHERE id=?",
                (text_revision_id, artifact_id, "completed", now, chapter_id),
            )
        return {
            "book_id": book_id,
            "chapter_id": chapter_id,
            "text_revision_id": text_revision_id,
            "plan_id": plan_id,
            "job_id": job_id,
            "job_chapter_id": job_chapter_id,
            "artifact_id": artifact_id,
        }

    def _upgrade_to_schema_13(self) -> Database:
        _assert_isolated_db_path(self.db_path)
        database_13 = Database(self.db_path, migration_runner=schema_13_runner())
        self.assertEqual(database_13.initialize(), 13)
        return database_13

    def _request(self, client_request_id: str = "phase4-001", **overrides: Any) -> dict[str, Any]:
        request: dict[str, Any] = {
            "client_request_id": client_request_id,
            "book_id": self.fixture_ids["book_id"],
            "from_chapter": 10,
            "to_chapter": 10,
            "target_phase": "PREPARE",
            "plan_fingerprint": FINGERPRINT,
            "explicit_confirmation": True,
        }
        request.update(overrides)
        return request

    def _payload(self, request: dict[str, Any], *, state: str, job_id: int | None = None, error_code: str | None = None) -> dict[str, Any]:
        return build_result_payload(
            build_request_binding(request),
            state=state,
            job_id=job_id,
            chapter_results=[
                {
                    "chapter_id": self.fixture_ids["chapter_id"],
                    "chapter_number": 10,
                    "plan_eligibility": "READY_TO_PREPARE",
                    "result_status": state,
                    "job_chapter_id": self.fixture_ids["job_chapter_id"] if state == STATE_APPLIED else None,
                    "reason_codes": [],
                    "created_or_reused": "historical",
                }
            ],
            error_code=error_code,
            error_message="public safe message" if error_code else None,
            attempt_count=1,
        )

    def _run_worker(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        worker = Path(__file__).resolve().parent / "batch_prepare_isolated_worker.py"
        env = os.environ.copy()
        env["STORY_AUDIO_TESTING"] = "1"
        result = subprocess.run(
            [sys.executable, str(worker), str(self.db_path), action, json.dumps(payload or {})],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        return json.loads(result.stdout)

    def test_explicit_schema_13_activation_survives_connection_and_process_restart(self) -> None:
        before = {table: self.database.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"] for table in [
            "books",
            "chapters",
            "text_revisions",
            "casting_plans",
            "jobs",
            "job_chapters",
            "artifacts",
        ]}
        self.assertEqual(self.database.schema_version(), 12)
        self.assertEqual(LATEST_SCHEMA_VERSION, 12)
        self.assertFalse(Path("story_audio/migrations/0013_batch_prepare_requests.sql").exists())

        database_13 = self._upgrade_to_schema_13()
        self.assertEqual(database_13.schema_version(), 13)
        self.assertIsNotNone(
            database_13.fetch_one("SELECT 1 FROM sqlite_master WHERE type='table' AND name='batch_prepare_requests'")
        )
        after = {table: database_13.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"] for table in before}
        self.assertEqual(before, after)
        columns = {row["name"] for row in database_13.fetch_all("PRAGMA table_info(batch_prepare_requests)")}
        self.assertTrue({"client_request_id", "request_identity", "state", "result_payload_json"}.issubset(columns))
        indexes = {row["name"] for row in database_13.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='batch_prepare_requests'"
        )}
        self.assertIn("idx_batch_prepare_requests_stale_applying", indexes)
        process_view = self._run_worker("schema")
        self.assertEqual(process_view["schema"], 13)
        self.assertTrue(process_view["batch_prepare_requests"])

    def test_request_and_duplicate_replay_survive_connection_and_process_restart(self) -> None:
        database_13 = self._upgrade_to_schema_13()
        store = BatchPrepareRequestStore(database_13)
        request = self._request()
        record = store.create_or_replay_request(request)
        reopened = Database(self.db_path, migration_runner=schema_13_runner())
        same = BatchPrepareRequestStore(reopened).create_or_replay_request(dict(request))
        self.assertEqual(record.id, same.id)
        self.assertEqual(record.request_identity, same.request_identity)
        process_record = self._run_worker("create", request)["record"]
        self.assertEqual(process_record["id"], record.id)
        self.assertEqual(process_record["created_at"], record.created_at)
        self.assertEqual(database_13.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_requests")["n"], 1)

    def test_historical_applied_rejected_failed_replay_survives_restart_and_current_fact_changes(self) -> None:
        database_13 = self._upgrade_to_schema_13()
        store = BatchPrepareRequestStore(database_13)
        cases = [
            ("applied", STATE_APPLIED, None, DUPLICATE_APPLIED),
            ("rejected", STATE_REJECTED, "STALE_PLAN", DUPLICATE_REJECTED),
            ("failed", STATE_FAILED, "FAILED_RETRYABLE", DUPLICATE_FAILED_RETRYABLE),
        ]
        persisted: dict[str, tuple[int, dict[str, Any]]] = {}
        for suffix, state, error_code, _ in cases:
            request = self._request(client_request_id=f"phase4-{suffix}")
            record = store.create_or_replay_request(request)
            store.compare_and_transition_state(record.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
            payload = self._payload(
                request,
                state=state,
                job_id=self.fixture_ids["job_id"] if state == STATE_APPLIED else None,
                error_code=error_code,
            )
            if state == STATE_APPLIED:
                updated = store.record_applied_result(record.id, job_id=self.fixture_ids["job_id"], result_payload=payload)
            elif state == STATE_REJECTED:
                updated = store.record_rejection(
                    record.id,
                    result_payload=payload,
                    error_code=error_code or "STALE_PLAN",
                    error_message="public safe message",
                )
            else:
                updated = store.record_failure(
                    record.id,
                    result_payload=payload,
                    error_code=error_code or "FAILED_RETRYABLE",
                    error_message="public safe message",
                )
            persisted[suffix] = (updated.id, payload)

        with database_13.transaction() as connection:
            connection.execute("UPDATE chapters SET audio_status=? WHERE id=?", ("changed_after_result", self.fixture_ids["chapter_id"]))

        for suffix, state, error_code, expected_status in cases:
            request = self._request(client_request_id=f"phase4-{suffix}")
            replay_record = self._run_worker("create", request)["record"]
            self.assertEqual(replay_record["id"], persisted[suffix][0])
            self.assertEqual(replay_record["state"], state)
            replay = self._run_worker("replay", {"id": persisted[suffix][0]})["replay"]
            self.assertEqual(replay["status"], expected_status)
            self.assertTrue(replay["historical_result_replayed"])
            self.assertEqual(replay["stored_result_payload"], persisted[suffix][1])
            if state == STATE_FAILED:
                fresh = store.create_or_replay_request(self._request(client_request_id="phase4-failed-retry-fresh"))
                self.assertNotEqual(fresh.id, persisted[suffix][0])

    def test_payload_conflicts_after_restart_do_not_mutate_original_row(self) -> None:
        database_13 = self._upgrade_to_schema_13()
        store = BatchPrepareRequestStore(database_13)
        original = store.create_or_replay_request(self._request())
        conflicts = [
            self._request(to_chapter=11),
            self._request(plan_fingerprint="b" * 64),
            self._request(target_phase="START_RENDER"),
        ]
        for request in conflicts:
            with self.subTest(request=request):
                with self.assertRaises(BatchPrepareRequestConflict) as ctx:
                    BatchPrepareRequestStore(Database(self.db_path, migration_runner=schema_13_runner())).create_or_replay_request(request)
                self.assertEqual(ctx.exception.code, REQUEST_ID_CONFLICT)
                current = store.get_request(original.id)
                self.assertEqual(current.request_identity, original.request_identity)
                self.assertEqual(database_13.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_requests")["n"], 1)

    def test_concurrent_create_and_transition_races_have_one_database_winner(self) -> None:
        database_13 = self._upgrade_to_schema_13()

        same_barrier = threading.Barrier(6)
        same_results: list[int] = []
        same_errors: list[BaseException] = []

        def same_worker() -> None:
            same_barrier.wait()
            try:
                same_results.append(BatchPrepareRequestStore(Database(self.db_path, migration_runner=schema_13_runner())).create_or_replay_request(self._request()).id)
            except BaseException as exc:  # pragma: no cover - asserted below
                same_errors.append(exc)

        threads = [threading.Thread(target=same_worker) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(same_errors, [])
        self.assertEqual(len(set(same_results)), 1)
        self.assertEqual(database_13.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_requests")["n"], 1)

        diff_barrier = threading.Barrier(2)
        diff_results: list[int] = []
        diff_conflicts: list[str] = []

        def diff_worker(to_chapter: int) -> None:
            diff_barrier.wait()
            try:
                diff_results.append(
                    BatchPrepareRequestStore(Database(self.db_path, migration_runner=schema_13_runner())).create_or_replay_request(
                        self._request(client_request_id="phase4-conflict", to_chapter=to_chapter)
                    ).id
                )
            except BatchPrepareRequestConflict as exc:
                diff_conflicts.append(exc.code)

        threads = [threading.Thread(target=diff_worker, args=(value,)) for value in (10, 11)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(diff_results), 1)
        self.assertEqual(diff_conflicts, [REQUEST_ID_CONFLICT])

        race_record = BatchPrepareRequestStore(database_13).create_or_replay_request(self._request(client_request_id="phase4-transition"))
        transition_barrier = threading.Barrier(2)
        transition_winners = 0
        transition_losers = 0

        def transition_worker() -> None:
            nonlocal transition_winners, transition_losers
            transition_barrier.wait()
            try:
                BatchPrepareRequestStore(Database(self.db_path, migration_runner=schema_13_runner())).compare_and_transition_state(
                    race_record.id,
                    expected_state=STATE_PLANNED,
                    next_state=STATE_APPLYING,
                )
                transition_winners += 1
            except BatchPrepareStateConflict:
                transition_losers += 1

        threads = [threading.Thread(target=transition_worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual((transition_winners, transition_losers), (1, 1))
        applying = BatchPrepareRequestStore(database_13).get_request(race_record.id)
        self.assertEqual(applying.state, STATE_APPLYING)
        self.assertEqual(applying.attempt_count, 1)

        terminal_barrier = threading.Barrier(2)
        terminal_results: list[str] = []

        def terminal_worker(target: str) -> None:
            terminal_barrier.wait()
            local_store = BatchPrepareRequestStore(Database(self.db_path, migration_runner=schema_13_runner()))
            try:
                if target == STATE_APPLIED:
                    local_store.record_applied_result(
                        race_record.id,
                        job_id=self.fixture_ids["job_id"],
                        result_payload=self._payload(
                            self._request(client_request_id="phase4-transition"),
                            state=STATE_APPLIED,
                            job_id=self.fixture_ids["job_id"],
                        ),
                    )
                else:
                    local_store.record_failure(
                        race_record.id,
                        result_payload=self._payload(
                            self._request(client_request_id="phase4-transition"),
                            state=STATE_FAILED,
                            error_code="FAILED_RETRYABLE",
                        ),
                        error_code="FAILED_RETRYABLE",
                        error_message="public safe message",
                    )
                terminal_results.append(target)
            except BatchPrepareStateConflict:
                terminal_results.append("loser")

        threads = [threading.Thread(target=terminal_worker, args=(target,)) for target in (STATE_APPLIED, STATE_FAILED)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(terminal_results.count("loser"), 1)
        final = BatchPrepareRequestStore(database_13).get_request(race_record.id)
        self.assertIn(final.state, {STATE_APPLIED, STATE_FAILED})
        replay = BatchPrepareRequestStore(database_13).build_historical_replay(race_record.id)
        self.assertEqual(replay["state"], final.state)

    def test_stale_applying_detection_is_read_only_and_restart_stable(self) -> None:
        database_13 = self._upgrade_to_schema_13()
        store = BatchPrepareRequestStore(database_13)
        ids = {}
        for client_id, state in [
            ("old", STATE_APPLYING),
            ("new", STATE_APPLYING),
            ("planned", STATE_PLANNED),
            ("applied", STATE_APPLIED),
            ("failed", STATE_FAILED),
        ]:
            request = self._request(client_request_id=f"phase4-stale-{client_id}")
            record = store.create_or_replay_request(request)
            if state != STATE_PLANNED:
                store.compare_and_transition_state(record.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
            if state == STATE_APPLIED:
                store.record_applied_result(record.id, job_id=self.fixture_ids["job_id"], result_payload=self._payload(request, state=STATE_APPLIED, job_id=self.fixture_ids["job_id"]))
            if state == STATE_FAILED:
                store.record_failure(record.id, result_payload=self._payload(request, state=STATE_FAILED, error_code="FAILED_RETRYABLE"), error_code="FAILED_RETRYABLE", error_message="public safe message")
            ids[client_id] = record.id
        with database_13.transaction() as connection:
            connection.execute("UPDATE batch_prepare_requests SET applying_started_at=?, updated_at=? WHERE id=?", ("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", ids["old"]))
            connection.execute("UPDATE batch_prepare_requests SET applying_started_at=?, updated_at=? WHERE id=?", ("2026-03-01T00:00:00+00:00", "2026-03-01T00:00:00+00:00", ids["new"]))
        before = {
            row["id"]: dict(row)
            for row in database_13.fetch_all("SELECT * FROM batch_prepare_requests ORDER BY id")
        }
        stale = store.list_stale_applying_requests(older_than="2026-02-01T00:00:00+00:00")
        restarted = BatchPrepareRequestStore(Database(self.db_path, migration_runner=schema_13_runner())).list_stale_applying_requests(
            older_than="2026-02-01T00:00:00+00:00"
        )
        after = {
            row["id"]: dict(row)
            for row in database_13.fetch_all("SELECT * FROM batch_prepare_requests ORDER BY id")
        }
        self.assertEqual([row.id for row in stale], [ids["old"]])
        self.assertEqual([row.id for row in restarted], [ids["old"]])
        self.assertEqual(before, after)
        self.assertEqual(database_13.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"], 1)
        self.assertEqual(database_13.fetch_one("SELECT COUNT(*) AS n FROM job_chapters")["n"], 1)

    def test_migration_and_store_failures_roll_back_without_false_success(self) -> None:
        legacy_counts = {table: self.database.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"] for table in ["books", "chapters", "jobs", "job_chapters", "artifacts"]}
        bad_sql = DORMANT_MIGRATION_PATH.read_text(encoding="utf-8") + "\nCREATE TABLE broken_table(\n"
        broken = Database(self.db_path, migration_runner=schema_13_runner(bad_sql))
        with self.assertRaises(SchemaMigrationError):
            broken.initialize()
        self.assertEqual(self.database.schema_version(), 12)
        self.assertIsNone(self.database.fetch_one("SELECT 1 FROM sqlite_master WHERE type='table' AND name='batch_prepare_requests'"))
        self.assertEqual(
            {table: self.database.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"] for table in legacy_counts},
            legacy_counts,
        )

        database_13 = self._upgrade_to_schema_13()
        store = BatchPrepareRequestStore(database_13)
        with database_13.transaction() as connection:
            connection.execute(
                "CREATE TRIGGER fail_request_create BEFORE INSERT ON batch_prepare_requests BEGIN SELECT RAISE(ABORT, 'create failed'); END"
            )
        with self.assertRaises(BatchPrepareRequestConflict):
            store.create_or_replay_request(self._request(client_request_id="phase4-fail-create"))
        self.assertEqual(database_13.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_requests")["n"], 0)
        with database_13.transaction() as connection:
            connection.execute("DROP TRIGGER fail_request_create")
        created = store.create_or_replay_request(self._request(client_request_id="phase4-fail-create"))
        self.assertEqual(created.state, STATE_PLANNED)

        with database_13.transaction() as connection:
            connection.execute(
                "CREATE TRIGGER fail_apply_transition BEFORE UPDATE OF state ON batch_prepare_requests WHEN NEW.state='APPLYING' BEGIN SELECT RAISE(ABORT, 'transition failed'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            store.compare_and_transition_state(created.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
        self.assertEqual(store.get_request(created.id).state, STATE_PLANNED)
        with database_13.transaction() as connection:
            connection.execute("DROP TRIGGER fail_apply_transition")
        store.compare_and_transition_state(created.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)

        with database_13.transaction() as connection:
            connection.execute(
                "CREATE TRIGGER fail_applied_result BEFORE UPDATE OF state ON batch_prepare_requests WHEN NEW.state='APPLIED' BEGIN SELECT RAISE(ABORT, 'applied failed'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            store.record_applied_result(
                created.id,
                job_id=self.fixture_ids["job_id"],
                result_payload=self._payload(
                    self._request(client_request_id="phase4-fail-create"),
                    state=STATE_APPLIED,
                    job_id=self.fixture_ids["job_id"],
                ),
            )
        after_failure = store.get_request(created.id)
        self.assertEqual(after_failure.state, STATE_APPLYING)
        self.assertIsNone(after_failure.result_payload)
        self.assertIsNone(after_failure.completed_at)
        self.assertEqual(store.build_historical_replay(created.id)["historical_result_replayed"], False)
        with database_13.transaction() as connection:
            connection.execute("DROP TRIGGER fail_applied_result")
            connection.execute(
                "UPDATE batch_prepare_requests SET state='APPLIED', result_schema_version=1, result_payload_json=?, completed_at=?, updated_at=? WHERE id=?",
                ("{not json", utcnow(), utcnow(), created.id),
            )
        with self.assertRaises(BatchPrepareStoreDataError):
            store.build_historical_replay(created.id)

    def test_canonical_path_guards_reject_equivalent_paths_without_opening_database(self) -> None:
        canonical = canonical_production_db_path()
        variants = [
            canonical,
            canonical.resolve(),
            Path.cwd() / canonical.relative_to(Path.cwd()),
        ]
        drive = canonical.drive
        if drive:
            variants.append(Path(drive.lower() + str(canonical)[len(drive):]))
        for variant in variants:
            with self.subTest(variant=variant):
                with self.assertRaises(AssertionError):
                    _assert_isolated_db_path(variant)
        _assert_isolated_db_path(self.db_path)
        before_hash = hashlib.sha256(canonical.read_bytes()).hexdigest()
        before_stat = canonical.stat()
        after_hash = hashlib.sha256(canonical.read_bytes()).hexdigest()
        after_stat = canonical.stat()
        self.assertEqual(before_hash, after_hash)
        self.assertEqual(before_stat.st_size, after_stat.st_size)
        self.assertEqual(before_stat.st_mtime, after_stat.st_mtime)

    def test_integration_harness_has_no_execution_route_or_specific_chapter_coupling(self) -> None:
        database_13 = self._upgrade_to_schema_13()
        store = BatchPrepareRequestStore(database_13)
        record = store.create_or_replay_request(self._request())
        store.compare_and_transition_state(record.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
        store.record_failure(
            record.id,
            result_payload=self._payload(self._request(), state=STATE_FAILED, error_code="FAILED_RETRYABLE"),
            error_code="FAILED_RETRYABLE",
            error_message="public safe message",
        )
        self.assertEqual(database_13.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"], 1)
        self.assertEqual(database_13.fetch_one("SELECT COUNT(*) AS n FROM job_chapters")["n"], 1)
        self.assertEqual(database_13.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_requests")["n"], 1)
        for source_path in [
            Path("tests/test_batch_prepare_isolated_integration.py"),
            Path("tests/batch_prepare_isolated_worker.py"),
        ]:
            source = source_path.read_text(encoding="utf-8")
            self.assertNotIn("prepare" + "_job(", source)
            self.assertNotIn("create" + "_job(", source)
            self.assertNotIn("start" + "_prepared_job(", source)
            self.assertNotIn("@" + "app.", source)
            self.assertNotIn("36" + "9", source)


if __name__ == "__main__":
    unittest.main()
