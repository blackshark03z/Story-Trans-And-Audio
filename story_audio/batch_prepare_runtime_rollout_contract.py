from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


CONTRACT_SCHEMA = "story-audio-batch-prepare-runtime-rollout-contract/v1"
DESIGN_STATUS = "DESIGN_ONLY"
CURRENT_ROLLOUT_STAGE = "DESIGN_READY"
REQUIRED_ACTIVATION_SCHEMA = 12
TARGET_SCHEMA = 15
MAX_REQUEST_BYTES = 16_384
MAX_PREPARE_CHAPTERS = 256
INITIAL_CANARY_CHAPTERS = 3

AUTH_PRESENT_AND_REUSABLE = "AUTH_PRESENT_AND_REUSABLE"
AUTH_MISSING_BLOCKS_PRODUCTION = "AUTH_MISSING_BLOCKS_PRODUCTION"
LOCAL_ONLY_TEMPORARY_CONTROL = "LOCAL_ONLY_TEMPORARY_CONTROL"
OPERATOR_AUTH_DESIGN_REQUIRED = "OPERATOR_AUTH_DESIGN_REQUIRED"

AUTHORIZATION_FLAGS = {
    "runtime_implementation_authorized": False,
    "canonical_activation_authorized": False,
    "production_prepare_authorized": False,
    "api_mutation_route_authorized": False,
    "ui_control_authorized": False,
    "worker_wake_authorized": False,
    "start_render_authorized": False,
    "provider_tts_authorized": False,
}

RUNTIME_DEPENDENCY_GRAPH = (
    "RuntimeConfig",
    "FeatureFlagProvider",
    "CanonicalDatabaseProvider",
    "PrepareRequestStore",
    "ExecutionAttemptStore",
    "JobLinkStore",
    "TransactionManager",
    "TransactionRevalidator",
    "PreparedJobWriter",
    "ProductionAdapterFacade",
    "PrepareApiService",
    "PrepareStatusRecoveryApiService",
)

ROLLOUT_STAGES = (
    "DISABLED",
    "DESIGN_READY",
    "MIGRATION_REHEARSAL_READY",
    "CANONICAL_SCHEMA_READY_BUT_DISABLED",
    "CANARY_ENABLED",
    "LIMITED_ENABLED",
    "GENERAL_ENABLED",
)
TERMINAL_ROLLOUT_STATES = {"KILL_SWITCHED", "ROLLBACK_REQUIRED"}

MAINTENANCE_TRANSITIONS = {
    "ENTERING": {"ACTIVE", "FAILED_LOCKED"},
    "ACTIVE": {"MIGRATING", "FAILED_LOCKED"},
    "MIGRATING": {"VERIFYING", "FAILED_LOCKED"},
    "VERIFYING": {"EXIT_READY", "FAILED_LOCKED"},
    "FAILED_LOCKED": {"VERIFYING"},
    "EXIT_READY": {"EXITED", "FAILED_LOCKED"},
    "EXITED": set(),
}

PREPARE_RESPONSE_HTTP = {
    "DISABLED": 503,
    "PLANNED": 202,
    "APPLYING": 202,
    "APPLIED": 200,
    "REJECTED": 422,
    "FAILED": 500,
    "REQUEST_ID_CONFLICT": 409,
    "PLAN_STALE": 409,
    "OPERATOR_WINDOW_CLOSED": 423,
    "KILL_SWITCH_ACTIVE": 503,
    "SCHEMA_NOT_READY": 503,
    "RECOVERY_REQUIRED": 503,
    "OPERATOR_REVIEW_REQUIRED": 409,
}

AUDIT_EVENTS = frozenset(
    {
        "PREPARE_REQUEST_RECEIVED",
        "PREPARE_REQUEST_REPLAYED",
        "PREPARE_REQUEST_CONFLICT",
        "PREPARE_PLAN_STALE",
        "PREPARE_OWNER_ACQUIRED",
        "PREPARE_TRANSACTION_COMMITTED",
        "PREPARE_APPLIED_PERSISTED",
        "PREPARE_RECOVERY_REQUIRED",
        "PREPARE_RECOVERY_COMPLETED",
        "PREPARE_FAILED",
        "PREPARE_KILL_SWITCHED",
        "PREPARE_FEATURE_DISABLED",
        "PREPARE_CANONICAL_MIGRATION_STARTED",
        "PREPARE_CANONICAL_MIGRATION_COMPLETED",
        "PREPARE_CANONICAL_MIGRATION_FAILED",
        "PREPARE_ROLLBACK_STARTED",
        "PREPARE_ROLLBACK_COMPLETED",
    }
)

SAFE_AUDIT_FIELDS = frozenset(
    {
        "timestamp",
        "event_version",
        "correlation_id",
        "client_request_id",
        "request_identity",
        "book_id",
        "from_chapter",
        "to_chapter",
        "plan_fingerprint",
        "request_state",
        "result_code",
        "replay",
        "operator_identity_ref",
        "feature_flag_state",
        "schema_version",
    }
)

FORBIDDEN_FIELD_PARTS = (
    "owner_token",
    "token_hash",
    "password",
    "secret",
    "credential",
    "api_key",
    "raw_sql",
    "traceback",
    "full_text",
    "full_plan",
    "db_path",
    "backup_path",
    "access_token",
    "authorization",
    "bearer",
    "cookie",
    "session",
    "private_key",
    "token",
)

