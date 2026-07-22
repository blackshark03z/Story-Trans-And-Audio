from __future__ import annotations

import json
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from story_audio.batch_plan import build_batch_plan
from story_audio.batch_prepare_orchestrator import (
    FUTURE_AMBIGUOUS,
    FUTURE_FAILED_RETRYABLE,
    FUTURE_REJECTED,
    FUTURE_SUCCESS,
    OPERATOR_REBUILD_PLAN,
    RECONCILE_APPLIED_RESULT_RECOVERY_REQUIRED,
    RECONCILE_OPERATOR_REVIEW_REQUIRED,
    RECONCILE_SAFE_TO_MARK_FAILED_RETRYABLE,
    RECONCILE_STILL_IN_PROGRESS,
    STATUS_ACCEPTED,
    STATUS_APPLYING,
    STATUS_CONFLICT,
    STATUS_FAILED,
    STATUS_REJECTED,
    BatchPrepareOrchestrator,
    FuturePrepareResult,
    classify_stale_applying_request,
)
from story_audio.batch_prepare_persistence_contract import STATE_APPLYING, STATE_FAILED, STATE_PLANNED
from story_audio.batch_prepare_store import BatchPrepareRequestStore
from story_audio.config import canonical_production_db_path
from story_audio.db import Database
from tests.base import IsolatedTestCase
from tests.test_batch_prepare_migration import schema_13_runner


FINGERPRINT = "f" * 64


class PlanProvider:
    def __init__(self, *plans: dict):
        self.plans = list(plans)
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.plans) > 1:
            return self.plans.pop(0)
        return self.plans[0]


class FakeFutureTransaction:
    def __init__(self, result: FuturePrepareResult | None = None, *, delay: float = 0.0):
        self.result = result or FuturePrepareResult(
            status=FUTURE_SUCCESS,
            simulated_job_reference="future-prepare-001",
            chapter_results=(
                {
                    "chapter_id": 1010,
                    "chapter_number": 10,
                    "plan_eligibility": "ELIGIBLE",
                    "result_status": "SIMULATED_PREPARED",
                    "job_chapter_id": None,
                    "reason_codes": ["PREPARE_ELIGIBLE"],
                    "created_or_reused": "simulated",
                },
            ),
            audit_fields={"source": "fake"},
        )
        self.delay = delay
        self.calls: list[dict] = []

    def prepare(self, context):
        self.calls.append(dict(context))
        if self.delay:
            time.sleep(self.delay)
        return self.result


class FailingAppliedStore:
    def __init__(self, inner: BatchPrepareRequestStore):
        self.inner = inner

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def record_applied_result(self, *args, **kwargs):
        raise RuntimeError("terminal persistence failed")


class BatchPrepareOrchestratorTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.db = Database(self.config.db_path, migration_runner=schema_13_runner())
        self.assertNotEqual(self.config.db_path.resolve(), canonical_production_db_path().resolve())
        self.assertEqual(self.db.initialize(), 13)
        with self.db.transaction() as connection:
            self.book_id = int(
                connection.execute(
                    "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,datetime('now'),datetime('now'))",
                    ("Orchestrator Book", "test://book", "a" * 64, 2),
                ).lastrowid
            )
        self.store = BatchPrepareRequestStore(self.db)

    def _row(self, chapter_number: int, state: str = "READY_TO_PREPARE", **overrides):
        row = {
            "chapter_id": 1000 + chapter_number,
            "chapter_number": chapter_number,
            "chapter_title": f"Chapter {chapter_number}",
            "state": state,
            "next_action": "PREPARE",
            "blockers": [],
            "active_text_revision_id": 2000 + chapter_number,
            "latest_casting_plan_id": 3000 + chapter_number,
            "latest_casting_plan_revision": 1,
            "latest_casting_plan_status": "approved",
            "active_artifact_id": None,
            "active_output_job_id": None,
            "active_output_job_chapter_id": None,
            "live_job_id": None,
            "live_job_status": None,
            "human_qa_status": "pending",
        }
        row.update(overrides)
        return row

    def _plan(self, *rows: dict, from_chapter: int = 10, to_chapter: int = 10) -> dict:
        return build_batch_plan(
            {
                "scope": {
                    "book_id": self.book_id,
                    "book_title": "Orchestrator Book",
                    "from_chapter": from_chapter,
                    "to_chapter": to_chapter,
                    "chapter_count": len(rows),
                },
                "chapters": list(rows),
                "summary": {"total": len(rows)},
                "exceptions": [],
            },
            target_phase="PREPARE",
        )

    def _request(self, plan: dict, **overrides) -> dict:
        scope = plan["scope"]
        request = {
            "client_request_id": "prepare-orchestrator-001",
            "book_id": scope["book_id"],
            "from_chapter": scope["from_chapter"],
            "to_chapter": scope["to_chapter"],
            "target_phase": "PREPARE",
            "plan_fingerprint": plan["plan_fingerprint"],
            "explicit_confirmation": True,
        }
        request.update(overrides)
        return request

    def _orchestrator(self, provider: PlanProvider, future: FakeFutureTransaction | None = None, store=None):
        return BatchPrepareOrchestrator(
            current_plan_provider=provider,
            request_store=store or self.store,
            future_prepare_transaction=future or FakeFutureTransaction(),
        )

    def test_success_path_persists_applied_and_retry_replays_without_second_fake_call(self) -> None:
        plan = self._plan(self._row(10))
        future = FakeFutureTransaction()
        orchestrator = self._orchestrator(PlanProvider(plan), future)
        result = orchestrator.prepare(self._request(plan))
        self.assertEqual(result["status"], STATUS_ACCEPTED)
        self.assertTrue(result["ownership_acquired"])
        self.assertTrue(result["future_transaction_called"])
        self.assertFalse(result["mutation_authorized"])
        self.assertFalse(result["execution_endpoint_available"])
        self.assertFalse(result["real_job_execution"])
        self.assertFalse(result["prepare_starts_render"])
        self.assertEqual(len(future.calls), 1)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"], 0)
        record = self.store.get_request(result["request_id"])
        self.assertEqual(record.state, "APPLIED")
        self.assertIsNone(record.job_id)
        self.assertEqual(record.result_payload["simulated_job_reference"], "future-prepare-001")

        replay = orchestrator.prepare(self._request(plan))
        self.assertEqual(replay["status"], "APPLIED_REPLAYED")
        self.assertTrue(replay["replay"])
        self.assertEqual(len(future.calls), 1)

    def test_invalid_request_does_not_call_plan_store_or_future(self) -> None:
        future = FakeFutureTransaction()
        provider = PlanProvider(self._plan(self._row(10)))
        result = self._orchestrator(provider, future).prepare(None)  # type: ignore[arg-type]
        self.assertEqual(result["status"], "INVALID_REQUEST")
        self.assertEqual(provider.calls, [])
        self.assertEqual(future.calls, [])

    def test_missing_client_request_id_does_not_create_store_row_or_call_future(self) -> None:
        plan = self._plan(self._row(10))
        future = FakeFutureTransaction()
        result = self._orchestrator(PlanProvider(plan), future).prepare(self._request(plan, client_request_id=None))
        self.assertEqual(result["status"], "INVALID_REQUEST")
        self.assertEqual(future.calls, [])
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_requests")["n"], 0)

    def test_no_eligible_chapters_records_rejection_without_ownership_or_future_call(self) -> None:
        plan = self._plan(self._row(10, "CASTING_REVIEW", latest_casting_plan_status="draft"))
        future = FakeFutureTransaction()
        orchestrator = self._orchestrator(PlanProvider(plan), future)
        result = orchestrator.prepare(self._request(plan))
        self.assertEqual(result["status"], STATUS_REJECTED)
        self.assertFalse(result["ownership_acquired"])
        self.assertFalse(result["future_transaction_called"])
        self.assertEqual(result["error_code"], "NO_ELIGIBLE_CHAPTERS")
        self.assertEqual(future.calls, [])
        record = self.store.get_request(result["request_id"])
        self.assertEqual(record.state, "REJECTED")
        self.assertEqual(record.attempt_count, 0)
        replay = orchestrator.prepare(self._request(plan))
        self.assertEqual(replay["status"], "REJECTED_REPLAYED")

    def test_stale_before_future_transaction_records_rejection_and_skips_future_call(self) -> None:
        old_plan = self._plan(self._row(10, active_text_revision_id=1))
        new_plan = self._plan(self._row(10, active_text_revision_id=2))
        future = FakeFutureTransaction()
        result = self._orchestrator(PlanProvider(old_plan, new_plan), future).prepare(self._request(old_plan))
        self.assertEqual(result["status"], STATUS_REJECTED)
        self.assertEqual(result["error_code"], "STALE_PLAN")
        self.assertEqual(result["operator_action"], OPERATOR_REBUILD_PLAN)
        self.assertEqual(future.calls, [])
        record = self.store.get_request(result["request_id"])
        self.assertEqual(record.state, "REJECTED")
        self.assertEqual(record.attempt_count, 1)

    def test_applying_duplicate_returns_in_progress_and_does_not_call_future(self) -> None:
        plan = self._plan(self._row(10))
        request = self._request(plan)
        record = self.store.create_or_replay_request(request)
        self.store.compare_and_transition_state(record.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
        future = FakeFutureTransaction()
        result = self._orchestrator(PlanProvider(plan), future).prepare(request)
        self.assertEqual(result["status"], STATUS_APPLYING)
        self.assertTrue(result["replay"])
        self.assertEqual(future.calls, [])

    def test_failed_duplicate_replays_without_retry(self) -> None:
        plan = self._plan(self._row(10))
        request = self._request(plan)
        binding_record = self.store.create_or_replay_request(request)
        applying = self.store.compare_and_transition_state(binding_record.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
        from story_audio.batch_prepare_persistence_contract import build_request_binding, build_result_payload

        binding = build_request_binding(request)
        payload = build_result_payload(binding, state=STATE_FAILED, job_id=None, chapter_results=[], error_code="FAILED_RETRYABLE")
        self.store.record_failure(
            applying.id,
            result_payload=payload,
            error_code="FAILED_RETRYABLE",
            error_message="retry after review",
        )
        future = FakeFutureTransaction()
        result = self._orchestrator(PlanProvider(plan), future).prepare(request)
        self.assertEqual(result["status"], "FAILED_REPLAYED")
        self.assertEqual(future.calls, [])

    def test_same_request_id_different_payload_returns_conflict(self) -> None:
        plan = self._plan(self._row(10))
        orchestrator = self._orchestrator(PlanProvider(plan), FakeFutureTransaction())
        orchestrator.prepare(self._request(plan))
        changed_plan = self._plan(self._row(10), self._row(11), from_chapter=10, to_chapter=11)
        conflict = self._orchestrator(PlanProvider(changed_plan), FakeFutureTransaction()).prepare(
            self._request(changed_plan)
        )
        self.assertEqual(conflict["status"], STATUS_CONFLICT)
        self.assertEqual(conflict["error_code"], "REQUEST_ID_CONFLICT")

    def test_concurrent_same_request_has_one_owner_and_one_future_call(self) -> None:
        plan = self._plan(self._row(10))
        future = FakeFutureTransaction(delay=0.15)
        orchestrator = self._orchestrator(PlanProvider(plan), future)
        barrier = threading.Barrier(2)
        results: list[dict] = []

        def worker() -> None:
            barrier.wait()
            results.append(orchestrator.prepare(self._request(plan)))

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(future.calls), 1)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_requests")["n"], 1)
        self.assertEqual(sum(1 for result in results if result["future_transaction_called"]), 1)

    def test_future_rejected_retryable_and_ambiguous_results_are_terminal_and_public_safe(self) -> None:
        cases = [
            (FUTURE_REJECTED, STATUS_REJECTED, "PREPARE_CONFLICT"),
            (FUTURE_FAILED_RETRYABLE, STATUS_FAILED, "FAILED_RETRYABLE"),
            (FUTURE_AMBIGUOUS, STATUS_FAILED, "FAILED_REVIEW_REQUIRED"),
        ]
        for index, (future_status, service_status, error_code) in enumerate(cases, start=1):
            with self.subTest(future_status=future_status):
                plan = self._plan(self._row(10 + index), from_chapter=10 + index, to_chapter=10 + index)
                future = FakeFutureTransaction(
                    FuturePrepareResult(
                        status=future_status,
                        error_message="public safe message",
                        chapter_results=(),
                    )
                )
                result = self._orchestrator(PlanProvider(plan), future).prepare(
                    self._request(plan, client_request_id=f"failure-{index}")
                )
                self.assertEqual(result["status"], service_status)
                self.assertEqual(result["error_code"], error_code)
                self.assertNotIn("Traceback", json.dumps(result))

    def test_applied_persistence_failure_cannot_return_success(self) -> None:
        plan = self._plan(self._row(10))
        future = FakeFutureTransaction()
        result = self._orchestrator(PlanProvider(plan), future, store=FailingAppliedStore(self.store)).prepare(self._request(plan))
        self.assertEqual(result["status"], STATUS_FAILED)
        self.assertEqual(result["error_code"], "FAILED_REVIEW_REQUIRED")
        self.assertTrue(result["future_transaction_called"])
        record = self.store.get_request(result["request_id"])
        self.assertEqual(record.state, STATE_APPLYING)

    def test_reconciliation_classifier_is_deterministic_and_non_mutating(self) -> None:
        plan = self._plan(self._row(10))
        request = self._request(plan)
        record = self.store.create_or_replay_request(request)
        applying = self.store.compare_and_transition_state(record.id, expected_state=STATE_PLANNED, next_state=STATE_APPLYING)
        before = applying.as_dict()
        decisions = [
            classify_stale_applying_request(record=applying, current_plan=plan, is_stale=False),
            classify_stale_applying_request(record=applying, current_plan=plan, is_stale=True),
            classify_stale_applying_request(record=applying, current_plan=plan, execution_evidence={"status": "ambiguous"}, is_stale=True),
            classify_stale_applying_request(record=applying, current_plan=plan, execution_evidence={"status": "applied"}, is_stale=True),
            classify_stale_applying_request(record=applying, current_plan={"plan_fingerprint": "0" * 64}, is_stale=True),
        ]
        self.assertEqual(decisions[0]["decision"], RECONCILE_STILL_IN_PROGRESS)
        self.assertEqual(decisions[1]["decision"], RECONCILE_SAFE_TO_MARK_FAILED_RETRYABLE)
        self.assertEqual(decisions[2]["decision"], RECONCILE_OPERATOR_REVIEW_REQUIRED)
        self.assertEqual(decisions[3]["decision"], RECONCILE_APPLIED_RESULT_RECOVERY_REQUIRED)
        self.assertEqual(decisions[4]["decision"], RECONCILE_OPERATOR_REVIEW_REQUIRED)
        after = self.store.get_request(applying.id).as_dict()
        self.assertEqual(before, after)
        self.assertEqual(decisions, [
            classify_stale_applying_request(record=applying, current_plan=plan, is_stale=False),
            classify_stale_applying_request(record=applying, current_plan=plan, is_stale=True),
            classify_stale_applying_request(record=applying, current_plan=plan, execution_evidence={"status": "ambiguous"}, is_stale=True),
            classify_stale_applying_request(record=applying, current_plan=plan, execution_evidence={"status": "applied"}, is_stale=True),
            classify_stale_applying_request(record=applying, current_plan={"plan_fingerprint": "0" * 64}, is_stale=True),
        ])

    def test_reconciliation_rejects_non_applying_record_without_mutation(self) -> None:
        plan = self._plan(self._row(10))
        record = self.store.create_or_replay_request(self._request(plan))
        decision = classify_stale_applying_request(record=record, current_plan=plan, is_stale=True)
        self.assertEqual(decision["decision"], "REQUEST_RECORD_CORRUPT")
        self.assertFalse(decision["automatic_mutation"])

    def test_orchestrator_source_has_no_execution_route_provider_or_chapter_coupling(self) -> None:
        source = Path("story_audio/batch_prepare_orchestrator.py").read_text(encoding="utf-8")
        forbidden = [
            "from .api",
            "from .pipeline",
            "@app.",
            "PipelineWorker",
            "worker.wake",
            "Gemini",
            "tts",
            "369",
            "Database(",
            "MigrationRunner",
        ]
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)
        self.assertNotIn("prepare" + "_job(", source)
        self.assertNotIn("create" + "_job(", source)
        self.assertNotIn("start" + "_prepared_job(", source)

    def test_orchestrator_import_has_no_side_effects_or_global_ownership_registry(self) -> None:
        before = self.db.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_requests")["n"]
        __import__("story_audio.batch_prepare_orchestrator")
        after = self.db.fetch_one("SELECT COUNT(*) AS n FROM batch_prepare_requests")["n"]
        self.assertEqual(before, after)
        source = Path("story_audio/batch_prepare_orchestrator.py").read_text(encoding="utf-8")
        for token in ["GLOBAL_OWNER", "REQUEST_REGISTRY", "threading.Lock", "time.time(", "datetime.now("]:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_no_execution_helpers_are_called(self) -> None:
        plan = self._plan(self._row(10))
        with patch("story_audio.pipeline.prepare_job") as prepare_job, patch(
            "story_audio.pipeline.create_job"
        ) as create_job, patch("story_audio.pipeline.start_prepared_job") as start_prepared_job:
            result = self._orchestrator(PlanProvider(plan), FakeFutureTransaction()).prepare(self._request(plan))
        self.assertEqual(result["status"], STATUS_ACCEPTED)
        prepare_job.assert_not_called()
        create_job.assert_not_called()
        start_prepared_job.assert_not_called()


if __name__ == "__main__":
    unittest.main()
