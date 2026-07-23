from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .active_output import get_active_output_bindings, get_latest_casting_plan_bindings
from .db import Database
from .files import sha256_text
from .pipeline import JOB_ACTIVE_STATUSES, JOB_PREPARED_STATUS
from .voice_eligibility import EffectiveVoiceCatalog, inspect_casting_plan


PREPARED_STATUSES = {JOB_PREPARED_STATUS}
LIVE_JOB_STATUSES = set(JOB_ACTIVE_STATUSES)
TERMINAL_JOB_STATUSES = {"completed", "completed_with_errors", "failed", "cancelled"}

STATE_META = {
    "TEXT_BLOCKED": ("RESOLVE_TEXT", "text_blocked", True),
    "SPEAKER_EXCEPTIONS": ("REVIEW_SPEAKERS", "speaker_exceptions", True),
    "VOICE_BLOCKED": ("CONFIGURE_VOICES", "voice_blocked", True),
    "CASTING_REVIEW": ("REVIEW_FINAL_VOICE_MAP", "casting_review", True),
    "READY_TO_PREPARE": ("PREPARE", None, False),
    "PREPARED": ("START_RENDER", "prepared", True),
    "RENDERING_OR_PAUSED": ("MONITOR_OR_RESUME", "rendering_or_paused", True),
    "RENDERED_NOT_QA": ("QA", "qa_required", True),
    "COMPLETE": ("VIEW_OUTPUTS_OR_SELECT_NEXT_SCOPE", None, False),
    "STATE_UNRESOLVED": ("RELOAD_READ_ONLY", "state_unresolved", True),
}


def _placeholders(count: int) -> str:
    return ",".join("?" for _ in range(count))


def _parse_human_approval(raw: Any) -> dict[str, Any] | None:
    if raw in (None, ""):
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _human_qa_status(raw: Any, active_artifact_id: int | None) -> str:
    approval = _parse_human_approval(raw)
    if not approval:
        return "pending"
    status = str(approval.get("status") or "").lower()
    stored_artifact_id = int(approval.get("artifact_id") or 0)
    matches_active = bool(stored_artifact_id and active_artifact_id and stored_artifact_id == active_artifact_id)
    if status == "approved" and matches_active:
        return "accepted"
    if status == "approved":
        return "approved_stale"
    if status == "needs_fixes":
        return "needs_fixes"
    return "pending"


