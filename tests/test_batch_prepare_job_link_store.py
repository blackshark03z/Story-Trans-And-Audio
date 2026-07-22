from __future__ import annotations

import os
import hashlib
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any

from story_audio.batch_prepare_job_link_store import (
    JOB_LINK_CONFLICT,
    LINKAGE_EVIDENCE_CONFLICT,
    LINKAGE_RECORD_CORRUPT,
    LINKAGE_TABLE_MISSING,
    PARENT_JOB_INVALID,
    PARENT_REQUEST_INVALID,
    REQUEST_LINK_CONFLICT,
    BatchPrepareJobLinkConflict,
    BatchPrepareJobLinkCorruptError,
    BatchPrepareJobLinkInput,
    BatchPrepareJobLinkSchemaError,
    BatchPrepareJobLinkStore,
    BatchPrepareJobLinkValidationError,
)
from story_audio.config import canonical_production_db_path
from story_audio.db import Database, utcnow
from tests.test_batch_prepare_job_link_migration import schema_14_runner


class BatchPrepareJobLinkStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._original_testing = os.environ.get("STORY_AUDIO_TESTING")
        os.environ["STORY_AUDIO_TESTING"] = "1"
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name).resolve() / "links.db"
        self.assertNotEqual(os.path.normcase(str(self.db_path)), os.path.normcase(str(canonical_production_db_path().resolve())))
        self.database = Database(self.db_path, migration_runner=schema_14_runner())
        self.database.initialize()
        self.fixture = self._fixture()

    def tearDown(self) -> None:
        if self._original_testing is None:
            os.environ.pop("STORY_AUDIO_TESTING", None)
        else:
            os.environ["STORY_AUDIO_TESTING"] = self._original_testing
        self.temp.cleanup()
        super().tearDown()

    def _fixture(
        self,
        *,
        client_request_id: str = "request-1",
        request_identity: str = "a" * 64,
        plan_fingerprint: str = "b" * 64,
        state: str = "APPLYING",
        job_status: str = "prepared",
        from_chapter: int = 1,
        to_chapter: int = 2,
        chapter_count: int = 2,
    ) -> dict[str, int | str]:
        now = utcnow()
        source_sha = hashlib.sha256(client_request_id.encode("utf-8")).hexdigest()
        with self.database.transaction() as connection:
            book_id = int(connection.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (f"Link Store {client_request_id}", f"{client_request_id}.epub", source_sha, chapter_count, now, now),
            ).lastrowid)
            chapter_ids = []
            for offset, number in enumerate(range(from_chapter, from_chapter + chapter_count), start=1):
                chapter_ids.append(int(connection.execute(
                    "INSERT INTO chapters(book_id,chapter_number,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (book_id, number, f"Chapter {number}", now, now),
                ).lastrowid))
            job_id = int(connection.execute(
                """INSERT INTO jobs(
                    book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                    settings_json,total_chapters,scheduled_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (book_id, job_status, from_chapter, to_chapter, "custom:26", "off", "m4a", "{}", chapter_count, now, now, now),
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
                (client_request_id, request_identity, book_id, from_chapter, to_chapter, "PREPARE", plan_fingerprint, state, now, now),
            ).lastrowid)
        return {
            "book_id": book_id,
            "job_id": job_id,
            "request_id": request_id,
            "request_identity": request_identity,
            "plan_fingerprint": plan_fingerprint,
            "chapter_snapshot_digest": "c" * 64,
            "now": now,
            "chapter_count": chapter_count,
        }

    def _input(self, fixture: dict[str, int | str] | None = None, **overrides: Any) -> BatchPrepareJobLinkInput:
        fixture = fixture or self.fixture
        payload = {
            "batch_prepare_request_id": int(fixture["request_id"]),
            "request_identity": str(fixture["request_identity"]),
            "job_id": int(fixture["job_id"]),
            "plan_fingerprint": str(fixture["plan_fingerprint"]),
            "chapter_snapshot_digest": str(fixture["chapter_snapshot_digest"]),
            "expected_chapter_count": int(fixture["chapter_count"]),
            "actual_chapter_count": int(fixture["chapter_count"]),
            "transaction_committed_at": str(fixture["now"]),
            "transaction_reference": f"tx-{fixture['request_id']}",
            "evidence_source": "store-test",
        }
        payload.update(overrides)
        return BatchPrepareJobLinkInput(**payload)

    def _store(self) -> BatchPrepareJobLinkStore:
        return BatchPrepareJobLinkStore(Database(self.db_path, migration_runner=schema_14_runner()))

    def test_create_lookup_historical_evidence_and_exact_replay(self) -> None:
        store = self._store()
        first = store.create_or_replay(self._input())
        self.assertFalse(first.replay)
        self.assertEqual(first.record.batch_prepare_request_id, self.fixture["request_id"])
        self.assertEqual(store.get_by_request_id(int(self.fixture["request_id"])).id, first.record.id)
        self.assertEqual(store.get_by_request_identity(str(self.fixture["request_identity"])).id, first.record.id)
        self.assertEqual(store.get_by_job_id(int(self.fixture["job_id"])).id, first.record.id)
        evidence = store.build_historical_linkage_evidence(int(self.fixture["request_id"]))
        self.assertEqual(evidence["request_identity"], self.fixture["request_identity"])
        self.assertEqual(evidence["job_id"], self.fixture["job_id"])
        self.assertFalse(evidence["worker_woken"])
        self.assertFalse(evidence["render_started"])
        replay = store.create_or_replay(self._input())
        self.assertTrue(replay.replay)
        self.assertEqual(replay.record.id, first.record.id)
        self.assertEqual(replay.record.created_at, first.record.created_at)
        self.assertEqual(self.database.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_job_links")["n"], 1)

    def test_parent_request_validation_rejects_invalid_states_and_mismatches(self) -> None:
        cases = [
            ({"batch_prepare_request_id": 9999}, PARENT_REQUEST_INVALID),
            ({"request_identity": "d" * 64}, PARENT_REQUEST_INVALID),
            ({"plan_fingerprint": "e" * 64}, PARENT_REQUEST_INVALID),
        ]
        for overrides, code in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(BatchPrepareJobLinkValidationError) as ctx:
                    self._store().create_or_replay(self._input(**overrides))
                self.assertEqual(ctx.exception.code, code)
        for state in ["PLANNED", "REJECTED", "FAILED"]:
            fixture = self._fixture(
                client_request_id=f"state-{state.lower()}",
                request_identity=(str(len(state)) * 64)[:64],
                state=state,
            )
            with self.subTest(state=state):
                with self.assertRaises(BatchPrepareJobLinkValidationError) as ctx:
                    self._store().create_or_replay(self._input(fixture))
                self.assertEqual(ctx.exception.code, PARENT_REQUEST_INVALID)
        with self.database.transaction() as connection:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute(
                "UPDATE batch_prepare_requests SET target_phase=? WHERE id=?",
                ("START_RENDER", self.fixture["request_id"]),
            )
        with self.assertRaises(BatchPrepareJobLinkValidationError) as ctx:
            self._store().create_or_replay(self._input())
        self.assertEqual(ctx.exception.code, PARENT_REQUEST_INVALID)

    def test_parent_job_validation_rejects_invalid_job_evidence(self) -> None:
        cases = [
            ({"job_id": 9999}, PARENT_JOB_INVALID),
            (self._fixture(client_request_id="scheduled", request_identity="2" * 64, job_status="scheduled"), PARENT_JOB_INVALID),
        ]
        for item, code in cases:
            with self.subTest(item=item):
                with self.assertRaises(BatchPrepareJobLinkValidationError) as ctx:
                    if isinstance(item, dict) and "job_id" in item and "request_id" not in item:
                        self._store().create_or_replay(self._input(**item))
                    else:
                        self._store().create_or_replay(self._input(item))
                self.assertEqual(ctx.exception.code, code)
        with self.assertRaises(BatchPrepareJobLinkValidationError):
            self._store().create_or_replay(self._input(expected_chapter_count=3, actual_chapter_count=3))
        with self.database.transaction() as connection:
            connection.execute("UPDATE jobs SET started_at=? WHERE id=?", (utcnow(), self.fixture["job_id"]))
        with self.assertRaises(BatchPrepareJobLinkValidationError) as ctx:
            self._store().create_or_replay(self._input())
        self.assertEqual(ctx.exception.code, PARENT_JOB_INVALID)

    def test_input_validation_rejects_bad_evidence_before_insert(self) -> None:
        cases = [
            {"plan_fingerprint": ""},
            {"plan_fingerprint": "A" * 64},
            {"chapter_snapshot_digest": ""},
            {"chapter_snapshot_digest": "g" * 64},
            {"expected_chapter_count": 0, "actual_chapter_count": 0},
            {"expected_chapter_count": 2, "actual_chapter_count": 1},
            {"prepared_status": "scheduled"},
            {"transaction_evidence_version": 2},
            {"transaction_committed_at": ""},
            {"worker_woken": True},
            {"render_started": True},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(BatchPrepareJobLinkValidationError):
                    self._store().create_or_replay(self._input(**overrides))
        self.assertEqual(self.database.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_job_links")["n"], 0)

    def test_conflicts_are_deterministic_and_do_not_overwrite(self) -> None:
        store = self._store()
        original = store.create_or_replay(self._input()).record
        other_job = self._fixture(client_request_id="other-job", request_identity="4" * 64)
        with self.assertRaises(BatchPrepareJobLinkConflict) as ctx:
            store.create_or_replay(self._input(job_id=int(other_job["job_id"])))
        self.assertEqual(ctx.exception.code, REQUEST_LINK_CONFLICT)
        other_request = self._fixture(client_request_id="other-request", request_identity="5" * 64)
        with self.assertRaises(BatchPrepareJobLinkConflict) as ctx:
            store.create_or_replay(self._input(other_request, job_id=int(self.fixture["job_id"])))
        self.assertEqual(ctx.exception.code, JOB_LINK_CONFLICT)
        for overrides in [
            {"plan_fingerprint": "6" * 64},
            {"chapter_snapshot_digest": "7" * 64},
            {"expected_chapter_count": 1, "actual_chapter_count": 1},
            {"transaction_evidence_version": 2},
        ]:
            with self.subTest(overrides=overrides):
                with self.assertRaises((BatchPrepareJobLinkConflict, BatchPrepareJobLinkValidationError)) as conflict:
                    store.create_or_replay(self._input(**overrides))
                self.assertIn(conflict.exception.code, {LINKAGE_EVIDENCE_CONFLICT, PARENT_REQUEST_INVALID, PARENT_JOB_INVALID})
        current = store.get_by_request_id(int(self.fixture["request_id"]))
        self.assertEqual(current.id, original.id)
        self.assertEqual(current.job_id, original.job_id)
        self.assertEqual(self.database.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_job_links")["n"], 1)

    def test_existing_linkage_replays_after_parent_applied_but_new_linkage_does_not(self) -> None:
        store = self._store()
        original = store.create_or_replay(self._input()).record
        with self.database.transaction() as connection:
            connection.execute("UPDATE batch_prepare_requests SET state=? WHERE id=?", ("APPLIED", self.fixture["request_id"]))
        replay = store.create_or_replay(self._input())
        self.assertTrue(replay.replay)
        self.assertEqual(replay.record.id, original.id)
        applied_fixture = self._fixture(client_request_id="applied-new", request_identity="8" * 64, state="APPLIED")
        with self.assertRaises(BatchPrepareJobLinkValidationError) as ctx:
            store.create_or_replay(self._input(applied_fixture))
        self.assertEqual(ctx.exception.code, PARENT_REQUEST_INVALID)

    def test_corrupt_stored_row_fails_closed(self) -> None:
        store = self._store()
        record = store.create_or_replay(self._input()).record
        with self.database.transaction() as connection:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute("UPDATE batch_prepare_job_links SET worker_woken=1 WHERE id=?", (record.id,))
        with self.assertRaises(BatchPrepareJobCorruptOrValidationError) as ctx:
            store.get_by_request_id(int(self.fixture["request_id"]))
        self.assertEqual(ctx.exception.code, LINKAGE_RECORD_CORRUPT)

    def test_table_absent_and_constructor_do_not_migrate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schema13-only.db"
            database = Database(path)
            database.initialize()
            store = BatchPrepareJobLinkStore(database)
            with self.assertRaises(BatchPrepareJobLinkSchemaError) as ctx:
                store.get_by_request_id(1)
            self.assertEqual(ctx.exception.code, LINKAGE_TABLE_MISSING)
            self.assertIsNone(database.fetch_one(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='batch_prepare_job_links'"
            ))

    def test_concurrent_same_exact_linkage_has_one_create_and_one_replay(self) -> None:
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def worker() -> None:
            barrier.wait()
            try:
                results.append(self._store().create_or_replay(self._input()))
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual({result.record.id for result in results}, {1})
        self.assertEqual(sorted(result.replay for result in results), [False, True])
        self.assertEqual(self.database.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_job_links")["n"], 1)

    def test_concurrent_request_and_job_conflicts_have_one_winner(self) -> None:
        with self.database.transaction() as connection:
            now = utcnow()
            other_job_id = int(connection.execute(
                """INSERT INTO jobs(
                    book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                    settings_json,total_chapters,scheduled_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.fixture["book_id"], "prepared", 1, 2, "custom:26", "off", "m4a", "{}", 2, now, now, now),
            ).lastrowid)
            chapter_rows = connection.execute(
                "SELECT id FROM chapters WHERE book_id=? ORDER BY chapter_number",
                (self.fixture["book_id"],),
            ).fetchall()
            for index, row in enumerate(chapter_rows, start=1):
                connection.execute(
                    "INSERT INTO job_chapters(job_id,chapter_id,sequence,status) VALUES(?,?,?,?)",
                    (other_job_id, int(row["id"]), index, "pending"),
                )
        request_barrier = threading.Barrier(2)
        request_results = []
        request_conflicts = []

        def request_worker(job_id: int) -> None:
            request_barrier.wait()
            try:
                request_results.append(self._store().create_or_replay(self._input(job_id=job_id)))
            except BatchPrepareJobLinkConflict as exc:
                request_conflicts.append(exc.code)

        threads = [
            threading.Thread(target=request_worker, args=(int(self.fixture["job_id"]),)),
            threading.Thread(target=request_worker, args=(other_job_id,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(request_results), 1)
        self.assertEqual(request_conflicts, [REQUEST_LINK_CONFLICT])

        fixture_a = self._fixture(client_request_id="job-race-a", request_identity="d" * 64)
        with self.database.transaction() as connection:
            now = utcnow()
            request_b_id = int(connection.execute(
                """INSERT INTO batch_prepare_requests(
                    client_request_id,request_identity,book_id,from_chapter,to_chapter,
                    target_phase,plan_fingerprint,state,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    "job-race-b",
                    "e" * 64,
                    fixture_a["book_id"],
                    1,
                    2,
                    "PREPARE",
                    fixture_a["plan_fingerprint"],
                    "APPLYING",
                    now,
                    now,
                ),
            ).lastrowid)
        fixture_b = dict(fixture_a)
        fixture_b["request_id"] = request_b_id
        fixture_b["request_identity"] = "e" * 64
        fixture_b["now"] = now
        job_barrier = threading.Barrier(2)
        job_results = []
        job_conflicts = []

        def job_worker(fixture: dict[str, int | str]) -> None:
            job_barrier.wait()
            try:
                job_results.append(self._store().create_or_replay(self._input(fixture, job_id=int(fixture_a["job_id"]))))
            except BatchPrepareJobLinkConflict as exc:
                job_conflicts.append(exc.code)

        threads = [threading.Thread(target=job_worker, args=(fixture,)) for fixture in (fixture_a, fixture_b)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(job_results), 1)
        self.assertEqual(job_conflicts, [JOB_LINK_CONFLICT])
        self.assertEqual(len([row for row in self.database.fetch_all("SELECT * FROM batch_prepare_job_links")]), 2)

    def test_safety_no_side_effects_or_forbidden_imports(self) -> None:
        before = {
            table: self.database.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]
            for table in ["batch_prepare_requests", "jobs", "job_chapters"]
        }
        self._store().create_or_replay(self._input())
        after = {
            table: self.database.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]
            for table in before
        }
        self.assertEqual(before, after)
        source = Path("story_audio/batch_prepare_job_link_store.py").read_text(encoding="utf-8")
        self.assertNotIn("from .pipeline", source)
        self.assertNotIn("prepare" + "_job(", source)
        self.assertNotIn("create" + "_job(", source)
        self.assertNotIn("start" + "_prepared_job(", source)
        self.assertNotIn("worker.wake", source)
        self.assertNotIn("Gemini", source)
        self.assertNotIn("TTS", source)
        self.assertNotIn("@app.", source)
        self.assertNotIn("36" + "9", source)


BatchPrepareJobCorruptOrValidationError = (BatchPrepareJobLinkCorruptError, BatchPrepareJobLinkValidationError)


if __name__ == "__main__":
    unittest.main()
