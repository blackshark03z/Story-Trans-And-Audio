from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from story_audio.batch_prepare_runtime_rollout_contract import (
    AUDIT_EVENTS,
    AUTH_MISSING_BLOCKS_PRODUCTION,
    AUTH_PRESENT_AND_REUSABLE,
    LOCAL_ONLY_TEMPORARY_CONTROL,
    OPERATOR_AUTH_DESIGN_REQUIRED,
    AuthorizationEvidence,
    BackupEvidence,
    CanonicalActivationPreflight,
    MigrationPostflight,
    RuntimeFeatureFlags,
    authorization_flags,
    build_prepare_api_response,
    classify_authentication,
    classify_migration_stage_failure,
    classify_prepare_status,
    classify_restore_trigger,
    contract_metadata,
    evaluate_feature_gate,
    evaluate_kill_switch,
    evaluate_maintenance_transition,
    evaluate_restore_outcome,
    evaluate_rollout_transition,
    evaluate_start_render_boundary,
    http_status_for_prepare,
    parse_feature_flags,
    production_readiness,
    redact_for_public,
    runtime_dependency_graph,
    validate_activation_preflight,
    validate_audit_event,
    validate_backup_evidence,
    validate_migration_postflight,
    validate_operator_confirmation,
    validate_prepare_api_request,
    validate_public_payload,
)


HEX = "a" * 64


def valid_preflight() -> CanonicalActivationPreflight:
    return CanonicalActivationPreflight(
        canonical_path_verified=True,
        process_inventory_recorded=True,
        mutation_processes_stopped=True,
        maintenance_state="ACTIVE",
        schema_version=12,
        quick_check="ok",
        source_sha256=HEX,
        source_size=4_009_984,
        source_mtime="2026-07-20T05:31:47Z",
        wal_shm_policy="SQLITE_BACKUP_API",
        no_active_write_transaction=True,
        backup_verified=True,
        backup_sha256="b" * 64,
        backup_readable=True,
        free_space_sufficient=True,
        migration_hashes={13: "c" * 64, 14: "d" * 64, 15: "e" * 64},
        migration_chain=(13, 14, 15),
        rollback_artifact_verified=True,
        feature_flags_disabled=True,
        operator_approved=True,
        protected_baseline_verified=True,
        active_prepare_request_count=0,
        deployment_correlation_id="deploy-12345678",
        backup_evidence=valid_backup(),
        canonical_identity_ref="canonical-db-production",
        operator_identity_ref="operator-ref-1",
        reviewer_identity_ref="reviewer-ref-1",
    )


def valid_backup() -> BackupEvidence:
    return BackupEvidence(
        source_identity_verified=True,
        source_identity_ref="canonical-db-production",
        source_schema=12,
        source_sha256=HEX,
        source_size=4_009_984,
        source_mtime="2026-07-20T05:31:47Z",
        source_quick_check="ok",
        backup_identity_recorded=True,
        backup_identity_ref="activation-backup-20260723",
        backup_sha256="b" * 64,
        backup_size=4_009_984,
        backup_quick_check="ok",
        backup_matches_source_identity=True,
        backup_schema=12,
        atomic_snapshot_verified=True,
        created_timestamp="2026-07-23T00:00:00Z",
        operator_identity_ref="operator-ref-1",
        correlation_id="deploy-12345678",
        wal_shm_policy="SQLITE_BACKUP_API",
        retention_policy_ref="canonical-migration-backup-v1",
    )


def valid_postflight() -> MigrationPostflight:
    return MigrationPostflight(
        applied_chain=(13, 14, 15),
        final_schema=15,
        required_tables_verified=True,
        required_indexes_verified=True,
        foreign_keys_verified=True,
        legacy_counts_preserved=True,
        jobs_created=0,
        requests_created=0,
        feature_flags_disabled=True,
        quick_check="ok",
        runtime_startup_verified=True,
        protected_baseline_verified=True,
        migration_hashes_verified=True,
        verified_stage_chain=(13, 14, 15),
    )


def valid_request() -> dict:
    return {
        "client_request_id": "request-12345678",
        "book_id": 1,
        "from_chapter": 370,
        "to_chapter": 372,
        "target_phase": "PREPARE",
        "plan_fingerprint": HEX,
        "confirmation": True,
        "correlation_id": "operator-12345678",
    }


