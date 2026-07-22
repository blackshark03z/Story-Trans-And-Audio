from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from story_audio.batch_plan import build_batch_plan
from story_audio.batch_prepare_contract import (
    CONTRACT_ACCEPTED,
    REJECTED_CONFIRMATION_REQUIRED,
    REJECTED_INVALID_REQUEST,
    REJECTED_NO_ELIGIBLE_CHAPTERS,
    REJECTED_SCOPE_MISMATCH,
    REJECTED_STALE_PLAN,
    REJECTED_UNSUPPORTED_LIFECYCLE,
    REJECTED_UNSUPPORTED_PHASE,
    evaluate_prepare_contract,
)
from story_audio.db import Database
from tests.base import IsolatedTestCase


class PlanProvider:
    def __init__(self, plan: dict):
        self.plan = plan
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.plan


class BatchPrepareContractTests(IsolatedTestCase):
    def _readiness(self, rows: list[dict] | None = None, *, scope: dict | None = None) -> dict:
        return {
            "scope": scope
            or {
                "book_id": 1,
                "book_title": "Book",
                "from_chapter": 10,
                "to_chapter": 12,
                "chapter_count": len(rows or []),
            },
            "chapters": rows or [],
            "summary": {"total": len(rows or [])},
            "exceptions": [],
        }

    def _row(self, chapter_number: int, state: str, **overrides) -> dict:
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

    def _plan(self, *rows: dict, scope: dict | None = None) -> dict:
        return build_batch_plan(self._readiness(list(rows), scope=scope), target_phase="PREPARE")

    def _request(self, plan: dict, **overrides) -> dict:
        scope = plan["scope"]
        request = {
            "book_id": scope["book_id"],
            "from_chapter": scope["from_chapter"],
            "to_chapter": scope["to_chapter"],
            "target_phase": "PREPARE",
            "plan_fingerprint": plan["plan_fingerprint"],
            "explicit_confirmation": True,
        }
        request.update(overrides)
        return request

    def _evaluate(self, plan: dict, **request_overrides):
        provider = PlanProvider(plan)
        result = evaluate_prepare_contract(self._request(plan, **request_overrides), provider)
        return result, provider

    def test_valid_prepare_contract_builds_non_executable_intent(self) -> None:
        plan = self._plan(self._row(10, "READY_TO_PREPARE"))
        result, provider = self._evaluate(plan)
        self.assertEqual(result["status"], CONTRACT_ACCEPTED)
        self.assertEqual(provider.calls[0]["target_phase"], "PREPARE")
        self.assertFalse(result["mutation_authorized"])
        self.assertFalse(result["execution_endpoint_available"])
        self.assertFalse(result["prepare_starts_render"])
        self.assertEqual(len(result["execution_intent"]), 1)
        self.assertEqual(result["execution_intent"][0]["intended_mutation"], "PREPARE_DURABLE_JOB")

    def test_prepare_is_the_only_supported_phase(self) -> None:
        plan = self._plan(self._row(10, "READY_TO_PREPARE"))
        for phase in ["APPROVAL", "START_RENDER", "RESUME_OR_MONITOR", "QA_CLOSEOUT", "NO_ACTION", "MUTATE"]:
            with self.subTest(phase=phase):
                result, provider = self._evaluate(plan, target_phase=phase)
                self.assertEqual(result["status"], REJECTED_UNSUPPORTED_PHASE)
                self.assertEqual(provider.calls, [])
                self.assertFalse(result["mutation_authorized"])
                self.assertFalse(result["execution_endpoint_available"])

    def test_missing_fingerprint_is_rejected_without_substitution(self) -> None:
        plan = self._plan(self._row(10, "READY_TO_PREPARE"))
        result, provider = self._evaluate(plan, plan_fingerprint=None)
        self.assertEqual(result["status"], REJECTED_INVALID_REQUEST)
        self.assertEqual(result["current_fingerprint"], None)
        self.assertEqual(provider.calls, [])

    def test_empty_fingerprint_is_rejected_without_substitution(self) -> None:
        plan = self._plan(self._row(10, "READY_TO_PREPARE"))
        result, provider = self._evaluate(plan, plan_fingerprint="")
        self.assertEqual(result["status"], REJECTED_INVALID_REQUEST)
        self.assertEqual(result["current_fingerprint"], None)
        self.assertEqual(provider.calls, [])

    def test_non_object_request_is_rejected_without_provider_call(self) -> None:
        plan = self._plan(self._row(10, "READY_TO_PREPARE"))
        provider = PlanProvider(plan)
        result = evaluate_prepare_contract(None, provider)  # type: ignore[arg-type]
        self.assertEqual(result["status"], REJECTED_INVALID_REQUEST)
        self.assertEqual(result["reason"], "Request must be an object.")
        self.assertEqual(provider.calls, [])

    def test_stale_fingerprint_is_rejected(self) -> None:
        plan = self._plan(self._row(10, "READY_TO_PREPARE"))
        result, _provider = self._evaluate(plan, plan_fingerprint="0" * 64)
        self.assertEqual(result["status"], REJECTED_STALE_PLAN)
        self.assertEqual(result["current_fingerprint"], plan["plan_fingerprint"])

    def test_scope_mismatch_is_rejected(self) -> None:
        plan = self._plan(
            self._row(10, "READY_TO_PREPARE"),
            scope={"book_id": 1, "book_title": "Book", "from_chapter": 99, "to_chapter": 99, "chapter_count": 1},
        )
        request = {
            "book_id": 1,
            "from_chapter": 10,
            "to_chapter": 10,
            "target_phase": "PREPARE",
            "plan_fingerprint": plan["plan_fingerprint"],
            "explicit_confirmation": True,
        }
        result = evaluate_prepare_contract(request, PlanProvider(plan))
        self.assertEqual(result["status"], REJECTED_SCOPE_MISMATCH)

    def test_confirmation_is_required_before_recompute(self) -> None:
        plan = self._plan(self._row(10, "READY_TO_PREPARE"))
        result, provider = self._evaluate(plan, explicit_confirmation=False)
        self.assertEqual(result["status"], REJECTED_CONFIRMATION_REQUIRED)
        self.assertEqual(provider.calls, [])

    def test_missing_confirmation_is_required_before_recompute(self) -> None:
        plan = self._plan(self._row(10, "READY_TO_PREPARE"))
        request = self._request(plan)
        request.pop("explicit_confirmation")
        provider = PlanProvider(plan)
        result = evaluate_prepare_contract(request, provider)
        self.assertEqual(result["status"], REJECTED_CONFIRMATION_REQUIRED)
        self.assertEqual(provider.calls, [])

    def test_truthy_string_confirmation_is_rejected(self) -> None:
        plan = self._plan(self._row(10, "READY_TO_PREPARE"))
        result, provider = self._evaluate(plan, explicit_confirmation="true")
        self.assertEqual(result["status"], REJECTED_CONFIRMATION_REQUIRED)
        self.assertEqual(provider.calls, [])

    def test_intent_uses_only_current_plan_included_rows(self) -> None:
        plan = self._plan(
            self._row(10, "READY_TO_PREPARE"),
            self._row(11, "CASTING_REVIEW", latest_casting_plan_status="draft"),
        )
        result, _provider = self._evaluate(
            plan,
            included=[{"chapter_id": 9999, "chapter_number": 9999}],
            excluded=[],
        )
        self.assertEqual([row["chapter_number"] for row in result["eligible_chapters"]], [10])
        self.assertEqual([row["chapter_number"] for row in result["execution_intent"]], [10])

    def test_excluded_chapters_remain_excluded_from_prepare_intent(self) -> None:
        plan = self._plan(
            self._row(10, "COMPLETE", active_artifact_id=1, human_qa_status="accepted"),
            self._row(11, "RENDERED_NOT_QA", active_artifact_id=2),
            self._row(12, "PREPARED", live_job_id=8, live_job_status="prepared"),
            self._row(13, "RENDERING_OR_PAUSED", live_job_id=9, live_job_status="running"),
            scope={"book_id": 1, "book_title": "Book", "from_chapter": 10, "to_chapter": 13, "chapter_count": 4},
        )
        result, _provider = self._evaluate(plan)
        self.assertEqual(result["status"], REJECTED_NO_ELIGIBLE_CHAPTERS)
        self.assertEqual(result["execution_intent"], [])
        self.assertEqual(len(result["excluded_chapters"]), 4)

    def test_no_eligible_chapters_returns_deterministic_safe_result(self) -> None:
        plan = self._plan(self._row(10, "CASTING_REVIEW", latest_casting_plan_status="draft"))
        first, _ = self._evaluate(plan)
        second, _ = self._evaluate(plan)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], REJECTED_NO_ELIGIBLE_CHAPTERS)
        self.assertFalse(first["mutation_authorized"])

    def test_repeated_evaluation_is_deterministic(self) -> None:
        plan = self._plan(self._row(10, "READY_TO_PREPARE"), self._row(11, "READY_TO_PREPARE"))
        first, _ = self._evaluate(plan)
        second, _ = self._evaluate(plan)
        self.assertEqual(first, second)
        self.assertEqual([row["chapter_number"] for row in first["execution_intent"]], [10, 11])

    def test_canonical_fact_change_makes_old_request_stale(self) -> None:
        old_plan = self._plan(self._row(10, "READY_TO_PREPARE", active_text_revision_id=2001))
        new_plan = self._plan(self._row(10, "READY_TO_PREPARE", active_text_revision_id=2002))
        result = evaluate_prepare_contract(self._request(old_plan), PlanProvider(new_plan))
        self.assertNotEqual(old_plan["plan_fingerprint"], new_plan["plan_fingerprint"])
        self.assertEqual(result["status"], REJECTED_STALE_PLAN)

    def test_existing_prepared_work_is_not_eligible_for_duplicate_prepare(self) -> None:
        plan = self._plan(self._row(10, "PREPARED", live_job_id=77, live_job_status="prepared"))
        result, _ = self._evaluate(plan)
        self.assertEqual(result["status"], REJECTED_NO_ELIGIBLE_CHAPTERS)
        self.assertIn("PREPARED_JOB_EXISTS", result["excluded_chapters"][0]["reason_codes"])
        self.assertEqual(
            result["duplicate_request_behavior"]["after_prepared_job_exists"],
            "current plan excludes the chapter as PREPARED_JOB_EXISTS",
        )

    def test_duplicate_request_semantics_are_not_overstated(self) -> None:
        plan = self._plan(self._row(10, "READY_TO_PREPARE"))
        result, _ = self._evaluate(plan)
        self.assertEqual(result["idempotency"]["status"], "PARTIALLY_SUPPORTED")
        self.assertEqual(result["duplicate_request_behavior"]["status"], "PARTIALLY_SUPPORTED")
        self.assertEqual(result["duplicate_request_behavior"]["client_request_id"], "NOT_DEFINED")

    def test_partial_failure_semantics_are_not_overstated(self) -> None:
        plan = self._plan(self._row(10, "READY_TO_PREPARE"))
        result, _ = self._evaluate(plan)
        self.assertEqual(result["partial_failure"]["status"], "NOT_YET_DEFINED")
        self.assertEqual(result["partial_failure"]["unit"], "job_chapter")

    def test_retry_semantics_require_recompute_after_state_change(self) -> None:
        plan = self._plan(self._row(10, "READY_TO_PREPARE"))
        result, _ = self._evaluate(plan)
        self.assertEqual(result["retry"]["status"], "PARTIALLY_SUPPORTED")
        self.assertIn("recompute", result["retry"]["after_state_change"])

    def test_prepare_contract_never_starts_render(self) -> None:
        plan = self._plan(self._row(10, "READY_TO_PREPARE"))
        result, _ = self._evaluate(plan)
        self.assertFalse(result["prepare_starts_render"])
        self.assertFalse(result["safety"]["worker_wake"])

    def test_no_batch_prepare_route_is_registered(self) -> None:
        from story_audio.api import app

        routes = [
            route
            for route in app.routes
            if getattr(route, "path", "").startswith("/api/production/")
            and any(method in {"POST", "PUT", "PATCH", "DELETE"} for method in getattr(route, "methods", set()))
        ]
        self.assertEqual(routes, [])

    def test_contract_does_not_call_mutation_helpers_or_provider_clients(self) -> None:
        plan = self._plan(self._row(10, "READY_TO_PREPARE"))
        with patch("story_audio.pipeline.prepare_job") as prepare_job, patch(
            "story_audio.pipeline.start_prepared_job"
        ) as start_prepared_job, patch("story_audio.diagnostics.retry_job_chapter") as retry_job_chapter, patch(
            "story_audio.diagnostics.retry_segment"
        ) as retry_segment:
            result, _ = self._evaluate(plan)
        self.assertEqual(result["status"], CONTRACT_ACCEPTED)
        prepare_job.assert_not_called()
        start_prepared_job.assert_not_called()
        retry_job_chapter.assert_not_called()
        retry_segment.assert_not_called()

    def test_contract_module_has_no_database_or_lifecycle_imports(self) -> None:
        source = Path("story_audio/batch_prepare_contract.py").read_text(encoding="utf-8")
        forbidden = [
            "from .db",
            "import sqlite",
            "prepare_job",
            "start_prepared_job",
            "retry_job_chapter",
            "retry_segment",
            "PipelineWorker",
            "tts_service",
            "Gemini",
        ]
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_contract_evaluation_does_not_change_database_counts(self) -> None:
        db = Database(self.config.db_path)
        db.initialize()
        tables = ["speaker_assignment_drafts", "casting_plans", "jobs", "job_chapters", "segments", "artifacts"]
        before = {table: db.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"] for table in tables}
        plan = self._plan(self._row(10, "READY_TO_PREPARE"))
        self._evaluate(plan)
        after = {table: db.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"] for table in tables}
        self.assertEqual(before, after)

    def test_public_contract_does_not_expose_paths_snapshots_or_tracebacks(self) -> None:
        plan = self._plan(self._row(10, "READY_TO_PREPARE"))
        result, _ = self._evaluate(plan)
        encoded = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(str(self.config.data_dir), encoded)
        self.assertNotIn(str(self.config.output_dir), encoded)
        self.assertNotIn("content_path", encoded)
        self.assertNotIn("voice_snapshot_json", encoded)
        self.assertNotIn("casting_snapshot_json", encoded)
        self.assertNotIn("Traceback", encoded)

    def test_no_chapter_369_hard_code(self) -> None:
        source = Path("story_audio/batch_prepare_contract.py").read_text(encoding="utf-8")
        self.assertNotIn("369", source)
        plan = self._plan(
            self._row(701, "READY_TO_PREPARE"),
            scope={"book_id": 5, "book_title": "Any", "from_chapter": 701, "to_chapter": 701, "chapter_count": 1},
        )
        result, _ = self._evaluate(plan)
        self.assertEqual(result["status"], CONTRACT_ACCEPTED)
        self.assertEqual(result["execution_intent"][0]["chapter_number"], 701)

    def test_one_intent_per_chapter_even_if_plan_accidentally_duplicates(self) -> None:
        row = self._row(10, "READY_TO_PREPARE")
        plan = self._plan(row, dict(row))
        result, _ = self._evaluate(plan)
        self.assertEqual(len(result["execution_intent"]), 1)
        self.assertEqual(len(result["eligible_chapters"]), 1)

    def test_ordering_follows_current_batch_plan(self) -> None:
        plan = self._plan(self._row(12, "READY_TO_PREPARE"), self._row(10, "READY_TO_PREPARE"))
        result, _ = self._evaluate(plan)
        self.assertEqual([row["chapter_number"] for row in result["execution_intent"]], [12, 10])

    def test_every_result_reports_honest_authorization(self) -> None:
        plan = self._plan(self._row(10, "READY_TO_PREPARE"))
        results = [
            self._evaluate(plan)[0],
            self._evaluate(plan, target_phase="APPROVAL")[0],
            self._evaluate(plan, explicit_confirmation=False)[0],
            self._evaluate(plan, plan_fingerprint="0" * 64)[0],
        ]
        for result in results:
            self.assertFalse(result["mutation_authorized"])
            self.assertFalse(result["execution_endpoint_available"])

    def test_client_authoritative_eligibility_payload_is_ignored(self) -> None:
        plan = self._plan(self._row(10, "CASTING_REVIEW", latest_casting_plan_status="draft"))
        result, _ = self._evaluate(
            plan,
            included=[{"chapter_id": 123, "chapter_number": 123, "eligibility": "ELIGIBLE"}],
            excluded=[],
        )
        self.assertEqual(result["status"], REJECTED_NO_ELIGIBLE_CHAPTERS)
        self.assertEqual(result["execution_intent"], [])

    def test_authorization_change_fails_closed(self) -> None:
        plan = self._plan(self._row(10, "READY_TO_PREPARE"))
        plan["authorization"] = {"status": "AUTHORIZED", "execution_endpoint_available": True}
        result, _ = self._evaluate(plan)
        self.assertEqual(result["status"], REJECTED_UNSUPPORTED_LIFECYCLE)


if __name__ == "__main__":
    unittest.main()