RESTORE_TRIGGERS = frozenset(
    {
        "MIGRATION_FAILURE",
        "SCHEMA_MISMATCH",
        "QUICK_CHECK_FAILURE",
        "MISSING_SCHEMA_OBJECT",
        "RUNTIME_STARTUP_FAILURE",
        "DATA_COUNT_CHANGE",
        "PROTECTED_BASELINE_CHANGE",
        "POSTFLIGHT_FAILURE",
        "FEATURE_FLAG_MISBEHAVIOR",
    }
)

KILL_SWITCH_TRIGGERS = frozenset(
    {
        "DUPLICATE_JOB_ANOMALY",
        "CANONICAL_HASH_ANOMALY",
        "SCHEMA_MISMATCH",
        "CORRUPT_DURABLE_STATE",
        "RECOVERY_AMBIGUITY",
        "UNEXPECTED_WORKER_PICKUP",
        "PROTECTED_BASELINE_CHANGE",
        "EXCESSIVE_FAILURE_RATE",
        "AUTHENTICATION_INCIDENT",
        "AUDIT_PIPELINE_FAILURE",
    }
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_CORRELATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\[^\\]+\\|/(?:home|users|var|etc|tmp)/)", re.IGNORECASE)
_SQL_TEXT = re.compile(r"\b(?:select|insert|update|delete|drop|alter|pragma)\b", re.IGNORECASE)
_TRACEBACK = re.compile(r"traceback|file \".*\", line \d+", re.IGNORECASE)


@dataclass(frozen=True)
class RuntimeFeatureFlags:
    feature_available: bool = False
    mutation_enabled: bool = False
    canonical_schema_ready: bool = False
    operator_window_open: bool = False
    kill_switch_active: bool = True
    start_render_enabled: bool = False
    config_valid: bool = True


@dataclass(frozen=True)
class CanonicalActivationPreflight:
    canonical_path_verified: bool
    process_inventory_recorded: bool
    mutation_processes_stopped: bool
    maintenance_state: str
    schema_version: int
    quick_check: str
    source_sha256: str
    source_size: int
    source_mtime: str
    wal_shm_policy: str
    no_active_write_transaction: bool
    backup_verified: bool
    backup_sha256: str
    backup_readable: bool
    free_space_sufficient: bool
    migration_hashes: Mapping[int, str]
    migration_chain: tuple[int, ...]
    rollback_artifact_verified: bool
    feature_flags_disabled: bool
    operator_approved: bool
    protected_baseline_verified: bool
    active_prepare_request_count: int
    deployment_correlation_id: str
    backup_evidence: BackupEvidence | None = None
    canonical_identity_ref: str = ""
    operator_identity_ref: str = ""
    reviewer_identity_ref: str = ""


@dataclass(frozen=True)
class BackupEvidence:
    source_identity_verified: bool
    source_identity_ref: str
    source_schema: int
    source_sha256: str
    source_size: int
    source_mtime: str
    source_quick_check: str
    backup_identity_recorded: bool
    backup_identity_ref: str
    backup_sha256: str
    backup_size: int
    backup_quick_check: str
    backup_matches_source_identity: bool
    backup_schema: int
    atomic_snapshot_verified: bool
    created_timestamp: str
    operator_identity_ref: str
    correlation_id: str
    wal_shm_policy: str
    retention_policy_ref: str


@dataclass(frozen=True)
class MigrationPostflight:
    applied_chain: tuple[int, ...]
    final_schema: int
    required_tables_verified: bool
    required_indexes_verified: bool
    foreign_keys_verified: bool
    legacy_counts_preserved: bool
    jobs_created: int
    requests_created: int
    feature_flags_disabled: bool
    quick_check: str
    runtime_startup_verified: bool
    protected_baseline_verified: bool
    migration_hashes_verified: bool = False
    verified_stage_chain: tuple[int, ...] = ()


@dataclass(frozen=True)
class AuthorizationEvidence:
    authentication_present: bool
    reusable_operator_role: bool
    credential_outside_url: bool
    origin_controls: bool
    csrf_controls: bool
    audit_identity_available: bool
    local_only: bool = True


def authorization_flags() -> dict[str, bool]:
    return dict(AUTHORIZATION_FLAGS)


def contract_metadata() -> dict[str, Any]:
    return {
        "contract_schema": CONTRACT_SCHEMA,
        "design_status": DESIGN_STATUS,
        "current_rollout_stage": CURRENT_ROLLOUT_STAGE,
        "runtime_dependency_graph": list(RUNTIME_DEPENDENCY_GRAPH),
        **authorization_flags(),
    }


def runtime_dependency_graph() -> tuple[str, ...]:
    return RUNTIME_DEPENDENCY_GRAPH


def parse_feature_flags(values: Mapping[str, Any] | None = None) -> tuple[RuntimeFeatureFlags, tuple[str, ...]]:
    source = dict(values or {})
    names = {
        "PREPARE_FEATURE_AVAILABLE": "feature_available",
        "PREPARE_MUTATION_ENABLED": "mutation_enabled",
        "PREPARE_CANONICAL_SCHEMA_READY": "canonical_schema_ready",
        "PREPARE_OPERATOR_WINDOW_OPEN": "operator_window_open",
        "PREPARE_KILL_SWITCH_ACTIVE": "kill_switch_active",
        "START_RENDER_ENABLED": "start_render_enabled",
    }
    parsed: dict[str, bool] = {
        "feature_available": False,
        "mutation_enabled": False,
        "canonical_schema_ready": False,
        "operator_window_open": False,
        "kill_switch_active": True,
        "start_render_enabled": False,
    }
    errors: list[str] = []
    errors.extend(f"UNKNOWN_FEATURE_FLAG_{name}" for name in sorted(set(source) - set(names)))
    for external, field_name in names.items():
        if external not in source:
            continue
        raw = source[external]
        if isinstance(raw, bool):
            parsed[field_name] = raw
        elif isinstance(raw, str) and raw.strip().lower() in {"true", "false"}:
            parsed[field_name] = raw.strip().lower() == "true"
        else:
            errors.append(f"INVALID_{external}")
            parsed[field_name] = True if field_name == "kill_switch_active" else False
    return RuntimeFeatureFlags(**parsed, config_valid=not errors), tuple(errors)