def valid_audit_fields() -> dict:
    return {
        "timestamp": "2026-07-23T00:00:00Z",
        "event_version": 1,
        "correlation_id": "operator-12345678",
        "result_code": "OK",
        "schema_version": 15,
        "client_request_id": "request-12345678",
        "operator_identity_ref": "operator-ref-1",
    }


class FeatureFlagTests(unittest.TestCase):
    def test_defaults_are_disabled_and_kill_switch_is_safe(self) -> None:
        flags, errors = parse_feature_flags()
        self.assertEqual(errors, ())
        self.assertFalse(flags.feature_available)
        self.assertFalse(flags.mutation_enabled)
        self.assertTrue(flags.kill_switch_active)

    def test_unknown_values_fail_closed(self) -> None:
        flags, errors = parse_feature_flags(
            {"PREPARE_MUTATION_ENABLED": "maybe", "PREPARE_KILL_SWITCH_ACTIVE": "maybe"}
        )
        self.assertFalse(flags.config_valid)
        self.assertFalse(flags.mutation_enabled)
        self.assertTrue(flags.kill_switch_active)
        self.assertEqual(len(errors), 2)
        flags, errors = parse_feature_flags({"UNREVIEWED_FLAG": True})
        self.assertFalse(flags.config_valid)
        self.assertTrue(flags.kill_switch_active)
        self.assertEqual(errors, ("UNKNOWN_FEATURE_FLAG_UNREVIEWED_FLAG",))

    def test_all_future_flags_require_schema_identity_and_auth(self) -> None:
        flags, errors = parse_feature_flags(
            {
                "PREPARE_FEATURE_AVAILABLE": True,
                "PREPARE_MUTATION_ENABLED": True,
                "PREPARE_CANONICAL_SCHEMA_READY": True,
                "PREPARE_OPERATOR_WINDOW_OPEN": True,
                "PREPARE_KILL_SWITCH_ACTIVE": False,
            }
        )
        self.assertFalse(errors)
        result = evaluate_feature_gate(
            flags, schema_version=15, runtime_identity_explicit=True, authentication_ready=True
        )
        self.assertTrue(result["future_mutation_gate_open"])
        self.assertFalse(result["current_mutation_authorized"])
        self.assertTrue(result["read_only_planning_available"])
        self.assertFalse(result["prepare_starts_render"])

    def test_each_missing_gate_blocks_future_construction(self) -> None:
        base = RuntimeFeatureFlags(True, True, True, True, False, False, True)
        cases = [
            (replace(base, feature_available=False), 15, True, True),
            (replace(base, mutation_enabled=False), 15, True, True),
            (replace(base, canonical_schema_ready=False), 15, True, True),
            (replace(base, operator_window_open=False), 15, True, True),
            (replace(base, kill_switch_active=True), 15, True, True),
            (base, 12, True, True),
            (base, 15, False, True),
            (base, 15, True, False),
        ]
        for flags, schema, identity, auth in cases:
            with self.subTest(flags=flags, schema=schema, identity=identity, auth=auth):
                result = evaluate_feature_gate(
                    flags,
                    schema_version=schema,
                    runtime_identity_explicit=identity,
                    authentication_ready=auth,
                )
                self.assertFalse(result["future_mutation_gate_open"])
                self.assertFalse(result["prepare_service_constructible"])
                self.assertTrue(result["read_only_planning_available"])

    def test_start_render_is_independent_and_never_implied(self) -> None:
        flags = RuntimeFeatureFlags(True, True, True, True, False, True, True)
        result = evaluate_feature_gate(
            flags, schema_version=15, runtime_identity_explicit=True, authentication_ready=True
        )
        self.assertTrue(result["start_render_flag_configured"])
        self.assertFalse(result["start_render_enabled"])
        self.assertFalse(result["prepare_starts_render"])


