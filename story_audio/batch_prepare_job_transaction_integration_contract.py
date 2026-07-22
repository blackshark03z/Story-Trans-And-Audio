from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Protocol, Sequence


CONTRACT_SCHEMA = "story-audio-batch-prepare-job-transaction-integration-contract/v1"
DESIGN_STATUS = "DESIGN_ONLY"

TARGET_PHASE_PREPARE = "PREPARE"
REQUEST_STATE_APPLYING = "APPLYING"
PREPARED_STATUS = "prepared"
PENDING_JOB_CHAPTER_STATUS = "pending"

OP_RELOAD_REQUEST = "RELOAD_REQUEST_IN_TRANSACTION"
OP_RELOAD_AUTHORITATIVE_INPUTS = "RELOAD_AUTHORITATIVE_INPUTS_IN_TRANSACTION"
OP_CHECK_EXISTING_LINKAGE = "CHECK_EXISTING_LINKAGE"
OP_CHECK_CONFLICTING_LINKAGE = "CHECK_CONFLICTING_LINKAGE"
OP_CHECK_JOB_CONFLICTS = "CHECK_JOB_CONFLICTS"
OP_INSERT_JOB = "INSERT_PREPARED_JOB"
OP_INSERT_JOB_CHAPTER = "INSERT_JOB_CHAPTER"
OP_INSERT_LINKAGE = "INSERT_REQUEST_JOB_LINKAGE"
OP_VALIDATE_COUNTS = "VALIDATE_COUNTS_AND_BINDINGS"
OP_COMMIT = "COMMIT_TRANSACTION"
OP_RELOAD_EVIDENCE = "RELOAD_COMMITTED_EVIDENCE"
OP_ELIGIBLE_APPLIED = "MARK_ELIGIBLE_FOR_APPLIED_RECORD"

VALID_TRANSACTION_DECISION = "VALID_TRANSACTION_PLAN"
INVALID_TRANSACTION_PLAN = "INVALID_TRANSACTION_PLAN"
PRECONDITION_REJECTED = "PRECONDITION_REJECTED"
TRANSACTION_SCOPE_REJECTED = "TRANSACTION_SCOPE_REJECTED"
WRITE_SET_REJECTED = "WRITE_SET_REJECTED"
LINKAGE_EVIDENCE_REJECTED = "LINKAGE_EVIDENCE_REJECTED"

COMMITTED = "COMMITTED"
REPLAYED_COMMITTED = "REPLAYED_COMMITTED"
DETERMINISTIC_CONFLICT = "DETERMINISTIC_CONFLICT"
ROLLBACK_CONFIRMED = "ROLLBACK_CONFIRMED"
ROLLBACK_REQUIRED = "ROLLBACK_REQUIRED"
OUTCOME_AMBIGUOUS = "OUTCOME_AMBIGUOUS"
CORRUPT_STATE = "CORRUPT_STATE"

RECOVER_COMMITTED_TRANSACTION = "RECOVER_COMMITTED_TRANSACTION"
CONFIRMED_ROLLBACK_NO_COMMIT = "CONFIRMED_ROLLBACK_NO_COMMIT"
TRANSACTION_OUTCOME_AMBIGUOUS = "TRANSACTION_OUTCOME_AMBIGUOUS"
REQUEST_JOB_CONFLICT = "REQUEST_JOB_CONFLICT"
CORRUPT_COMMITTED_STATE = "CORRUPT_COMMITTED_STATE"
OPERATOR_REVIEW_REQUIRED = "OPERATOR_REVIEW_REQUIRED"

DESIGN_READY_FOR_ISOLATED_IMPLEMENTATION_ASSESSMENT = "DESIGN_READY_FOR_ISOLATED_IMPLEMENTATION_ASSESSMENT"
BLOCKED_BY_TRANSACTION_ABSTRACTION = "BLOCKED_BY_TRANSACTION_ABSTRACTION"
BLOCKED_BY_OWNERSHIP_EVIDENCE = "BLOCKED_BY_OWNERSHIP_EVIDENCE"
BLOCKED_BY_CONFLICT_RACE = "BLOCKED_BY_CONFLICT_RACE"
BLOCKED_BY_AUTHORITATIVE_INPUT_REVALIDATION = "BLOCKED_BY_AUTHORITATIVE_INPUT_REVALIDATION"

