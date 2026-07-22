from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any


MUTATION_AUTHORIZATION_STATUS = "MUTATION_NOT_AUTHORIZED"

SUPPORTED_TARGET_PHASES = (
    "APPROVAL",
    "PREPARE",
    "START_RENDER",
    "RESUME_OR_MONITOR",
    "QA_CLOSEOUT",
    "NO_ACTION",
)

ELIGIBLE = "ELIGIBLE"
EXCLUDED_COMPLETE = "EXCLUDED_COMPLETE"
EXCLUDED_BLOCKED = "EXCLUDED_BLOCKED"
EXCLUDED_ALREADY_PREPARED = "EXCLUDED_ALREADY_PREPARED"
EXCLUDED_RUNNING_OR_PAUSED = "EXCLUDED_RUNNING_OR_PAUSED"
EXCLUDED_RENDERED_NOT_QA = "EXCLUDED_RENDERED_NOT_QA"
EXCLUDED_UNSUPPORTED = "EXCLUDED_UNSUPPORTED"

_BLOCKED_STATES = {
    "TEXT_BLOCKED",
    "SPEAKER_EXCEPTIONS",
    "VOICE_BLOCKED",
    "CASTING_REVIEW",
    "STATE_UNRESOLVED",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _reason_codes(item: dict[str, Any], target_phase: str, eligibility: str) -> list[str]:
    state = str(item.get("state") or "")
    blockers = [str(blocker) for blocker in item.get("blockers") or []]
    plan_status = str(item.get("latest_casting_plan_status") or "").lower()
    codes: list[str] = []

    if eligibility == ELIGIBLE:
        codes.append(f"{target_phase}_ELIGIBLE")
    elif state == "COMPLETE":
        codes.append("ACTIVE_OUTPUT_COMPLETE")
    elif state == "RENDERED_NOT_QA":
        codes.append("HUMAN_QA_NOT_ACCEPTED")
    elif state == "PREPARED":
        codes.append("PREPARED_JOB_EXISTS")
    elif state == "RENDERING_OR_PAUSED":
        codes.append("LIVE_JOB_REQUIRES_MONITOR_OR_RESUME")
    elif state == "READY_TO_PREPARE":
        codes.append("JOB_NOT_PREPARED")
    elif state == "TEXT_BLOCKED":
        codes.append("APPROVED_TEXT_MISSING")
    elif state == "SPEAKER_EXCEPTIONS":
        codes.append("SPEAKER_REVIEW_REQUIRED")
    elif state == "VOICE_BLOCKED":
        codes.append("VOICE_NOT_READY")
    elif state == "CASTING_REVIEW":
        if plan_status == "draft":
            codes.append("CASTING_PLAN_NOT_APPROVED")
        elif item.get("latest_casting_plan_id") is None:
            codes.append("CASTING_PLAN_MISSING")
        else:
            codes.append("CASTING_REVIEW_REQUIRED")
    elif state == "STATE_UNRESOLVED":
        codes.append("STATE_UNRESOLVED")
    else:
        codes.append("UNSUPPORTED_READINESS_STATE")

    for blocker in blockers:
        lowered = blocker.lower()
        if "active audio artifact binding is invalid" in lowered:
            codes.append("ACTIVE_OUTPUT_BINDING_INVALID")
        elif "multiple live jobs" in lowered:
            codes.append("MULTIPLE_LIVE_JOBS")
        elif "unsupported casting plan status" in lowered:
            codes.append("UNSUPPORTED_CASTING_PLAN_STATUS")

    return list(dict.fromkeys(codes))


def _operator_message(item: dict[str, Any], target_phase: str, eligibility: str) -> str:
    if eligibility == ELIGIBLE:
        return f"Chapter is eligible for future {target_phase} execution after explicit confirmation."
    blockers = item.get("blockers") or []
    if blockers:
        return str(blockers[0])
    if eligibility == EXCLUDED_COMPLETE:
        return "Chapter already has accepted active output."
    if eligibility == EXCLUDED_ALREADY_PREPARED:
        return "Chapter already has a prepared job."
    if eligibility == EXCLUDED_RUNNING_OR_PAUSED:
        return "Chapter already has live render work to monitor or resume."
    if eligibility == EXCLUDED_RENDERED_NOT_QA:
        return "Chapter has active output awaiting Human QA."
    return "Chapter is not eligible for the requested future batch phase."


def _eligibility_for_phase(state: str, target_phase: str) -> str:
    if target_phase == "NO_ACTION":
        return ELIGIBLE if state == "COMPLETE" else EXCLUDED_UNSUPPORTED

    if state == "COMPLETE":
        return EXCLUDED_COMPLETE
    if state == "STATE_UNRESOLVED":
        return EXCLUDED_UNSUPPORTED

    if target_phase == "PREPARE":
        if state == "READY_TO_PREPARE":
            return ELIGIBLE
        if state == "PREPARED":
            return EXCLUDED_ALREADY_PREPARED
        if state == "RENDERING_OR_PAUSED":
            return EXCLUDED_RUNNING_OR_PAUSED
        if state == "RENDERED_NOT_QA":
            return EXCLUDED_RENDERED_NOT_QA
        if state in _BLOCKED_STATES:
            return EXCLUDED_BLOCKED
        return EXCLUDED_UNSUPPORTED

    if target_phase == "START_RENDER":
        if state == "PREPARED":
            return ELIGIBLE
        if state == "RENDERING_OR_PAUSED":
            return EXCLUDED_RUNNING_OR_PAUSED
        if state == "RENDERED_NOT_QA":
            return EXCLUDED_RENDERED_NOT_QA
        return EXCLUDED_BLOCKED if state in _BLOCKED_STATES | {"READY_TO_PREPARE"} else EXCLUDED_UNSUPPORTED

    if target_phase == "RESUME_OR_MONITOR":
        if state == "RENDERING_OR_PAUSED":
            return ELIGIBLE
        if state == "PREPARED":
            return EXCLUDED_ALREADY_PREPARED
        if state == "RENDERED_NOT_QA":
            return EXCLUDED_RENDERED_NOT_QA
        return EXCLUDED_BLOCKED if state in _BLOCKED_STATES | {"READY_TO_PREPARE"} else EXCLUDED_UNSUPPORTED

    if target_phase == "QA_CLOSEOUT":
        if state == "RENDERED_NOT_QA":
            return ELIGIBLE
        if state == "PREPARED":
            return EXCLUDED_ALREADY_PREPARED
        if state == "RENDERING_OR_PAUSED":
            return EXCLUDED_RUNNING_OR_PAUSED
        return EXCLUDED_BLOCKED if state in _BLOCKED_STATES | {"READY_TO_PREPARE"} else EXCLUDED_UNSUPPORTED

    if target_phase == "APPROVAL":
        if state == "CASTING_REVIEW":
            return ELIGIBLE
        if state == "PREPARED":
            return EXCLUDED_ALREADY_PREPARED
        if state == "RENDERING_OR_PAUSED":
            return EXCLUDED_RUNNING_OR_PAUSED
        if state == "RENDERED_NOT_QA":
            return EXCLUDED_RENDERED_NOT_QA
        return EXCLUDED_BLOCKED if state in _BLOCKED_STATES | {"READY_TO_PREPARE"} else EXCLUDED_UNSUPPORTED

    return EXCLUDED_UNSUPPORTED


def _plan_identity_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "chapter_id": item.get("chapter_id"),
        "chapter_number": item.get("chapter_number"),
        "state": item.get("state"),
        "next_action": item.get("next_action"),
        "active_artifact_id": item.get("active_artifact_id"),
        "active_output_job_id": item.get("active_output_job_id"),
        "active_output_job_chapter_id": item.get("active_output_job_chapter_id"),
        "human_qa_status": item.get("human_qa_status"),
        "active_text_revision_id": item.get("active_text_revision_id"),
        "latest_speaker_draft_id": item.get("latest_speaker_draft_id"),
        "latest_speaker_draft_status": item.get("latest_speaker_draft_status"),
        "latest_casting_plan_id": item.get("latest_casting_plan_id"),
        "latest_casting_plan_revision": item.get("latest_casting_plan_revision"),
        "latest_casting_plan_status": item.get("latest_casting_plan_status"),
        "live_job_id": item.get("live_job_id"),
        "live_job_status": item.get("live_job_status"),
        "blockers": item.get("blockers") or [],
    }