def evaluate_feature_gate(
    flags: RuntimeFeatureFlags,
    *,
    schema_version: int,
    runtime_identity_explicit: bool,
    authentication_ready: bool,
) -> dict[str, Any]:
    reasons: list[str] = []
    if not flags.config_valid:
        reasons.append("FEATURE_CONFIG_INVALID")
    if flags.kill_switch_active:
        reasons.append("KILL_SWITCH_ACTIVE")
    if not flags.feature_available:
        reasons.append("FEATURE_UNAVAILABLE")
    if not flags.mutation_enabled:
        reasons.append("MUTATION_DISABLED")
    if not flags.canonical_schema_ready or schema_version != TARGET_SCHEMA:
        reasons.append("SCHEMA_NOT_READY")
    if not flags.operator_window_open:
        reasons.append("OPERATOR_WINDOW_CLOSED")
    if not runtime_identity_explicit:
        reasons.append("RUNTIME_IDENTITY_NOT_EXPLICIT")
    if not authentication_ready:
        reasons.append("AUTH_NOT_READY")
    future_gate_open = not reasons
    return {
        "future_mutation_gate_open": future_gate_open,
        "current_mutation_authorized": False,
        "read_only_planning_available": True,
        "status_read_available": True,
        "prepare_service_constructible": future_gate_open,
        "start_render_flag_configured": bool(flags.start_render_enabled),
        "start_render_enabled": False,
        "prepare_starts_render": False,
        "reasons": reasons,
    }


def validate_activation_preflight(evidence: CanonicalActivationPreflight) -> dict[str, Any]:
    errors: list[str] = []
    checks = (
        (evidence.canonical_path_verified, "CANONICAL_PATH_NOT_VERIFIED"),
        (evidence.process_inventory_recorded, "PROCESS_INVENTORY_MISSING"),
        (evidence.mutation_processes_stopped, "MUTATION_PROCESS_ACTIVE"),
        (evidence.maintenance_state == "ACTIVE", "MAINTENANCE_NOT_ACTIVE"),
        (evidence.schema_version == REQUIRED_ACTIVATION_SCHEMA, "SOURCE_SCHEMA_NOT_12"),
        (evidence.quick_check == "ok", "SOURCE_QUICK_CHECK_FAILED"),
        (bool(_HEX64.fullmatch(evidence.source_sha256)), "SOURCE_HASH_INVALID"),
        (evidence.source_size > 0, "SOURCE_SIZE_MISSING"),
        (bool(evidence.source_mtime), "SOURCE_MTIME_MISSING"),
        (evidence.wal_shm_policy in {"SQLITE_BACKUP_API", "CHECKPOINT_AND_COPY"}, "WAL_SHM_POLICY_INVALID"),
        (evidence.no_active_write_transaction, "ACTIVE_WRITE_TRANSACTION"),
        (evidence.backup_verified, "BACKUP_NOT_VERIFIED"),
        (bool(_HEX64.fullmatch(evidence.backup_sha256)), "BACKUP_HASH_INVALID"),
        (evidence.backup_readable, "BACKUP_NOT_READABLE"),
        (evidence.free_space_sufficient, "FREE_SPACE_INSUFFICIENT"),
        (tuple(evidence.migration_chain) == (13, 14, 15), "MIGRATION_CHAIN_INVALID"),
        (evidence.rollback_artifact_verified, "ROLLBACK_ARTIFACT_MISSING"),
        (evidence.feature_flags_disabled, "FEATURE_FLAGS_NOT_DISABLED"),
        (evidence.operator_approved, "OPERATOR_APPROVAL_MISSING"),
        (evidence.protected_baseline_verified, "PROTECTED_BASELINE_NOT_VERIFIED"),
        (evidence.active_prepare_request_count == 0, "ACTIVE_PREPARE_REQUEST_EXISTS"),
        (bool(_CORRELATION_ID.fullmatch(evidence.deployment_correlation_id)), "CORRELATION_ID_INVALID"),
        (_safe_reference(evidence.canonical_identity_ref), "CANONICAL_IDENTITY_REF_INVALID"),
        (bool(evidence.operator_identity_ref), "OPERATOR_IDENTITY_MISSING"),
        (bool(evidence.reviewer_identity_ref), "REVIEWER_IDENTITY_MISSING"),
    )
    errors.extend(error for valid, error in checks if not valid)
    if set(evidence.migration_hashes) != {13, 14, 15} or any(
        not _HEX64.fullmatch(value) for value in evidence.migration_hashes.values()
    ):
        errors.append("MIGRATION_HASHES_INVALID")
    if evidence.backup_evidence is None:
        errors.append("BOUND_BACKUP_EVIDENCE_REQUIRED")
    else:
        backup_result = validate_backup_evidence(evidence.backup_evidence)
        if not backup_result["valid"]:
            errors.append("BOUND_BACKUP_EVIDENCE_INVALID")
        if (
            evidence.backup_evidence.source_schema != evidence.schema_version
            or evidence.backup_evidence.source_identity_ref != evidence.canonical_identity_ref
            or evidence.backup_evidence.source_sha256 != evidence.source_sha256
            or evidence.backup_evidence.source_size != evidence.source_size
            or evidence.backup_evidence.backup_sha256 != evidence.backup_sha256
        ):
            errors.append("BACKUP_PREFLIGHT_BINDING_MISMATCH")
    return _result(not errors, "ACTIVATION_PREFLIGHT_READY" if not errors else "ACTIVATION_PREFLIGHT_BLOCKED", errors)