class MigrationDesignTests(unittest.TestCase):
    def test_complete_preflight_is_ready(self) -> None:
        self.assertTrue(validate_activation_preflight(valid_preflight())["valid"])

    def test_every_preflight_evidence_class_fails_closed(self) -> None:
        cases = {
            "canonical_path_verified": False,
            "process_inventory_recorded": False,
            "mutation_processes_stopped": False,
            "maintenance_state": "ENTERING",
            "schema_version": 13,
            "quick_check": "failed",
            "source_sha256": "bad",
            "source_size": 0,
            "source_mtime": "",
            "wal_shm_policy": "COPY_LIVE_FILES",
            "no_active_write_transaction": False,
            "backup_verified": False,
            "backup_sha256": "bad",
            "backup_readable": False,
            "free_space_sufficient": False,
            "migration_hashes": {13: HEX},
            "migration_chain": (13, 15),
            "rollback_artifact_verified": False,
            "feature_flags_disabled": False,
            "operator_approved": False,
            "protected_baseline_verified": False,
            "active_prepare_request_count": 1,
            "deployment_correlation_id": "bad",
            "backup_evidence": None,
            "canonical_identity_ref": "",
            "operator_identity_ref": "",
            "reviewer_identity_ref": "",
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                result = validate_activation_preflight(replace(valid_preflight(), **{field: value}))
                self.assertFalse(result["valid"])

    def test_backup_evidence_is_complete(self) -> None:
        self.assertTrue(validate_backup_evidence(valid_backup())["valid"])

    def test_backup_hash_size_quick_check_and_identity_are_required(self) -> None:
        cases = {
            "source_identity_verified": False,
            "source_identity_ref": r"D:\\private\\app.db",
            "source_sha256": "",
            "backup_sha256": "",
            "backup_identity_ref": "",
            "backup_size": 0,
            "backup_quick_check": "failed",
            "backup_matches_source_identity": False,
            "backup_schema": 13,
            "atomic_snapshot_verified": False,
            "operator_identity_ref": "",
            "retention_policy_ref": "",
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                self.assertFalse(validate_backup_evidence(replace(valid_backup(), **{field: value}))["valid"])

    def test_postflight_accepts_only_exact_chain_and_no_mutations(self) -> None:
        self.assertTrue(validate_migration_postflight(valid_postflight())["valid"])
        cases = {
            "applied_chain": (13, 15),
            "final_schema": 14,
            "required_tables_verified": False,
            "required_indexes_verified": False,
            "foreign_keys_verified": False,
            "legacy_counts_preserved": False,
            "jobs_created": 1,
            "requests_created": 1,
            "feature_flags_disabled": False,
            "quick_check": "failed",
            "runtime_startup_verified": False,
            "protected_baseline_verified": False,
            "migration_hashes_verified": False,
            "verified_stage_chain": (13, 14),
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                result = validate_migration_postflight(replace(valid_postflight(), **{field: value}))
                self.assertFalse(result["valid"])
                self.assertEqual(result["code"], "ROLLBACK_REQUIRED")

    def test_each_migration_stage_failure_requires_full_restore(self) -> None:
        for failed_target, observed_schema, partial in ((13, 12, False), (14, 13, True), (15, 14, True)):
            with self.subTest(failed_target=failed_target):
                result = classify_migration_stage_failure(
                    failed_target=failed_target, observed_schema=observed_schema
                )
                self.assertTrue(result["known_stage"])
                self.assertEqual(result["partial_schema_state"], partial)
                self.assertTrue(result["rollback_required"])
                self.assertEqual(result["restore_strategy"], "FULL_VERIFIED_DATABASE_RESTORE")
                self.assertEqual(result["maintenance_state"], "FAILED_LOCKED")
                self.assertFalse(result["runtime_restart_allowed"])
        unknown = classify_migration_stage_failure(failed_target=16, observed_schema=15)
        self.assertFalse(unknown["known_stage"])
        self.assertTrue(unknown["rollback_required"])

    def test_restore_uses_full_verified_file_not_sql_downgrade(self) -> None:
        for trigger in (
            "MIGRATION_FAILURE", "SCHEMA_MISMATCH", "QUICK_CHECK_FAILURE",
            "MISSING_SCHEMA_OBJECT", "RUNTIME_STARTUP_FAILURE", "DATA_COUNT_CHANGE",
            "PROTECTED_BASELINE_CHANGE", "POSTFLIGHT_FAILURE", "FEATURE_FLAG_MISBEHAVIOR",
            "UNKNOWN", "NEW_MIGRATION_FAILURE",
        ):
            with self.subTest(trigger=trigger):
                result = classify_restore_trigger(trigger)
                self.assertTrue(result["restore_required"])
                self.assertEqual(result["strategy"], "FULL_VERIFIED_DATABASE_RESTORE")
                self.assertFalse(result["sql_down_migration_allowed"])
        post = classify_restore_trigger("FEATURE_FLAG_MISBEHAVIOR", operational_phase="POST_ACTIVATION")
        self.assertFalse(post["restore_required"])
        self.assertEqual(post["strategy"], "KILL_SWITCH_PRESERVE_AND_RECONCILE")

    def test_restore_outcome_stays_locked_until_all_evidence_passes(self) -> None:
        valid = evaluate_restore_outcome(
            restore_completed=True,
            expected_hash_restored=True,
            schema_restored=True,
            quick_check="ok",
            feature_flags_disabled=True,
            failed_database_archived=True,
            atomic_replacement_verified=True,
            wal_shm_handled=True,
            incident_recorded=True,
            reviewer_approved=True,
            read_only_startup_verified=True,
        )
        self.assertTrue(valid["restore_verified"])
        self.assertEqual(valid["maintenance_state"], "EXIT_READY")
        self.assertFalse(valid["prepare_enabled"])
        cases = [
            {"restore_completed": False},
            {"expected_hash_restored": False},
            {"schema_restored": False},
            {"quick_check": "failed"},
            {"feature_flags_disabled": False},
            {"failed_database_archived": False},
            {"atomic_replacement_verified": False},
            {"wal_shm_handled": False},
            {"incident_recorded": False},
            {"reviewer_approved": False},
            {"read_only_startup_verified": False},
        ]
        base = dict(
            restore_completed=True,
            expected_hash_restored=True,
            schema_restored=True,
            quick_check="ok",
            feature_flags_disabled=True,
            failed_database_archived=True,
            atomic_replacement_verified=True,
            wal_shm_handled=True,
            incident_recorded=True,
            reviewer_approved=True,
            read_only_startup_verified=True,
        )
        for mutation in cases:
            with self.subTest(mutation=mutation):
                result = evaluate_restore_outcome(**{**base, **mutation})
                self.assertFalse(result["restore_verified"])
                self.assertEqual(result["maintenance_state"], "FAILED_LOCKED")

    def test_maintenance_state_machine_fails_closed(self) -> None:
        self.assertTrue(evaluate_maintenance_transition("ENTERING", "ACTIVE")["allowed"])
        self.assertTrue(evaluate_maintenance_transition("ACTIVE", "MIGRATING")["allowed"])
        self.assertFalse(evaluate_maintenance_transition("VERIFYING", "EXIT_READY")["allowed"])
        self.assertTrue(
            evaluate_maintenance_transition("VERIFYING", "EXIT_READY", postflight_verified=True)["allowed"]
        )
        self.assertTrue(evaluate_maintenance_transition("VERIFYING", "EXIT_READY", restore_verified=True)["allowed"])
        self.assertFalse(evaluate_maintenance_transition("EXIT_READY", "EXITED")["allowed"])
        self.assertTrue(evaluate_maintenance_transition("EXIT_READY", "EXITED", reviewer_approved=True)["allowed"])
        self.assertEqual(evaluate_maintenance_transition("MYSTERY", "EXITED")["state"], "FAILED_LOCKED")


class ApiContractTests(unittest.TestCase):
    def test_valid_prepare_request(self) -> None:
        result = validate_prepare_api_request(valid_request(), request_bytes=500)
        self.assertTrue(result["valid"])
        self.assertTrue(result["server_recomputes_plan"])
        self.assertFalse(result["client_eligibility_is_authoritative"])
        self.assertFalse(result["api_mutation_route_authorized"])

    def test_invalid_request_fields_fail_closed(self) -> None:
        mutations = [
            {"client_request_id": "bad"},
            {"book_id": True},
            {"from_chapter": 0},
            {"to_chapter": 0},
            {"from_chapter": 3, "to_chapter": 2},
            {"from_chapter": 1, "to_chapter": 300},
            {"target_phase": "START_RENDER"},
            {"plan_fingerprint": "bad"},
            {"confirmation": False},
            {"confirmation": "true"},
            {"correlation_id": "bad"},
        ]
        for mutation in mutations:
            payload = {**valid_request(), **mutation}
            with self.subTest(mutation=mutation):
                self.assertFalse(validate_prepare_api_request(payload, request_bytes=500)["valid"])

    def test_client_authority_execution_and_secret_fields_are_rejected(self) -> None:
        for field in (
            "included_chapters", "excluded_chapters", "job_id", "job_status",
            "owner_token", "execution_generation", "prepared_result", "render", "start_render",
        ):
            payload = {**valid_request(), field: "unsafe"}
            with self.subTest(field=field):
                result = validate_prepare_api_request(payload, request_bytes=500)
                self.assertFalse(result["valid"])
                self.assertTrue(any(field in error.lower() for error in result["errors"]))

    def test_non_object_and_oversized_requests_are_rejected(self) -> None:
        self.assertFalse(validate_prepare_api_request([])["valid"])
        self.assertFalse(validate_prepare_api_request(valid_request())["valid"])
        self.assertFalse(validate_prepare_api_request(valid_request(), request_bytes=16_385)["valid"])

    def test_http_status_mapping_is_explicit(self) -> None:
        expected = {
            "DISABLED": 503, "PLANNED": 202, "APPLYING": 202, "APPLIED": 200,
            "REJECTED": 422, "FAILED": 500, "REQUEST_ID_CONFLICT": 409,
            "PLAN_STALE": 409, "OPERATOR_WINDOW_CLOSED": 423,
            "KILL_SWITCH_ACTIVE": 503, "SCHEMA_NOT_READY": 503,
            "RECOVERY_REQUIRED": 503, "OPERATOR_REVIEW_REQUIRED": 409,
        }
        for status, code in expected.items():
            with self.subTest(status=status):
                self.assertEqual(http_status_for_prepare(status), code)

    def test_public_response_is_bounded_and_honest(self) -> None:
        payload = build_prepare_api_response(
            "APPLIED",
            client_request_id="request-12345678",
            request_identity="identity-safe",
            request_state="APPLIED",
            scope={"book_id": 1, "from_chapter": 370, "to_chapter": 372},
            plan_fingerprint=HEX,
            replay=True,
            correlation_id="operator-12345678",
        )
        self.assertEqual(payload["http_status"], 200)
        self.assertFalse(payload["mutation_authorized"])
        self.assertFalse(payload["execution_endpoint_available"])
        self.assertFalse(payload["real_job_execution"])
        self.assertFalse(payload["prepare_starts_render"])
        self.assertTrue(validate_public_payload(payload)["valid"])

    def test_public_response_rejects_unbounded_or_unsupported_fields(self) -> None:
        with self.assertRaises(ValueError):
            build_prepare_api_response(
                "FAILED", client_request_id="request-12345678", error_code="x" * 257
            )
        with self.assertRaises(ValueError):
            build_prepare_api_response(
                "APPLIED", client_request_id="request-12345678", scope={"job_id": 7}
            )

    def test_public_response_rejects_token_path_sql_and_traceback(self) -> None:
        cases = [
            {"owner_token": "raw-secret"},
            {"error": r"D:\\private\\app.db"},
            {"error": "SELECT * FROM private"},
            {"error": 'Traceback File "x.py", line 1'},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                self.assertFalse(validate_public_payload(payload)["valid"])

    def test_status_classification_is_read_only(self) -> None:
        cases = [
            ("APPLIED", {}, "APPLIED"),
            ("REJECTED", {}, "REJECTED"),
            ("FAILED", {}, "FAILED"),
            ("APPLYING", {"owner_active": True}, "OPERATOR_REVIEW_REQUIRED"),
            ("APPLYING", {"owner_active": True, "lease_remaining_seconds": 12}, "APPLYING"),
            ("APPLYING", {"committed_evidence_valid": True}, "RECOVERY_REQUIRED"),
            ("APPLYING", {}, "RECOVERY_REQUIRED"),
            ("PLANNED", {}, "PLANNED"),
            (None, {}, "REJECTED"),
            ("APPLYING", {"corrupt": True}, "OPERATOR_REVIEW_REQUIRED"),
        ]
        for state, kwargs, expected in cases:
            with self.subTest(state=state, kwargs=kwargs):
                result = classify_prepare_status(state, **kwargs)
                self.assertEqual(result["status"], expected)
                self.assertTrue(result["read_only"])
                self.assertFalse(result["acquires_owner"])
                self.assertFalse(result["runs_transaction"])
                self.assertFalse(result["creates_job"])
                self.assertFalse(result["auto_retry"])
                self.assertFalse(result["starts_render"])
                if expected == "APPLYING":
                    self.assertEqual(result["retry_after_seconds"], 12)
                else:
                    self.assertIsNone(result["retry_after_seconds"])


class OperatorSecurityTests(unittest.TestCase):
    def test_authentication_gap_is_not_concealed(self) -> None:
        missing = AuthorizationEvidence(False, False, False, False, False, False)
        self.assertEqual(classify_authentication(missing), AUTH_MISSING_BLOCKS_PRODUCTION)
        local = AuthorizationEvidence(True, False, True, False, False, True, local_only=True)
        self.assertEqual(classify_authentication(local), LOCAL_ONLY_TEMPORARY_CONTROL)
        partial = AuthorizationEvidence(True, True, True, False, False, True, local_only=False)
        self.assertEqual(classify_authentication(partial), OPERATOR_AUTH_DESIGN_REQUIRED)
        ready = AuthorizationEvidence(True, True, True, True, True, True, local_only=False)
        self.assertEqual(classify_authentication(ready), AUTH_PRESENT_AND_REUSABLE)

    def test_operator_confirmation_binds_current_fingerprint_and_range(self) -> None:
        valid = validate_operator_confirmation(
            submitted_fingerprint=HEX,
            current_fingerprint=HEX,
            confirmation=True,
            operator_window_open=True,
            range_size=3,
            canary=True,
            authentication_classification=AUTH_PRESENT_AND_REUSABLE,
            operator_identity_ref="operator-ref-1",
            correlation_id="operator-12345678",
            scope_reviewed=True,
            csrf_origin_verified=True,
        )
        self.assertTrue(valid["valid"])
        cases = [
            {"submitted_fingerprint": "b" * 64},
            {"confirmation": False},
            {"operator_window_open": False},
            {"range_size": 4},
            {"included_chapters_from_client_authoritative": True},
            {"authentication_classification": AUTH_MISSING_BLOCKS_PRODUCTION},
            {"operator_identity_ref": ""},
            {"scope_reviewed": False},
            {"csrf_origin_verified": False},
        ]
        base = dict(
            submitted_fingerprint=HEX,
            current_fingerprint=HEX,
            confirmation=True,
            operator_window_open=True,
            range_size=3,
            canary=True,
            authentication_classification=AUTH_PRESENT_AND_REUSABLE,
            operator_identity_ref="operator-ref-1",
            correlation_id="operator-12345678",
            scope_reviewed=True,
            csrf_origin_verified=True,
        )
        for mutation in cases:
            with self.subTest(mutation=mutation):
                self.assertFalse(validate_operator_confirmation(**{**base, **mutation})["valid"])

    def test_audit_allowlist_and_required_fields(self) -> None:
        for event in AUDIT_EVENTS:
            with self.subTest(event=event):
                self.assertTrue(validate_audit_event(event, valid_audit_fields())["valid"])
        self.assertFalse(validate_audit_event("UNKNOWN", valid_audit_fields())["valid"])
        for field in ("timestamp", "event_version", "correlation_id", "result_code", "schema_version", "operator_identity_ref"):
            fields = valid_audit_fields()
            fields.pop(field)
            with self.subTest(field=field):
                self.assertFalse(validate_audit_event("PREPARE_REQUEST_RECEIVED", fields)["valid"])

    def test_audit_rejects_unknown_unbounded_and_sensitive_values(self) -> None:
        cases = [
            {"owner_token": "secret"},
            {"result_code": "x" * 513},
            {"result_code": r"D:\\private\\app.db"},
            {"result_code": "DROP TABLE jobs"},
            {"result_code": 'Traceback File "x.py", line 1'},
            {"feature_flag_state": {"access_token": "secret"}},
            {"feature_flag_state": {"nested": r"\\server\\private"}},
        ]
        for mutation in cases:
            with self.subTest(mutation=mutation):
                fields = {**valid_audit_fields(), **mutation}
                self.assertFalse(validate_audit_event("PREPARE_FAILED", fields)["valid"])

    def test_redaction_is_deterministic_and_retains_safe_correlation(self) -> None:
        payload = {
            "correlation_id": "operator-12345678",
            "owner_token": "secret-value",
            "access_token": "secret-access",
            "error": r"D:\\private\\app.db",
            "nested": {"password": "secret"},
        }
        first = redact_for_public(payload)
        second = redact_for_public(payload)
        self.assertEqual(first, second)
        self.assertEqual(first["correlation_id"], "operator-12345678")
        self.assertEqual(first["owner_token"], "<redacted>")
        self.assertEqual(first["access_token"], "<redacted>")
        self.assertEqual(first["error"], "<redacted>")
        self.assertEqual(first["nested"]["password"], "<redacted>")

    def test_kill_switch_preserves_reads_and_blocks_mutation_retry_render(self) -> None:
        flags = RuntimeFeatureFlags(kill_switch_active=False)
        normal = evaluate_kill_switch(flags)
        self.assertFalse(normal["kill_switch_active"])
        for trigger in (
            "DUPLICATE_JOB_ANOMALY", "CANONICAL_HASH_ANOMALY", "SCHEMA_MISMATCH",
            "CORRUPT_DURABLE_STATE", "RECOVERY_AMBIGUITY", "UNEXPECTED_WORKER_PICKUP",
            "PROTECTED_BASELINE_CHANGE", "EXCESSIVE_FAILURE_RATE",
            "AUTHENTICATION_INCIDENT", "AUDIT_PIPELINE_FAILURE",
        ):
            with self.subTest(trigger=trigger):
                result = evaluate_kill_switch(flags, [trigger])
                self.assertTrue(result["new_prepare_mutation_blocked"])
                self.assertTrue(result["read_only_planning_available"])
                self.assertTrue(result["status_recovery_read_available"])
                self.assertTrue(result["existing_requests_preserved"])
                self.assertFalse(result["automatic_retry_allowed"])
                self.assertFalse(result["start_render_allowed"])


class RolloutAndSafetyTests(unittest.TestCase):
    def test_rollout_stage_order_and_gates(self) -> None:
        self.assertTrue(evaluate_rollout_transition("DISABLED", "DESIGN_READY")["allowed"])
        self.assertFalse(
            evaluate_rollout_transition("DESIGN_READY", "MIGRATION_REHEARSAL_READY")["allowed"]
        )
        self.assertTrue(
            evaluate_rollout_transition(
                "DESIGN_READY", "MIGRATION_REHEARSAL_READY", clone_rehearsal_passed=True
            )["allowed"]
        )
        self.assertFalse(
            evaluate_rollout_transition("DESIGN_READY", "CANARY_ENABLED")["allowed"]
        )
        self.assertFalse(
            evaluate_rollout_transition(
                "MIGRATION_REHEARSAL_READY", "CANONICAL_SCHEMA_READY_BUT_DISABLED",
                canonical_schema_ready=True, feature_flags_disabled=False, postflight_verified=True,
            )["allowed"]
        )
        self.assertTrue(
            evaluate_rollout_transition(
                "MIGRATION_REHEARSAL_READY", "CANONICAL_SCHEMA_READY_BUT_DISABLED",
                canonical_schema_ready=True, feature_flags_disabled=True, postflight_verified=True,
            )["allowed"]
        )
        self.assertFalse(
            evaluate_rollout_transition(
                "CANONICAL_SCHEMA_READY_BUT_DISABLED", "CANARY_ENABLED"
            )["allowed"]
        )
        self.assertTrue(
            evaluate_rollout_transition(
                "CANONICAL_SCHEMA_READY_BUT_DISABLED", "CANARY_ENABLED",
                separate_canary_authorization=True,
                production_authentication_ready=True,
                operator_window_open=True,
                kill_switch_inactive=True,
                start_render_disabled=True,
                readiness_verified=True,
            )["allowed"]
        )
        self.assertFalse(
            evaluate_rollout_transition("CANARY_ENABLED", "LIMITED_ENABLED")["allowed"]
        )
        self.assertTrue(
            evaluate_rollout_transition(
                "CANARY_ENABLED", "LIMITED_ENABLED", limited_rollout_authorized=True
            )["allowed"]
        )
        self.assertFalse(
            evaluate_rollout_transition("LIMITED_ENABLED", "GENERAL_ENABLED")["allowed"]
        )
        self.assertTrue(
            evaluate_rollout_transition(
                "LIMITED_ENABLED", "GENERAL_ENABLED", general_rollout_authorized=True
            )["allowed"]
        )
        self.assertEqual(
            evaluate_rollout_transition("DESIGN_READY", "MIGRATION_REHEARSAL_READY", rollback_required=True)["state"],
            "ROLLBACK_REQUIRED",
        )

    def test_production_readiness_remains_false(self) -> None:
        result = production_readiness(
            runtime_design_complete=True,
            clone_rehearsal_complete=False,
            rollback_rehearsal_complete=False,
            authentication_classification=AUTH_MISSING_BLOCKS_PRODUCTION,
            feature_flag_tests_passed=True,
            kill_switch_tests_passed=True,
            audit_redaction_tests_passed=True,
        )
        self.assertFalse(result["production_ready"])
        self.assertIn("CLONE_REHEARSAL_INCOMPLETE", result["blockers"])
        self.assertIn("AUTHENTICATION_NOT_PRODUCTION_READY", result["blockers"])
        self.assertFalse(result["canonical_activation_authorized"])
        self.assertFalse(result["production_prepare_authorized"])

        future_complete = production_readiness(
            runtime_design_complete=True,
            clone_rehearsal_complete=True,
            rollback_rehearsal_complete=True,
            authentication_classification=AUTH_PRESENT_AND_REUSABLE,
            feature_flag_tests_passed=True,
            kill_switch_tests_passed=True,
            audit_redaction_tests_passed=True,
        )
        self.assertTrue(future_complete["future_prerequisites_satisfied"])
        self.assertFalse(future_complete["production_ready"])

    def test_existing_start_route_is_not_safe_for_future_batch_jobs(self) -> None:
        blocked = evaluate_start_render_boundary(
            batch_prepared_job=True,
            separate_start_authorization=False,
            production_authentication_ready=True,
            operator_window_open=True,
            kill_switch_inactive=True,
        )
        self.assertFalse(blocked["future_start_gate_open"])
        self.assertFalse(blocked["legacy_start_route_safe_for_batch_jobs"])
        self.assertTrue(blocked["requires_batch_linkage_guard"])
        self.assertFalse(blocked["current_start_authorized"])
        self.assertFalse(blocked["worker_wake_authorized"])

    def test_metadata_and_dependency_graph_are_explicit(self) -> None:
        metadata = contract_metadata()
        self.assertEqual(metadata["design_status"], "DESIGN_ONLY")
        self.assertEqual(metadata["current_rollout_stage"], "DESIGN_READY")
        self.assertEqual(tuple(metadata["runtime_dependency_graph"]), runtime_dependency_graph())
        self.assertEqual(runtime_dependency_graph()[0], "RuntimeConfig")
        self.assertEqual(runtime_dependency_graph()[-1], "PrepareStatusRecoveryApiService")
        self.assertTrue(all(value is False for value in authorization_flags().values()))

    def test_pure_module_has_no_executable_side_effect_imports_or_calls(self) -> None:
        source = Path("story_audio/batch_prepare_runtime_rollout_contract.py").read_text(encoding="utf-8")
        forbidden = (
            "import sqlite3", "sqlite3.connect", "MigrationRunner(", "FastAPI(",
            "@app.", "prepare_job(", "create_job(", "start_prepared_job(",
            "wake_worker(", "PipelineWorker(", "requests.", "subprocess.", "os.environ",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_runtime_files_do_not_import_phase11_contract(self) -> None:
        for path in (
            "story_audio/api.py", "story_audio/pipeline.py", "story_audio/db.py",
            "story_audio/batch_prepare_isolated_adapter.py", "story_audio/batch_prepare_orchestrator.py",
        ):
            with self.subTest(path=path):
                self.assertNotIn(
                    "batch_prepare_runtime_rollout_contract",
                    Path(path).read_text(encoding="utf-8"),
                )


if __name__ == "__main__":
    unittest.main()
