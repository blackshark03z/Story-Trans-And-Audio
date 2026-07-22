from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any


DESIGN_STATUS = "SCHEMA_STORE_IMPLEMENTED_NO_EXECUTION"
SUPPORTED_PHASE = "PREPARE"
AUTHORIZATION_STATUS = "PREPARE_EXECUTION_NOT_AUTHORIZED"
CONTRACT_SCHEMA = "story-audio-batch-prepare-idempotency-contract/v1"
REQUEST_SCHEMA = "story-audio-batch-prepare-request-binding/v1"
RESULT_SCHEMA = "story-audio-batch-prepare-result/v1"
CURRENT_SCHEMA_VERSION = 12
PROPOSED_SCHEMA_VERSION = 13
PROPOSED_REQUEST_TABLE = "batch_prepare_requests"

STATE_PLANNED = "PLANNED"
STATE_APPLYING = "APPLYING"
STATE_APPLIED = "APPLIED"
STATE_REJECTED = "REJECTED"
STATE_FAILED = "FAILED"

REQUEST_STATES = (
    STATE_PLANNED,
    STATE_APPLYING,
    STATE_APPLIED,
    STATE_REJECTED,
    STATE_FAILED,
)

TERMINAL_STATES = (STATE_APPLIED, STATE_REJECTED, STATE_FAILED)

ALLOWED_TRANSITIONS = {
    STATE_PLANNED: (STATE_APPLYING, STATE_REJECTED),
    STATE_APPLYING: (STATE_APPLIED, STATE_REJECTED, STATE_FAILED),
    STATE_APPLIED: (),
    STATE_REJECTED: (),
    STATE_FAILED: (),
}

DUPLICATE_PLANNED = "DUPLICATE_PLANNED_REPLAY_CURRENT_STATE"
DUPLICATE_APPLYING = "DUPLICATE_APPLYING_IN_PROGRESS"
DUPLICATE_APPLIED = "DUPLICATE_APPLIED_REPLAY_RESULT"
DUPLICATE_REJECTED = "DUPLICATE_REJECTED_REPLAY_REJECTION"
DUPLICATE_FAILED = "DUPLICATE_FAILED_REPLAY_FAILURE_REVIEW_REQUIRED"
DUPLICATE_FAILED_RETRYABLE = "DUPLICATE_FAILED_REPLAY_FAILURE_RETRYABLE"
DUPLICATE_FAILED_REVIEW_REQUIRED = DUPLICATE_FAILED
REQUEST_ID_CONFLICT = "REQUEST_ID_CONFLICT"

FAILURE_CODES = (
    "INVALID_REQUEST",
    "UNSUPPORTED_PHASE",
    "CONFIRMATION_REQUIRED",
    "STALE_PLAN",
    "NO_ELIGIBLE_CHAPTERS",
    "REQUEST_ID_CONFLICT",
    "PREPARE_CONFLICT",
    "APPLYING",
    "APPLIED",
    "FAILED_RETRYABLE",
    "FAILED_REVIEW_REQUIRED",
)

RETRYABLE_FAILURE_CODES = ("FAILED_RETRYABLE",)
REVIEW_REQUIRED_FAILURE_CODES = ("FAILED_REVIEW_REQUIRED", "PREPARE_CONFLICT")

CHAPTER_RESULT_FIELDS = (
    "chapter_id",
    "chapter_number",
    "plan_eligibility",
    "result_status",
    "job_chapter_id",
    "reason_codes",
    "created_or_reused",
)

SECRET_OR_UNSAFE_RESULT_KEYS = (
    "path",
    "absolute_path",
    "content_path",
    "text",
    "full_text",
    "casting_plan_blob",
    "voice_snapshot_json",
    "secret",
    "api_key",
    "traceback",
)

CLIENT_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
PLAN_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


class PreparePersistenceContractError(ValueError):
    """Raised when a pure Phase 2 persistence contract input is invalid."""


