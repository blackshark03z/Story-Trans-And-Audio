from __future__ import annotations

import importlib
import unittest
from pathlib import Path

from story_audio.batch_prepare_job_adapter_contract import (
    ADAPTER_INPUT_INVALID,
    COMMIT_EVIDENCE_INVALID,
    DUPLICATE_NO_SAFE_RETRY,
    DUPLICATE_REPLAY_COMMITTED_RESULT,
    EVIDENCE_ACTIVE_JOB_FOUND,
    EVIDENCE_COMPLETED_JOB_FOUND,
    EVIDENCE_JOB_PARTIAL_OR_CORRUPT,
    EVIDENCE_JOB_REFERENCE_WITHOUT_COMMIT,
    EVIDENCE_LEGACY_UNLINKED_JOB,
    EVIDENCE_LINKAGE_MISMATCH,
    EVIDENCE_MULTIPLE_MATCHING_JOBS,
    EVIDENCE_NONE,
    EVIDENCE_PREPARED_JOB_COMMITTED,
    EVIDENCE_TRANSACTION_NOT_FOUND,
    EVIDENCE_UNKNOWN,
    EXISTING_ACTIVE_JOB,
    EXISTING_PREPARED_JOB,
    LINKAGE_CONFLICT,
    OPERATOR_REVIEW_REQUIRED,
    RECONCILE_CORRUPT_TRANSACTION_STATE,
    RECONCILE_OPERATOR_REVIEW_REQUIRED,
    RECONCILE_RECOVER_COMMITTED_RESULT,
    RECONCILE_REQUEST_JOB_CONFLICT,
    RECONCILE_SAFE_NO_COMMIT_CONFIRMED,
    REQUEST_STATE_NOT_APPLYING,
    RESULT_PERSISTENCE_REQUIRED,
    TRANSACTION_EVIDENCE_MISSING,
    TRANSACTION_FAILED_ROLLED_BACK,
    TRANSACTION_OUTCOME_AMBIGUOUS,
    AdapterInput,
    ChapterPrepareSnapshot,
    ExternalJobEvidence,
    JobChapterEvidence,
    TransactionEvidence,
    ambiguous_after_commit_response,
    authorization_gates,
    build_historical_result_payload,
    chapter_snapshot_digest,
    classify_reconciliation_evidence,
    commit_confirmed_request_result_missing,
    contract_metadata,
    evaluate_committed_success,
    evaluate_duplicate_invocation,
    failure_before_commit,
    map_existing_job_conflict,
    validate_adapter_input,
)


IDENTITY = "a" * 64
FINGERPRINT = "b" * 64


