from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from story_audio.batch_prepare_execution_attempt_store import BatchPrepareExecutionAttemptStore
from story_audio.batch_prepare_isolated_transaction_service import AmbiguousPrepareOutcome
from story_audio.batch_prepare_persistence_contract import build_request_binding
from tests.batch_prepare_phase10_fixture import Phase10FixtureMixin
from tests.test_batch_prepare_isolated_adapter import CountingPlanProvider


class FailAppliedOnceStore:
    def __init__(self, inner):
        self.inner = inner
        self.failed = False

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def record_applied_result(self, *args, **kwargs):
        if not self.failed:
            self.failed = True
            raise RuntimeError("simulated APPLIED persistence loss")
        return self.inner.record_applied_result(*args, **kwargs)


class AmbiguousService:
    def __init__(self, attempts: BatchPrepareExecutionAttemptStore):
        self.attempts = attempts
        self.db = attempts.db

    def prepare(self, snapshot, *, failure_injector=None):
        self.attempts.mark_outcome_ambiguous(
            request_id=snapshot.request_id,
            generation=snapshot.owner_generation,
            reason_code="SIMULATED_COMMIT_UNCERTAINTY",
        )
        raise AmbiguousPrepareOutcome("simulated uncertainty")


class BatchPreparePhase10RecoveryTests(Phase10FixtureMixin):
    def test_applied_persistence_failure_recovers_same_job_without_plan_recompute(self) -> None:
        plan = self.plan()
        failing_store = FailAppliedOnceStore(self.store)
        first, _ = self.orchestrator(request_store=failing_store)
        failed_response = first.prepare(self.request(plan))
        self.assertEqual(failed_response["status"], "PREPARE_FAILED")
        self.assertEqual(self.store.get_request(failed_response["request_id"]).state, "APPLYING")
        self.assertEqual(self.counts()["jobs"], 1)

        provider = CountingPlanProvider(self.plan_provider)
        recovered_orchestrator, _ = self.orchestrator(current_plan_provider=provider)
        recovered = recovered_orchestrator.prepare(self.request(plan))
        self.assertEqual(recovered["request_state"], "APPLIED")
        self.assertTrue(recovered["replay"])
        self.assertEqual(recovered["result"]["recovery_source"], "committed_evidence_recovery")
        self.assertEqual(provider.calls, 0)
        self.assertEqual(self.counts()["jobs"], 1)
        self.assertEqual(self.counts()["batch_prepare_job_links"], 1)

    def test_post_commit_response_exception_recovers_before_failed_mapping(self) -> None:
        plan = self.plan()
        raised = []

        def hook(stage, _context):
            if stage == "after_commit_before_applied" and not raised:
                raised.append(True)
                raise ConnectionError("simulated response loss")

        orchestrator, _ = self.orchestrator(lifecycle_hook=hook)
        result = orchestrator.prepare(self.request(plan))
        self.assertEqual(result["request_state"], "APPLIED")
        self.assertEqual(self.counts()["jobs"], 1)
        self.assertEqual(self.counts()["batch_prepare_job_links"], 1)

    def test_ambiguous_commit_is_terminal_review_required_and_never_reruns(self) -> None:
        plan = self.plan()
        attempts = BatchPrepareExecutionAttemptStore(self.database)
        orchestrator, _ = self.orchestrator(transaction_service=AmbiguousService(attempts))
        first = orchestrator.prepare(self.request(plan))
        self.assertEqual(first["request_state"], "FAILED")
        self.assertEqual(first["error_code"], "FAILED_REVIEW_REQUIRED")
        self.assertEqual(self.counts()["jobs"], 0)
        second = orchestrator.prepare(self.request(plan))
        self.assertEqual(second["status"], "FAILED_REPLAYED")
        self.assertEqual(first["result"]["recovery_classification"], "OUTCOME_AMBIGUOUS")
        self.assertEqual(second["result"]["recovery_classification"], "OUTCOME_AMBIGUOUS")
        self.assertEqual(second["result"], first["result"])
        self.assertEqual(self.counts()["jobs"], 0)
        with self.database.connect() as connection:
            attempt = connection.execute("SELECT state FROM batch_prepare_execution_attempts").fetchone()
        self.assertEqual(attempt["state"], "OUTCOME_AMBIGUOUS")

    def test_corrupt_committed_evidence_never_creates_replacement_job(self) -> None:
        plan = self.plan()
        failing_store = FailAppliedOnceStore(self.store)
        first, _ = self.orchestrator(request_store=failing_store)
        response = first.prepare(self.request(plan))
        self.assertEqual(self.store.get_request(response["request_id"]).state, "APPLYING")
        with self.database.transaction() as connection:
            connection.execute("UPDATE jobs SET status='scheduled' WHERE id=1")
        recovery, _ = self.orchestrator()
        result = recovery.prepare(self.request(plan))
        self.assertEqual(result["request_state"], "FAILED")
        self.assertEqual(result["error_code"], "FAILED_REVIEW_REQUIRED")
        self.assertEqual(self.counts()["jobs"], 1)

    def _assert_precommit_stage_rolls_back(self, stage_to_fail: str) -> None:
        plan = self.plan()

        def injector(stage, _context):
            if stage == stage_to_fail:
                raise RuntimeError(f"injected {stage}")

        orchestrator, _ = self.orchestrator(transaction_failure_injector=injector)
        result = orchestrator.prepare(self.request(plan))
        self.assertEqual(result["request_state"], "FAILED")
        counts = self.counts()
        self.assertEqual(counts["jobs"], 0)
        self.assertEqual(counts["job_chapters"], 0)
        self.assertEqual(counts["batch_prepare_job_links"], 0)
        with self.database.connect() as connection:
            attempt = connection.execute("SELECT state FROM batch_prepare_execution_attempts").fetchone()
        self.assertEqual(attempt["state"], "ROLLBACK_CONFIRMED")

    def test_failure_after_job_insert_rolls_back_everything(self) -> None:
        self._assert_precommit_stage_rolls_back("after_job_insert")

    def test_failure_after_partial_job_chapters_rolls_back_everything(self) -> None:
        self._assert_precommit_stage_rolls_back("after_job_chapter_insert")

    def test_failure_after_linkage_rolls_back_everything(self) -> None:
        self._assert_precommit_stage_rolls_back("after_linkage_insert")

    def test_failure_after_attempt_update_rolls_back_everything(self) -> None:
        self._assert_precommit_stage_rolls_back("after_attempt_update")

    def test_failed_historical_request_does_not_retry_transaction(self) -> None:
        plan = self.plan()

        def injector(stage, _context):
            if stage == "after_job_insert":
                raise RuntimeError("fail once")

        first, _ = self.orchestrator(transaction_failure_injector=injector)
        initial = first.prepare(self.request(plan))
        self.assertEqual(initial["request_state"], "FAILED")
        clean, _ = self.orchestrator()
        replay = clean.prepare(self.request(plan))
        self.assertEqual(replay["status"], "FAILED_REPLAYED")
        self.assertEqual(self.counts()["jobs"], 0)

    def test_corrupt_recovery_timestamp_is_bounded_non_mutating_review_response(self) -> None:
        plan = self.plan()
        request = self.request(plan, client_request_id="corrupt-recovery")
        record = self.store.create_or_replay_request(request)
        applying = self.store.compare_and_transition_state(record.id, expected_state="PLANNED", next_state="APPLYING")
        _orchestrator, adapter = self.orchestrator()
        adapter.acquire(
            {
                "request_id": applying.id,
                "request": build_request_binding(request).as_dict(),
                "plan": plan,
                "eligible_chapters": list(plan.get("eligible_chapters") or plan["included"]),
            }
        )
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE batch_prepare_execution_attempts SET lease_expires_at='not-a-timestamp' WHERE batch_prepare_request_id=?",
                (applying.id,),
            )
        recovery, _ = self.orchestrator()
        response = recovery.prepare(request)
        self.assertEqual(response["status"], "PREPARE_FAILED")
        self.assertEqual(response["error_code"], "FAILED_REVIEW_REQUIRED")
        self.assertEqual(self.store.get_request(applying.id).state, "APPLYING")
        self.assertEqual(self.counts()["jobs"], 0)

    def test_transaction_begin_failure_records_proven_rollback_before_request_failure(self) -> None:
        plan = self.plan()
        service = self.orchestrator()[1].transaction_service
        service.manager.begin = MagicMock(side_effect=RuntimeError("simulated begin failure"))
        orchestrator, _ = self.orchestrator(transaction_service=service)
        result = orchestrator.prepare(self.request(plan, client_request_id="begin-failure"))
        self.assertEqual(result["request_state"], "FAILED")
        self.assertEqual(self.counts()["jobs"], 0)
        with self.database.connect() as connection:
            attempt = connection.execute(
                "SELECT state FROM batch_prepare_execution_attempts WHERE batch_prepare_request_id=?",
                (result["request_id"],),
            ).fetchone()
        self.assertEqual(attempt["state"], "ROLLBACK_CONFIRMED")


if __name__ == "__main__":
    unittest.main()
