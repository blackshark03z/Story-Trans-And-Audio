from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Callable

from .batch_plan import MUTATION_AUTHORIZATION_STATUS


SUPPORTED_PHASE = "PREPARE"

CONTRACT_ACCEPTED = "CONTRACT_ACCEPTED"
REJECTED_INVALID_REQUEST = "REJECTED_INVALID_REQUEST"
REJECTED_UNSUPPORTED_PHASE = "REJECTED_UNSUPPORTED_PHASE"
REJECTED_CONFIRMATION_REQUIRED = "REJECTED_CONFIRMATION_REQUIRED"
REJECTED_SCOPE_MISMATCH = "REJECTED_SCOPE_MISMATCH"
REJECTED_STALE_PLAN = "REJECTED_STALE_PLAN"
REJECTED_NO_ELIGIBLE_CHAPTERS = "REJECTED_NO_ELIGIBLE_CHAPTERS"
REJECTED_UNSUPPORTED_LIFECYCLE = "REJECTED_UNSUPPORTED_LIFECYCLE"

FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")

PlanProvider = Callable[..., dict[str, Any]]


def _base_response(
    *,
    status: str,
    request: dict[str, Any],
    current_plan: dict[str, Any] | None,
    submitted_fingerprint: str | None,
    reason: str,
) -> dict[str, Any]:
    current_scope = current_plan.get("scope") if current_plan else None
    current_fingerprint = current_plan.get("plan_fingerprint") if current_plan else None
    return {
        "schema": "story-audio-batch-prepare-contract/v1",
        "status": status,
        "reason": reason,
        "mutation_authorized": False,
        "execution_endpoint_available": False,
        "requested_phase": str(request.get("target_phase") or "").upper(),
        "supported_phase": SUPPORTED_PHASE,
        "scope": current_scope or _request_scope(request),
        "submitted_fingerprint": submitted_fingerprint,
        "current_fingerprint": current_fingerprint,
        "confirmation": {
            "required": True,
            "received": bool(request.get("explicit_confirmation") is True),
        },
        "eligible_chapters": [],
        "excluded_chapters": list(current_plan.get("excluded") or []) if current_plan else [],
        "execution_intent": [],
        "planned_result_contract": {
            "unit": "chapter",
            "actual_mutation_performed": False,
            "success_status_name": "PREPARE_PLANNED_ONLY",
            "failure_status_name": "PREPARE_NOT_ATTEMPTED",
        },
        "idempotency": {
            "status": "PARTIALLY_SUPPORTED",
            "basis": [
                "plan_fingerprint",
                "chapter_id",
                "active_text_revision_id",
                "latest_casting_plan_id",
                "latest_casting_plan_revision",
                "latest_casting_plan_status",
                "live_job_id",
                "live_job_status",
                "active_artifact_id",
                "human_qa_status",
            ],
            "notes": (
                "Plan and request evaluation are deterministic. Actual batch prepare "
                "idempotency is not persisted in Phase 1; existing single-chapter prepare "
                "guards reject conflicting prepared or active jobs."
            ),
        },
        "duplicate_request_behavior": {
            "status": "PARTIALLY_SUPPORTED",
            "same_request_same_facts": "same deterministic contract response",
            "after_prepared_job_exists": "current plan excludes the chapter as PREPARED_JOB_EXISTS",
            "after_state_change": "old fingerprint is rejected as stale",
            "client_request_id": "NOT_DEFINED",
        },
        "partial_failure": {
            "status": "NOT_YET_DEFINED",
            "unit": "job_chapter",
            "notes": (
                "Single-job execution records per-JobChapter success/failure after start, "
                "but this Phase 1 contract performs no mutation and defines no batch "
                "rollback or partial-commit policy."
            ),
        },
        "retry": {
            "status": "PARTIALLY_SUPPORTED",
            "before_mutation": "safe to re-evaluate with the same current facts",
            "after_prepared_job_exists": "recompute the plan; do not create duplicate PREPARE intent",
            "after_state_change": "recompute the plan; stale fingerprints are rejected",
            "after_failed_execution": "existing retry is job_chapter_or_segment scoped, not batch-scoped",
        },
        "prepare_starts_render": False,
        "safety": {
            "api_route_registered": False,
            "database_write": False,
            "worker_wake": False,
            "provider_call": False,
            "tts_call": False,
        },
    }


