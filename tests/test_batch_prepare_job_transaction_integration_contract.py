from __future__ import annotations

import importlib
import unittest
from pathlib import Path

from story_audio.batch_prepare_job_transaction_integration_contract import (
    BLOCKED_BY_AUTHORITATIVE_INPUT_REVALIDATION,
    BLOCKED_BY_CONFLICT_RACE,
    BLOCKED_BY_OWNERSHIP_EVIDENCE,
    BLOCKED_BY_TRANSACTION_ABSTRACTION,
    COMMITTED,
    CONFIRMED_ROLLBACK_NO_COMMIT,
    CORRUPT_COMMITTED_STATE,
    CORRUPT_STATE,
    DETERMINISTIC_CONFLICT,
    OPERATOR_REVIEW_REQUIRED,
    OUTCOME_AMBIGUOUS,
    RECOVER_COMMITTED_TRANSACTION,
    REPLAYED_COMMITTED,
    ROLLBACK_CONFIRMED,
    ROLLBACK_REQUIRED,
    TRANSACTION_OUTCOME_AMBIGUOUS,
    JobWriteSet,
    JobChapterBinding,
    LinkageCommitEvidence,
    RecoveryEvidence,
    RequestPreconditions,
    TransactionOperationPlan,
    TransactionScopedDependencies,
    authorization_flags,
    classify_duplicate_or_recovery,
    classify_interruption,
    contract_metadata,
    implementation_prerequisites,
    model_smoke_results,
    orchestrator_handoff,
    readiness_decision,
    validate_linkage_and_commit_evidence,
    validate_operation_plan,
    validate_preconditions,
    validate_transaction_scope,
    validate_write_set,
)


VALID_ORDER = (
    "RELOAD_REQUEST_IN_TRANSACTION",
    "RELOAD_AUTHORITATIVE_INPUTS_IN_TRANSACTION",
    "CHECK_EXISTING_LINKAGE",
    "CHECK_CONFLICTING_LINKAGE",
    "CHECK_JOB_CONFLICTS",
    "INSERT_PREPARED_JOB",
    "INSERT_JOB_CHAPTER",
    "INSERT_REQUEST_JOB_LINKAGE",
    "VALIDATE_COUNTS_AND_BINDINGS",
    "COMMIT_TRANSACTION",
    "RELOAD_COMMITTED_EVIDENCE",
    "MARK_ELIGIBLE_FOR_APPLIED_RECORD",
)


