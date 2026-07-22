from __future__ import annotations

import sqlite3
import unittest
from dataclasses import replace

from story_audio.batch_prepare_execution_attempt_store import BatchPrepareExecutionAttemptStore
from story_audio.batch_prepare_transaction_manager import (
    BatchPrepareTransactionManager,
    IsolatedTransactionStateError,
    IsolatedWriteTransaction,
)
from story_audio.batch_prepare_transaction_revalidator import BatchPrepareTransactionRevalidator
from story_audio.prepared_job_transaction_repository import (
    PreparedJobTransactionError,
    PreparedJobTransactionRepository,
)
from tests.phase9_fixture import Phase9FixtureMixin


class PreparedJobTransactionRepositoryTests(Phase9FixtureMixin):
    def _open_validated(self):
        _, snapshot = self.acquire_and_snapshot()
        transaction = BatchPrepareTransactionManager(self.db_path).begin(snapshot.transaction_reference)
        validated = BatchPrepareTransactionRevalidator(
            BatchPrepareExecutionAttemptStore(self.database)
        ).validate(transaction.connection, snapshot)
        return snapshot, transaction, validated

    def test_inserts_exact_prepared_job_and_pinned_job_chapters_without_commit(self) -> None:
        snapshot, transaction, validated = self._open_validated()
        result = PreparedJobTransactionRepository().insert(transaction, validated)
        self.assertFalse(result.committed)
        self.assertTrue(transaction.active)
        evidence = PreparedJobTransactionRepository.inspect(transaction.connection, result.job_id)
        self.assertEqual(evidence["job"]["status"], "prepared")
        self.assertEqual(evidence["job"]["total_chapters"], 2)
        self.assertEqual([row["text_revision_id"] for row in evidence["job_chapters"]], [
            item.text_revision_id for item in snapshot.chapters
        ])
        self.assertEqual([row["casting_plan_id"] for row in evidence["job_chapters"]], [
            item.casting_plan_id for item in snapshot.chapters
        ])
        self.assertEqual(transaction.connection.execute("SELECT COUNT(*) FROM segments").fetchone()[0], 0)
        self.assertEqual(transaction.connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], 0)
        transaction.rollback()
        transaction.close()
        self.assertEqual(self.database.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"], 0)

    def test_caller_commit_persists_and_repository_never_begins_or_commits(self) -> None:
        _, transaction, validated = self._open_validated()
        result = PreparedJobTransactionRepository().insert(transaction, validated)
        self.assertTrue(transaction.connection.in_transaction)
        transaction.commit()
        transaction.close()
        self.assertEqual(self.database.fetch_one("SELECT status FROM jobs WHERE id=?", (result.job_id,))["status"], "prepared")
        self.assertEqual(self.database.fetch_one(
            "SELECT COUNT(*) AS n FROM job_chapters WHERE job_id=?", (result.job_id,)
        )["n"], 2)

    def test_failure_after_job_or_partial_job_chapter_rolls_back_under_caller(self) -> None:
        for target in ["after_job_insert", "after_job_chapter_insert"]:
            fixture = self.fixture if target == "after_job_insert" else self.create_scope(
                client_request_id="partial", request_identity="c" * 64, source_suffix="partial", chapter_numbers=(20, 21)
            )
            _, snapshot = self.acquire_and_snapshot(fixture)
            transaction = BatchPrepareTransactionManager(self.db_path).begin(snapshot.transaction_reference)
            validated = BatchPrepareTransactionRevalidator(BatchPrepareExecutionAttemptStore(self.database)).validate(
                transaction.connection, snapshot
            )
            def fail(stage, context):
                if stage == target:
                    raise RuntimeError(target)
            with self.subTest(target=target), self.assertRaises(RuntimeError):
                PreparedJobTransactionRepository().insert(transaction, validated, stage_hook=fail)
            transaction.rollback()
            transaction.close()
            self.assertEqual(self.database.fetch_one(
                "SELECT COUNT(*) AS n FROM jobs WHERE book_id=?", (fixture["book_id"],)
            )["n"], 0)

    def test_rejects_inactive_transaction_reference_mismatch_and_bad_write_inputs(self) -> None:
        snapshot, transaction, validated = self._open_validated()
        raw = sqlite3.connect(self.db_path)
        raw.row_factory = sqlite3.Row
        inactive = IsolatedWriteTransaction(raw, snapshot.transaction_reference)
        validator = BatchPrepareTransactionRevalidator(BatchPrepareExecutionAttemptStore(self.database))
        with self.assertRaises(IsolatedTransactionStateError):
            PreparedJobTransactionRepository().insert(inactive, None)  # type: ignore[arg-type]
        raw.close()

        wrong_request = replace(validated.request, transaction_reference="other")
        with self.assertRaises(PreparedJobTransactionError):
            PreparedJobTransactionRepository().insert(transaction, replace(validated, request=wrong_request))
        with self.assertRaises(PreparedJobTransactionError):
            PreparedJobTransactionRepository().insert(transaction, validated, output_format="wav")
        with self.assertRaises(PreparedJobTransactionError):
            PreparedJobTransactionRepository().insert(transaction, validated, settings_json="[]")
        transaction.rollback()
        transaction.close()


if __name__ == "__main__":
    unittest.main()