def _fingerprint(scope: dict[str, Any], target_phase: str, chapters: list[dict[str, Any]]) -> str:
    payload = {
        "schema": "story-audio-batch-plan/v1",
        "scope": scope,
        "target_phase": target_phase,
        "chapters": [_plan_identity_item(item) for item in chapters],
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _contract() -> dict[str, Any]:
    return {
        "idempotency": {
            "status": "PARTIALLY_SUPPORTED",
            "basis": [
                "chapter_id",
                "active_text_revision_id",
                "latest_casting_plan_id",
                "latest_casting_plan_revision",
                "latest_casting_plan_status",
                "active_artifact_id",
                "active_output_job_id",
                "live_job_id",
                "live_job_status",
                "human_qa_status",
            ],
            "notes": (
                "Single-chapter prepare/start paths have conflict guards, but no persisted "
                "batch idempotency record exists in Phase 1."
            ),
        },
        "retry": {
            "status": "PARTIALLY_SUPPORTED",
            "unit": "segment_or_job_chapter_after_existing_job_failure",
            "notes": (
                "Existing retry routes operate on failed job chapters or segments. "
                "Batch retry execution is not implemented by this endpoint."
            ),
        },
        "partial_failure": {
            "status": "PARTIALLY_SUPPORTED",
            "unit": "job_chapter",
            "policy": "PLAN_ONLY_NOT_EXECUTED",
            "notes": (
                "The worker records per-chapter completion/failure inside one job, but "
                "Phase 1 defines no batch execution or rollback policy."
            ),
        },
        "confirmation_required": True,
    }


def build_batch_plan(readiness: dict[str, Any], *, target_phase: str) -> dict[str, Any]:
    normalized_phase = str(target_phase or "").upper()
    if normalized_phase not in SUPPORTED_TARGET_PHASES:
        allowed = ", ".join(SUPPORTED_TARGET_PHASES)
        raise ValueError(f"Unsupported target_phase '{target_phase}'. Supported phases: {allowed}.")

    chapters = [dict(item) for item in readiness.get("chapters") or []]
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for item in chapters:
        state = str(item.get("state") or "")
        eligibility = _eligibility_for_phase(state, normalized_phase)
        row = {
            "chapter_id": item.get("chapter_id"),
            "chapter_number": item.get("chapter_number"),
            "chapter_title": item.get("chapter_title"),
            "readiness_state": state,
            "next_action": item.get("next_action"),
            "eligibility": eligibility,
            "reason_codes": _reason_codes(item, normalized_phase, eligibility),
            "operator_message": _operator_message(item, normalized_phase, eligibility),
            "active_text_revision_id": item.get("active_text_revision_id"),
            "latest_casting_plan_id": item.get("latest_casting_plan_id"),
            "latest_casting_plan_revision": item.get("latest_casting_plan_revision"),
            "latest_casting_plan_status": item.get("latest_casting_plan_status"),
            "active_artifact_id": item.get("active_artifact_id"),
            "active_output_job_id": item.get("active_output_job_id"),
            "live_job_id": item.get("live_job_id"),
            "live_job_status": item.get("live_job_status"),
            "human_qa_status": item.get("human_qa_status"),
        }
        if eligibility == ELIGIBLE:
            included.append(row)
        else:
            excluded.append(row)

    eligibility_counts = Counter(row["eligibility"] for row in included + excluded)
    blocked = eligibility_counts[EXCLUDED_BLOCKED] + eligibility_counts[EXCLUDED_UNSUPPORTED]
    plan_fingerprint = _fingerprint(dict(readiness.get("scope") or {}), normalized_phase, chapters)
    return {
        "schema": "story-audio-batch-plan/v1",
        "scope": readiness.get("scope") or {},
        "requested_phase": normalized_phase,
        "supported_target_phases": list(SUPPORTED_TARGET_PHASES),
        "plan_fingerprint": plan_fingerprint,
        "authorization": {
            "status": MUTATION_AUTHORIZATION_STATUS,
            "requires_explicit_confirmation": True,
            "execution_endpoint_available": False,
        },
        "summary": {
            "total": len(chapters),
            "eligible": len(included),
            "excluded": len(excluded),
            "blocked": blocked,
            "already_complete": eligibility_counts[EXCLUDED_COMPLETE],
            "already_prepared": eligibility_counts[EXCLUDED_ALREADY_PREPARED],
            "running_or_paused": eligibility_counts[EXCLUDED_RUNNING_OR_PAUSED],
            "rendered_not_qa": eligibility_counts[EXCLUDED_RENDERED_NOT_QA],
            "unsupported": eligibility_counts[EXCLUDED_UNSUPPORTED],
            "eligibility_counts": dict(sorted(eligibility_counts.items())),
        },
        "included": included,
        "excluded": excluded,
        "execution_contract": _contract(),
    }
