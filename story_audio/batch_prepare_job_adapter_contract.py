from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


CONTRACT_SCHEMA = "story-audio-batch-prepare-job-adapter-contract/v1"
RESULT_SCHEMA_VERSION = 1
DESIGN_STATUS = "DESIGN_ONLY"

TARGET_PHASE_PREPARE = "PREPARE"
REQUEST_STATE_APPLYING = "APPLYING"
PREPARED_JOB_STATUS = "prepared"
PENDING_JOB_CHAPTER_STATUS = "pending"

ADAPTER_INPUT_INVALID = "ADAPTER_INPUT_INVALID"
REQUEST_STATE_NOT_APPLYING = "REQUEST_STATE_NOT_APPLYING"
REQUEST_BINDING_MISMATCH = "REQUEST_BINDING_MISMATCH"
PLAN_SNAPSHOT_MISMATCH = "PLAN_SNAPSHOT_MISMATCH"
EXISTING_JOB_CONFLICT = "EXISTING_JOB_CONFLICT"
TRANSACTION_FAILED_ROLLED_BACK = "TRANSACTION_FAILED_ROLLED_BACK"
TRANSACTION_OUTCOME_AMBIGUOUS = "TRANSACTION_OUTCOME_AMBIGUOUS"
COMMIT_EVIDENCE_INVALID = "COMMIT_EVIDENCE_INVALID"
LINKAGE_CONFLICT = "LINKAGE_CONFLICT"
RESULT_PERSISTENCE_REQUIRED = "RESULT_PERSISTENCE_REQUIRED"
OPERATOR_REVIEW_REQUIRED = "OPERATOR_REVIEW_REQUIRED"

EXISTING_PREPARED_JOB = "EXISTING_PREPARED_JOB"
EXISTING_ACTIVE_JOB = "EXISTING_ACTIVE_JOB"
REQUEST_JOB_LINK_CONFLICT = "REQUEST_JOB_LINK_CONFLICT"
CHAPTER_ALREADY_BOUND = "CHAPTER_ALREADY_BOUND"
PLAN_SNAPSHOT_CONFLICT = "PLAN_SNAPSHOT_CONFLICT"
TRANSACTION_EVIDENCE_MISSING = "TRANSACTION_EVIDENCE_MISSING"

EVIDENCE_NONE = "NONE"
EVIDENCE_TRANSACTION_NOT_FOUND = "TRANSACTION_NOT_FOUND"
EVIDENCE_PREPARED_JOB_COMMITTED = "PREPARED_JOB_COMMITTED"
EVIDENCE_JOB_PARTIAL_OR_CORRUPT = "JOB_PARTIAL_OR_CORRUPT"
EVIDENCE_ACTIVE_JOB_FOUND = "ACTIVE_JOB_FOUND"
EVIDENCE_COMPLETED_JOB_FOUND = "COMPLETED_JOB_FOUND"
EVIDENCE_MULTIPLE_MATCHING_JOBS = "MULTIPLE_MATCHING_JOBS"
EVIDENCE_LINKAGE_MISMATCH = "LINKAGE_MISMATCH"
EVIDENCE_UNKNOWN = "UNKNOWN"
EVIDENCE_JOB_REFERENCE_WITHOUT_COMMIT = "JOB_REFERENCE_WITHOUT_COMMIT"
EVIDENCE_LEGACY_UNLINKED_JOB = "LEGACY_UNLINKED_JOB"

RECONCILE_SAFE_NO_COMMIT_CONFIRMED = "SAFE_NO_COMMIT_CONFIRMED"
RECONCILE_RECOVER_COMMITTED_RESULT = "RECOVER_COMMITTED_RESULT"
RECONCILE_OPERATOR_REVIEW_REQUIRED = "OPERATOR_REVIEW_REQUIRED"
RECONCILE_REQUEST_JOB_CONFLICT = "REQUEST_JOB_CONFLICT"
RECONCILE_CORRUPT_TRANSACTION_STATE = "CORRUPT_TRANSACTION_STATE"