def validate_backup_evidence(evidence: BackupEvidence) -> dict[str, Any]:
    errors: list[str] = []
    checks = (
        (evidence.source_identity_verified, "SOURCE_IDENTITY_NOT_VERIFIED"),
        (_safe_reference(evidence.source_identity_ref), "SOURCE_IDENTITY_REF_INVALID"),
        (evidence.source_schema == REQUIRED_ACTIVATION_SCHEMA, "SOURCE_SCHEMA_NOT_12"),
        (bool(_HEX64.fullmatch(evidence.source_sha256)), "SOURCE_HASH_INVALID"),
        (evidence.source_size > 0, "SOURCE_SIZE_INVALID"),
        (bool(evidence.source_mtime), "SOURCE_MTIME_MISSING"),
        (evidence.source_quick_check == "ok", "SOURCE_QUICK_CHECK_FAILED"),
        (evidence.backup_identity_recorded, "BACKUP_IDENTITY_MISSING"),
        (_safe_reference(evidence.backup_identity_ref), "BACKUP_IDENTITY_REF_INVALID"),
        (bool(_HEX64.fullmatch(evidence.backup_sha256)), "BACKUP_HASH_INVALID"),
        (evidence.backup_size > 0, "BACKUP_SIZE_INVALID"),
        (evidence.backup_quick_check == "ok", "BACKUP_QUICK_CHECK_FAILED"),
        (evidence.backup_matches_source_identity, "BACKUP_SOURCE_IDENTITY_MISMATCH"),
        (evidence.backup_schema == evidence.source_schema, "BACKUP_SCHEMA_MISMATCH"),
        (evidence.atomic_snapshot_verified, "ATOMIC_SNAPSHOT_NOT_VERIFIED"),
        (bool(evidence.created_timestamp), "BACKUP_TIMESTAMP_MISSING"),
        (bool(evidence.operator_identity_ref), "OPERATOR_IDENTITY_MISSING"),
        (bool(_CORRELATION_ID.fullmatch(evidence.correlation_id)), "CORRELATION_ID_INVALID"),
        (evidence.wal_shm_policy in {"SQLITE_BACKUP_API", "CHECKPOINT_AND_COPY"}, "WAL_SHM_POLICY_INVALID"),
        (bool(evidence.retention_policy_ref), "RETENTION_POLICY_MISSING"),
    )
    errors.extend(error for valid, error in checks if not valid)
    return _result(not errors, "BACKUP_EVIDENCE_VALID" if not errors else "BACKUP_EVIDENCE_REJECTED", errors)


def validate_migration_postflight(evidence: MigrationPostflight) -> dict[str, Any]:
    errors: list[str] = []
    checks = (
        (tuple(evidence.applied_chain) == (13, 14, 15), "MIGRATION_CHAIN_INVALID"),
        (evidence.final_schema == TARGET_SCHEMA, "FINAL_SCHEMA_NOT_15"),
        (evidence.required_tables_verified, "REQUIRED_TABLES_MISSING"),
        (evidence.required_indexes_verified, "REQUIRED_INDEXES_MISSING"),
        (evidence.foreign_keys_verified, "FOREIGN_KEYS_NOT_VERIFIED"),
        (evidence.legacy_counts_preserved, "LEGACY_COUNTS_CHANGED"),
        (evidence.jobs_created == 0, "UNEXPECTED_JOB_CREATED"),
        (evidence.requests_created == 0, "UNEXPECTED_REQUEST_CREATED"),
        (evidence.feature_flags_disabled, "FEATURE_FLAGS_ENABLED"),
        (evidence.quick_check == "ok", "POSTFLIGHT_QUICK_CHECK_FAILED"),
        (evidence.runtime_startup_verified, "RUNTIME_STARTUP_NOT_VERIFIED"),
        (evidence.protected_baseline_verified, "PROTECTED_BASELINE_CHANGED"),
        (evidence.migration_hashes_verified, "MIGRATION_HASHES_NOT_VERIFIED"),
        (tuple(evidence.verified_stage_chain) == (13, 14, 15), "MIGRATION_STAGES_NOT_VERIFIED"),
    )
    errors.extend(error for valid, error in checks if not valid)
    return _result(not errors, "POSTFLIGHT_VERIFIED" if not errors else "ROLLBACK_REQUIRED", errors)


def classify_migration_stage_failure(*, failed_target: int, observed_schema: int) -> dict[str, Any]:
    expected_predecessor = {13: 12, 14: 13, 15: 14}.get(failed_target)
    known_stage = expected_predecessor is not None
    partial_schema_state = known_stage and observed_schema not in {REQUIRED_ACTIVATION_SCHEMA, TARGET_SCHEMA}
    return {
        "failed_target": failed_target,
        "observed_schema": observed_schema,
        "known_stage": known_stage,
        "expected_predecessor": expected_predecessor,
        "partial_schema_state": partial_schema_state,
        "rollback_required": True,
        "restore_strategy": "FULL_VERIFIED_DATABASE_RESTORE",
        "maintenance_state": "FAILED_LOCKED",
        "feature_flags_disabled": True,
        "runtime_restart_allowed": False,
        "operator_review_required": True,
    }