class BatchPrepareJobAdapterContractTests(unittest.TestCase):
    def _chapter(self, chapter_number: int = 10, **overrides) -> ChapterPrepareSnapshot:
        values = {
            "book_id": 1,
            "chapter_id": chapter_number + 100,
            "chapter_number": chapter_number,
            "text_revision_id": chapter_number + 1000,
            "casting_plan_id": chapter_number + 2000,
            "casting_plan_revision": 1,
            "eligibility_evidence": ("READY_TO_PREPARE", "approved_plan"),
            "deterministic_order": chapter_number - 9,
        }
        values.update(overrides)
        return ChapterPrepareSnapshot(**values)

    def _input(self, chapters: tuple[ChapterPrepareSnapshot, ...] | None = None, **overrides) -> AdapterInput:
        values = {
            "request_id": 44,
            "client_request_id": "client-44",
            "request_identity": IDENTITY,
            "book_id": 1,
            "from_chapter": 10,
            "to_chapter": 12,
            "target_phase": "PREPARE",
            "plan_fingerprint": FINGERPRINT,
            "request_state": "APPLYING",
            "eligible_chapters": chapters if chapters is not None else (self._chapter(10), self._chapter(11), self._chapter(12)),
            "orchestration_attempt": 1,
            "explicit_no_render": True,
        }
        values.update(overrides)
        return AdapterInput(**values)

    def _evidence(self, adapter_input: AdapterInput | None = None, **overrides) -> TransactionEvidence:
        adapter_input = adapter_input or self._input()
        chapters = tuple(
            JobChapterEvidence(
                chapter_id=chapter.chapter_id,
                chapter_number=chapter.chapter_number,
                job_chapter_reference=f"future-job-chapter-{index}",
            )
            for index, chapter in enumerate(adapter_input.eligible_chapters, start=1)
        )
        values = {
            "request_identity": adapter_input.request_identity,
            "job_reference": "future-job-1",
            "committed": True,
            "committed_at": "2026-07-22T12:00:00+00:00",
            "prepared_status": "prepared",
            "expected_chapter_count": len(adapter_input.eligible_chapters),
            "actual_chapter_count": len(adapter_input.eligible_chapters),
            "chapter_snapshot_digest": chapter_snapshot_digest(adapter_input.eligible_chapters),
            "plan_fingerprint": adapter_input.plan_fingerprint,
            "worker_woken": False,
            "render_started": False,
            "job_chapters": chapters,
        }
        values.update(overrides)
        return TransactionEvidence(**values)

    def _matching_external(self, adapter_input: AdapterInput | None = None, **overrides) -> ExternalJobEvidence:
        adapter_input = adapter_input or self._input()
        values = {
            "evidence_state": EVIDENCE_PREPARED_JOB_COMMITTED,
            "request_identity": adapter_input.request_identity,
            "job_reference": "future-job-1",
            "chapter_snapshot_digest": chapter_snapshot_digest(adapter_input.eligible_chapters),
            "plan_fingerprint": adapter_input.plan_fingerprint,
            "prepared_status": "prepared",
            "committed": True,
            "job_count": 1,
        }
        values.update(overrides)
        return ExternalJobEvidence(**values)

    def test_01_valid_applying_request_input(self) -> None:
        result = validate_adapter_input(self._input())
        self.assertTrue(result["valid"])
        self.assertEqual(result["chapter_count"], 3)

    def test_02_non_applying_request_rejected(self) -> None:
        result = validate_adapter_input(self._input(request_state="PLANNED"))
        self.assertFalse(result["valid"])
        self.assertEqual(result["code"], REQUEST_STATE_NOT_APPLYING)

    def test_03_missing_request_identity_rejected(self) -> None:
        result = validate_adapter_input(self._input(request_identity=""))
        self.assertIn("MISSING_OR_INVALID_REQUEST_IDENTITY", result["errors"])

    def test_04_scope_mismatch_rejected(self) -> None:
        result = validate_adapter_input(self._input(chapters=(self._chapter(13),)))
        self.assertIn("SCOPE_MISMATCH", result["errors"])

    def test_05_invalid_fingerprint_rejected(self) -> None:
        result = validate_adapter_input(self._input(plan_fingerprint="not-a-fingerprint"))
        self.assertIn("MISSING_OR_INVALID_PLAN_FINGERPRINT", result["errors"])

    def test_06_empty_eligible_chapters_rejected(self) -> None:
        result = validate_adapter_input(self._input(chapters=()))
        self.assertIn("EMPTY_ELIGIBLE_CHAPTERS", result["errors"])

    def test_07_duplicate_chapter_rejected(self) -> None:
        chapter = self._chapter(10)
        result = validate_adapter_input(self._input(chapters=(chapter, chapter)))
        self.assertIn("DUPLICATE_CHAPTER", result["errors"])

    def test_08_cross_book_chapter_rejected(self) -> None:
        result = validate_adapter_input(self._input(chapters=(self._chapter(10, book_id=2),)))
        self.assertIn("CROSS_BOOK_CHAPTER", result["errors"])

    def test_09_non_deterministic_order_rejected(self) -> None:
        result = validate_adapter_input(
            self._input(chapters=(self._chapter(10, deterministic_order=2), self._chapter(11, deterministic_order=1)))
        )
        self.assertIn("NON_DETERMINISTIC_CHAPTER_ORDER", result["errors"])

    def test_10_missing_revision_or_plan_identity_rejected(self) -> None:
        result = validate_adapter_input(self._input(chapters=(self._chapter(10, text_revision_id=0),)))
        self.assertIn("MISSING_REVISION_OR_PLAN_IDENTITY", result["errors"])

    def test_11_valid_committed_success_accepted(self) -> None:
        adapter_input = self._input()
        result = evaluate_committed_success(adapter_input, self._evidence(adapter_input))
        self.assertTrue(result["applied_eligible"])

    def test_12_missing_commit_evidence_rejected(self) -> None:
        adapter_input = self._input()
        result = evaluate_committed_success(adapter_input, self._evidence(adapter_input, committed_at=None))
        self.assertEqual(result["code"], COMMIT_EVIDENCE_INVALID)

    def test_13_allocated_uncommitted_job_rejected(self) -> None:
        adapter_input = self._input()
        result = evaluate_committed_success(adapter_input, self._evidence(adapter_input, committed=False))
        self.assertIn("TRANSACTION_NOT_COMMITTED", result["errors"])

    def test_14_wrong_request_identity_rejected(self) -> None:
        adapter_input = self._input()
        result = evaluate_committed_success(adapter_input, self._evidence(adapter_input, request_identity="c" * 64))
        self.assertIn("REQUEST_BINDING_MISMATCH", result["errors"])

    def test_15_wrong_fingerprint_rejected(self) -> None:
        adapter_input = self._input()
        result = evaluate_committed_success(adapter_input, self._evidence(adapter_input, plan_fingerprint="c" * 64))
        self.assertIn("PLAN_SNAPSHOT_MISMATCH", result["errors"])

    def test_16_chapter_count_mismatch_rejected(self) -> None:
        adapter_input = self._input()
        result = evaluate_committed_success(adapter_input, self._evidence(adapter_input, actual_chapter_count=2))
        self.assertIn("CHAPTER_COUNT_MISMATCH", result["errors"])

    def test_17_snapshot_digest_mismatch_rejected(self) -> None:
        adapter_input = self._input()
        result = evaluate_committed_success(adapter_input, self._evidence(adapter_input, chapter_snapshot_digest="d" * 64))
        self.assertIn("CHAPTER_SNAPSHOT_DIGEST_MISMATCH", result["errors"])

    def test_18_non_prepared_status_rejected(self) -> None:
        adapter_input = self._input()
        result = evaluate_committed_success(adapter_input, self._evidence(adapter_input, prepared_status="scheduled"))
        self.assertIn("JOB_STATUS_NOT_PREPARED", result["errors"])

    def test_19_worker_woken_result_rejected(self) -> None:
        adapter_input = self._input()
        result = evaluate_committed_success(adapter_input, self._evidence(adapter_input, worker_woken=True))
        self.assertIn("WORKER_WOKEN", result["errors"])

    def test_20_render_started_result_rejected(self) -> None:
        adapter_input = self._input()
        result = evaluate_committed_success(adapter_input, self._evidence(adapter_input, render_started=True))
        self.assertIn("RENDER_STARTED", result["errors"])

    def test_21_partial_chapter_result_rejected(self) -> None:
        adapter_input = self._input()
        result = evaluate_committed_success(adapter_input, self._evidence(adapter_input, job_chapters=()))
        self.assertIn("JOB_CHAPTER_EVIDENCE_INCOMPLETE", result["errors"])

    def test_22_duplicate_job_chapter_reference_rejected(self) -> None:
        adapter_input = self._input()
        chapters = (
            JobChapterEvidence(110, 10, "dup"),
            JobChapterEvidence(111, 11, "dup"),
            JobChapterEvidence(112, 12, "ok"),
        )
        result = evaluate_committed_success(adapter_input, self._evidence(adapter_input, job_chapters=chapters))
        self.assertIn("DUPLICATE_JOB_CHAPTER_REFERENCE", result["errors"])

    def test_23_existing_committed_same_linkage_replays(self) -> None:
        adapter_input = self._input()
        result = evaluate_duplicate_invocation(adapter_input, self._evidence(adapter_input))
        self.assertEqual(result["duplicate_action"], DUPLICATE_REPLAY_COMMITTED_RESULT)

    def test_24_existing_linkage_wrong_request_conflicts(self) -> None:
        adapter_input = self._input()
        result = evaluate_duplicate_invocation(adapter_input, self._evidence(adapter_input, request_identity="c" * 64))
        self.assertEqual(result["code"], LINKAGE_CONFLICT)

    def test_25_existing_linkage_wrong_snapshot_conflicts(self) -> None:
        adapter_input = self._input()
        result = evaluate_duplicate_invocation(adapter_input, self._evidence(adapter_input, chapter_snapshot_digest="d" * 64))
        self.assertEqual(result["code"], LINKAGE_CONFLICT)

    def test_26_job_reference_without_commit_evidence_is_ambiguous(self) -> None:
        adapter_input = self._input()
        result = evaluate_duplicate_invocation(adapter_input, self._evidence(adapter_input, committed=False))
        self.assertEqual(result["code"], TRANSACTION_OUTCOME_AMBIGUOUS)

    def test_27_no_linkage_evidence_does_not_claim_safe_retry(self) -> None:
        result = evaluate_duplicate_invocation(self._input(), None)
        self.assertEqual(result["duplicate_action"], DUPLICATE_NO_SAFE_RETRY)
        self.assertFalse(result["second_job_allowed"])

    def test_28_multiple_matching_jobs_operator_review(self) -> None:
        result = evaluate_duplicate_invocation(self._input(), ExternalJobEvidence(EVIDENCE_MULTIPLE_MATCHING_JOBS, job_count=2))
        self.assertEqual(result["decision"], RECONCILE_OPERATOR_REVIEW_REQUIRED)

    def test_29_legacy_unlinked_job_operator_review(self) -> None:
        result = evaluate_duplicate_invocation(self._input(), ExternalJobEvidence(EVIDENCE_LEGACY_UNLINKED_JOB, job_count=1))
        self.assertEqual(result["decision"], RECONCILE_OPERATOR_REVIEW_REQUIRED)

    def test_30_duplicate_call_never_claims_second_job_safe(self) -> None:
        for evidence in (None, self._evidence(self._input()), ExternalJobEvidence(EVIDENCE_UNKNOWN)):
            with self.subTest(evidence=evidence):
                self.assertFalse(evaluate_duplicate_invocation(self._input(), evidence)["second_job_allowed"])

    def test_31_existing_prepared_conflict_mapping(self) -> None:
        self.assertEqual(map_existing_job_conflict(ExternalJobEvidence(EVIDENCE_PREPARED_JOB_COMMITTED))["code"], EXISTING_PREPARED_JOB)

    def test_32_existing_active_conflict_mapping(self) -> None:
        self.assertEqual(map_existing_job_conflict(ExternalJobEvidence(EVIDENCE_ACTIVE_JOB_FOUND))["code"], EXISTING_ACTIVE_JOB)

    def test_33_rollback_confirmed_result(self) -> None:
        result = failure_before_commit()
        self.assertEqual(result["code"], TRANSACTION_FAILED_ROLLED_BACK)
        self.assertFalse(result["job_durable"])

    def test_34_ambiguous_outcome_result(self) -> None:
        result = ambiguous_after_commit_response()
        self.assertEqual(result["code"], TRANSACTION_OUTCOME_AMBIGUOUS)

    def test_35_commit_confirmed_request_result_missing(self) -> None:
        result = commit_confirmed_request_result_missing()
        self.assertEqual(result["code"], RESULT_PERSISTENCE_REQUIRED)

    def test_36_corrupt_partial_job_evidence(self) -> None:
        result = classify_reconciliation_evidence(self._input(), ExternalJobEvidence(EVIDENCE_JOB_PARTIAL_OR_CORRUPT))
        self.assertEqual(result["decision"], RECONCILE_CORRUPT_TRANSACTION_STATE)

    def test_37_public_errors_contain_no_raw_exception(self) -> None:
        result = failure_before_commit()
        text = repr(result).lower()
        self.assertNotIn("traceback", text)
        self.assertNotIn("sqlite", text)

    def test_38_unknown_evidence_fails_closed(self) -> None:
        result = classify_reconciliation_evidence(self._input(), ExternalJobEvidence(EVIDENCE_UNKNOWN))
        self.assertEqual(result["decision"], RECONCILE_OPERATOR_REVIEW_REQUIRED)

    def test_39_no_transaction_evidence(self) -> None:
        result = classify_reconciliation_evidence(self._input(), ExternalJobEvidence(EVIDENCE_NONE))
        self.assertEqual(result["decision"], RECONCILE_SAFE_NO_COMMIT_CONFIRMED)

    def test_40_transaction_not_found_evidence(self) -> None:
        result = classify_reconciliation_evidence(self._input(), ExternalJobEvidence(EVIDENCE_TRANSACTION_NOT_FOUND))
        self.assertEqual(result["code"], TRANSACTION_FAILED_ROLLED_BACK)

    def test_41_prepared_committed_job_recovery(self) -> None:
        adapter_input = self._input()
        result = classify_reconciliation_evidence(adapter_input, self._matching_external(adapter_input))
        self.assertEqual(result["decision"], RECONCILE_RECOVER_COMMITTED_RESULT)

    def test_42_active_job_found(self) -> None:
        result = classify_reconciliation_evidence(self._input(), ExternalJobEvidence(EVIDENCE_ACTIVE_JOB_FOUND))
        self.assertEqual(result["decision"], RECONCILE_REQUEST_JOB_CONFLICT)

    def test_43_completed_job_found(self) -> None:
        result = classify_reconciliation_evidence(self._input(), ExternalJobEvidence(EVIDENCE_COMPLETED_JOB_FOUND))
        self.assertEqual(result["decision"], RECONCILE_REQUEST_JOB_CONFLICT)

    def test_44_multiple_jobs_found(self) -> None:
        result = classify_reconciliation_evidence(self._input(), ExternalJobEvidence(EVIDENCE_MULTIPLE_MATCHING_JOBS))
        self.assertEqual(result["decision"], RECONCILE_OPERATOR_REVIEW_REQUIRED)

    def test_45_linkage_mismatch(self) -> None:
        result = classify_reconciliation_evidence(self._input(), ExternalJobEvidence(EVIDENCE_LINKAGE_MISMATCH))
        self.assertEqual(result["decision"], RECONCILE_REQUEST_JOB_CONFLICT)

    def test_46_deterministic_repeated_classification(self) -> None:
        adapter_input = self._input()
        evidence = ExternalJobEvidence(EVIDENCE_JOB_REFERENCE_WITHOUT_COMMIT)
        self.assertEqual(
            classify_reconciliation_evidence(adapter_input, evidence),
            classify_reconciliation_evidence(adapter_input, evidence),
        )

    def test_47_classifier_read_only_shape(self) -> None:
        result = classify_reconciliation_evidence(self._input(), ExternalJobEvidence(EVIDENCE_UNKNOWN))
        self.assertFalse(result["automatic_mutation"])
        self.assertFalse(result["retry_transaction"])

    def test_48_adapter_implementation_authorized_false(self) -> None:
        self.assertFalse(authorization_gates()["adapter_implementation_authorized"])

    def test_49_real_job_execution_false(self) -> None:
        self.assertFalse(authorization_gates()["real_job_execution"])

    def test_50_mutation_authorized_false(self) -> None:
        self.assertFalse(authorization_gates()["mutation_authorized"])

    def test_51_execution_endpoint_available_false(self) -> None:
        self.assertFalse(authorization_gates()["execution_endpoint_available"])

    def test_52_prepare_starts_render_false(self) -> None:
        self.assertFalse(authorization_gates()["prepare_starts_render"])

    def test_53_no_pipeline_import(self) -> None:
        source = self._module_source()
        self.assertNotIn("story_audio.pipeline", source)

    def test_54_no_existing_job_creation_helper_call(self) -> None:
        source = self._module_source()
        self.assertNotIn("prepare_job", source)
        self.assertNotIn("create_job", source)

    def test_55_no_db_connection(self) -> None:
        source = self._module_source()
        self.assertNotIn("Database", source)
        self.assertNotIn(".connect(", source)

    def test_56_no_migration_activation(self) -> None:
        source = self._module_source()
        self.assertNotIn("MigrationRunner", source)
        self.assertNotIn("initialize(", source)

    def test_57_no_api_route(self) -> None:
        source = self._module_source()
        self.assertNotIn("FastAPI", source)
        self.assertNotIn("@app.", source)

    def test_58_no_provider_or_tts(self) -> None:
        source = self._module_source().lower()
        self.assertNotIn("gemini", source)
        self.assertNotIn("tts", source)

    def test_59_no_chapter_369_hard_code(self) -> None:
        self.assertNotIn("369", self._module_source())

    def test_60_module_import_has_no_side_effects(self) -> None:
        module = importlib.import_module("story_audio.batch_prepare_job_adapter_contract")
        before = contract_metadata()
        importlib.reload(module)
        self.assertEqual(before, module.contract_metadata())

    def test_61_no_global_mutable_job_registry(self) -> None:
        module = importlib.import_module("story_audio.batch_prepare_job_adapter_contract")
        self.assertFalse(hasattr(module, "jobs"))
        self.assertFalse(hasattr(module, "job_chapters"))

    def test_62_historical_payload_safe_fields_only(self) -> None:
        adapter_input = self._input()
        payload = build_historical_result_payload(adapter_input, self._evidence(adapter_input))
        text = repr(payload).lower()
        for forbidden in ("full_text", "casting_snapshot_json", "voice_snapshot_json", "traceback", "wav", "m4a", ":\\"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(payload["chapter_count"], 3)
        self.assertFalse(payload["worker_woken"])
        self.assertFalse(payload["render_started"])

    def test_untrusted_input_source_rejected(self) -> None:
        result = validate_adapter_input(self._input(source="client_payload"))
        self.assertEqual(result["code"], ADAPTER_INPUT_INVALID)
        self.assertIn("UNTRUSTED_INPUT_SOURCE", result["errors"])

    def test_wrong_target_phase_rejected(self) -> None:
        result = validate_adapter_input(self._input(target_phase="START_RENDER"))
        self.assertEqual(result["code"], ADAPTER_INPUT_INVALID)
        self.assertIn("UNSUPPORTED_TARGET_PHASE", result["errors"])

    def test_invalid_range_rejected(self) -> None:
        result = validate_adapter_input(self._input(from_chapter=12, to_chapter=10))
        self.assertEqual(result["code"], ADAPTER_INPUT_INVALID)
        self.assertIn("INVALID_SCOPE", result["errors"])

    def test_missing_casting_plan_identity_rejected(self) -> None:
        result = validate_adapter_input(self._input(chapters=(self._chapter(10, casting_plan_id=0),)))
        self.assertIn("MISSING_REVISION_OR_PLAN_IDENTITY", result["errors"])

    def test_extra_chapter_evidence_rejected(self) -> None:
        adapter_input = self._input()
        chapters = tuple(self._evidence(adapter_input).job_chapters) + (
            JobChapterEvidence(chapter_id=999, chapter_number=99, job_chapter_reference="extra"),
        )
        result = evaluate_committed_success(
            adapter_input,
            self._evidence(adapter_input, actual_chapter_count=4, job_chapters=chapters),
        )
        self.assertIn("CHAPTER_COUNT_MISMATCH", result["errors"])
        self.assertIn("JOB_CHAPTER_EVIDENCE_INCOMPLETE", result["errors"])
        self.assertIn("JOB_CHAPTER_SNAPSHOT_MISMATCH", result["errors"])

    def test_unknown_evidence_version_rejected(self) -> None:
        adapter_input = self._input()
        result = evaluate_committed_success(
            adapter_input,
            self._evidence(adapter_input, transaction_evidence_version=999),
        )
        self.assertIn("UNSUPPORTED_TRANSACTION_EVIDENCE_VERSION", result["errors"])

    def test_no_misleading_job_created_true_claim(self) -> None:
        adapter_input = self._input()
        payloads = [
            validate_adapter_input(adapter_input),
            evaluate_committed_success(adapter_input, self._evidence(adapter_input)),
            build_historical_result_payload(adapter_input, self._evidence(adapter_input)),
            contract_metadata(),
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertNotEqual(payload.get("job_created"), True)
                self.assertNotIn("real_job_id", payload)
                self.assertNotIn("execution_authorized", payload)
                self.assertNotIn("production_committed", payload)

    def test_external_prepared_mismatch_is_linkage_conflict(self) -> None:
        adapter_input = self._input()
        result = classify_reconciliation_evidence(adapter_input, self._matching_external(adapter_input, plan_fingerprint="c" * 64))
        self.assertEqual(result["decision"], RECONCILE_REQUEST_JOB_CONFLICT)

    def test_map_partial_conflict_requires_transaction_evidence(self) -> None:
        result = map_existing_job_conflict(ExternalJobEvidence(EVIDENCE_JOB_PARTIAL_OR_CORRUPT))
        self.assertEqual(result["code"], TRANSACTION_EVIDENCE_MISSING)

    def test_map_unknown_conflict_fails_closed(self) -> None:
        result = map_existing_job_conflict(ExternalJobEvidence(EVIDENCE_UNKNOWN))
        self.assertEqual(result["code"], "EXISTING_JOB_CONFLICT")

    @staticmethod
    def _module_source() -> str:
        return Path("story_audio/batch_prepare_job_adapter_contract.py").read_text(encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