def _latest_drafts(db: Database, chapter_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not chapter_ids:
        return {}
    rows = db.fetch_all(
        f"""
        SELECT sad.*
        FROM speaker_assignment_drafts sad
        JOIN (
            SELECT chapter_id, MAX(id) AS id
            FROM speaker_assignment_drafts
            WHERE chapter_id IN ({_placeholders(len(chapter_ids))})
            GROUP BY chapter_id
        ) latest ON latest.id = sad.id
        """,
        tuple(chapter_ids),
    )
    return {int(row["chapter_id"]): dict(row) for row in rows}


def _approved_text_ids(db: Database, chapter_ids: list[int]) -> set[int]:
    if not chapter_ids:
        return set()
    rows = db.fetch_all(
        f"""
        SELECT c.id
        FROM chapters c
        JOIN text_revisions tr ON tr.id = c.active_text_revision_id
        WHERE c.id IN ({_placeholders(len(chapter_ids))})
          AND tr.status = 'approved'
        """,
        tuple(chapter_ids),
    )
    return {int(row["id"]) for row in rows}


def _live_jobs(db: Database, chapter_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    if not chapter_ids:
        return {}
    statuses = sorted(PREPARED_STATUSES | LIVE_JOB_STATUSES)
    rows = db.fetch_all(
        f"""
        SELECT j.id AS job_id,
               j.status AS job_status,
               j.book_id,
               j.from_chapter,
               j.to_chapter,
               j.casting_plan_id AS job_casting_plan_id,
               jc.id AS job_chapter_id,
               jc.chapter_id,
               jc.status AS job_chapter_status,
               jc.text_revision_id,
               jc.casting_plan_id AS job_chapter_casting_plan_id
        FROM job_chapters jc
        JOIN jobs j ON j.id = jc.job_id
        WHERE jc.chapter_id IN ({_placeholders(len(chapter_ids))})
          AND j.status IN ({_placeholders(len(statuses))})
        ORDER BY CASE WHEN j.status = ? THEN 0 ELSE 1 END, j.id
        """,
        tuple(chapter_ids + statuses + [JOB_PREPARED_STATUS]),
    )
    result: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(int(row["chapter_id"]), []).append(dict(row))
    return result


def _voice_blocker(
    plan: dict[str, Any] | None,
    *,
    voice_catalog: EffectiveVoiceCatalog | None,
    chapter_id: int,
    chapter_number: int,
) -> tuple[str | None, list[dict[str, Any]]]:
    if not plan:
        return None, []
    if plan.get("_payload_error"):
        return str(plan["_payload_error"]), []
    payload = plan.get("_payload")
    utterances = payload.get("utterances") if isinstance(payload, dict) else None
    if voice_catalog is not None and isinstance(payload, dict):
        issues = list(
            inspect_casting_plan(
                payload,
                voice_catalog,
                chapter_id=chapter_id,
                chapter_number=chapter_number,
            )
        )
        if issues:
            return str(issues[0]["message"]), issues
    if plan.get("narrator_voice_id") in (None, ""):
        return "Casting Plan is missing narrator voice.", []
    if not isinstance(utterances, list):
        return None, []
    for item in utterances:
        if isinstance(item, dict) and item.get("resolved_voice_id") in (None, ""):
            return "Casting Plan has an utterance without a resolved voice.", []
    return None, []


def _read_casting_payload(db: Database, plan: dict[str, Any]) -> dict[str, Any] | None:
    content_path = str(plan.get("content_path") or "")
    if not content_path:
        plan["_payload_error"] = "Casting Plan content path is missing."
        return None
    try:
        blobs_root = (db.path.parent / "blobs").resolve()
        target = (blobs_root / Path(content_path)).resolve()
        if target != blobs_root and blobs_root not in target.parents:
            plan["_payload_error"] = "Casting Plan content path is invalid."
            return None
        payload_text = target.read_text(encoding="utf-8")
        if sha256_text(payload_text) != str(plan.get("plan_sha256") or ""):
            plan["_payload_error"] = "Casting Plan content hash mismatch."
            return None
        payload = json.loads(payload_text)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        plan["_payload_error"] = "Casting Plan payload cannot be read safely."
        return None
    if not isinstance(payload, dict):
        plan["_payload_error"] = "Casting Plan payload has unsupported shape."
        return None
    return payload


def _latest_casting_payloads(db: Database, chapter_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not chapter_ids:
        return {}
    rows = db.fetch_all(
        f"""
        SELECT cp.chapter_id,
               cp.id,
               cp.plan_revision,
               cp.status,
               cp.text_revision_id,
               cp.narrator_voice_id,
               cp.content_path,
               cp.plan_sha256
        FROM casting_plans cp
        JOIN (
            SELECT chapter_id, MAX(plan_revision) AS plan_revision
            FROM casting_plans
            WHERE chapter_id IN ({_placeholders(len(chapter_ids))})
            GROUP BY chapter_id
        ) latest
          ON latest.chapter_id = cp.chapter_id
         AND latest.plan_revision = cp.plan_revision
        WHERE cp.chapter_id IN ({_placeholders(len(chapter_ids))})
        """,
        tuple(chapter_ids + chapter_ids),
    )
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        plan = dict(row)
        plan["_payload"] = _read_casting_payload(db, plan)
        result[int(row["chapter_id"])] = plan
    return result


def _state_item(
    *,
    chapter: dict[str, Any],
    approved_text_ids: set[int],
    active_binding: dict[str, Any],
    latest_plan: dict[str, Any] | None,
    latest_draft: dict[str, Any] | None,
    live_jobs: list[dict[str, Any]],
    voice_catalog: EffectiveVoiceCatalog | None,
) -> dict[str, Any]:
    chapter_id = int(chapter["id"])
    active_artifact_id = active_binding.get("active_output_artifact_id")
    human_qa_status = _human_qa_status(chapter.get("human_approval_json"), active_artifact_id)
    blockers: list[str] = []
    voice_issues: list[dict[str, Any]] = []
    state = "STATE_UNRESOLVED"

    if active_binding.get("active_audio_artifact_id") and not active_binding.get("active_output_artifact_id"):
        blockers.append("Active audio artifact binding is invalid.")
    elif active_artifact_id:
        state = "COMPLETE" if human_qa_status == "accepted" else "RENDERED_NOT_QA"
        if state == "RENDERED_NOT_QA":
            blockers.append("Active audio exists but Human QA is not accepted.")
    elif len(live_jobs) > 1:
        blockers.append("Multiple live jobs exist for this chapter.")
    elif len(live_jobs) == 1:
        job_status = str(live_jobs[0].get("job_status") or "").lower()
        state = "PREPARED" if job_status in PREPARED_STATUSES else "RENDERING_OR_PAUSED"
        if state == "PREPARED":
            blockers.append("Prepared job is waiting for explicit start.")
        else:
            blockers.append("Existing job needs monitoring or resume.")
    elif str(chapter.get("audio_status") or "").lower() in TERMINAL_JOB_STATUSES:
        blockers.append("Chapter has terminal audio status but no active output.")
    elif chapter_id not in approved_text_ids:
        state = "TEXT_BLOCKED"
        blockers.append("Active approved Text Revision is missing.")
    elif latest_draft and str(latest_draft.get("status") or "").lower() not in {"approved"}:
        state = "SPEAKER_EXCEPTIONS"
        blockers.append("Latest Speaker Draft is not approved.")
    elif latest_draft and int(latest_draft.get("invalid_count") or 0) > 0:
        state = "SPEAKER_EXCEPTIONS"
        blockers.append("Latest Speaker Draft has invalid rows.")
    elif not latest_plan:
        state = "CASTING_REVIEW"
        blockers.append("Final Voice Map is missing.")
    else:
        voice_blocker, voice_issues = _voice_blocker(
            latest_plan,
            voice_catalog=voice_catalog,
            chapter_id=chapter_id,
            chapter_number=int(chapter["chapter_number"]),
        )
        if voice_blocker:
            state = "VOICE_BLOCKED"
            blockers.append(voice_blocker)
        else:
            plan_status = str(latest_plan.get("status") or "").lower()
            if plan_status == "draft":
                state = "CASTING_REVIEW"
                blockers.append("Final Voice Map is draft/unapproved.")
            elif plan_status == "approved":
                state = "READY_TO_PREPARE"
            else:
                state = "STATE_UNRESOLVED"
                blockers.append(f"Unsupported Casting Plan status: {latest_plan.get('status')}.")

    next_action, exception_kind, requires_operator_action = STATE_META[state]
    item = {
        "chapter_id": chapter_id,
        "chapter_number": int(chapter["chapter_number"]),
        "chapter_title": chapter["title"],
        "state": state,
        "next_action": next_action,
        "requires_operator_action": bool(requires_operator_action),
        "active_artifact_id": active_artifact_id,
        "active_output_job_id": active_binding.get("active_output_job_id"),
        "active_output_job_chapter_id": active_binding.get("active_output_job_chapter_id"),
        "human_qa_status": human_qa_status,
        "active_text_revision_id": int(chapter["active_text_revision_id"]) if chapter["active_text_revision_id"] else None,
        "latest_speaker_draft_id": int(latest_draft["id"]) if latest_draft else None,
        "latest_speaker_draft_status": latest_draft.get("status") if latest_draft else None,
        "latest_casting_plan_id": int(latest_plan["id"]) if latest_plan else None,
        "latest_casting_plan_revision": int(latest_plan["plan_revision"]) if latest_plan else None,
        "latest_casting_plan_status": latest_plan.get("status") if latest_plan else None,
        "live_job_id": int(live_jobs[0]["job_id"]) if len(live_jobs) == 1 else None,
        "live_job_status": live_jobs[0].get("job_status") if len(live_jobs) == 1 else None,
        "blockers": blockers,
        "voice_issues": voice_issues,
    }
    if exception_kind and state not in {"READY_TO_PREPARE", "COMPLETE"}:
        item["exception_kind"] = exception_kind
    return item


def get_range_readiness(
    db: Database,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    voice_catalog: EffectiveVoiceCatalog | None = None,
) -> dict[str, Any]:
    if from_chapter > to_chapter:
        raise ValueError("from_chapter must be less than or equal to to_chapter.")
    book = db.fetch_one("SELECT id,title FROM books WHERE id=?", (book_id,))
    if not book:
        raise LookupError("Book not found.")
    chapters = [
        dict(row)
        for row in db.fetch_all(
            """
            SELECT id,book_id,chapter_number,title,active_text_revision_id,audio_status,
                   active_audio_artifact_id,human_approval_json
            FROM chapters
            WHERE book_id=? AND chapter_number BETWEEN ? AND ?
            ORDER BY chapter_number,id
            """,
            (book_id, from_chapter, to_chapter),
        )
    ]
    if not chapters:
        raise LookupError("No chapters found for the selected range.")
    expected = list(range(from_chapter, to_chapter + 1))
    actual = [int(row["chapter_number"]) for row in chapters]
    missing = sorted(set(expected) - set(actual))
    if missing:
        raise LookupError(f"Selected range is missing chapters: {missing[:20]}.")

    chapter_ids = [int(row["id"]) for row in chapters]
    active_bindings = get_active_output_bindings(db, chapter_ids)
    latest_plan_bindings = get_latest_casting_plan_bindings(db, chapter_ids)
    latest_plan_payloads = _latest_casting_payloads(db, chapter_ids)
    latest_drafts = _latest_drafts(db, chapter_ids)
    approved_text_ids = _approved_text_ids(db, chapter_ids)
    live_jobs = _live_jobs(db, chapter_ids)

    items: list[dict[str, Any]] = []
    for chapter in chapters:
        chapter_id = int(chapter["id"])
        latest_plan = latest_plan_payloads.get(chapter_id)
        if latest_plan:
            latest_plan.update(latest_plan_bindings.get(chapter_id, {}))
        items.append(
            _state_item(
                chapter=chapter,
                approved_text_ids=approved_text_ids,
                active_binding=active_bindings.get(chapter_id, {}),
                latest_plan=latest_plan,
                latest_draft=latest_drafts.get(chapter_id),
                live_jobs=live_jobs.get(chapter_id, []),
                voice_catalog=voice_catalog,
            )
        )

    exceptions = [
        {
            "chapter_id": item["chapter_id"],
            "chapter_number": item["chapter_number"],
            "state": item["state"],
            "next_action": item["next_action"],
            "exception_kind": item.get("exception_kind"),
            "message": item["blockers"][0] if item["blockers"] else item["next_action"],
            "voice_issues": item.get("voice_issues") or [],
        }
        for item in items
        if item["requires_operator_action"] and item["state"] not in {"COMPLETE", "READY_TO_PREPARE"}
    ]
    state_counts = Counter(item["state"] for item in items)
    summary = {
        "total": len(items),
        "complete": state_counts["COMPLETE"],
        "ready_to_prepare": state_counts["READY_TO_PREPARE"],
        "needs_attention": len(exceptions),
        "rendering_or_paused": state_counts["RENDERING_OR_PAUSED"],
        "prepared": state_counts["PREPARED"],
        "rendered_not_qa": state_counts["RENDERED_NOT_QA"],
        "state_counts": dict(sorted(state_counts.items())),
    }
    return {
        "scope": {
            "book_id": int(book["id"]),
            "book_title": book["title"],
            "from_chapter": from_chapter,
            "to_chapter": to_chapter,
            "chapter_count": len(items),
        },
        "summary": summary,
        "chapters": items,
        "exceptions": exceptions,
    }