def classify_restore_trigger(
    trigger: str, *, operational_phase: str = "SCHEMA_ACTIVATION_WINDOW"
) -> dict[str, Any]:
    normalized = str(trigger or "").strip().upper()
    schema_window = str(operational_phase).strip().upper() == "SCHEMA_ACTIVATION_WINDOW"
    return {
        "trigger": normalized or "UNKNOWN",
        "restore_required": schema_window,
        "strategy": "FULL_VERIFIED_DATABASE_RESTORE" if schema_window else "KILL_SWITCH_PRESERVE_AND_RECONCILE",
        "sql_down_migration_allowed": False,
        "maintenance_must_remain_locked": True,
        "prepare_must_remain_disabled": True,
        "operator_review_required": True,
        "recognized_trigger": normalized in RESTORE_TRIGGERS,
    }


def evaluate_restore_outcome(
    *,
    restore_completed: bool,
    expected_hash_restored: bool,
    schema_restored: bool,
    quick_check: str,
    feature_flags_disabled: bool,
    failed_database_archived: bool,
    atomic_replacement_verified: bool,
    wal_shm_handled: bool,
    incident_recorded: bool,
    reviewer_approved: bool,
    read_only_startup_verified: bool,
) -> dict[str, Any]:
    verified = all(
        (
            restore_completed,
            expected_hash_restored,
            schema_restored,
            quick_check == "ok",
            feature_flags_disabled,
            failed_database_archived,
            atomic_replacement_verified,
            wal_shm_handled,
            incident_recorded,
            reviewer_approved,
            read_only_startup_verified,
        )
    )
    return {
        "restore_verified": verified,
        "maintenance_state": "EXIT_READY" if verified else "FAILED_LOCKED",
        "runtime_mode": "DISABLED_READ_ONLY" if verified else "STOPPED",
        "prepare_enabled": False,
        "start_render_allowed": False,
    }


def evaluate_maintenance_transition(
    current: str, target: str, *, postflight_verified: bool = False,
    restore_verified: bool = False, reviewer_approved: bool = False,
) -> dict[str, Any]:
    current, target = str(current).upper(), str(target).upper()
    if current not in MAINTENANCE_TRANSITIONS or target not in MAINTENANCE_TRANSITIONS:
        return _decision(False, "FAILED_LOCKED", "UNKNOWN_MAINTENANCE_STATE")
    if target not in MAINTENANCE_TRANSITIONS[current]:
        return _decision(False, "FAILED_LOCKED", "INVALID_MAINTENANCE_TRANSITION")
    if target == "EXIT_READY" and not (postflight_verified or restore_verified):
        return _decision(False, "FAILED_LOCKED", "POSTFLIGHT_NOT_VERIFIED")
    if target == "EXITED" and not reviewer_approved:
        return _decision(False, "FAILED_LOCKED", "REVIEWER_APPROVAL_REQUIRED")
    return _decision(True, target, None)