DUPLICATE_REPLAY_COMMITTED_RESULT = "DUPLICATE_REPLAY_COMMITTED_RESULT"
DUPLICATE_NO_SAFE_RETRY = "DUPLICATE_NO_SAFE_RETRY"
DUPLICATE_SECOND_JOB_NOT_ALLOWED = "DUPLICATE_SECOND_JOB_NOT_ALLOWED"

HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")
ACTIVE_JOB_STATUSES = frozenset(
    {"scheduled", "queued", "running", "repairing", "synthesizing", "assembling", "paused", "interrupted"}
)

AUTHORIZATION_GATES = {
    "adapter_implementation_authorized": False,
    "real_job_execution": False,
    "mutation_authorized": False,
    "execution_endpoint_available": False,
    "prepare_starts_render": False,
}


@dataclass(frozen=True)
class ChapterPrepareSnapshot:
    book_id: int
    chapter_id: int
    chapter_number: int
    text_revision_id: int
    casting_plan_id: int
    casting_plan_revision: int
    eligibility_evidence: tuple[str, ...]
    deterministic_order: int


@dataclass(frozen=True)
class AdapterInput:
    request_id: int
    client_request_id: str
    request_identity: str
    book_id: int
    from_chapter: int
    to_chapter: int
    target_phase: str
    plan_fingerprint: str
    request_state: str
    eligible_chapters: tuple[ChapterPrepareSnapshot, ...]
    orchestration_attempt: int
    explicit_no_render: bool = True
    source: str = "second_validated_current_plan_snapshot"


@dataclass(frozen=True)
class JobChapterEvidence:
    chapter_id: int
    chapter_number: int
    job_chapter_reference: str
    status: str = PENDING_JOB_CHAPTER_STATUS


@dataclass(frozen=True)
class TransactionEvidence:
    request_identity: str
    job_reference: str
    committed: bool
    committed_at: str | None
    prepared_status: str
    expected_chapter_count: int
    actual_chapter_count: int
    chapter_snapshot_digest: str
    plan_fingerprint: str
    worker_woken: bool
    render_started: bool
    job_chapters: tuple[JobChapterEvidence, ...]
    transaction_evidence_version: int = RESULT_SCHEMA_VERSION


@dataclass(frozen=True)
class ExternalJobEvidence:
    evidence_state: str
    request_identity: str | None = None
    job_reference: str | None = None
    chapter_snapshot_digest: str | None = None
    plan_fingerprint: str | None = None
    prepared_status: str | None = None
    committed: bool | None = None
    job_count: int = 0
    details: Mapping[str, Any] = field(default_factory=dict)


def authorization_gates() -> dict[str, bool]:
    return dict(AUTHORIZATION_GATES)


def contract_metadata() -> dict[str, Any]:
    return {
        "contract_schema": CONTRACT_SCHEMA,
        "status": DESIGN_STATUS,
        **authorization_gates(),
    }


def chapter_snapshot_digest(chapters: Sequence[ChapterPrepareSnapshot]) -> str:
    rows = [
        {
            "book_id": chapter.book_id,
            "chapter_id": chapter.chapter_id,
            "chapter_number": chapter.chapter_number,
            "text_revision_id": chapter.text_revision_id,
            "casting_plan_id": chapter.casting_plan_id,
            "casting_plan_revision": chapter.casting_plan_revision,
            "eligibility_evidence": list(chapter.eligibility_evidence),
            "deterministic_order": chapter.deterministic_order,
        }
        for chapter in chapters
    ]
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_adapter_input(adapter_input: AdapterInput) -> dict[str, Any]:
    errors: list[str] = []
    if adapter_input.request_state != REQUEST_STATE_APPLYING:
        errors.append(REQUEST_STATE_NOT_APPLYING)
    if adapter_input.target_phase != TARGET_PHASE_PREPARE:
        errors.append("UNSUPPORTED_TARGET_PHASE")
    if not HEX_64_RE.match(adapter_input.request_identity or ""):
        errors.append("MISSING_OR_INVALID_REQUEST_IDENTITY")
    if not adapter_input.client_request_id:
        errors.append("MISSING_CLIENT_REQUEST_ID")
    if not HEX_64_RE.match(adapter_input.plan_fingerprint or ""):
        errors.append("MISSING_OR_INVALID_PLAN_FINGERPRINT")
    if adapter_input.from_chapter > adapter_input.to_chapter:
        errors.append("INVALID_SCOPE")
    if not adapter_input.explicit_no_render:
        errors.append("NO_RENDER_INSTRUCTION_REQUIRED")
    if adapter_input.source != "second_validated_current_plan_snapshot":
        errors.append("UNTRUSTED_INPUT_SOURCE")
    errors.extend(_chapter_snapshot_errors(adapter_input))
    if errors:
        code = REQUEST_STATE_NOT_APPLYING if REQUEST_STATE_NOT_APPLYING in errors else ADAPTER_INPUT_INVALID
        return _result(False, code, errors=errors)
    return _result(
        True,
        None,
        chapter_count=len(adapter_input.eligible_chapters),
        chapter_snapshot_digest=chapter_snapshot_digest(adapter_input.eligible_chapters),
    )


