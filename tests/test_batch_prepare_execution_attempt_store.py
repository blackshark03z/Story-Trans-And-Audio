from __future__ import annotations

import hmac
import sqlite3
import threading
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from story_audio.batch_prepare_execution_attempt_store import (
    COMMITTED,
    EXPIRED,
    OUTCOME_AMBIGUOUS,
    ROLLBACK_CONFIRMED,
    BatchPrepareExecutionAttemptStore,
    ExecutionAttemptConflict,
    ExecutionAttemptOwnerRejected,
    ExecutionAttemptSchemaError,
)
from story_audio.batch_prepare_job_link_store import BatchPrepareJobLinkInput, BatchPrepareJobLinkStore
from story_audio.batch_prepare_transaction_revalidator import AuthoritativeChapterSnapshot, chapter_snapshot_digest
from story_audio.db import utcnow
from tests.phase9_fixture import Phase9FixtureMixin


class BatchPrepareExecutionAttemptStoreTests(Phase9FixtureMixin):
    def test_acquire_persists_hash_only_and_exact_owner_replay(self) -> None:
        lease, snapshot = self.acquire_and_snapshot(transaction_reference="tx-owner")
        row = self.database.fetch_one(
            "SELECT * FROM batch_prepare_execution_attempts WHERE id=?", (lease.record.id,)
        )
        self.assertNotEqual(row["owner_token_hash"], lease.owner_token)
        self.assertNotIn(lease.owner_token, repr(lease))
        self.assertNotIn(lease.owner_token, str(dict(row)))
        replay = BatchPrepareExecutionAttemptStore(self.database).acquire(
            request_id=snapshot.request_id,
            request_identity=snapshot.request_identity,
            plan_fingerprint=snapshot.plan_fingerprint,
            chapter_snapshot_digest=snapshot.chapter_snapshot_digest,
            replay_owner_token=snapshot.owner_token,
            transaction_reference=snapshot.transaction_reference,
        )
        self.assertTrue(replay.replay)
        self.assertEqual(replay.record.attempt_generation, lease.record.attempt_generation)
        self.assertEqual(self.database.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_execution_attempts")["n"], 1)

    def test_validate_rejects_wrong_token_identity_fingerprint_generation_and_expiry(self) -> None:
        _, snapshot = self.acquire_and_snapshot()
        store = BatchPrepareExecutionAttemptStore(self.database)
        with self.database.transaction() as connection:
            valid = store.validate_owner_in_connection(
                connection,
                request_id=snapshot.request_id,
                request_identity=snapshot.request_identity,
                generation=snapshot.owner_generation,
                owner_token=snapshot.owner_token,
                plan_fingerprint=snapshot.plan_fingerprint,
                chapter_snapshot_digest=snapshot.chapter_snapshot_digest,
                transaction_reference=snapshot.transaction_reference,
            )
            self.assertEqual(valid.attempt_generation, snapshot.owner_generation)
            cases = [
                {"owner_token": "wrong"},
                {"request_identity": "c" * 64},
                {"plan_fingerprint": "d" * 64},
                {"generation": snapshot.owner_generation + 1},
                {"transaction_reference": "wrong-reference"},
            ]
            base = {
                "request_id": snapshot.request_id,
                "request_identity": snapshot.request_identity,
                "generation": snapshot.owner_generation,
                "owner_token": snapshot.owner_token,
                "plan_fingerprint": snapshot.plan_fingerprint,
                "chapter_snapshot_digest": snapshot.chapter_snapshot_digest,
                "transaction_reference": snapshot.transaction_reference,
            }
            for overrides in cases:
                with self.subTest(overrides=overrides), self.assertRaises(ExecutionAttemptOwnerRejected):
                    store.validate_owner_in_connection(connection, **(base | overrides))
            with self.assertRaises(ExecutionAttemptOwnerRejected):
                store.validate_owner_in_connection(connection, **base, now="2999-01-01T00:00:00+00:00")

    def test_renew_and_monotonic_generation_fence_stale_owner(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        chapters = tuple(AuthoritativeChapterSnapshot(**item) for item in self.fixture["chapters"])
        digest = chapter_snapshot_digest(chapters)
        store = BatchPrepareExecutionAttemptStore(self.database)
        first = store.acquire(
            request_id=self.fixture["request_id"], request_identity=self.fixture["request_identity"],
            plan_fingerprint=self.fixture["plan_fingerprint"], chapter_snapshot_digest=digest,
            lease_seconds=5, now=start.isoformat(),
        )
        renewed = store.renew_lease(
            request_id=self.fixture["request_id"], generation=1, owner_token=first.owner_token,
            lease_seconds=10, now=(start + timedelta(seconds=1)).isoformat(),
        )
        self.assertGreater(renewed.lease_expires_at, first.record.lease_expires_at)
        second = store.acquire(
            request_id=self.fixture["request_id"], request_identity=self.fixture["request_identity"],
            plan_fingerprint=self.fixture["plan_fingerprint"], chapter_snapshot_digest=digest,
            lease_seconds=5, now=(start + timedelta(seconds=20)).isoformat(),
        )
        self.assertEqual(second.record.attempt_generation, 2)
        self.assertEqual(self.database.fetch_one(
            "SELECT state FROM batch_prepare_execution_attempts WHERE attempt_generation=1"
        )["state"], EXPIRED)
        with self.database.transaction() as connection, self.assertRaises(ExecutionAttemptOwnerRejected):
            store.validate_owner_in_connection(
                connection, request_id=self.fixture["request_id"], request_identity=self.fixture["request_identity"],
                generation=1, owner_token=first.owner_token, plan_fingerprint=self.fixture["plan_fingerprint"],
                chapter_snapshot_digest=digest, transaction_reference=first.record.transaction_reference,
            )

    def test_only_one_concurrent_owner_wins(self) -> None:
        _, snapshot = self.acquire_and_snapshot()
        # Expire the bootstrap owner so the race is for a new generation.
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE batch_prepare_execution_attempts SET lease_acquired_at=?,lease_expires_at=? WHERE id=?",
                ("2000-01-01T00:00:00+00:00", "2000-01-02T00:00:00+00:00", 1),
            )
        winners: list[int] = []
        errors: list[type[BaseException]] = []
        barrier = threading.Barrier(3)

        def acquire() -> None:
            barrier.wait()
            try:
                result = BatchPrepareExecutionAttemptStore(self.database).acquire(
                    request_id=snapshot.request_id, request_identity=snapshot.request_identity,
                    plan_fingerprint=snapshot.plan_fingerprint, chapter_snapshot_digest=snapshot.chapter_snapshot_digest,
                )
                winners.append(result.record.attempt_generation)
            except BaseException as exc:
                errors.append(type(exc))

        threads = [threading.Thread(target=acquire) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertEqual(winners, [2])
        self.assertEqual(errors, [ExecutionAttemptConflict])

    def _commit_link(self, fixture, snapshot, store) -> tuple[int, int]:
        now = utcnow()
        with self.database.transaction() as connection:
            job_id = int(connection.execute(
                """INSERT INTO jobs(book_id,status,from_chapter,to_chapter,voice_name,repair_mode,
                output_format,settings_json,total_chapters,scheduled_at,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (fixture["book_id"], "prepared", fixture["from_chapter"], fixture["to_chapter"], "custom:26", "off", "m4a", "{}", len(fixture["chapters"]), now, now, now),
            ).lastrowid)
            for chapter in fixture["chapters"]:
                connection.execute(
                    "INSERT INTO job_chapters(job_id,chapter_id,sequence,status) VALUES(?,?,?,'pending')",
                    (job_id, chapter["chapter_id"], chapter["deterministic_order"]),
                )
            link = BatchPrepareJobLinkStore(self.database).create_or_replay_in_connection(
                connection,
                BatchPrepareJobLinkInput(
                    batch_prepare_request_id=fixture["request_id"], request_identity=fixture["request_identity"],
                    job_id=job_id, plan_fingerprint=fixture["plan_fingerprint"],
                    chapter_snapshot_digest=snapshot.chapter_snapshot_digest,
                    expected_chapter_count=len(fixture["chapters"]), actual_chapter_count=len(fixture["chapters"]),
                    transaction_committed_at=now, transaction_reference=snapshot.transaction_reference,
                ),
            ).record
            committed = store.mark_committed_in_connection(
                connection, request_id=fixture["request_id"], generation=snapshot.owner_generation,
                job_link_id=link.id, committed_at=now,
            )
        return committed.id, link.id

    def test_committed_rollback_ambiguous_and_terminal_immutability(self) -> None:
        _, snapshot = self.acquire_and_snapshot()
        store = BatchPrepareExecutionAttemptStore(self.database)
        attempt_id, link_id = self._commit_link(self.fixture, snapshot, store)
        self.assertEqual(store.get_current(snapshot.request_id).state, COMMITTED)
        self.assertEqual(store.build_recovery_evidence(snapshot.request_id, 1)["linkage"]["id"], link_id)
        with self.assertRaises(ExecutionAttemptConflict):
            store.mark_rollback_confirmed(request_id=snapshot.request_id, generation=1)
        with self.assertRaises(ExecutionAttemptConflict):
            store.acquire(
                request_id=snapshot.request_id, request_identity=snapshot.request_identity,
                plan_fingerprint=snapshot.plan_fingerprint,
                chapter_snapshot_digest=snapshot.chapter_snapshot_digest,
            )

        rollback_fixture = self.create_scope(
            client_request_id="rollback", request_identity="e" * 64, source_suffix="rollback", chapter_numbers=(20,)
        )
        _, rollback_snapshot = self.acquire_and_snapshot(rollback_fixture)
        self.assertEqual(store.mark_rollback_confirmed(
            request_id=rollback_fixture["request_id"], generation=1
        ).state, ROLLBACK_CONFIRMED)
        ambiguous_fixture = self.create_scope(
            client_request_id="ambiguous", request_identity="f" * 64, source_suffix="ambiguous", chapter_numbers=(30,)
        )
        _, ambiguous_snapshot = self.acquire_and_snapshot(ambiguous_fixture)
        self.assertEqual(store.mark_outcome_ambiguous(
            request_id=ambiguous_fixture["request_id"], generation=1, reason_code="COMMIT_UNKNOWN"
        ).state, OUTCOME_AMBIGUOUS)
        self.assertEqual(attempt_id, 1)
        self.assertEqual(rollback_snapshot.owner_generation, ambiguous_snapshot.owner_generation)

    def test_constant_time_compare_restart_validation_and_corrupt_record_fail_closed(self) -> None:
        _, snapshot = self.acquire_and_snapshot()
        reopened = BatchPrepareExecutionAttemptStore(type(self.database)(self.db_path, migration_runner=self.database.migration_runner))
        with patch.object(hmac, "compare_digest", wraps=hmac.compare_digest) as compare:
            with self.database.transaction() as connection:
                reopened.validate_owner_in_connection(
                    connection, request_id=snapshot.request_id, request_identity=snapshot.request_identity,
                    generation=1, owner_token=snapshot.owner_token, plan_fingerprint=snapshot.plan_fingerprint,
                    chapter_snapshot_digest=snapshot.chapter_snapshot_digest,
                    transaction_reference=snapshot.transaction_reference,
                )
            self.assertTrue(compare.called)
        with self.database.transaction() as connection:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute("UPDATE batch_prepare_execution_attempts SET owner_token_hash='bad' WHERE id=1")
        with self.assertRaises(ExecutionAttemptSchemaError):
            reopened.get_current(snapshot.request_id)

    def test_store_does_not_migrate_or_change_request_state(self) -> None:
        _, snapshot = self.acquire_and_snapshot()
        self.assertEqual(self.database.fetch_one(
            "SELECT state FROM batch_prepare_requests WHERE id=?", (snapshot.request_id,)
        )["state"], "APPLYING")
        with self.database.transaction() as connection:
            connection.execute("DROP TABLE batch_prepare_execution_attempts")
        with self.assertRaises(ExecutionAttemptSchemaError):
            BatchPrepareExecutionAttemptStore(self.database).get_current(snapshot.request_id)