@dataclass(frozen=True)
class PrepareRequestBinding:
    client_request_id: str
    request_identity: str
    target_phase: str
    book_id: int
    from_chapter: int
    to_chapter: int
    plan_fingerprint: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _coerce_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise PreparePersistenceContractError(f"{field_name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PreparePersistenceContractError(f"{field_name} must be an integer") from exc
    if parsed < 1:
        raise PreparePersistenceContractError(f"{field_name} must be positive")
    return parsed


def normalize_client_request_id(value: Any) -> str:
    if not isinstance(value, str):
        raise PreparePersistenceContractError("client_request_id is required")
    normalized = value.strip()
    if not normalized:
        raise PreparePersistenceContractError("client_request_id is required")
    if len(normalized) > 200:
        raise PreparePersistenceContractError("client_request_id is too long")
    if not CLIENT_REQUEST_ID_RE.match(normalized):
        raise PreparePersistenceContractError(
            "client_request_id may contain only letters, numbers, dot, dash, underscore, and colon"
        )
    return normalized


def normalize_target_phase(value: Any) -> str:
    phase = str(value or "").strip().upper()
    if phase != SUPPORTED_PHASE:
        raise PreparePersistenceContractError("Only target_phase PREPARE is supported")
    return phase


def normalize_plan_fingerprint(value: Any) -> str:
    if not isinstance(value, str) or not PLAN_FINGERPRINT_RE.match(value):
        raise PreparePersistenceContractError("plan_fingerprint must be a 64-character lowercase hex value")
    return value


def build_request_identity(
    *,
    client_request_id: str,
    target_phase: str,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    plan_fingerprint: str,
) -> str:
    payload = {
        "schema": REQUEST_SCHEMA,
        "client_request_id": normalize_client_request_id(client_request_id),
        "target_phase": normalize_target_phase(target_phase),
        "book_id": _coerce_int(book_id, "book_id"),
        "from_chapter": _coerce_int(from_chapter, "from_chapter"),
        "to_chapter": _coerce_int(to_chapter, "to_chapter"),
        "plan_fingerprint": normalize_plan_fingerprint(plan_fingerprint),
    }
    if payload["from_chapter"] > payload["to_chapter"]:
        raise PreparePersistenceContractError("from_chapter must be less than or equal to to_chapter")
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def build_request_binding(request: Mapping[str, Any]) -> PrepareRequestBinding:
    if not isinstance(request, Mapping):
        raise PreparePersistenceContractError("Request must be an object")
    if request.get("explicit_confirmation") is not True:
        raise PreparePersistenceContractError("explicit_confirmation must be true")

    client_request_id = normalize_client_request_id(request.get("client_request_id"))
    target_phase = normalize_target_phase(request.get("target_phase"))
    book_id = _coerce_int(request.get("book_id"), "book_id")
    from_chapter = _coerce_int(request.get("from_chapter"), "from_chapter")
    to_chapter = _coerce_int(request.get("to_chapter"), "to_chapter")
    if from_chapter > to_chapter:
        raise PreparePersistenceContractError("from_chapter must be less than or equal to to_chapter")
    plan_fingerprint = normalize_plan_fingerprint(request.get("plan_fingerprint"))
    request_identity = build_request_identity(
        client_request_id=client_request_id,
        target_phase=target_phase,
        book_id=book_id,
        from_chapter=from_chapter,
        to_chapter=to_chapter,
        plan_fingerprint=plan_fingerprint,
    )
    return PrepareRequestBinding(
        client_request_id=client_request_id,
        request_identity=request_identity,
        target_phase=target_phase,
        book_id=book_id,
        from_chapter=from_chapter,
        to_chapter=to_chapter,
        plan_fingerprint=plan_fingerprint,
    )


def allowed_transition(current_state: str, next_state: str) -> bool:
    current = str(current_state or "").upper()
    target = str(next_state or "").upper()
    return target in ALLOWED_TRANSITIONS.get(current, ())


def classify_duplicate_request(
    *,
    existing_state: str,
    same_client_request_id: bool,
    same_request_identity: bool,
    existing_error_code: str | None = None,
) -> str:
    if not same_client_request_id or not same_request_identity:
        return REQUEST_ID_CONFLICT
    state = str(existing_state or "").upper()
    if state == STATE_PLANNED:
        return DUPLICATE_PLANNED
    if state == STATE_APPLYING:
        return DUPLICATE_APPLYING
    if state == STATE_APPLIED:
        return DUPLICATE_APPLIED
    if state == STATE_REJECTED:
        return DUPLICATE_REJECTED
    if state == STATE_FAILED:
        if existing_error_code in RETRYABLE_FAILURE_CODES:
            return DUPLICATE_FAILED_RETRYABLE
        return DUPLICATE_FAILED_REVIEW_REQUIRED
    raise PreparePersistenceContractError(f"Unknown request state: {existing_state}")


def build_result_payload(
    binding: PrepareRequestBinding,
    *,
    state: str,
    job_id: int | None,
    chapter_results: list[Mapping[str, Any]],
    error_code: str | None = None,
    error_message: str | None = None,
    attempt_count: int = 0,
) -> dict[str, Any]:
    normalized_state = str(state or "").upper()
    if normalized_state not in REQUEST_STATES:
        raise PreparePersistenceContractError("Result state is invalid")
    if error_code is not None and error_code not in FAILURE_CODES:
        raise PreparePersistenceContractError("error_code is not part of the public failure taxonomy")
    cleaned_chapters = []
    for row in chapter_results:
        cleaned = {field: row.get(field) for field in CHAPTER_RESULT_FIELDS}
        cleaned_chapters.append(cleaned)
    return {
        "schema": RESULT_SCHEMA,
        "result_schema_version": 1,
        "request_identity": binding.request_identity,
        "client_request_id": binding.client_request_id,
        "target_phase": binding.target_phase,
        "book_id": binding.book_id,
        "from_chapter": binding.from_chapter,
        "to_chapter": binding.to_chapter,
        "plan_fingerprint": binding.plan_fingerprint,
        "state": normalized_state,
        "job_id": job_id,
        "chapter_results": cleaned_chapters,
        "error_code": error_code,
        "error_message": error_message,
        "attempt_count": int(attempt_count),
        "mutation_authorized": False,
        "execution_endpoint_available": False,
        "prepare_starts_render": False,
    }


def build_replay_contract(
    *,
    existing_state: str,
    stored_result_payload: Mapping[str, Any] | None,
    error_code: str | None = None,
) -> dict[str, Any]:
    state = str(existing_state or "").upper()
    if state not in REQUEST_STATES:
        raise PreparePersistenceContractError("existing_state is invalid")
    payload = dict(stored_result_payload or {})
    encoded = _canonical_json(payload)
    lowered = encoded.lower()
    for forbidden in SECRET_OR_UNSAFE_RESULT_KEYS:
        if forbidden in lowered:
            raise PreparePersistenceContractError("Stored result payload contains unsafe replay fields")
    decision = classify_duplicate_request(
        existing_state=state,
        same_client_request_id=True,
        same_request_identity=True,
        existing_error_code=error_code,
    )
    return {
        "schema": CONTRACT_SCHEMA,
        "status": decision,
        "state": state,
        "replay_source": "durable_request_record",
        "historical_result_replayed": state in {STATE_APPLIED, STATE_REJECTED, STATE_FAILED},
        "stored_result_payload": payload,
        "error_code": error_code,
        "mutation_authorized": False,
        "execution_endpoint_available": False,
        "prepare_starts_render": False,
    }


def get_persistence_design_contract() -> dict[str, Any]:
    return {
        "schema": CONTRACT_SCHEMA,
        "status": DESIGN_STATUS,
        "authorization": {
            "status": AUTHORIZATION_STATUS,
            "mutation_authorized": False,
            "execution_endpoint_available": False,
            "prepare_starts_render": False,
        },
        "request_identity": {
            "client_request_id": {
                "required": True,
                "max_length": 200,
                "format": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$",
                "normalization": "strip outer whitespace; preserve case; reject unsafe characters",
                "reuse_policy": "same client_request_id cannot bind to a different phase, scope, or fingerprint",
            },
            "canonical_request_identity": {
                "algorithm": "sha256(canonical_json(request_schema, client_request_id, target_phase, scope, plan_fingerprint))",
                "includes_timestamp": False,
                "includes_random_uuid": False,
                "distinct_from_plan_fingerprint": True,
            },
        },
        "payload_binding": {
            "bound_fields": [
                "client_request_id",
                "target_phase",
                "book_id",
                "from_chapter",
                "to_chapter",
                "plan_fingerprint",
            ],
            "same_client_request_id_different_payload": REQUEST_ID_CONFLICT,
            "latest_request_wins": False,
        },
        "state_machine": {
            "initial_state": STATE_PLANNED,
            "states": list(REQUEST_STATES),
            "terminal_states": list(TERMINAL_STATES),
            "allowed_transitions": {key: list(value) for key, value in ALLOWED_TRANSITIONS.items()},
            "retryable_states": [STATE_PLANNED, STATE_APPLYING],
            "failed_retry_policy": (
                "FAILED is replay-only for the same client_request_id. FAILED_RETRYABLE "
                "may be retried only by creating a fresh client_request_id after plan "
                "revalidation; FAILED_REVIEW_REQUIRED requires operator review first."
            ),
        },
        "duplicate_behavior": {
            STATE_PLANNED: DUPLICATE_PLANNED,
            STATE_APPLYING: DUPLICATE_APPLYING,
            STATE_APPLIED: DUPLICATE_APPLIED,
            STATE_REJECTED: DUPLICATE_REJECTED,
            STATE_FAILED: {
                "FAILED_RETRYABLE": DUPLICATE_FAILED_RETRYABLE,
                "FAILED_REVIEW_REQUIRED": DUPLICATE_FAILED_REVIEW_REQUIRED,
            },
        },
        "timeout_replay": {
            "same_client_request_id": "lookup durable request record",
            STATE_APPLYING: "return in-progress response; do not mark failed solely because of timeout",
            STATE_APPLIED: "replay stored result_payload with original job_id and chapter results",
            STATE_REJECTED: "replay stored deterministic rejection",
            STATE_FAILED: "replay stored failure; only a fresh client_request_id can create a new attempt",
            "different_payload": REQUEST_ID_CONFLICT,
        },
        "atomicity": {
            "recommended_option": "A_REQUEST_APPLYING_COMMITTED_BEFORE_JOB_TRANSACTION",
            "job_creation_policy": "all_or_nothing_job_and_job_chapters",
            "state_sequence": [STATE_PLANNED, STATE_APPLYING, STATE_APPLIED],
            "request_applying_committed_before_job_transaction": True,
            "request_and_job_in_one_transaction": False,
            "compare_and_transition": (
                "Future implementation must update PLANNED to APPLYING with a guarded "
                "WHERE state='PLANNED' predicate inside a transaction and treat zero "
                "updated rows as duplicate/in-progress/conflict."
            ),
            "abandoned_applying_recovery": (
                "A stale APPLYING row requires reconciliation by checking its bound job_id and any "
                "job linked by request audit metadata. If no Job exists and the plan "
                "fingerprint still matches current facts, mark FAILED_RETRYABLE for "
                "operator-visible retry with a fresh client_request_id. If a matching Job "
                "exists, complete APPLIED replay from that Job. If evidence is ambiguous "
                "or facts changed, mark FAILED_REVIEW_REQUIRED. Never auto-create a second Job."
            ),
            "stale_applying_threshold_minutes": 30,
        },
        "concurrency_uniqueness": {
            "unique_client_request_id": True,
            "unique_request_identity": True,
            "no_check_then_insert_only": True,
            "payload_binding_before_apply": True,
            "guarded_state_transition_required": True,
        },
        "batch_shape": {
            "one_request_one_job": True,
            "one_job_per_chapter": False,
            "job_chapters": "one JobChapter per eligible chapter",
        },
        "per_chapter_result": {
            "fields": list(CHAPTER_RESULT_FIELDS),
            "statuses": ["PREPARED", "EXCLUDED", "CONFLICT", "FAILED"],
            "excluded_chapters_have_job_chapter": False,
            "atomic_batch_mixed_success": False,
        },
        "result_replay": {
            "recommended_storage": "result_payload_json",
            "versioned_schema": RESULT_SCHEMA,
            "historical_not_current_readiness": True,
            "safe_field_policy": "no paths, secrets, full text, full casting plan blob, voice snapshot blob, or traceback",
        },
        "fingerprint_race_guard": {
            "validate_at_request": True,
            "validate_before_applying": True,
            "validate_inside_or_equivalent_to_protected_execution_boundary": True,
            "use_current_plan_to_rewrite_applied_result": False,
        },
        "failure_taxonomy": list(FAILURE_CODES),
        "retention": {
            STATE_APPLIED: "retain indefinitely until a separate reviewed cleanup policy exists",
            STATE_REJECTED: "retain at least through operator retry/replay window; initial implementation should retain indefinitely",
            STATE_FAILED: "retain indefinitely for audit and review",
            STATE_APPLYING: "retain; stale rows require reconciliation, not hard delete",
            "hard_delete_initially_allowed": False,
            "cleanup_implementation": "separate future task",
        },
        "proposed_migration": {
            "current_schema_version": CURRENT_SCHEMA_VERSION,
            "future_schema_version": PROPOSED_SCHEMA_VERSION,
            "implemented": True,
            "activation": "DORMANT_EXPLICIT_TARGET_ONLY",
            "artifact_path": "story_audio/migrations/dormant/0013_batch_prepare_requests.sql",
            "default_auto_discovered": False,
            "table": PROPOSED_REQUEST_TABLE,
            "columns": [
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("client_request_id", "TEXT NOT NULL"),
                ("request_identity", "TEXT NOT NULL"),
                ("book_id", "INTEGER NOT NULL REFERENCES books(id)"),
                ("from_chapter", "INTEGER NOT NULL"),
                ("to_chapter", "INTEGER NOT NULL"),
                ("target_phase", "TEXT NOT NULL CHECK(target_phase IN ('PREPARE'))"),
                ("plan_fingerprint", "TEXT NOT NULL"),
                ("state", "TEXT NOT NULL CHECK(state IN ('PLANNED','APPLYING','APPLIED','REJECTED','FAILED'))"),
                ("job_id", "INTEGER REFERENCES jobs(id)"),
                ("result_schema_version", "INTEGER"),
                ("result_payload_json", "TEXT"),
                ("error_code", "TEXT"),
                ("error_message", "TEXT"),
                ("attempt_count", "INTEGER NOT NULL DEFAULT 0"),
                ("applying_started_at", "TEXT"),
                ("completed_at", "TEXT"),
                ("created_at", "TEXT NOT NULL"),
                ("updated_at", "TEXT NOT NULL"),
            ],
            "unique_constraints": ["UNIQUE(client_request_id)", "UNIQUE(request_identity)"],
            "check_constraints": [
                "target_phase IN ('PREPARE')",
                "state IN ('PLANNED','APPLYING','APPLIED','REJECTED','FAILED')",
                "from_chapter <= to_chapter",
            ],
            "indexes": [
                "idx_batch_prepare_requests_state_updated",
                "idx_batch_prepare_requests_job",
                "idx_batch_prepare_requests_scope",
            ],
        },
        "authorization_gates": [
            "canonical schema activation in a separate task",
            "offline migration upgrade tests",
            "runtime API route implementation in a separate task",
            "explicit confirmation remains mandatory",
            "START_RENDER remains a separate action",
        ],
    }