def evaluate_committed_success(adapter_input: AdapterInput, evidence: TransactionEvidence) -> dict[str, Any]:
    validation = validate_adapter_input(adapter_input)
    if not validation["valid"]:
        return validation
    expected_digest = validation["chapter_snapshot_digest"]
    errors: list[str] = []
    if evidence.transaction_evidence_version != RESULT_SCHEMA_VERSION:
        errors.append("UNSUPPORTED_TRANSACTION_EVIDENCE_VERSION")
    if not evidence.committed or not evidence.committed_at:
        errors.append("TRANSACTION_NOT_COMMITTED")
    if not evidence.job_reference:
        errors.append("MISSING_JOB_REFERENCE")
    if evidence.request_identity != adapter_input.request_identity:
        errors.append(REQUEST_BINDING_MISMATCH)
    if evidence.plan_fingerprint != adapter_input.plan_fingerprint:
        errors.append(PLAN_SNAPSHOT_MISMATCH)
    if evidence.chapter_snapshot_digest != expected_digest:
        errors.append("CHAPTER_SNAPSHOT_DIGEST_MISMATCH")
    if evidence.prepared_status != PREPARED_JOB_STATUS:
        errors.append("JOB_STATUS_NOT_PREPARED")
    expected_count = len(adapter_input.eligible_chapters)
    if evidence.expected_chapter_count != expected_count or evidence.actual_chapter_count != expected_count:
        errors.append("CHAPTER_COUNT_MISMATCH")
    if len(evidence.job_chapters) != expected_count:
        errors.append("JOB_CHAPTER_EVIDENCE_INCOMPLETE")
    chapter_refs = [chapter.job_chapter_reference for chapter in evidence.job_chapters]
    if len(chapter_refs) != len(set(chapter_refs)):
        errors.append("DUPLICATE_JOB_CHAPTER_REFERENCE")
    evidence_chapter_ids = [chapter.chapter_id for chapter in evidence.job_chapters]
    expected_chapter_ids = [chapter.chapter_id for chapter in adapter_input.eligible_chapters]
    if evidence_chapter_ids != expected_chapter_ids:
        errors.append("JOB_CHAPTER_SNAPSHOT_MISMATCH")
    if evidence.worker_woken:
        errors.append("WORKER_WOKEN")
    if evidence.render_started:
        errors.append("RENDER_STARTED")
    if errors:
        return _result(False, COMMIT_EVIDENCE_INVALID, errors=errors, applied_eligible=False)
    return _result(
        True,
        None,
        applied_eligible=True,
        job_reference=evidence.job_reference,
        chapter_snapshot_digest=expected_digest,
        plan_fingerprint=adapter_input.plan_fingerprint,
    )


