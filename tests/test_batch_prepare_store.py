from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from story_audio.batch_prepare_persistence_contract import (
    DUPLICATE_APPLIED,
    DUPLICATE_APPLYING,
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
    RESULT_PAYLOAD_MAX_BYTES,
    BatchPrepareRequestConflict,
    BatchPrepareRequestStore,
    BatchPrepareStateConflict,
    BatchPrepareStoreDataError,
    BatchPrepareStoreSchemaError,
)
from story_audio.config import canonical_production_db_path
from story_audio.db import Database, utcnow
from tests.test_batch_prepare_migration import schema_13_runner


FINGERPRINT = "a" * 64


class BatchPrepareStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._original_testing = os.environ.get("STORY_AUDIO_TESTING")
        os.environ["STORY_AUDIO_TESTING"] = "1"
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "store.db"
        self.assertNotEqual(self.path.resolve(), canonical_production_db_path().resolve())
        self.db = Database(self.path, migration_runner=schema_13_runner())
        self.db.initialize()
        self.store = BatchPrepareRequestStore(self.db)
        self.book_id = self._insert_book()

    def tearDown(self) -> None:
        if self._original_testing is None:
            os.environ.pop("STORY_AUDIO_TESTING", None)
        else:
            os.environ["STORY_AUDIO_TESTING"] = self._original_testing
        self.temp.cleanup()
        super().tearDown()

    def _insert_book(self) -> int:
        now = utcnow()
        with self.db.transaction() as connection:
            return int(
                connection.execute(
                    "INSERT INTO books(title,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?)",
                    ("Book", "book.epub", "f" * 64, now, now),
                ).lastrowid
            )

    def _request(self, **overrides) -> dict[str, object]:
        request = {
            "client_request_id": "prepare-001",
            "book_id": self.book_id,
            "from_chapter": 10,
            "to_chapter": 12,
            "target_phase": "PREPARE",
            "plan_fingerprint": FINGERPRINT,
            "explicit_confirmation": True,
        }
        request.update(overrides)
        return request

    def _payload(self, record, *, state: str, job_id: int | None = None, error_code: str | None = None):
        binding = build_request_binding(self._request(client_request_id=record.client_request_id))
        return build_result_payload(
            binding,
            state=state,
            job_id=job_id,
            chapter_results=[],
            error_code=error_code,
            error_message="public safe message" if error_code else None,
            attempt_count=record.attempt_count,
        )

    def _insert_job(self) -> int:
        now = utcnow()
        with self.db.transaction() as connection:
            return int(
                connection.execute(
                    """INSERT INTO jobs(
                        book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                        settings_json,total_chapters,scheduled_at,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (self.book_id, "prepared", 10, 12, "voice", "off", "m4a", "{}", 3, now, now, now),
                ).lastrowid
            )

    def test_valid_create_request(self) -> None:
        record = self.store.create_or_replay_request(self._request())
        self.assertEqual(record.state, STATE_PLANNED)
        self.assertEqual(record.client_request_id, "prepare-001")
        self.assertEqual(record.target_phase, "PREPARE")
        self.assertEqual(record.job_id, None)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_requests")["n"], 1)

    def test_missing_or_invalid_client_request_id_rejected(self) -> None:
        for value in [None, "", "bad/id"]:
            with self.subTest(value=value):
                with self.assertRaises(Exception):
                    self.store.create_or_replay_request(self._request(client_request_id=value))
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_requests")["n"], 0)

    def test_same_id_same_payload_returns_same_row(self) -> None:
        first = self.store.create_or_replay_request(self._request())
        second = self.store.create_or_replay_request(dict(self._request()))
        self.assertEqual(first.id, second.id)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_requests")["n"], 1)

    def test_same_id_different_scope_fingerprint_or_phase_conflicts_without_mutation(self) -> None:
        original = self.store.create_or_replay_request(self._request())
        conflicts = [
            self._request(to_chapter=13),
            self._request(plan_fingerprint="b" * 64),
            self._request(target_phase="START_RENDER"),
        ]
        for request in conflicts:
            with self.subTest(request=request):
                with self.assertRaises(BatchPrepareRequestConflict) as ctx:
                    self.store.create_or_replay_request(request)
                self.assertEqual(ctx.exception.code, REQUEST_ID_CONFLICT)
        current = self.store.get_request(original.id)
        self.assertEqual(current.request_identity, original.request_identity)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_requests")["n"], 1)

    def test_canonical_identity_is_preserved(self) -> None:
        binding = build_request_binding(self._request())
        record = self.store.create_or_replay_request(self._request())
        self.assertEqual(record.request_identity, binding.request_identity)

    def test_concurrent_same_request_insert_creates_one_row(self) -> None:
        results = []
        errors = []

        def worker() -> None:
            try:
                results.append(self.store.create_or_replay_request(self._request()).id)
            except Exception as exc:  # pragma: no cover - failure detail is asserted below
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(set(results), {results[0]})
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_requests")["n"], 1)

    def test_concurrent_different_payload_same_id_produces_conflict(self) -> None:
        errors = []
        results = []

        def worker(to_chapter: int) -> None:
            try:
                results.append(self.store.create_or_replay_request(self._request(to_chapter=to_chapter)).id)
            except BatchPrepareRequestConflict as exc:
                errors.append(exc.code)

        threads = [threading.Thread(target=worker, args=(value,)) for value in [12, 13]]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_requests")["n"], 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(errors, [REQUEST_ID_CONFLICT])

    def test_planned_to_applying_succeeds_once_and_sets_metadata(self) -> None:
        record = self.store.create_or_replay_request(self._request())
        applying = self.store.compare_and_transition_state(record.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
        self.assertEqual(applying.state, STATE_APPLYING)
        self.assertEqual(applying.attempt_count, 1)
        self.assertIsNotNone(applying.applying_started_at)
        with self.assertRaises(BatchPrepareStateConflict):
            self.store.compare_and_transition_state(record.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)

    def test_allowed_terminal_transitions_from_applying(self) -> None:
        for target, error_code in [
            (STATE_APPLIED, None),
            (STATE_REJECTED, "STALE_PLAN"),
            (STATE_FAILED, "FAILED_RETRYABLE"),
        ]:
            with self.subTest(target=target):
                record = self.store.create_or_replay_request(
                    self._request(client_request_id=f"request-{target.lower()}")
                )
                self.store.compare_and_transition_state(record.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
                payload = self._payload(record, state=target, job_id=44 if target == STATE_APPLIED else None, error_code=error_code)
                if target == STATE_APPLIED:
                    job_id = self._insert_job()
                    payload = self._payload(record, state=target, job_id=job_id, error_code=error_code)
                    updated = self.store.record_applied_result(record.id, job_id=job_id, result_payload=payload)
                    self.assertEqual(updated.job_id, job_id)
                elif target == STATE_REJECTED:
                    updated = self.store.record_rejection(
                        record.id,
                        result_payload=payload,
                        error_code="STALE_PLAN",
                        error_message="public safe message",
                    )
                else:
                    updated = self.store.record_failure(
                        record.id,
                        result_payload=payload,
                        error_code="FAILED_RETRYABLE",
                        error_message="public safe message",
                    )
                self.assertEqual(updated.state, target)
                self.assertIsNotNone(updated.completed_at)

    def test_planned_rejection_records_terminal_result_without_applying_ownership(self) -> None:
        record = self.store.create_or_replay_request(self._request(client_request_id="planned-rejected"))
        payload = self._payload(record, state=STATE_REJECTED, error_code="NO_ELIGIBLE_CHAPTERS")
        updated = self.store.record_rejection(
            record.id,
            result_payload=payload,
            error_code="NO_ELIGIBLE_CHAPTERS",
            error_message="public safe message",
        )
        self.assertEqual(updated.state, STATE_REJECTED)
        self.assertEqual(updated.attempt_count, 0)
        self.assertIsNone(updated.applying_started_at)
        self.assertIsNotNone(updated.completed_at)
        self.assertEqual(self.store.build_historical_replay(record.id)["status"], "DUPLICATE_REJECTED_REPLAY_REJECTION")

    def test_invalid_and_terminal_transitions_are_rejected(self) -> None:
        record = self.store.create_or_replay_request(self._request())
        with self.assertRaises(BatchPrepareStateConflict):
            self.store.compare_and_transition_state(record.id, expected_state=STATE_PLANNED, next_state=STATE_APPLIED)
        self.store.compare_and_transition_state(record.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
        job_id = self._insert_job()
        applied = self.store.record_applied_result(
            record.id,
            job_id=job_id,
            result_payload=self._payload(record, state=STATE_APPLIED, job_id=job_id),
        )
        with self.assertRaises(BatchPrepareStateConflict):
            self.store.compare_and_transition_state(applied.id, expected_state=STATE_APPLIED, next_state=STATE_APPLYING)
        with self.assertRaises(BatchPrepareStateConflict):
            self.store.record_failure(
                applied.id,
                result_payload=self._payload(record, state=STATE_FAILED, error_code="FAILED_RETRYABLE"),
                error_code="FAILED_RETRYABLE",
                error_message="public safe message",
            )

    def test_duplicate_replay_contracts_for_all_states(self) -> None:
        planned = self.store.create_or_replay_request(self._request(client_request_id="planned"))
        self.assertEqual(self.store.build_historical_replay(planned.id)["status"], "DUPLICATE_PLANNED_REPLAY_CURRENT_STATE")

        applying = self.store.create_or_replay_request(self._request(client_request_id="applying"))
        self.store.compare_and_transition_state(applying.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
        self.assertEqual(self.store.build_historical_replay(applying.id)["status"], DUPLICATE_APPLYING)

        applied = self.store.create_or_replay_request(self._request(client_request_id="applied"))
        self.store.compare_and_transition_state(applied.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
        job_id = self._insert_job()
        self.store.record_applied_result(
            applied.id,
            job_id=job_id,
            result_payload=self._payload(applied, state=STATE_APPLIED, job_id=job_id),
        )
        self.assertEqual(self.store.build_historical_replay(applied.id)["status"], DUPLICATE_APPLIED)

        rejected = self.store.create_or_replay_request(self._request(client_request_id="rejected"))
        self.store.compare_and_transition_state(rejected.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
        self.store.record_rejection(
            rejected.id,
            result_payload=self._payload(rejected, state=STATE_REJECTED, error_code="STALE_PLAN"),
            error_code="STALE_PLAN",
            error_message="public safe message",
        )
        self.assertEqual(self.store.build_historical_replay(rejected.id)["status"], DUPLICATE_REJECTED)

        failed = self.store.create_or_replay_request(self._request(client_request_id="failed"))
        self.store.compare_and_transition_state(failed.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
        self.store.record_failure(
            failed.id,
            result_payload=self._payload(failed, state=STATE_FAILED, error_code="FAILED_RETRYABLE"),
            error_code="FAILED_RETRYABLE",
            error_message="public safe message",
        )
        self.assertEqual(self.store.build_historical_replay(failed.id)["status"], DUPLICATE_FAILED_RETRYABLE)

    def test_historical_replay_is_not_recomputed_after_other_data_changes(self) -> None:
        record = self.store.create_or_replay_request(self._request())
        self.store.compare_and_transition_state(record.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
        job_id = self._insert_job()
        payload = self._payload(record, state=STATE_APPLIED, job_id=job_id)
        self.store.record_applied_result(record.id, job_id=job_id, result_payload=payload)
        with self.db.transaction() as connection:
            connection.execute("UPDATE books SET title=? WHERE id=?", ("Changed", self.book_id))
        replay = self.store.build_historical_replay(record.id)
        self.assertEqual(replay["stored_result_payload"], payload)

    def test_result_payload_validation_and_size_limit(self) -> None:
        record = self.store.create_or_replay_request(self._request())
        self.store.compare_and_transition_state(record.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
        with self.assertRaises(Exception):
            self.store.record_applied_result(record.id, job_id=44, result_payload=[])  # type: ignore[arg-type]
        with self.assertRaises(Exception):
            self.store.record_applied_result(record.id, job_id=44, result_payload={"schema": "bad"})
        huge = dict(self._payload(record, state=STATE_APPLIED, job_id=44))
        huge["padding"] = "x" * RESULT_PAYLOAD_MAX_BYTES
        with self.assertRaises(Exception):
            self.store.record_applied_result(record.id, job_id=44, result_payload=huge)
        unsafe = dict(self._payload(record, state=STATE_APPLIED, job_id=44))
        unsafe["traceback"] = "Traceback"
        with self.assertRaises(Exception):
            self.store.record_applied_result(record.id, job_id=44, result_payload=unsafe)
        failed_payload = self._payload(record, state=STATE_FAILED, error_code="FAILED_RETRYABLE")
        with self.assertRaises(Exception):
            self.store.record_failure(
                record.id,
                result_payload=failed_payload,
                error_code="FAILED_RETRYABLE",
                error_message="x" * 1001,
            )

    def test_invalid_stored_json_is_rejected_clearly(self) -> None:
        record = self.store.create_or_replay_request(self._request())
        self.store.compare_and_transition_state(record.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
        with self.db.transaction() as connection:
            connection.execute(
                """UPDATE batch_prepare_requests
                   SET state='APPLIED', result_schema_version=1, result_payload_json=?, completed_at=?, updated_at=?
                   WHERE id=?""",
                ("{not json", utcnow(), utcnow(), record.id),
            )
        with self.assertRaises(BatchPrepareStoreDataError):
            self.store.build_historical_replay(record.id)

    def test_safe_public_error_is_persisted(self) -> None:
        record = self.store.create_or_replay_request(self._request())
        self.store.compare_and_transition_state(record.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
        payload = self._payload(record, state=STATE_FAILED, error_code="FAILED_REVIEW_REQUIRED")
        updated = self.store.record_failure(
            record.id,
            result_payload=payload,
            error_code="FAILED_REVIEW_REQUIRED",
            error_message="operator review required",
        )
        self.assertEqual(updated.error_code, "FAILED_REVIEW_REQUIRED")
        self.assertEqual(updated.error_message, "operator review required")

    def test_stale_applying_query_is_deterministic_and_read_only(self) -> None:
        old = self.store.create_or_replay_request(self._request(client_request_id="old"))
        new = self.store.create_or_replay_request(self._request(client_request_id="new"))
        self.store.compare_and_transition_state(old.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
        self.store.compare_and_transition_state(new.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
        with self.db.transaction() as connection:
            connection.execute("UPDATE batch_prepare_requests SET applying_started_at=? WHERE id=?", ("2026-01-01T00:00:00+00:00", old.id))
            connection.execute("UPDATE batch_prepare_requests SET applying_started_at=? WHERE id=?", ("2026-02-01T00:00:00+00:00", new.id))
        before = self.db.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_requests WHERE state='APPLYING'")["n"]
        stale = self.store.list_stale_applying_requests(older_than="2026-01-15T00:00:00+00:00")
        after = self.db.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_requests WHERE state='APPLYING'")["n"]
        self.assertEqual([row.id for row in stale], [old.id])
        self.assertEqual(before, after)

    def test_job_relation_nullable_and_at_most_one_job(self) -> None:
        record = self.store.create_or_replay_request(self._request())
        self.assertIsNone(record.job_id)
        with self.db.transaction() as connection:
            now = utcnow()
            job_id = connection.execute(
                """INSERT INTO jobs(
                    book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                    settings_json,total_chapters,scheduled_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.book_id, "prepared", 10, 12, "voice", "off", "m4a", "{}", 3, now, now, now),
            ).lastrowid
        self.store.compare_and_transition_state(record.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
        updated = self.store.record_applied_result(
            record.id,
            job_id=job_id,
            result_payload=self._payload(record, state=STATE_APPLIED, job_id=job_id),
        )
        self.assertEqual(updated.job_id, job_id)

    def test_store_fails_when_schema_table_absent_and_never_auto_migrates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schema12.db"
            self.assertNotEqual(path.resolve(), canonical_production_db_path().resolve())
            database = Database(path)
            database.initialize()
            store = BatchPrepareRequestStore(database)
            with self.assertRaises(BatchPrepareStoreSchemaError):
                store.create_or_replay_request(self._request())
            self.assertIsNone(
                database.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name='batch_prepare_requests'")
            )

    def test_import_and_constructor_have_no_side_effects(self) -> None:
        with patch("story_audio.db.Database.connect") as connect:
            BatchPrepareRequestStore(self.db)
            connect.assert_not_called()

    def test_store_never_calls_execution_or_provider_boundaries(self) -> None:
        with patch("story_audio.pipeline.prepare_job") as prepare_job, patch(
            "story_audio.pipeline.create_job"
        ) as create_job, patch("story_audio.pipeline.start_prepared_job") as start_prepared_job:
            record = self.store.create_or_replay_request(self._request())
            self.store.compare_and_transition_state(record.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
            self.store.record_failure(
                record.id,
                result_payload=self._payload(record, state=STATE_FAILED, error_code="FAILED_RETRYABLE"),
                error_code="FAILED_RETRYABLE",
                error_message="public safe message",
            )
        prepare_job.assert_not_called()
        create_job.assert_not_called()
        start_prepared_job.assert_not_called()
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"], 0)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM job_chapters")["n"], 0)

    def test_no_chapter_369_hard_code(self) -> None:
        source = Path("story_audio/batch_prepare_store.py").read_text(encoding="utf-8")
        self.assertNotIn("369", source)


if __name__ == "__main__":
    unittest.main()