AUTHORIZATION_FLAGS = {
    "integration_implementation_authorized": False,
    "pipeline_modification_authorized": False,
    "real_job_execution": False,
    "mutation_authorized": False,
    "execution_endpoint_available": False,
    "prepare_starts_render": False,
}

REQUIRED_OPERATION_ORDER = (
    OP_RELOAD_REQUEST,
    OP_RELOAD_AUTHORITATIVE_INPUTS,
    OP_CHECK_EXISTING_LINKAGE,
    OP_CHECK_CONFLICTING_LINKAGE,
    OP_CHECK_JOB_CONFLICTS,
    OP_INSERT_JOB,
    OP_INSERT_JOB_CHAPTER,
    OP_INSERT_LINKAGE,
    OP_VALIDATE_COUNTS,
    OP_COMMIT,
    OP_RELOAD_EVIDENCE,
    OP_ELIGIBLE_APPLIED,
)


class TransactionManager(Protocol):
    def begin_isolated_write_transaction(self) -> object:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...


class RequestExecutionRepository(Protocol):
    def load_and_verify_applying_request(self, transaction: object, request_identity: str) -> Mapping[str, Any]:
        ...


class AuthoritativeInputRepository(Protocol):
    def reload_and_verify_chapter_inputs(self, transaction: object, chapter_ids: Sequence[int]) -> Mapping[str, Any]:
        ...


class JobConflictInspector(Protocol):
    def inspect_overlapping_prepared_or_active_jobs(self, transaction: object, chapter_ids: Sequence[int]) -> Mapping[str, Any]:
        ...


