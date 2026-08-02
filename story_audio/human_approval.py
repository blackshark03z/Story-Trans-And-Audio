from __future__ import annotations

import json
from typing import Any

from .db import Database


def _parse_human_approval(raw: Any) -> dict[str, Any] | None:
    if raw in (None, ""):
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _is_placeholder_note(note: Any) -> bool:
    text = str(note or "").strip().lower()
    return not text or text == "x"


def resolve_authoritative_human_approval(
    db: Database,
    chapter_id: int,
    *,
    active_artifact_id: int | None = None,
) -> dict[str, Any] | None:
    """Return the current human approval, preferring audit evidence for repairs."""

    chapter = db.fetch_one(
        "SELECT human_approval_json FROM chapters WHERE id=?",
        (chapter_id,),
    )
    if not chapter:
        return None

    current = _parse_human_approval(chapter["human_approval_json"])
    if not current:
        return None

    status = str(current.get("status") or "").lower()
    if status != "needs_fixes":
        return current

    if not _is_placeholder_note(current.get("notes")):
        return current

    artifact_id = int(current.get("artifact_id") or 0) or int(active_artifact_id or 0)
    rows = db.fetch_all(
        """
        SELECT details_json,created_at
        FROM audit_events
        WHERE chapter_id=? AND event_code='human_qa_recorded'
        ORDER BY id DESC
        """,
        (chapter_id,),
    )

    fallback: dict[str, Any] | None = None
    for row in rows:
        try:
            details = json.loads(row["details_json"] or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(details, dict):
            continue
        if artifact_id and int(details.get("artifact_id") or 0) != artifact_id:
            continue
        if str(details.get("status") or "").lower() != "needs_fixes":
            continue

        resolved = dict(current)
        for key in ("artifact_id", "job_id", "sha256", "duration_ms", "qa_feedback"):
            if key in details and details.get(key) is not None:
                resolved[key] = details[key]
        resolved["notes"] = str(details.get("notes") or "")
        resolved["recorded_at"] = row["created_at"]
        if fallback is None:
            fallback = dict(resolved)
        if not _is_placeholder_note(resolved["notes"]):
            return resolved

    return fallback or current


def resolve_repair_plan_evidence(
    db: Database,
    chapter_id: int,
    *,
    active_artifact_id: int | None = None,
) -> dict[str, Any] | None:
    """Return the newest confirmed repair plan for the current rejected artifact."""

    rows = db.fetch_all(
        """
        SELECT id,details_json,created_at
        FROM audit_events
        WHERE chapter_id=? AND event_code='repair_plan_confirmed'
        ORDER BY id DESC
        """,
        (chapter_id,),
    )
    for row in rows:
        try:
            details = json.loads(row["details_json"] or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(details, dict):
            continue
        if active_artifact_id and int(details.get("artifact_id") or 0) != int(active_artifact_id):
            continue
        return {
            "evidence_id": int(row["id"]),
            "recorded_at": row["created_at"],
            **details,
        }
    return None