def build_historical_result_payload(adapter_input: AdapterInput, evidence: TransactionEvidence) -> dict[str, Any]:
    success = evaluate_committed_success(adapter_input, evidence)
    if not success["valid"]:
        return {
            "result_schema_version": RESULT_SCHEMA_VERSION,
            "status": COMMIT_EVIDENCE_INVALID,
            "applied_eligible": False,
            "errors": list(success["errors"]),
            **authorization_gates(),
        }
    return {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "request_identity": adapter_input.request_identity,
        "job_reference": evidence.job_reference,
        "job_status": PREPARED_JOB_STATUS,
        "chapter_count": len(evidence.job_chapters),
        "chapters": [
            {
                "chapter_id": chapter.chapter_id,
                "chapter_number": chapter.chapter_number,
                "job_chapter_reference": chapter.job_chapter_reference,
                "status": "PREPARED",
            }
            for chapter in evidence.job_chapters
        ],
        "chapter_snapshot_digest": evidence.chapter_snapshot_digest,
        "plan_fingerprint": evidence.plan_fingerprint,
        "committed_at": evidence.committed_at,
        "worker_woken": evidence.worker_woken,
        "render_started": evidence.render_started,
        "replay_source": "durable_adapter_commit_evidence",
        **authorization_gates(),
    }


def evaluate_duplicate_invocation(
    adapter_input: AdapterInput,
    evidence: TransactionEvidence | ExternalJobEvidence | None,
) -> dict[str, Any]:
    if evidence is None:
        return _result(
            False,
            TRANSACTION_EVIDENCE_MISSING,
            duplicate_action=DUPLICATE_NO_SAFE_RETRY,
            second_job_allowed=False,
        )
    if isinstance(evidence, TransactionEvidence):
        success = evaluate_committed_success(adapter_input, evidence)
        if success["valid"]:
            return _result(
                True,
                None,
                duplicate_action=DUPLICATE_REPLAY_COMMITTED_RESULT,
                second_job_allowed=False,
                job_reference=evidence.job_reference,
            )
        if not evidence.committed and evidence.job_reference:
            return _result(
                False,
                TRANSACTION_OUTCOME_AMBIGUOUS,
                duplicate_action=DUPLICATE_NO_SAFE_RETRY,
                second_job_allowed=False,
                errors=success["errors"],
            )
        return _result(
            False,
            LINKAGE_CONFLICT,
            duplicate_action=DUPLICATE_SECOND_JOB_NOT_ALLOWED,
            second_job_allowed=False,
            errors=success["errors"],
        )
    decision = classify_reconciliation_evidence(adapter_input, evidence)
    return {
        **decision,
        "second_job_allowed": False,
        "duplicate_action": (
            DUPLICATE_REPLAY_COMMITTED_RESULT
            if decision["decision"] == RECONCILE_RECOVER_COMMITTED_RESULT
            else DUPLICATE_NO_SAFE_RETRY
        ),
    }


def map_existing_job_conflict(evidence: ExternalJobEvidence) -> dict[str, Any]:
    state = evidence.evidence_state
    if state == EVIDENCE_PREPARED_JOB_COMMITTED:
        if evidence.request_identity:
            return _result(False, EXISTING_PREPARED_JOB, conflict_type="same_or_linked_prepared_job")
        return _result(False, EXISTING_PREPARED_JOB, conflict_type="legacy_unlinked_prepared_job")
    if state == EVIDENCE_ACTIVE_JOB_FOUND:
        return _result(False, EXISTING_ACTIVE_JOB, conflict_type="active_render_or_startable_job")
    if state == EVIDENCE_COMPLETED_JOB_FOUND:
        return _result(False, CHAPTER_ALREADY_BOUND, conflict_type="completed_historical_job")
    if state == EVIDENCE_LINKAGE_MISMATCH:
        return _result(False, REQUEST_JOB_LINK_CONFLICT, conflict_type="request_linkage_mismatch")
    if state == EVIDENCE_JOB_PARTIAL_OR_CORRUPT:
        return _result(False, TRANSACTION_EVIDENCE_MISSING, conflict_type="partial_or_corrupt_job")
    if state == EVIDENCE_MULTIPLE_MATCHING_JOBS:
        return _result(False, OPERATOR_REVIEW_REQUIRED, conflict_type="multiple_matching_jobs")
    return _result(False, EXISTING_JOB_CONFLICT, conflict_type="unknown_existing_job_conflict")