def _request_scope(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "book_id": request.get("book_id"),
        "from_chapter": request.get("from_chapter"),
        "to_chapter": request.get("to_chapter"),
    }


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _request_numbers(request: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    return (
        _coerce_int(request.get("book_id")),
        _coerce_int(request.get("from_chapter")),
        _coerce_int(request.get("to_chapter")),
    )


def _scope_matches(request: dict[str, Any], current_plan: dict[str, Any]) -> bool:
    book_id, from_chapter, to_chapter = _request_numbers(request)
    scope = current_plan.get("scope") or {}
    return (
        book_id is not None
        and from_chapter is not None
        and to_chapter is not None
        and int(scope.get("book_id") or -1) == book_id
        and int(scope.get("from_chapter") or -1) == from_chapter
        and int(scope.get("to_chapter") or -1) == to_chapter
    )


def _intent_row(row: dict[str, Any], plan_fingerprint: str) -> dict[str, Any]:
    return {
        "chapter_id": row.get("chapter_id"),
        "chapter_number": row.get("chapter_number"),
        "current_readiness_state": row.get("readiness_state"),
        "eligibility": row.get("eligibility"),
        "plan_fingerprint": plan_fingerprint,
        "intended_mutation": "PREPARE_DURABLE_JOB",
        "expected_existing_state": "READY_TO_PREPARE",
        "idempotency_basis": {
            "active_text_revision_id": row.get("active_text_revision_id"),
            "latest_casting_plan_id": row.get("latest_casting_plan_id"),
            "latest_casting_plan_revision": row.get("latest_casting_plan_revision"),
            "latest_casting_plan_status": row.get("latest_casting_plan_status"),
            "live_job_id": row.get("live_job_id"),
            "live_job_status": row.get("live_job_status"),
            "active_artifact_id": row.get("active_artifact_id"),
            "human_qa_status": row.get("human_qa_status"),
        },
        "contract_status": "PREPARE_PLANNED_ONLY",
        "reason_codes": list(row.get("reason_codes") or []),
    }


def evaluate_prepare_contract(request: dict[str, Any], current_plan_provider: PlanProvider) -> dict[str, Any]:
    """Evaluate the Phase 1 PREPARE mutation contract without performing mutation."""

    if not isinstance(request, Mapping):
        request = {}
        return _base_response(
            status=REJECTED_INVALID_REQUEST,
            request=request,
            current_plan=None,
            submitted_fingerprint=None,
            reason="Request must be an object.",
        )
    request = dict(request)
    normalized_phase = str(request.get("target_phase") or "").upper()
    submitted_fingerprint = request.get("plan_fingerprint")
    if normalized_phase != SUPPORTED_PHASE:
        return _base_response(
            status=REJECTED_UNSUPPORTED_PHASE,
            request=request,
            current_plan=None,
            submitted_fingerprint=submitted_fingerprint if isinstance(submitted_fingerprint, str) else None,
            reason="Only target_phase PREPARE is supported by this contract.",
        )
    if not isinstance(submitted_fingerprint, str) or not FINGERPRINT_RE.match(submitted_fingerprint):
        return _base_response(
            status=REJECTED_INVALID_REQUEST,
            request=request,
            current_plan=None,
            submitted_fingerprint=submitted_fingerprint if isinstance(submitted_fingerprint, str) else None,
            reason="A 64-character lowercase hex plan_fingerprint is required.",
        )
    if request.get("explicit_confirmation") is not True:
        return _base_response(
            status=REJECTED_CONFIRMATION_REQUIRED,
            request=request,
            current_plan=None,
            submitted_fingerprint=submitted_fingerprint,
            reason="explicit_confirmation must be true after operator review.",
        )

    book_id, from_chapter, to_chapter = _request_numbers(request)
    if book_id is None or from_chapter is None or to_chapter is None or from_chapter > to_chapter:
        return _base_response(
            status=REJECTED_INVALID_REQUEST,
            request=request,
            current_plan=None,
            submitted_fingerprint=submitted_fingerprint,
            reason="book_id, from_chapter, and to_chapter are required and must form a valid range.",
        )

    current_plan = current_plan_provider(
        book_id=book_id,
        from_chapter=from_chapter,
        to_chapter=to_chapter,
        target_phase=SUPPORTED_PHASE,
    )
    if not _scope_matches(request, current_plan):
        return _base_response(
            status=REJECTED_SCOPE_MISMATCH,
            request=request,
            current_plan=current_plan,
            submitted_fingerprint=submitted_fingerprint,
            reason="Current plan scope does not match the submitted request scope.",
        )
    if str(current_plan.get("requested_phase") or "").upper() != SUPPORTED_PHASE:
        return _base_response(
            status=REJECTED_SCOPE_MISMATCH,
            request=request,
            current_plan=current_plan,
            submitted_fingerprint=submitted_fingerprint,
            reason="Current plan target phase does not match PREPARE.",
        )
    authorization = current_plan.get("authorization") or {}
    if (
        authorization.get("status") != MUTATION_AUTHORIZATION_STATUS
        or authorization.get("execution_endpoint_available") is not False
    ):
        return _base_response(
            status=REJECTED_UNSUPPORTED_LIFECYCLE,
            request=request,
            current_plan=current_plan,
            submitted_fingerprint=submitted_fingerprint,
            reason="Current batch-plan authorization no longer matches Phase 1 fail-closed contract.",
        )
    if current_plan.get("plan_fingerprint") != submitted_fingerprint:
        return _base_response(
            status=REJECTED_STALE_PLAN,
            request=request,
            current_plan=current_plan,
            submitted_fingerprint=submitted_fingerprint,
            reason="Submitted plan_fingerprint does not match the current PREPARE plan.",
        )

    included = list(current_plan.get("included") or [])
    status = CONTRACT_ACCEPTED if included else REJECTED_NO_ELIGIBLE_CHAPTERS
    reason = (
        "PREPARE contract validation passed; execution remains unauthorized."
        if included
        else "Current PREPARE plan has no eligible chapters."
    )
    result = _base_response(
        status=status,
        request=request,
        current_plan=current_plan,
        submitted_fingerprint=submitted_fingerprint,
        reason=reason,
    )
    fingerprint = str(current_plan.get("plan_fingerprint") or "")
    intent = [_intent_row(row, fingerprint) for row in included]
    # Preserve backend ordering while failing closed on accidental duplicate rows.
    seen: set[Any] = set()
    deduped_intent: list[dict[str, Any]] = []
    deduped_included: list[dict[str, Any]] = []
    for row, intent_row in zip(included, intent):
        chapter_id = row.get("chapter_id")
        if chapter_id in seen:
            continue
        seen.add(chapter_id)
        deduped_included.append(row)
        deduped_intent.append(intent_row)
    result["eligible_chapters"] = deduped_included
    result["execution_intent"] = deduped_intent
    return result