class PreparedJobWriter(Protocol):
    def insert_prepared_job_with_chapters(self, transaction: object, write_set: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


class RequestJobLinkWriter(Protocol):
    def insert_request_job_linkage(self, transaction: object, linkage: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


class CommitEvidenceReader(Protocol):
    def reload_committed_evidence(self, request_identity: str) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class TransactionScopedDependencies:
    transaction_owner: str
    request_repository_scoped: bool
    authoritative_inputs_scoped: bool
    conflict_inspector_scoped: bool
    job_writer_scoped: bool
    link_writer_scoped: bool
    evidence_reader_post_commit: bool
    nested_autonomous_commit: bool = False
    self_committing_repository: bool = False
    connection_mismatch: bool = False


@dataclass(frozen=True)
class RequestPreconditions:
    request_exists: bool = True
    identity_matches: bool = True
    target_phase: str = TARGET_PHASE_PREPARE
    state: str = REQUEST_STATE_APPLYING
    fingerprint_matches: bool = True
    ownership_attempt_matches: bool = True
    ownership_token_present: bool = True
    ownership_token_matches: bool = True
    ownership_generation_matches: bool = True
    ownership_lease_active: bool = True
    authoritative_inputs_match: bool = True
    active_text_revisions_match: bool = True
    approved_casting_plans_match: bool = True
    existing_request_link_conflict: bool = False
    existing_job_link_conflict: bool = False


@dataclass(frozen=True)
class TransactionOperationPlan:
    operations: tuple[str, ...]
    expected_chapter_count: int
    job_chapter_operations: tuple[int, ...]
    applied_persistence_inside_job_transaction: bool = False


@dataclass(frozen=True)
class JobWriteSet:
    job_insert_count: int
    job_status: str
    job_chapter_count: int
    expected_chapter_count: int
    duplicate_chapters: bool = False
    excluded_chapter_written: bool = False
    worker_wake: bool = False
    render_start: bool = False
    segment_write: bool = False
    artifact_write: bool = False
    audio_write: bool = False
    chapter_bindings: tuple[JobChapterBinding, ...] = ()


@dataclass(frozen=True)
class JobChapterBinding:
    chapter_id: int
    chapter_number: int
    text_revision_id: int
    casting_plan_id: int
    status: str = PENDING_JOB_CHAPTER_STATUS


@dataclass(frozen=True)
class LinkageCommitEvidence:
    linkage_visible_after_commit: bool
    request_identity_matches: bool
    job_visible_after_commit: bool
    job_status: str
    job_chapter_count: int
    expected_chapter_count: int
    snapshot_digest_matches: bool
    plan_fingerprint_matches: bool
    worker_woken: bool
    render_started: bool
    evidence_version: int = 1
    timestamp_is_sole_commit_proof: bool = False
    pre_commit_job_reference_only: bool = False
    conflicting_linkage: bool = False
    transaction_reference: str = "transaction-1"
    job_transaction_reference: str = "transaction-1"
    linkage_transaction_reference: str = "transaction-1"
    post_commit_transaction_reference: str = "transaction-1"
    chapter_bindings_verified: bool = True
    authoritative_inputs_revalidated: bool = True
    audit_failure_misreported_as_rollback: bool = False


@dataclass(frozen=True)
class RecoveryEvidence:
    linkage_count: int
    linkage_matches: bool = False
    job_visible: bool = False
    job_prepared: bool = False
    chapter_count_matches: bool = False
    digest_matches: bool = False
    fingerprint_matches: bool = False
    corrupt_state: bool = False
    multiple_unlinked_jobs: bool = False
    absence_reliable: bool = False
    unknown_outcome: bool = False


@dataclass(frozen=True)
class ImplementationGate:
    name: str
    current_support: str
    required_change: str
    blocks_implementation: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def authorization_flags() -> dict[str, bool]:
    return dict(AUTHORIZATION_FLAGS)


def contract_metadata() -> dict[str, Any]:
    return {
        "contract_schema": CONTRACT_SCHEMA,
        "design_status": DESIGN_STATUS,
        **authorization_flags(),
    }


def validate_operation_plan(plan: TransactionOperationPlan) -> dict[str, Any]:
    errors: list[str] = []
    positions = {operation: index for index, operation in enumerate(plan.operations)}
    for operation in REQUIRED_OPERATION_ORDER:
        operation_count = plan.operations.count(operation)
        if operation_count == 0:
            errors.append(f"MISSING_{operation}")
        elif operation_count != 1:
            errors.append(f"DUPLICATE_{operation}")
    for operation in plan.operations:
        if operation not in REQUIRED_OPERATION_ORDER:
            errors.append(f"UNKNOWN_OPERATION_{operation}")
    if not errors:
        for left, right in zip(REQUIRED_OPERATION_ORDER, REQUIRED_OPERATION_ORDER[1:]):
            if positions[left] > positions[right]:
                errors.append(f"ORDER_{left}_BEFORE_{right}")
    if plan.operations.count(OP_INSERT_JOB) != 1:
        errors.append("ONE_JOB_INSERT_REQUIRED")
    if plan.expected_chapter_count <= 0:
        errors.append("EXPECTED_CHAPTER_COUNT_REQUIRED")
    if len(plan.job_chapter_operations) != plan.expected_chapter_count:
        errors.append("EXACT_JOB_CHAPTER_OPERATION_COUNT_REQUIRED")
    if len(set(plan.job_chapter_operations)) != len(plan.job_chapter_operations):
        errors.append("DUPLICATE_JOB_CHAPTER_OPERATION")
    if plan.applied_persistence_inside_job_transaction:
        errors.append("APPLIED_PERSISTENCE_MUST_REMAIN_ORCHESTRATOR_TERMINAL_STEP")
    return _result(not errors, VALID_TRANSACTION_DECISION if not errors else INVALID_TRANSACTION_PLAN, errors=errors)


def validate_preconditions(preconditions: RequestPreconditions) -> dict[str, Any]:
    errors: list[str] = []
    if not preconditions.request_exists:
        errors.append("REQUEST_MISSING")
    if not preconditions.identity_matches:
        errors.append("REQUEST_IDENTITY_MISMATCH")
    if preconditions.target_phase != TARGET_PHASE_PREPARE:
        errors.append("REQUEST_PHASE_NOT_PREPARE")
    if preconditions.state != REQUEST_STATE_APPLYING:
        errors.append("REQUEST_STATE_NOT_APPLYING")
    if not preconditions.fingerprint_matches:
        errors.append("PLAN_FINGERPRINT_MISMATCH")
    if not preconditions.ownership_attempt_matches:
        errors.append("OWNERSHIP_ATTEMPT_MISMATCH")
    if not preconditions.ownership_token_present:
        errors.append("OWNERSHIP_TOKEN_REQUIRED")
    if not preconditions.ownership_token_matches:
        errors.append("OWNERSHIP_TOKEN_MISMATCH")
    if not preconditions.ownership_generation_matches:
        errors.append("OWNERSHIP_GENERATION_MISMATCH")
    if not preconditions.ownership_lease_active:
        errors.append("OWNERSHIP_LEASE_EXPIRED")
    if not preconditions.authoritative_inputs_match:
        errors.append("AUTHORITATIVE_INPUT_SNAPSHOT_MISMATCH")
    if not preconditions.active_text_revisions_match:
        errors.append("ACTIVE_TEXT_REVISION_MISMATCH")
    if not preconditions.approved_casting_plans_match:
        errors.append("APPROVED_CASTING_PLAN_MISMATCH")
    if preconditions.existing_request_link_conflict:
        errors.append("EXISTING_REQUEST_LINK_CONFLICT")
    if preconditions.existing_job_link_conflict:
        errors.append("EXISTING_JOB_LINK_CONFLICT")
    return _result(not errors, "PRECONDITIONS_VALID" if not errors else PRECONDITION_REJECTED, errors=errors)


def validate_transaction_scope(dependencies: TransactionScopedDependencies) -> dict[str, Any]:
    errors: list[str] = []
    if dependencies.transaction_owner != "future_integration_service":
        errors.append("SINGLE_INTEGRATION_SERVICE_TRANSACTION_OWNER_REQUIRED")
    if not dependencies.request_repository_scoped:
        errors.append("REQUEST_REPOSITORY_MUST_USE_CALLER_TRANSACTION")
    if not dependencies.authoritative_inputs_scoped:
        errors.append("AUTHORITATIVE_INPUTS_MUST_USE_CALLER_TRANSACTION")
    if not dependencies.conflict_inspector_scoped:
        errors.append("CONFLICT_INSPECTOR_MUST_USE_CALLER_TRANSACTION")
    if not dependencies.job_writer_scoped:
        errors.append("JOB_WRITER_MUST_USE_CALLER_TRANSACTION")
    if not dependencies.link_writer_scoped:
        errors.append("LINK_WRITER_MUST_USE_CALLER_TRANSACTION")
    if not dependencies.evidence_reader_post_commit:
        errors.append("POST_COMMIT_EVIDENCE_RELOAD_REQUIRED")
    if dependencies.nested_autonomous_commit:
        errors.append("NESTED_AUTONOMOUS_COMMIT_REJECTED")
    if dependencies.self_committing_repository:
        errors.append("REPOSITORY_SELF_COMMIT_REJECTED")
    if dependencies.connection_mismatch:
        errors.append("TRANSACTION_CONNECTION_MISMATCH")
    return _result(not errors, "TRANSACTION_SCOPE_VALID" if not errors else TRANSACTION_SCOPE_REJECTED, errors=errors)


def validate_write_set(write_set: JobWriteSet) -> dict[str, Any]:
    errors: list[str] = []
    if write_set.job_insert_count != 1:
        errors.append("EXACTLY_ONE_JOB_INSERT_REQUIRED")
    if write_set.job_status != PREPARED_STATUS:
        errors.append("JOB_STATUS_MUST_BE_PREPARED")
    if write_set.expected_chapter_count <= 0:
        errors.append("EXPECTED_CHAPTER_COUNT_REQUIRED")
    if write_set.job_chapter_count != write_set.expected_chapter_count:
        errors.append("JOB_CHAPTER_COUNT_MISMATCH")
    if len(write_set.chapter_bindings) != write_set.expected_chapter_count:
        errors.append("JOB_CHAPTER_BINDING_COUNT_MISMATCH")
    chapter_ids = [binding.chapter_id for binding in write_set.chapter_bindings]
    if len(set(chapter_ids)) != len(chapter_ids):
        errors.append("DUPLICATE_JOB_CHAPTER_ID")
    for binding in write_set.chapter_bindings:
        if binding.chapter_id <= 0 or binding.chapter_number <= 0:
            errors.append("INVALID_JOB_CHAPTER_IDENTITY")
        if binding.text_revision_id <= 0:
            errors.append("TEXT_REVISION_PIN_REQUIRED")
        if binding.casting_plan_id <= 0:
            errors.append("CASTING_PLAN_PIN_REQUIRED")
        if binding.status != PENDING_JOB_CHAPTER_STATUS:
            errors.append("JOB_CHAPTER_STATUS_MUST_BE_PENDING")
    if write_set.duplicate_chapters:
        errors.append("DUPLICATE_CHAPTER_BINDING")
    if write_set.excluded_chapter_written:
        errors.append("EXCLUDED_CHAPTER_WRITTEN")
    if write_set.worker_wake:
        errors.append("WORKER_WAKE_FORBIDDEN")
    if write_set.render_start:
        errors.append("RENDER_START_FORBIDDEN")
    if write_set.segment_write:
        errors.append("SEGMENT_WRITE_FORBIDDEN")
    if write_set.artifact_write:
        errors.append("ARTIFACT_WRITE_FORBIDDEN")
    if write_set.audio_write:
        errors.append("AUDIO_WRITE_FORBIDDEN")
    return _result(not errors, "WRITE_SET_VALID" if not errors else WRITE_SET_REJECTED, errors=errors)


def validate_linkage_and_commit_evidence(evidence: LinkageCommitEvidence) -> dict[str, Any]:
    errors: list[str] = []
    if evidence.pre_commit_job_reference_only:
        errors.append("PRE_COMMIT_JOB_REFERENCE_IS_NOT_SUCCESS")
    if not evidence.linkage_visible_after_commit:
        errors.append("COMMITTED_LINKAGE_NOT_VISIBLE")
    if not evidence.request_identity_matches:
        errors.append("REQUEST_IDENTITY_MISMATCH")
    if not evidence.job_visible_after_commit:
        errors.append("COMMITTED_JOB_NOT_VISIBLE")
    if evidence.job_status != PREPARED_STATUS:
        errors.append("JOB_STATUS_NOT_PREPARED")
    if evidence.job_chapter_count != evidence.expected_chapter_count:
        errors.append("JOB_CHAPTER_COUNT_MISMATCH")
    if not evidence.snapshot_digest_matches:
        errors.append("SNAPSHOT_DIGEST_MISMATCH")
    if not evidence.plan_fingerprint_matches:
        errors.append("PLAN_FINGERPRINT_MISMATCH")
    if evidence.worker_woken:
        errors.append("WORKER_WOKEN")
    if evidence.render_started:
        errors.append("RENDER_STARTED")
    if evidence.evidence_version != 1:
        errors.append("UNSUPPORTED_EVIDENCE_VERSION")
    if evidence.timestamp_is_sole_commit_proof:
        errors.append("TIMESTAMP_ALONE_IS_NOT_COMMIT_PROOF")
    if evidence.conflicting_linkage:
        errors.append("CONFLICTING_LINKAGE")
    transaction_references = {
        evidence.transaction_reference,
        evidence.job_transaction_reference,
        evidence.linkage_transaction_reference,
        evidence.post_commit_transaction_reference,
    }
    if not evidence.transaction_reference or "" in transaction_references:
        errors.append("TRANSACTION_REFERENCE_REQUIRED")
    elif len(transaction_references) != 1:
        errors.append("TRANSACTION_REFERENCE_MISMATCH")
    if not evidence.chapter_bindings_verified:
        errors.append("JOB_CHAPTER_BINDINGS_NOT_VERIFIED")
    if not evidence.authoritative_inputs_revalidated:
        errors.append("AUTHORITATIVE_INPUTS_NOT_REVALIDATED")
    if evidence.audit_failure_misreported_as_rollback:
        errors.append("POST_COMMIT_AUDIT_FAILURE_IS_NOT_ROLLBACK")
    return _result(not errors, "COMMIT_EVIDENCE_VALID" if not errors else LINKAGE_EVIDENCE_REJECTED, errors=errors)


def classify_duplicate_or_recovery(evidence: RecoveryEvidence) -> dict[str, Any]:
    if evidence.corrupt_state:
        return _decision(CORRUPT_COMMITTED_STATE, CORRUPT_STATE)
    if evidence.multiple_unlinked_jobs:
        return _decision(OPERATOR_REVIEW_REQUIRED, OUTCOME_AMBIGUOUS)
    if evidence.linkage_count > 1:
        return _decision(CORRUPT_COMMITTED_STATE, CORRUPT_STATE)
    if evidence.linkage_count == 1:
        if all(
            [
                evidence.linkage_matches,
                evidence.job_visible,
                evidence.job_prepared,
                evidence.chapter_count_matches,
                evidence.digest_matches,
                evidence.fingerprint_matches,
            ]
        ):
            return _decision(RECOVER_COMMITTED_TRANSACTION, REPLAYED_COMMITTED, rerun_allowed=False)
        return _decision(REQUEST_JOB_CONFLICT, DETERMINISTIC_CONFLICT)
    if evidence.unknown_outcome:
        return _decision(TRANSACTION_OUTCOME_AMBIGUOUS, OUTCOME_AMBIGUOUS)
    if evidence.absence_reliable:
        return _decision(CONFIRMED_ROLLBACK_NO_COMMIT, ROLLBACK_CONFIRMED)
    return _decision(TRANSACTION_OUTCOME_AMBIGUOUS, OUTCOME_AMBIGUOUS)


def classify_interruption(
    point: str,
    *,
    rollback_observed: bool = False,
    post_commit_evidence_valid: bool = False,
) -> dict[str, Any]:
    matrix = {
        "before_begin": ("no transaction", "no job/linkage", ROLLBACK_CONFIRMED, True),
        "after_request_revalidation": ("open transaction", "rollback must be observed", ROLLBACK_REQUIRED, False),
        "after_job_insert": ("uncommitted", "rollback must remove job", ROLLBACK_REQUIRED, False),
        "after_partial_job_chapters": ("uncommitted", "rollback must remove partial chapters", ROLLBACK_REQUIRED, False),
        "after_all_job_chapters": ("uncommitted", "rollback must remove job and chapters", ROLLBACK_REQUIRED, False),
        "after_linkage_insert": ("uncommitted", "rollback must remove linkage/job/chapters", ROLLBACK_REQUIRED, False),
        "during_commit": ("commit uncertain", "unknown until evidence reload", OUTCOME_AMBIGUOUS, False),
        "commit_succeeded_response_lost": ("commit outcome requires evidence", "reload linkage/job", OUTCOME_AMBIGUOUS, False),
        "commit_evidence_reload_failed": ("commit uncertain", "operator evidence required", OUTCOME_AMBIGUOUS, False),
        "applied_persistence_failed": ("commit outcome requires evidence", "request may remain APPLYING", OUTCOME_AMBIGUOUS, False),
    }
    state, durable_state, safe_result, retry = matrix.get(
        point,
        ("unknown", "unknown", OUTCOME_AMBIGUOUS, False),
    )
    precommit_points = {
        "after_request_revalidation",
        "after_job_insert",
        "after_partial_job_chapters",
        "after_all_job_chapters",
        "after_linkage_insert",
    }
    if point in precommit_points and rollback_observed:
        durable_state, safe_result, retry = "rollback and durable absence observed", ROLLBACK_CONFIRMED, True
    if point == "commit_succeeded_response_lost" and post_commit_evidence_valid:
        state, durable_state, safe_result = "committed", "verified linkage/job visible", REPLAYED_COMMITTED
    if point == "applied_persistence_failed" and post_commit_evidence_valid:
        state, durable_state, safe_result = "committed", "verified linkage/job visible; request may remain APPLYING", COMMITTED
    return {
        "contract_schema": CONTRACT_SCHEMA,
        "point": point,
        "transaction_state": state,
        "durable_state": durable_state,
        "safe_result": safe_result,
        "rerun_allowed": retry,
        "automatic_rerun": False,
        **authorization_flags(),
    }


def orchestrator_handoff(adapter_evidence: Mapping[str, Any]) -> dict[str, Any]:
    adapter_result = OUTCOME_AMBIGUOUS
    if adapter_evidence.get("valid") is True and adapter_evidence.get("code") == "COMMIT_EVIDENCE_VALID":
        adapter_result = COMMITTED
    elif (
        adapter_evidence.get("decision") == RECOVER_COMMITTED_TRANSACTION
        and adapter_evidence.get("transaction_decision") == REPLAYED_COMMITTED
    ):
        adapter_result = REPLAYED_COMMITTED
    elif adapter_evidence.get("transaction_decision") in {
        DETERMINISTIC_CONFLICT,
        ROLLBACK_CONFIRMED,
        OUTCOME_AMBIGUOUS,
        CORRUPT_STATE,
    }:
        adapter_result = str(adapter_evidence["transaction_decision"])
    mapping = {
        COMMITTED: (True, False, "orchestrator_may_record_applied_from_verified_evidence"),
        REPLAYED_COMMITTED: (True, False, "orchestrator_may_recover_applied_from_verified_evidence"),
        DETERMINISTIC_CONFLICT: (False, False, "orchestrator_records_rejected_or_failed_by_existing_contract"),
        ROLLBACK_CONFIRMED: (False, False, "orchestrator_records_safe_failure_or_reviewed_retryable_failure"),
        OUTCOME_AMBIGUOUS: (False, True, "operator_reconciliation_required_before_any_retry"),
        CORRUPT_STATE: (False, True, "fail_closed_operator_review_required"),
    }
    applied_allowed, review_required, instruction = mapping.get(adapter_result, (False, True, "unknown_result_fails_closed"))
    return {
        "contract_schema": CONTRACT_SCHEMA,
        "adapter_result": adapter_result,
        "verified_evidence_required": True,
        "eligible_for_applied_record": applied_allowed,
        "requires_operator_review": review_required,
        "instruction": instruction,
        "start_render_allowed": False,
        **authorization_flags(),
    }


def implementation_prerequisites() -> tuple[ImplementationGate, ...]:
    return (
        ImplementationGate("Caller-owned DB transaction", "Database supports BEGIN IMMEDIATE but current helpers own transactions", "Introduce integration-owned transaction boundary", True),
        ImplementationGate("Transaction-scoped Job writer", "Current job creation opens its own transaction", "Extract writer that accepts caller transaction", True),
        ImplementationGate("Transaction-scoped linkage writer", "Current linkage store opens its own transaction", "Extract writer that accepts caller transaction", True),
        ImplementationGate("Request reload in transaction", "Current request store opens its own transactions", "Add read/verify using caller transaction", True),
        ImplementationGate("Authoritative input revalidation", "Chapter eligibility, active revisions, and approved plans are read before Job transaction", "Reload and verify all immutable pins inside caller transaction", True),
        ImplementationGate("Durable ownership evidence", "State and attempt_count exist; no durable owner token", "Add owner token, monotonic fencing generation, lease, and guarded terminal writes", True),
        ImplementationGate("Conflict race protection", "Existing overlap check is query-based before insert", "Serialize per scope or add DB-enforced overlap protection", True),
        ImplementationGate("Linkage uniqueness", "Dormant schema 14 enforces request identity and job uniqueness", "Activate only after separate canonical approval", False),
        ImplementationGate("Commit evidence reload", "Linkage store can build evidence after commit", "Expose transaction-safe post-commit reader", False),
        ImplementationGate("Failure injection points", "Pure/fake tests exist; real boundary not instrumented", "Add isolated failure injection around each operation", True),
        ImplementationGate("Post-commit audit semantics", "Current audit is a separate transaction and can fail after Job commit", "Make audit failure non-authoritative or persist audit in the owning transaction", True),
        ImplementationGate("No-worker/no-render guarantee", "Prepared lifecycle and worker pickup exclusion exist", "Carry no-wake/no-render assertions into real adapter tests", False),
    )


def readiness_decision() -> dict[str, Any]:
    gate_rows = implementation_prerequisites()
    blockers = [gate.name for gate in gate_rows if gate.blocks_implementation]
    codes: list[str] = []
    if any("transaction" in gate.name.lower() or "writer" in gate.name.lower() for gate in gate_rows if gate.blocks_implementation):
        codes.append(BLOCKED_BY_TRANSACTION_ABSTRACTION)
    if any("ownership" in gate.name.lower() for gate in gate_rows if gate.blocks_implementation):
        codes.append(BLOCKED_BY_OWNERSHIP_EVIDENCE)
    if any("conflict race" in gate.name.lower() for gate in gate_rows if gate.blocks_implementation):
        codes.append(BLOCKED_BY_CONFLICT_RACE)
    if any("authoritative input" in gate.name.lower() for gate in gate_rows if gate.blocks_implementation):
        codes.append(BLOCKED_BY_AUTHORITATIVE_INPUT_REVALIDATION)
    return {
        "contract_schema": CONTRACT_SCHEMA,
        "overall_decision": DESIGN_READY_FOR_ISOLATED_IMPLEMENTATION_ASSESSMENT if not blockers else "IMPLEMENTATION_NOT_READY",
        "blockers": blockers,
        "blocker_codes": codes,
        "gates": [gate.as_dict() for gate in gate_rows],
        **authorization_flags(),
    }


def model_smoke_results() -> dict[str, Any]:
    valid_plan = validate_operation_plan(
        TransactionOperationPlan(
            operations=REQUIRED_OPERATION_ORDER,
            expected_chapter_count=3,
            job_chapter_operations=(1, 2, 3),
        )
    )
    wrong_order = validate_operation_plan(
        TransactionOperationPlan(
            operations=(
                OP_RELOAD_REQUEST,
                OP_INSERT_JOB,
                OP_INSERT_LINKAGE,
                OP_INSERT_JOB_CHAPTER,
                OP_COMMIT,
                OP_RELOAD_EVIDENCE,
                OP_ELIGIBLE_APPLIED,
            ),
            expected_chapter_count=1,
            job_chapter_operations=(1,),
        )
    )
    pre_commit = validate_linkage_and_commit_evidence(
        LinkageCommitEvidence(
            linkage_visible_after_commit=False,
            request_identity_matches=True,
            job_visible_after_commit=False,
            job_status=PREPARED_STATUS,
            job_chapter_count=3,
            expected_chapter_count=3,
            snapshot_digest_matches=True,
            plan_fingerprint_matches=True,
            worker_woken=False,
            render_started=False,
            pre_commit_job_reference_only=True,
        )
    )
    return {
        "valid_transaction_plan": valid_plan["valid"],
        "wrong_operation_order_rejected": not wrong_order["valid"],
        "pre_commit_response_rejected": not pre_commit["valid"],
        "commit_response_lost": classify_duplicate_or_recovery(
            RecoveryEvidence(
                linkage_count=1,
                linkage_matches=True,
                job_visible=True,
                job_prepared=True,
                chapter_count_matches=True,
                digest_matches=True,
                fingerprint_matches=True,
            )
        )["decision"],
        "unknown_commit_outcome": classify_duplicate_or_recovery(RecoveryEvidence(linkage_count=0, unknown_outcome=True))["decision"],
        "applied_persistence_failure": classify_interruption(
            "applied_persistence_failed", post_commit_evidence_valid=True
        )["automatic_rerun"],
        "real_db_writes": False,
        **authorization_flags(),
    }


def _result(valid: bool, code: str, *, errors: Sequence[str] = (), **extra: Any) -> dict[str, Any]:
    return {
        "contract_schema": CONTRACT_SCHEMA,
        "valid": valid,
        "code": code,
        "errors": list(errors),
        **extra,
        **authorization_flags(),
    }


def _decision(decision: str, result: str, *, rerun_allowed: bool = False) -> dict[str, Any]:
    return {
        "contract_schema": CONTRACT_SCHEMA,
        "decision": decision,
        "transaction_decision": result,
        "rerun_allowed": rerun_allowed,
        "automatic_rerun": False,
        "future_job_reference": None,
        **authorization_flags(),
    }


__all__ = [
    "BLOCKED_BY_CONFLICT_RACE",
    "BLOCKED_BY_AUTHORITATIVE_INPUT_REVALIDATION",
    "BLOCKED_BY_OWNERSHIP_EVIDENCE",
    "BLOCKED_BY_TRANSACTION_ABSTRACTION",
    "COMMITTED",
    "CONTRACT_SCHEMA",
    "CORRUPT_STATE",
    "DETERMINISTIC_CONFLICT",
    "DESIGN_READY_FOR_ISOLATED_IMPLEMENTATION_ASSESSMENT",
    "DESIGN_STATUS",
    "OPERATOR_REVIEW_REQUIRED",
    "OUTCOME_AMBIGUOUS",
    "RECOVER_COMMITTED_TRANSACTION",
    "REPLAYED_COMMITTED",
    "ROLLBACK_CONFIRMED",
    "ROLLBACK_REQUIRED",
    "CONFIRMED_ROLLBACK_NO_COMMIT",
    "TRANSACTION_OUTCOME_AMBIGUOUS",
    "TransactionOperationPlan",
    "TransactionScopedDependencies",
    "RequestPreconditions",
    "JobWriteSet",
    "JobChapterBinding",
    "LinkageCommitEvidence",
    "RecoveryEvidence",
    "ImplementationGate",
    "authorization_flags",
    "classify_duplicate_or_recovery",
    "classify_interruption",
    "contract_metadata",
    "implementation_prerequisites",
    "model_smoke_results",
    "orchestrator_handoff",
    "readiness_decision",
    "validate_linkage_and_commit_evidence",
    "validate_operation_plan",
    "validate_preconditions",
    "validate_transaction_scope",
    "validate_write_set",
]