def classify_reconciliation_evidence(adapter_input: AdapterInput, evidence: ExternalJobEvidence) -> dict[str, Any]:
    state = evidence.evidence_state
    if state in {EVIDENCE_NONE, EVIDENCE_TRANSACTION_NOT_FOUND}:
        return _reconcile(RECONCILE_SAFE_NO_COMMIT_CONFIRMED, TRANSACTION_FAILED_ROLLED_BACK)
    if state == EVIDENCE_PREPARED_JOB_COMMITTED:
        if _external_evidence_matches(adapter_input, evidence):
            return _reconcile(RECONCILE_RECOVER_COMMITTED_RESULT, RESULT_PERSISTENCE_REQUIRED)
        return _reconcile(RECONCILE_REQUEST_JOB_CONFLICT, LINKAGE_CONFLICT)
    if state in {EVIDENCE_JOB_PARTIAL_OR_CORRUPT, EVIDENCE_JOB_REFERENCE_WITHOUT_COMMIT}:
        return _reconcile(RECONCILE_CORRUPT_TRANSACTION_STATE, TRANSACTION_OUTCOME_AMBIGUOUS)
    if state in {EVIDENCE_ACTIVE_JOB_FOUND, EVIDENCE_COMPLETED_JOB_FOUND, EVIDENCE_LINKAGE_MISMATCH}:
        return _reconcile(RECONCILE_REQUEST_JOB_CONFLICT, EXISTING_JOB_CONFLICT)
    if state in {EVIDENCE_MULTIPLE_MATCHING_JOBS, EVIDENCE_LEGACY_UNLINKED_JOB, EVIDENCE_UNKNOWN}:
        return _reconcile(RECONCILE_OPERATOR_REVIEW_REQUIRED, OPERATOR_REVIEW_REQUIRED)
    return _reconcile(RECONCILE_OPERATOR_REVIEW_REQUIRED, OPERATOR_REVIEW_REQUIRED)


def failure_before_commit() -> dict[str, Any]:
    return _result(
        False,
        TRANSACTION_FAILED_ROLLED_BACK,
        transaction_committed=False,
        job_durable=False,
        job_chapters_durable=False,
        second_job_allowed=False,
    )


def ambiguous_after_commit_response() -> dict[str, Any]:
    return _result(
        False,
        TRANSACTION_OUTCOME_AMBIGUOUS,
        transaction_committed="unknown",
        operator_action=OPERATOR_REVIEW_REQUIRED,
        second_job_allowed=False,
    )


def commit_confirmed_request_result_missing() -> dict[str, Any]:
    return _result(
        False,
        RESULT_PERSISTENCE_REQUIRED,
        transaction_committed=True,
        operator_action="APPLIED_RESULT_RECOVERY_REQUIRED",
        second_job_allowed=False,
    )


def _chapter_snapshot_errors(adapter_input: AdapterInput) -> list[str]:
    chapters = list(adapter_input.eligible_chapters)
    errors: list[str] = []
    if not chapters:
        return ["EMPTY_ELIGIBLE_CHAPTERS"]
    chapter_ids: set[int] = set()
    chapter_numbers: set[int] = set()
    orders: list[int] = []
    for chapter in chapters:
        if chapter.book_id != adapter_input.book_id:
            errors.append("CROSS_BOOK_CHAPTER")
        if chapter.chapter_number < adapter_input.from_chapter or chapter.chapter_number > adapter_input.to_chapter:
            errors.append("SCOPE_MISMATCH")
        if chapter.chapter_id in chapter_ids or chapter.chapter_number in chapter_numbers:
            errors.append("DUPLICATE_CHAPTER")
        chapter_ids.add(chapter.chapter_id)
        chapter_numbers.add(chapter.chapter_number)
        orders.append(chapter.deterministic_order)
        if chapter.text_revision_id <= 0 or chapter.casting_plan_id <= 0 or chapter.casting_plan_revision <= 0:
            errors.append("MISSING_REVISION_OR_PLAN_IDENTITY")
        if not chapter.eligibility_evidence:
            errors.append("MISSING_ELIGIBILITY_EVIDENCE")
    if orders != sorted(orders) or len(orders) != len(set(orders)):
        errors.append("NON_DETERMINISTIC_CHAPTER_ORDER")
    return sorted(set(errors))