class BatchPrepareJobTransactionIntegrationContractTests(unittest.TestCase):
    def _plan(self, operations=VALID_ORDER, expected=3, chapters=(1, 2, 3), **overrides):
        values = {
            "operations": tuple(operations),
            "expected_chapter_count": expected,
            "job_chapter_operations": tuple(chapters),
        }
        values.update(overrides)
        return TransactionOperationPlan(**values)

    def _scope(self, **overrides):
        values = {
            "transaction_owner": "future_integration_service",
            "request_repository_scoped": True,
            "authoritative_inputs_scoped": True,
            "conflict_inspector_scoped": True,
            "job_writer_scoped": True,
            "link_writer_scoped": True,
            "evidence_reader_post_commit": True,
        }
        values.update(overrides)
        return TransactionScopedDependencies(**values)

    def _write_set(self, **overrides):
        values = {
            "job_insert_count": 1,
            "job_status": "prepared",
            "job_chapter_count": 3,
            "expected_chapter_count": 3,
            "chapter_bindings": (
                JobChapterBinding(1, 1, 101, 201),
                JobChapterBinding(2, 2, 102, 202),
                JobChapterBinding(3, 3, 103, 203),
            ),
        }
        values.update(overrides)
        return JobWriteSet(**values)

    def _evidence(self, **overrides):
        values = {
            "linkage_visible_after_commit": True,
            "request_identity_matches": True,
            "job_visible_after_commit": True,
            "job_status": "prepared",
            "job_chapter_count": 3,
            "expected_chapter_count": 3,
            "snapshot_digest_matches": True,
            "plan_fingerprint_matches": True,
            "worker_woken": False,
            "render_started": False,
        }
        values.update(overrides)
        return LinkageCommitEvidence(**values)

    def assert_invalid_contains(self, result, error):
        self.assertFalse(result["valid"])
        self.assertIn(error, result["errors"])

    def test_01_valid_future_operation_plan(self):
        self.assertTrue(validate_operation_plan(self._plan())["valid"])

    def test_02_request_reload_precedes_job_insert(self):
        ops = list(VALID_ORDER)
        ops.remove("RELOAD_REQUEST_IN_TRANSACTION")
        ops.insert(4, "RELOAD_REQUEST_IN_TRANSACTION")
        result = validate_operation_plan(self._plan(operations=tuple(ops)))
        self.assert_invalid_contains(
            result,
            "ORDER_RELOAD_REQUEST_IN_TRANSACTION_BEFORE_RELOAD_AUTHORITATIVE_INPUTS_IN_TRANSACTION",
        )

    def test_03_conflict_check_precedes_job_insert(self):
        ops = list(VALID_ORDER)
        ops.remove("CHECK_JOB_CONFLICTS")
        ops.insert(5, "CHECK_JOB_CONFLICTS")
        result = validate_operation_plan(self._plan(operations=tuple(ops)))
        self.assert_invalid_contains(result, "ORDER_CHECK_JOB_CONFLICTS_BEFORE_INSERT_PREPARED_JOB")

    def test_04_job_insert_precedes_job_chapter_inserts(self):
        ops = tuple(op for op in VALID_ORDER if op not in {"INSERT_PREPARED_JOB", "INSERT_JOB_CHAPTER"})
        result = validate_operation_plan(self._plan(operations=(*ops[:4], "INSERT_JOB_CHAPTER", "INSERT_PREPARED_JOB", *ops[4:])))
        self.assert_invalid_contains(result, "ORDER_INSERT_PREPARED_JOB_BEFORE_INSERT_JOB_CHAPTER")

    def test_05_all_job_chapters_precede_linkage(self):
        ops = tuple(op for op in VALID_ORDER if op not in {"INSERT_JOB_CHAPTER", "INSERT_REQUEST_JOB_LINKAGE"})
        result = validate_operation_plan(self._plan(operations=(*ops[:5], "INSERT_REQUEST_JOB_LINKAGE", "INSERT_JOB_CHAPTER", *ops[5:])))
        self.assert_invalid_contains(result, "ORDER_INSERT_JOB_CHAPTER_BEFORE_INSERT_REQUEST_JOB_LINKAGE")

    def test_06_linkage_precedes_commit(self):
        ops = list(VALID_ORDER)
        ops.remove("INSERT_REQUEST_JOB_LINKAGE")
        ops.insert(8, "INSERT_REQUEST_JOB_LINKAGE")
        result = validate_operation_plan(self._plan(operations=tuple(ops)))
        self.assert_invalid_contains(result, "ORDER_INSERT_REQUEST_JOB_LINKAGE_BEFORE_VALIDATE_COUNTS_AND_BINDINGS")

    def test_07_commit_precedes_durable_evidence_reload(self):
        ops = tuple(op for op in VALID_ORDER if op not in {"COMMIT_TRANSACTION", "RELOAD_COMMITTED_EVIDENCE"})
        result = validate_operation_plan(self._plan(operations=(*ops[:8], "RELOAD_COMMITTED_EVIDENCE", "COMMIT_TRANSACTION", *ops[8:])))
        self.assert_invalid_contains(result, "ORDER_COMMIT_TRANSACTION_BEFORE_RELOAD_COMMITTED_EVIDENCE")

    def test_08_durable_evidence_precedes_applied_eligibility(self):
        ops = list(VALID_ORDER)
        evidence_index = ops.index("RELOAD_COMMITTED_EVIDENCE")
        applied_index = ops.index("MARK_ELIGIBLE_FOR_APPLIED_RECORD")
        ops[evidence_index], ops[applied_index] = ops[applied_index], ops[evidence_index]
        result = validate_operation_plan(self._plan(operations=tuple(ops)))
        self.assert_invalid_contains(result, "ORDER_RELOAD_COMMITTED_EVIDENCE_BEFORE_MARK_ELIGIBLE_FOR_APPLIED_RECORD")

    def test_09_invalid_reordered_plan_rejected(self):
        self.assertFalse(validate_operation_plan(self._plan(operations=tuple(reversed(VALID_ORDER))))["valid"])

    def test_10_applied_persistence_not_part_of_job_transaction(self):
        result = validate_operation_plan(self._plan(applied_persistence_inside_job_transaction=True))
        self.assert_invalid_contains(result, "APPLIED_PERSISTENCE_MUST_REMAIN_ORCHESTRATOR_TERMINAL_STEP")

    def test_11_missing_request_rejected(self):
        self.assert_invalid_contains(validate_preconditions(RequestPreconditions(request_exists=False)), "REQUEST_MISSING")

    def test_12_identity_mismatch_rejected(self):
        self.assert_invalid_contains(validate_preconditions(RequestPreconditions(identity_matches=False)), "REQUEST_IDENTITY_MISMATCH")

    def test_13_wrong_phase_rejected(self):
        self.assert_invalid_contains(validate_preconditions(RequestPreconditions(target_phase="START_RENDER")), "REQUEST_PHASE_NOT_PREPARE")

    def test_14_non_applying_state_rejected(self):
        self.assert_invalid_contains(validate_preconditions(RequestPreconditions(state="PLANNED")), "REQUEST_STATE_NOT_APPLYING")

    def test_15_fingerprint_mismatch_rejected(self):
        self.assert_invalid_contains(validate_preconditions(RequestPreconditions(fingerprint_matches=False)), "PLAN_FINGERPRINT_MISMATCH")

    def test_16_ownership_attempt_mismatch_rejected(self):
        self.assert_invalid_contains(validate_preconditions(RequestPreconditions(ownership_attempt_matches=False)), "OWNERSHIP_ATTEMPT_MISMATCH")

    def test_17_existing_request_link_conflict_rejected(self):
        self.assert_invalid_contains(validate_preconditions(RequestPreconditions(existing_request_link_conflict=True)), "EXISTING_REQUEST_LINK_CONFLICT")

    def test_18_existing_job_link_conflict_rejected(self):
        self.assert_invalid_contains(validate_preconditions(RequestPreconditions(existing_job_link_conflict=True)), "EXISTING_JOB_LINK_CONFLICT")

    def test_19_exactly_one_transaction_owner(self):
        self.assertTrue(validate_transaction_scope(self._scope())["valid"])

    def test_20_nested_autonomous_commit_rejected(self):
        self.assert_invalid_contains(validate_transaction_scope(self._scope(nested_autonomous_commit=True)), "NESTED_AUTONOMOUS_COMMIT_REJECTED")

    def test_21_job_writer_must_be_transaction_scoped(self):
        self.assert_invalid_contains(validate_transaction_scope(self._scope(job_writer_scoped=False)), "JOB_WRITER_MUST_USE_CALLER_TRANSACTION")

    def test_22_link_writer_must_be_transaction_scoped(self):
        self.assert_invalid_contains(validate_transaction_scope(self._scope(link_writer_scoped=False)), "LINK_WRITER_MUST_USE_CALLER_TRANSACTION")

    def test_23_repository_self_commit_rejected(self):
        self.assert_invalid_contains(validate_transaction_scope(self._scope(self_committing_repository=True)), "REPOSITORY_SELF_COMMIT_REJECTED")

    def test_24_connection_mismatch_rejected(self):
        self.assert_invalid_contains(validate_transaction_scope(self._scope(connection_mismatch=True)), "TRANSACTION_CONNECTION_MISMATCH")

    def test_25_one_job_only(self):
        self.assert_invalid_contains(validate_write_set(self._write_set(job_insert_count=2)), "EXACTLY_ONE_JOB_INSERT_REQUIRED")

    def test_26_exact_n_job_chapter_operations(self):
        self.assert_invalid_contains(validate_write_set(self._write_set(job_chapter_count=2)), "JOB_CHAPTER_COUNT_MISMATCH")

    def test_27_duplicate_chapter_rejected(self):
        self.assert_invalid_contains(validate_write_set(self._write_set(duplicate_chapters=True)), "DUPLICATE_CHAPTER_BINDING")

    def test_28_excluded_chapter_rejected(self):
        self.assert_invalid_contains(validate_write_set(self._write_set(excluded_chapter_written=True)), "EXCLUDED_CHAPTER_WRITTEN")

    def test_29_prepared_status_required(self):
        self.assert_invalid_contains(validate_write_set(self._write_set(job_status="scheduled")), "JOB_STATUS_MUST_BE_PREPARED")

    def test_30_worker_wake_rejected(self):
        self.assert_invalid_contains(validate_write_set(self._write_set(worker_wake=True)), "WORKER_WAKE_FORBIDDEN")

    def test_31_render_start_rejected(self):
        self.assert_invalid_contains(validate_write_set(self._write_set(render_start=True)), "RENDER_START_FORBIDDEN")

    def test_32_segment_artifact_audio_operations_rejected(self):
        result = validate_write_set(self._write_set(segment_write=True, artifact_write=True, audio_write=True))
        self.assert_invalid_contains(result, "SEGMENT_WRITE_FORBIDDEN")
        self.assertIn("ARTIFACT_WRITE_FORBIDDEN", result["errors"])
        self.assertIn("AUDIO_WRITE_FORBIDDEN", result["errors"])

    def test_33_same_transaction_linkage_required(self):
        self.assert_invalid_contains(validate_linkage_and_commit_evidence(self._evidence(linkage_visible_after_commit=False)), "COMMITTED_LINKAGE_NOT_VISIBLE")

    def test_34_missing_linkage_rejects_success(self):
        self.assertFalse(validate_linkage_and_commit_evidence(self._evidence(linkage_visible_after_commit=False))["valid"])

    def test_35_wrong_request_linkage(self):
        self.assert_invalid_contains(validate_linkage_and_commit_evidence(self._evidence(request_identity_matches=False)), "REQUEST_IDENTITY_MISMATCH")

    def test_36_wrong_job_linkage(self):
        self.assert_invalid_contains(validate_linkage_and_commit_evidence(self._evidence(job_visible_after_commit=False)), "COMMITTED_JOB_NOT_VISIBLE")

    def test_37_wrong_fingerprint(self):
        self.assert_invalid_contains(validate_linkage_and_commit_evidence(self._evidence(plan_fingerprint_matches=False)), "PLAN_FINGERPRINT_MISMATCH")

    def test_38_wrong_digest(self):
        self.assert_invalid_contains(validate_linkage_and_commit_evidence(self._evidence(snapshot_digest_matches=False)), "SNAPSHOT_DIGEST_MISMATCH")

    def test_39_count_mismatch(self):
        self.assert_invalid_contains(validate_linkage_and_commit_evidence(self._evidence(job_chapter_count=2)), "JOB_CHAPTER_COUNT_MISMATCH")

    def test_40_unsupported_evidence_version(self):
        self.assert_invalid_contains(validate_linkage_and_commit_evidence(self._evidence(evidence_version=2)), "UNSUPPORTED_EVIDENCE_VERSION")

    def test_41_pre_commit_job_id_not_success(self):
        self.assert_invalid_contains(validate_linkage_and_commit_evidence(self._evidence(pre_commit_job_reference_only=True)), "PRE_COMMIT_JOB_REFERENCE_IS_NOT_SUCCESS")

    def test_42_durable_post_commit_reload_required(self):
        self.assertTrue(validate_linkage_and_commit_evidence(self._evidence())["valid"])

    def test_43_timestamp_alone_not_commit_proof(self):
        self.assert_invalid_contains(validate_linkage_and_commit_evidence(self._evidence(timestamp_is_sole_commit_proof=True)), "TIMESTAMP_ALONE_IS_NOT_COMMIT_PROOF")

    def test_44_exact_existing_linkage_recovers(self):
        result = classify_duplicate_or_recovery(RecoveryEvidence(1, True, True, True, True, True, True))
        self.assertEqual(result["decision"], RECOVER_COMMITTED_TRANSACTION)

    def test_45_conflicting_linkage_fails(self):
        result = classify_duplicate_or_recovery(RecoveryEvidence(1, linkage_matches=False, job_visible=True))
        self.assertEqual(result["decision"], "REQUEST_JOB_CONFLICT")

    def test_46_no_linkage_confirmed_rollback(self):
        result = classify_duplicate_or_recovery(RecoveryEvidence(0, absence_reliable=True))
        self.assertEqual(result["decision"], CONFIRMED_ROLLBACK_NO_COMMIT)

    def test_47_no_linkage_unknown_outcome_ambiguous(self):
        result = classify_duplicate_or_recovery(RecoveryEvidence(0, unknown_outcome=True))
        self.assertEqual(result["decision"], TRANSACTION_OUTCOME_AMBIGUOUS)

    def test_48_corrupt_job_linkage_state(self):
        result = classify_duplicate_or_recovery(RecoveryEvidence(1, corrupt_state=True))
        self.assertEqual(result["decision"], CORRUPT_COMMITTED_STATE)

    def test_49_multiple_jobs_without_linkage_review(self):
        result = classify_duplicate_or_recovery(RecoveryEvidence(0, multiple_unlinked_jobs=True))
        self.assertEqual(result["decision"], OPERATOR_REVIEW_REQUIRED)

    def test_50_never_choose_newest_job(self):
        result = classify_duplicate_or_recovery(RecoveryEvidence(0, multiple_unlinked_jobs=True))
        self.assertFalse(result["automatic_rerun"])
        self.assertIsNone(result["future_job_reference"])

    def test_51_recovery_does_not_insert_job(self):
        self.assertFalse(classify_duplicate_or_recovery(RecoveryEvidence(0, unknown_outcome=True))["mutation_authorized"])

    def test_52_before_begin_safe(self):
        self.assertEqual(classify_interruption("before_begin")["safe_result"], ROLLBACK_CONFIRMED)

    def test_53_after_job_insert_requires_rollback_evidence(self):
        self.assertEqual(classify_interruption("after_job_insert")["safe_result"], ROLLBACK_REQUIRED)

    def test_54_partial_jobchapter_rollback_requires_evidence(self):
        self.assertEqual(classify_interruption("after_partial_job_chapters")["safe_result"], ROLLBACK_REQUIRED)

    def test_55_observed_rollback_allows_confirmed_result(self):
        result = classify_interruption("after_linkage_insert", rollback_observed=True)
        self.assertEqual(result["safe_result"], ROLLBACK_CONFIRMED)
        self.assertTrue(result["rerun_allowed"])

    def test_56_commit_response_lost_recovery(self):
        without_evidence = classify_interruption("commit_succeeded_response_lost")
        with_evidence = classify_interruption("commit_succeeded_response_lost", post_commit_evidence_valid=True)
        self.assertEqual(without_evidence["safe_result"], OUTCOME_AMBIGUOUS)
        self.assertEqual(with_evidence["safe_result"], REPLAYED_COMMITTED)

    def test_57_commit_evidence_reload_failure_ambiguous(self):
        self.assertEqual(classify_interruption("commit_evidence_reload_failed")["safe_result"], OUTCOME_AMBIGUOUS)

    def test_58_applied_persistence_failure_does_not_rerun(self):
        result = classify_interruption("applied_persistence_failed")
        self.assertFalse(result["rerun_allowed"])
        self.assertFalse(result["automatic_rerun"])

    def test_59_committed_allows_future_applied_recording(self):
        evidence = validate_linkage_and_commit_evidence(self._evidence())
        self.assertTrue(orchestrator_handoff(evidence)["eligible_for_applied_record"])

    def test_60_replayed_committed_allows_recovery(self):
        recovery = classify_duplicate_or_recovery(RecoveryEvidence(1, True, True, True, True, True, True))
        self.assertTrue(orchestrator_handoff(recovery)["eligible_for_applied_record"])

    def test_61_deterministic_conflict_does_not_allow_applied(self):
        conflict = classify_duplicate_or_recovery(RecoveryEvidence(1, linkage_matches=False, job_visible=True))
        self.assertFalse(orchestrator_handoff(conflict)["eligible_for_applied_record"])

    def test_62_rollback_confirmed_does_not_allow_applied(self):
        rollback = classify_duplicate_or_recovery(RecoveryEvidence(0, absence_reliable=True))
        self.assertFalse(orchestrator_handoff(rollback)["eligible_for_applied_record"])

    def test_63_ambiguous_outcome_requires_review(self):
        ambiguous = classify_duplicate_or_recovery(RecoveryEvidence(0, unknown_outcome=True))
        self.assertTrue(orchestrator_handoff(ambiguous)["requires_operator_review"])

    def test_64_corrupt_state_fails_closed(self):
        corrupt = classify_duplicate_or_recovery(RecoveryEvidence(1, corrupt_state=True))
        self.assertTrue(orchestrator_handoff(corrupt)["requires_operator_review"])

    def test_65_integration_implementation_authorized_false(self):
        self.assertFalse(authorization_flags()["integration_implementation_authorized"])

    def test_66_pipeline_modification_authorized_false(self):
        self.assertFalse(authorization_flags()["pipeline_modification_authorized"])

    def test_67_real_job_execution_false(self):
        self.assertFalse(authorization_flags()["real_job_execution"])

    def test_68_mutation_authorized_false(self):
        self.assertFalse(authorization_flags()["mutation_authorized"])

    def test_69_execution_endpoint_available_false(self):
        self.assertFalse(authorization_flags()["execution_endpoint_available"])

    def test_70_prepare_starts_render_false(self):
        self.assertFalse(authorization_flags()["prepare_starts_render"])

    def test_71_no_pipeline_import(self):
        self.assertNotIn("story_audio.pipeline", self._source())

    def test_72_no_db_connection(self):
        source = self._source()
        self.assertNotIn("sqlite3", source)
        self.assertNotIn(".connect(", source)
        self.assertNotIn("db.", source)

    def test_73_no_job_or_jobchapter_write(self):
        source = self._source()
        self.assertNotIn("INSERT INTO jobs", source)
        self.assertNotIn("INSERT INTO job_chapters", source)

    def test_74_no_linkage_mutation(self):
        source = self._source()
        self.assertNotIn("batch_prepare_job_links", source)
        self.assertNotIn(".execute(", source)

    def test_75_no_api_route(self):
        source = self._source()
        self.assertNotIn("FastAPI", source)
        self.assertNotIn("@app.", source)

    def test_76_no_migration_activation(self):
        source = self._source()
        self.assertNotIn("MigrationRunner", source)
        self.assertNotIn("initialize(", source)

    def test_77_no_provider_gemini_tts(self):
        source = self._source().lower()
        self.assertNotIn("gemini", source)
        self.assertNotIn("tts", source)

    def test_78_no_chapter_369_hard_code(self):
        self.assertNotIn("36" + "9", self._source())

    def test_79_import_no_side_effects(self):
        before = contract_metadata()
        module = importlib.import_module("story_audio.batch_prepare_job_transaction_integration_contract")
        importlib.reload(module)
        self.assertEqual(before, module.contract_metadata())

    def test_80_no_global_mutable_transaction_registry(self):
        module = importlib.import_module("story_audio.batch_prepare_job_transaction_integration_contract")
        self.assertFalse(hasattr(module, "transactions"))
        self.assertFalse(hasattr(module, "jobs"))
        self.assertFalse(hasattr(module, "registry"))

    def test_81_readiness_reports_expected_blockers(self):
        result = readiness_decision()
        self.assertIn(BLOCKED_BY_TRANSACTION_ABSTRACTION, result["blocker_codes"])
        self.assertIn(BLOCKED_BY_OWNERSHIP_EVIDENCE, result["blocker_codes"])
        self.assertIn(BLOCKED_BY_CONFLICT_RACE, result["blocker_codes"])
        self.assertIn(BLOCKED_BY_AUTHORITATIVE_INPUT_REVALIDATION, result["blocker_codes"])

    def test_82_readiness_cannot_be_overridden_by_caller_supplied_gates(self):
        self.assertEqual(readiness_decision()["overall_decision"], "IMPLEMENTATION_NOT_READY")
        self.assertFalse(readiness_decision()["integration_implementation_authorized"])

    def test_83_model_smoke(self):
        smoke = model_smoke_results()
        self.assertTrue(smoke["valid_transaction_plan"])
        self.assertTrue(smoke["wrong_operation_order_rejected"])
        self.assertTrue(smoke["pre_commit_response_rejected"])
        self.assertEqual(smoke["commit_response_lost"], RECOVER_COMMITTED_TRANSACTION)
        self.assertEqual(smoke["unknown_commit_outcome"], TRANSACTION_OUTCOME_AMBIGUOUS)
        self.assertFalse(smoke["applied_persistence_failure"])
        self.assertFalse(smoke["real_db_writes"])

    def test_84_unknown_and_duplicate_operations_are_rejected(self):
        duplicate = validate_operation_plan(self._plan(operations=(*VALID_ORDER, "COMMIT_TRANSACTION")))
        unknown = validate_operation_plan(self._plan(operations=(*VALID_ORDER, "UNBOUNDED_SIDE_EFFECT")))
        self.assert_invalid_contains(duplicate, "DUPLICATE_COMMIT_TRANSACTION")
        self.assert_invalid_contains(unknown, "UNKNOWN_OPERATION_UNBOUNDED_SIDE_EFFECT")

    def test_85_durable_ownership_fencing_is_required(self):
        self.assert_invalid_contains(
            validate_preconditions(RequestPreconditions(ownership_token_present=False)),
            "OWNERSHIP_TOKEN_REQUIRED",
        )
        self.assert_invalid_contains(
            validate_preconditions(RequestPreconditions(ownership_generation_matches=False)),
            "OWNERSHIP_GENERATION_MISMATCH",
        )
        self.assert_invalid_contains(
            validate_preconditions(RequestPreconditions(ownership_lease_active=False)),
            "OWNERSHIP_LEASE_EXPIRED",
        )

    def test_86_authoritative_inputs_are_revalidated_in_transaction(self):
        self.assert_invalid_contains(
            validate_transaction_scope(self._scope(authoritative_inputs_scoped=False)),
            "AUTHORITATIVE_INPUTS_MUST_USE_CALLER_TRANSACTION",
        )
        self.assert_invalid_contains(
            validate_preconditions(RequestPreconditions(active_text_revisions_match=False)),
            "ACTIVE_TEXT_REVISION_MISMATCH",
        )
        self.assert_invalid_contains(
            validate_preconditions(RequestPreconditions(approved_casting_plans_match=False)),
            "APPROVED_CASTING_PLAN_MISMATCH",
        )

    def test_87_jobchapter_bindings_require_exact_immutable_pins_and_status(self):
        invalid = self._write_set(
            chapter_bindings=(
                JobChapterBinding(1, 1, 0, 201),
                JobChapterBinding(2, 2, 102, 0),
                JobChapterBinding(3, 3, 103, 203, status="scheduled"),
            )
        )
        result = validate_write_set(invalid)
        self.assert_invalid_contains(result, "TEXT_REVISION_PIN_REQUIRED")
        self.assertIn("CASTING_PLAN_PIN_REQUIRED", result["errors"])
        self.assertIn("JOB_CHAPTER_STATUS_MUST_BE_PENDING", result["errors"])

    def test_88_transaction_reference_must_match_all_commit_evidence(self):
        result = validate_linkage_and_commit_evidence(
            self._evidence(post_commit_transaction_reference="transaction-2")
        )
        self.assert_invalid_contains(result, "TRANSACTION_REFERENCE_MISMATCH")

    def test_89_raw_status_string_cannot_authorize_applied_handoff(self):
        result = orchestrator_handoff({"transaction_decision": COMMITTED})
        self.assertFalse(result["eligible_for_applied_record"])
        self.assertTrue(result["requires_operator_review"])

    def test_90_post_commit_audit_failure_is_not_rollback(self):
        result = validate_linkage_and_commit_evidence(
            self._evidence(audit_failure_misreported_as_rollback=True)
        )
        self.assert_invalid_contains(result, "POST_COMMIT_AUDIT_FAILURE_IS_NOT_ROLLBACK")

    @staticmethod
    def _source() -> str:
        return Path("story_audio/batch_prepare_job_transaction_integration_contract.py").read_text(encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