def validate_prepare_api_request(payload: Any, *, request_bytes: int | None = None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return _result(False, "REQUEST_REJECTED", ["JSON_OBJECT_REQUIRED"])
    allowed = {
        "client_request_id", "book_id", "from_chapter", "to_chapter", "target_phase",
        "plan_fingerprint", "confirmation", "correlation_id",
    }
    errors: list[str] = []
    unknown = sorted(set(payload) - allowed)
    if unknown:
        errors.extend(f"FIELD_NOT_ALLOWED_{field}" for field in unknown)
    if request_bytes is None:
        errors.append("REQUEST_SIZE_EVIDENCE_REQUIRED")
    elif request_bytes < 0 or request_bytes > MAX_REQUEST_BYTES:
        errors.append("REQUEST_TOO_LARGE")
    request_id = str(payload.get("client_request_id") or "")
    if not _REQUEST_ID.fullmatch(request_id):
        errors.append("CLIENT_REQUEST_ID_INVALID")
    for name in ("book_id", "from_chapter", "to_chapter"):
        if isinstance(payload.get(name), bool) or not isinstance(payload.get(name), int) or int(payload[name]) <= 0:
            errors.append(f"{name.upper()}_INVALID")
    if isinstance(payload.get("from_chapter"), int) and isinstance(payload.get("to_chapter"), int):
        start, end = int(payload["from_chapter"]), int(payload["to_chapter"])
        if start > end:
            errors.append("CHAPTER_RANGE_INVALID")
        elif end - start + 1 > MAX_PREPARE_CHAPTERS:
            errors.append("CHAPTER_RANGE_TOO_LARGE")
    if payload.get("target_phase") != "PREPARE":
        errors.append("TARGET_PHASE_INVALID")
    fingerprint = str(payload.get("plan_fingerprint") or "").lower()
    if not _HEX64.fullmatch(fingerprint):
        errors.append("PLAN_FINGERPRINT_INVALID")
    if payload.get("confirmation") is not True:
        errors.append("LITERAL_CONFIRMATION_TRUE_REQUIRED")
    correlation = payload.get("correlation_id")
    if correlation is not None and not _CORRELATION_ID.fullmatch(str(correlation)):
        errors.append("CORRELATION_ID_INVALID")
    safe_request = {
        key: payload.get(key)
        for key in allowed
        if key in payload
    }
    safe_request["plan_fingerprint"] = fingerprint
    return {
        **_result(not errors, "REQUEST_VALID" if not errors else "REQUEST_REJECTED", errors),
        "request": safe_request if not errors else None,
        "server_recomputes_plan": True,
        "client_eligibility_is_authoritative": False,
        **authorization_flags(),
    }


def http_status_for_prepare(status: str) -> int:
    return PREPARE_RESPONSE_HTTP.get(str(status).upper(), 500)


def build_prepare_api_response(
    status: str,
    *,
    client_request_id: str,
    request_identity: str | None = None,
    request_state: str | None = None,
    scope: Mapping[str, int] | None = None,
    plan_fingerprint: str | None = None,
    replay: bool = False,
    operator_action: str = "REVIEW_STATUS",
    error_code: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    normalized = str(status).upper()
    if normalized not in PREPARE_RESPONSE_HTTP:
        normalized, error_code = "FAILED", "UNKNOWN_RESPONSE_STATUS"
    payload = {
        "status": normalized,
        "http_status": http_status_for_prepare(normalized),
        "client_request_id": client_request_id,
        "request_identity": request_identity,
        "request_state": request_state,
        "scope": dict(scope or {}),
        "plan_fingerprint": plan_fingerprint,
        "replay": bool(replay),
        "operator_action": operator_action,
        "error_code": error_code,
        "correlation_id": correlation_id,
        "mutation_authorized": False,
        "execution_endpoint_available": False,
        "real_job_execution": False,
        "prepare_starts_render": False,
    }
    for name in ("client_request_id", "request_identity", "operator_action", "error_code", "correlation_id"):
        value = payload.get(name)
        if value is not None and len(str(value)) > 256:
            raise ValueError(f"{name} is too long")
    if set(payload["scope"]) - {"book_id", "from_chapter", "to_chapter"}:
        raise ValueError("scope contains unsupported fields")
    if len(repr(payload).encode("utf-8")) > MAX_REQUEST_BYTES:
        raise ValueError("public response is too large")
    safety = validate_public_payload(payload)
    if not safety["valid"]:
        raise ValueError("unsafe public response")
    return payload


def classify_prepare_status(
    request_state: str | None,
    *,
    owner_active: bool = False,
    lease_remaining_seconds: int | None = None,
    committed_evidence_valid: bool = False,
    corrupt: bool = False,
    ambiguous: bool = False,
) -> dict[str, Any]:
    state = str(request_state or "UNKNOWN").upper()
    if corrupt or ambiguous:
        status, action = "OPERATOR_REVIEW_REQUIRED", "KEEP_DISABLED_AND_REVIEW"
    elif state == "APPLIED":
        status, action = "APPLIED", "HISTORICAL_REPLAY"
    elif state in {"REJECTED", "FAILED"}:
        status, action = state, "HISTORICAL_REPLAY"
    elif state == "APPLYING" and committed_evidence_valid:
        status, action = "RECOVERY_REQUIRED", "PERSIST_APPLIED_FROM_DURABLE_EVIDENCE"
    elif state == "APPLYING" and owner_active and lease_remaining_seconds is None:
        status, action = "OPERATOR_REVIEW_REQUIRED", "LEASE_EVIDENCE_REQUIRED"
    elif state == "APPLYING" and owner_active and lease_remaining_seconds > 0:
        status, action = "APPLYING", "WAIT_FOR_ACTIVE_OWNER"
    elif state == "APPLYING":
        status, action = "RECOVERY_REQUIRED", "CLASSIFY_EXPIRED_OWNER"
    elif state == "PLANNED":
        status, action = "PLANNED", "NO_STATUS_MUTATION"
    else:
        status, action = "REJECTED", "REQUEST_NOT_FOUND"
    return {
        "status": status,
        "operator_action": action,
        "read_only": True,
        "acquires_owner": False,
        "runs_transaction": False,
        "creates_job": False,
        "auto_retry": False,
        "starts_render": False,
        "retry_after_seconds": min(30, max(1, lease_remaining_seconds or 5)) if status == "APPLYING" else None,
        "timeout_policy": "BOUNDED_POLL_THEN_STATUS_RECHECK",
    }


def classify_authentication(evidence: AuthorizationEvidence) -> str:
    if not evidence.authentication_present:
        return AUTH_MISSING_BLOCKS_PRODUCTION
    if evidence.local_only and not evidence.reusable_operator_role:
        return LOCAL_ONLY_TEMPORARY_CONTROL
    if all(
        (
            evidence.reusable_operator_role,
            evidence.credential_outside_url,
            evidence.origin_controls,
            evidence.csrf_controls,
            evidence.audit_identity_available,
        )
    ):
        return AUTH_PRESENT_AND_REUSABLE
    return OPERATOR_AUTH_DESIGN_REQUIRED


def validate_operator_confirmation(
    *,
    submitted_fingerprint: str,
    current_fingerprint: str,
    confirmation: Any,
    operator_window_open: bool,
    range_size: int,
    canary: bool,
    included_chapters_from_client_authoritative: bool = False,
    authentication_classification: str = AUTH_MISSING_BLOCKS_PRODUCTION,
    operator_identity_ref: str = "",
    correlation_id: str = "",
    scope_reviewed: bool = False,
    csrf_origin_verified: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    if confirmation is not True:
        errors.append("LITERAL_CONFIRMATION_TRUE_REQUIRED")
    if submitted_fingerprint != current_fingerprint:
        errors.append("PLAN_STALE")
    if not _HEX64.fullmatch(str(current_fingerprint).lower()):
        errors.append("PLAN_FINGERPRINT_INVALID")
    if not operator_window_open:
        errors.append("OPERATOR_WINDOW_CLOSED")
    if range_size <= 0 or range_size > MAX_PREPARE_CHAPTERS:
        errors.append("RANGE_LIMIT_EXCEEDED")
    if canary and range_size > INITIAL_CANARY_CHAPTERS:
        errors.append("CANARY_RANGE_LIMIT_EXCEEDED")
    if included_chapters_from_client_authoritative:
        errors.append("CLIENT_ELIGIBILITY_NOT_AUTHORITY")
    if authentication_classification != AUTH_PRESENT_AND_REUSABLE:
        errors.append("PRODUCTION_AUTHENTICATION_REQUIRED")
    if not operator_identity_ref:
        errors.append("OPERATOR_IDENTITY_REQUIRED")
    if not _CORRELATION_ID.fullmatch(correlation_id):
        errors.append("CORRELATION_ID_INVALID")
    if not scope_reviewed:
        errors.append("SCOPE_REVIEW_REQUIRED")
    if not csrf_origin_verified:
        errors.append("CSRF_ORIGIN_VERIFICATION_REQUIRED")
    return _result(not errors, "OPERATOR_CONFIRMATION_VALID" if not errors else "OPERATOR_CONFIRMATION_REJECTED", errors)


def validate_audit_event(event_code: str, fields: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if event_code not in AUDIT_EVENTS:
        errors.append("AUDIT_EVENT_NOT_ALLOWED")
    unknown = sorted(set(fields) - SAFE_AUDIT_FIELDS)
    if unknown:
        errors.extend(f"AUDIT_FIELD_NOT_ALLOWED_{name}" for name in unknown)
    required = {"timestamp", "event_version", "correlation_id", "result_code", "schema_version", "operator_identity_ref"}
    if not ("MIGRATION" in event_code or "ROLLBACK" in event_code or event_code in {"PREPARE_KILL_SWITCHED", "PREPARE_FEATURE_DISABLED"}):
        required.add("client_request_id")
    for name in sorted(required - set(fields)):
        errors.append(f"AUDIT_FIELD_REQUIRED_{name}")
    for key, value in fields.items():
        if any(part in key.lower() for part in FORBIDDEN_FIELD_PARTS):
            errors.append(f"AUDIT_FIELD_FORBIDDEN_{key}")
        if not validate_public_payload({str(key): value})["valid"]:
            errors.append(f"AUDIT_VALUE_UNSAFE_{key}")
        if len(repr(value).encode("utf-8")) > 512:
            errors.append(f"AUDIT_FIELD_TOO_LONG_{key}")
    return _result(not errors, "AUDIT_EVENT_VALID" if not errors else "AUDIT_EVENT_REJECTED", errors)


def redact_for_public(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            lower = str(key).lower()
            result[str(key)] = "<redacted>" if any(part in lower for part in FORBIDDEN_FIELD_PARTS) else redact_for_public(item)
        return result
    if isinstance(value, (list, tuple)):
        return [redact_for_public(item) for item in value]
    if isinstance(value, str) and _unsafe_text(value):
        return "<redacted>"
    return value


def validate_public_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    encoded = repr(payload)
    errors: list[str] = []
    for key in payload:
        if any(part in str(key).lower() for part in FORBIDDEN_FIELD_PARTS):
            errors.append(f"PUBLIC_FIELD_FORBIDDEN_{key}")
    if _unsafe_text(encoded):
        errors.append("PUBLIC_PAYLOAD_CONTAINS_SENSITIVE_TEXT")
    return _result(not errors, "PUBLIC_PAYLOAD_SAFE" if not errors else "PUBLIC_PAYLOAD_REJECTED", errors)


def evaluate_kill_switch(flags: RuntimeFeatureFlags, anomalies: Sequence[str] = ()) -> dict[str, Any]:
    recognized = sorted({str(item).upper() for item in anomalies if str(item).upper() in KILL_SWITCH_TRIGGERS})
    active = flags.kill_switch_active or bool(recognized) or not flags.config_valid
    return {
        "kill_switch_active": active,
        "triggers": recognized,
        "new_prepare_mutation_blocked": active,
        "read_only_planning_available": True,
        "status_recovery_read_available": True,
        "existing_requests_preserved": True,
        "prepared_jobs_preserved": True,
        "automatic_retry_allowed": False,
        "start_render_allowed": False,
    }


def evaluate_rollout_transition(
    current: str,
    target: str,
    *,
    clone_rehearsal_passed: bool = False,
    canonical_schema_ready: bool = False,
    feature_flags_disabled: bool = True,
    postflight_verified: bool = False,
    separate_canary_authorization: bool = False,
    production_authentication_ready: bool = False,
    operator_window_open: bool = False,
    kill_switch_inactive: bool = False,
    start_render_disabled: bool = True,
    readiness_verified: bool = False,
    limited_rollout_authorized: bool = False,
    general_rollout_authorized: bool = False,
    rollback_required: bool = False,
) -> dict[str, Any]:
    current, target = str(current).upper(), str(target).upper()
    if rollback_required:
        return _decision(False, "ROLLBACK_REQUIRED", "ROLLBACK_REQUIRED")
    if current in TERMINAL_ROLLOUT_STATES or target in TERMINAL_ROLLOUT_STATES:
        return _decision(False, target if target in TERMINAL_ROLLOUT_STATES else current, "TERMINAL_ROLLOUT_STATE")
    if current not in ROLLOUT_STAGES or target not in ROLLOUT_STAGES:
        return _decision(False, "KILL_SWITCHED", "UNKNOWN_ROLLOUT_STAGE")
    if ROLLOUT_STAGES.index(target) != ROLLOUT_STAGES.index(current) + 1:
        return _decision(False, current, "ROLLOUT_STAGE_SKIP_REJECTED")
    if target == "MIGRATION_REHEARSAL_READY" and not clone_rehearsal_passed:
        return _decision(False, current, "CLONE_REHEARSAL_REQUIRED")
    if target == "CANONICAL_SCHEMA_READY_BUT_DISABLED" and not (
        canonical_schema_ready and feature_flags_disabled and postflight_verified
    ):
        return _decision(False, current, "CANONICAL_POSTFLIGHT_REQUIRED")
    if target == "CANARY_ENABLED" and not all(
        (separate_canary_authorization, production_authentication_ready,
         operator_window_open, kill_switch_inactive, start_render_disabled,
         readiness_verified)
    ):
        return _decision(False, current, "SEPARATE_CANARY_AUTHORIZATION_REQUIRED")
    if target == "LIMITED_ENABLED" and not limited_rollout_authorized:
        return _decision(False, current, "LIMITED_ROLLOUT_AUTHORIZATION_REQUIRED")
    if target == "GENERAL_ENABLED" and not general_rollout_authorized:
        return _decision(False, current, "GENERAL_ROLLOUT_AUTHORIZATION_REQUIRED")
    return _decision(True, target, None)


def production_readiness(
    *,
    runtime_design_complete: bool,
    clone_rehearsal_complete: bool,
    rollback_rehearsal_complete: bool,
    authentication_classification: str,
    feature_flag_tests_passed: bool,
    kill_switch_tests_passed: bool,
    audit_redaction_tests_passed: bool,
) -> dict[str, Any]:
    blockers: list[str] = []
    checks = (
        (runtime_design_complete, "RUNTIME_DESIGN_INCOMPLETE"),
        (clone_rehearsal_complete, "CLONE_REHEARSAL_INCOMPLETE"),
        (rollback_rehearsal_complete, "ROLLBACK_REHEARSAL_INCOMPLETE"),
        (authentication_classification == AUTH_PRESENT_AND_REUSABLE, "AUTHENTICATION_NOT_PRODUCTION_READY"),
        (feature_flag_tests_passed, "FEATURE_FLAG_TESTS_INCOMPLETE"),
        (kill_switch_tests_passed, "KILL_SWITCH_TESTS_INCOMPLETE"),
        (audit_redaction_tests_passed, "AUDIT_REDACTION_TESTS_INCOMPLETE"),
    )
    blockers.extend(reason for valid, reason in checks if not valid)
    return {
        "future_prerequisites_satisfied": not blockers,
        "production_ready": False,
        "blockers": blockers,
        "current_stage": CURRENT_ROLLOUT_STAGE,
        **authorization_flags(),
    }


def evaluate_start_render_boundary(
    *, batch_prepared_job: bool, separate_start_authorization: bool,
    production_authentication_ready: bool, operator_window_open: bool,
    kill_switch_inactive: bool,
) -> dict[str, Any]:
    future_allowed = all(
        (not batch_prepared_job or separate_start_authorization,
         production_authentication_ready, operator_window_open,
         kill_switch_inactive)
    )
    return {
        "future_start_gate_open": future_allowed,
        "current_start_authorized": False,
        "legacy_start_route_safe_for_batch_jobs": False,
        "requires_batch_linkage_guard": True,
        "worker_wake_authorized": False,
    }


def _unsafe_text(value: str) -> bool:
    lowered = value.lower()
    return (
        any(part in lowered for part in FORBIDDEN_FIELD_PARTS)
        or bool(_ABSOLUTE_PATH.search(value))
        or bool(_TRACEBACK.search(value))
        or bool(_SQL_TEXT.search(value))
    )


def _safe_reference(value: str) -> bool:
    return 1 <= len(str(value)) <= 128 and not _unsafe_text(str(value))


def _result(valid: bool, code: str, errors: Sequence[str]) -> dict[str, Any]:
    return {"valid": valid, "code": code, "errors": list(errors)}


def _decision(allowed: bool, state: str, reason: str | None) -> dict[str, Any]:
    return {"allowed": allowed, "state": state, "reason": reason}


__all__ = [
    "AUDIT_EVENTS", "AUTHORIZATION_FLAGS", "AUTH_MISSING_BLOCKS_PRODUCTION",
    "AUTH_PRESENT_AND_REUSABLE", "AuthorizationEvidence", "BackupEvidence",
    "CONTRACT_SCHEMA", "CURRENT_ROLLOUT_STAGE", "CanonicalActivationPreflight",
    "DESIGN_STATUS", "INITIAL_CANARY_CHAPTERS", "KILL_SWITCH_TRIGGERS",
    "LOCAL_ONLY_TEMPORARY_CONTROL", "MAX_PREPARE_CHAPTERS", "MAX_REQUEST_BYTES",
    "MigrationPostflight", "OPERATOR_AUTH_DESIGN_REQUIRED", "ROLLOUT_STAGES",
    "RUNTIME_DEPENDENCY_GRAPH", "RESTORE_TRIGGERS", "RuntimeFeatureFlags",
    "TARGET_SCHEMA", "authorization_flags", "build_prepare_api_response",
    "classify_authentication", "classify_migration_stage_failure", "classify_prepare_status",
    "classify_restore_trigger",
    "contract_metadata", "evaluate_feature_gate", "evaluate_kill_switch",
    "evaluate_maintenance_transition", "evaluate_restore_outcome", "evaluate_rollout_transition",
    "evaluate_start_render_boundary",
    "http_status_for_prepare", "parse_feature_flags", "production_readiness",
    "redact_for_public", "runtime_dependency_graph", "validate_activation_preflight",
    "validate_audit_event", "validate_backup_evidence", "validate_migration_postflight",
    "validate_operator_confirmation", "validate_prepare_api_request",
    "validate_public_payload",
]