def _external_evidence_matches(adapter_input: AdapterInput, evidence: ExternalJobEvidence) -> bool:
    validation = validate_adapter_input(adapter_input)
    if not validation["valid"]:
        return False
    return (
        evidence.request_identity == adapter_input.request_identity
        and evidence.plan_fingerprint == adapter_input.plan_fingerprint
        and evidence.chapter_snapshot_digest == validation["chapter_snapshot_digest"]
        and evidence.prepared_status == PREPARED_JOB_STATUS
        and evidence.committed is True
        and bool(evidence.job_reference)
    )


def _result(valid: bool, code: str | None, **extra: Any) -> dict[str, Any]:
    payload = {
        "contract_schema": CONTRACT_SCHEMA,
        "valid": valid,
        "code": code,
        "errors": extra.pop("errors", []),
        **authorization_gates(),
    }
    payload.update(extra)
    return payload


def _reconcile(decision: str, code: str) -> dict[str, Any]:
    return {
        "contract_schema": CONTRACT_SCHEMA,
        "decision": decision,
        "code": code,
        "automatic_mutation": False,
        "retry_transaction": False,
        **authorization_gates(),
    }


__all__ = [
    "ACTIVE_JOB_STATUSES",
    "ADAPTER_INPUT_INVALID",
    "AUTHORIZATION_GATES",
    "COMMIT_EVIDENCE_INVALID",
    "CONTRACT_SCHEMA",
    "DESIGN_STATUS",
    "DUPLICATE_NO_SAFE_RETRY",
    "DUPLICATE_REPLAY_COMMITTED_RESULT",
    "DUPLICATE_SECOND_JOB_NOT_ALLOWED",
    "EVIDENCE_ACTIVE_JOB_FOUND",
    "EVIDENCE_COMPLETED_JOB_FOUND",
    "EVIDENCE_JOB_PARTIAL_OR_CORRUPT",
    "EVIDENCE_JOB_REFERENCE_WITHOUT_COMMIT",
    "EVIDENCE_LEGACY_UNLINKED_JOB",
    "EVIDENCE_LINKAGE_MISMATCH",
    "EVIDENCE_MULTIPLE_MATCHING_JOBS",
    "EVIDENCE_NONE",
    "EVIDENCE_PREPARED_JOB_COMMITTED",
    "EVIDENCE_TRANSACTION_NOT_FOUND",
    "EVIDENCE_UNKNOWN",
    "EXISTING_ACTIVE_JOB",
    "EXISTING_JOB_CONFLICT",
    "EXISTING_PREPARED_JOB",
    "LINKAGE_CONFLICT",
    "OPERATOR_REVIEW_REQUIRED",
    "PLAN_SNAPSHOT_CONFLICT",
    "RECONCILE_CORRUPT_TRANSACTION_STATE",
    "RECONCILE_OPERATOR_REVIEW_REQUIRED",
    "RECONCILE_RECOVER_COMMITTED_RESULT",
    "RECONCILE_REQUEST_JOB_CONFLICT",
    "RECONCILE_SAFE_NO_COMMIT_CONFIRMED",
    "REQUEST_BINDING_MISMATCH",
    "REQUEST_JOB_LINK_CONFLICT",
    "REQUEST_STATE_NOT_APPLYING",
    "RESULT_PERSISTENCE_REQUIRED",
    "TARGET_PHASE_PREPARE",
    "TRANSACTION_EVIDENCE_MISSING",
    "TRANSACTION_FAILED_ROLLED_BACK",
    "TRANSACTION_OUTCOME_AMBIGUOUS",
    "AdapterInput",
    "ChapterPrepareSnapshot",
    "ExternalJobEvidence",
    "JobChapterEvidence",
    "TransactionEvidence",
    "ambiguous_after_commit_response",
    "authorization_gates",
    "build_historical_result_payload",
    "chapter_snapshot_digest",
    "classify_reconciliation_evidence",
    "commit_confirmed_request_result_missing",
    "contract_metadata",
    "evaluate_committed_success",
    "evaluate_duplicate_invocation",
    "failure_before_commit",
    "map_existing_job_conflict",
    "validate_adapter_input",
]
