from __future__ import annotations

import json
from typing import Any, Mapping

from .casting import split_utterances
from .character_assignment import is_unresolved_dialogue_text
from .db import Database
from .storage import ContentStore


APPROVED_CURRENT = "APPROVED_CURRENT"
CURRENT_REVIEW_REQUIRED = "CURRENT_REVIEW_REQUIRED"
ANALYSIS_REQUIRED = "ANALYSIS_REQUIRED"
NO_REVIEW_REQUIRED = "NO_REVIEW_REQUIRED"


def _unresolved_targets(text: str) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for utterance in split_utterances(text):
        segment = text[
            int(utterance["start_offset"]) : int(utterance["end_offset"])
        ].strip()
        if not is_unresolved_dialogue_text(segment):
            continue
        targets.append(
            {
                "utterance_id": str(utterance["utterance_id"]),
                "sequence": int(utterance["sequence"]),
                "text": segment,
            }
        )
    return targets


def _analysis_history(db: Database, chapter_id: int) -> list[dict[str, Any]]:
    rows = db.fetch_all(
        """
        SELECT id,event_code,details_json,created_at
        FROM audit_events
        WHERE chapter_id=? AND event_code IN (
            'speaker_review_analysis_generated',
            'speaker_review_analysis_failed',
            'speaker_review_suggestion_reviewed',
            'speaker_review_suggestion_noted'
        )
        ORDER BY id DESC
        """,
        (chapter_id,),
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        try:
            details = json.loads(row["details_json"] or "{}")
        except (TypeError, ValueError):
            details = {}
        result.append(
            {
                "kind": "analysis_event",
                "audit_event_id": int(row["id"]),
                "event_code": str(row["event_code"]),
                "analysis_run_id": details.get("analysis_run_id")
                or details.get("run_id"),
                "provider": details.get("provider") or "Gemini",
                "decision": details.get("decision"),
                "created_at": row["created_at"],
            }
        )
    return result


def resolve_chapter_speaker_state(
    db: Database,
    store: ContentStore,
    chapter: Mapping[str, Any],
    *,
    text: str | None = None,
) -> dict[str, Any]:
    """Resolve speaker readiness from the active revision, never stale history alone."""

    chapter_id = int(chapter["id"])
    current_revision_id = int(chapter.get("active_text_revision_id") or 0)
    if not current_revision_id:
        return {
            "status": ANALYSIS_REQUIRED,
            "current_revision_id": None,
            "unresolved_count": 0,
            "unresolved_targets": [],
            "blocks_progress": True,
            "history": [],
        }

    revision = db.fetch_one(
        "SELECT id,content_path FROM text_revisions WHERE id=? AND chapter_id=?",
        (current_revision_id, chapter_id),
    )
    if text is None:
        text = store.read_text(str(revision["content_path"])) if revision else ""
    unresolved_targets = _unresolved_targets(text or "")

    plans = [
        dict(row)
        for row in db.fetch_all(
            """
            SELECT id,text_revision_id,plan_revision,status,created_at,approved_at,archived_at
            FROM casting_plans
            WHERE chapter_id=?
            ORDER BY plan_revision DESC,id DESC
            """,
            (chapter_id,),
        )
    ]
    current_plan = next(
        (
            row
            for row in plans
            if int(row.get("text_revision_id") or 0) == current_revision_id
            and str(row.get("status") or "").lower() == "approved"
        ),
        None,
    )

    drafts = [
        dict(row)
        for row in db.fetch_all(
            """
            SELECT id,text_revision_id,status,target_count,valid_count,invalid_count,
                   model_id,prompt_version,response_schema,created_at,approved_at
            FROM speaker_assignment_drafts
            WHERE chapter_id=?
            ORDER BY created_at DESC,id DESC
            """,
            (chapter_id,),
        )
    ]
    review_counts = {
        int(row["draft_id"]): int(row["review_count"] or 0)
        for row in db.fetch_all(
            """
            SELECT r.draft_id,COUNT(*) AS review_count
            FROM speaker_assignment_reviews r
            JOIN speaker_assignment_drafts d ON d.id=r.draft_id
            WHERE d.chapter_id=?
            GROUP BY r.draft_id
            """,
            (chapter_id,),
        )
    }
    current_draft = next(
        (
            row
            for row in drafts
            if int(row.get("text_revision_id") or 0) == current_revision_id
        ),
        None,
    )

    history: list[dict[str, Any]] = []
    for draft in drafts:
        draft_id = int(draft["id"])
        source_revision_id = int(draft.get("text_revision_id") or 0)
        current = source_revision_id == current_revision_id
        review_count = review_counts.get(draft_id, 0)
        target_count = int(draft.get("target_count") or 0)
        history.append(
            {
                "kind": "speaker_draft",
                "draft_id": draft_id,
                "source_revision_id": source_revision_id,
                "current_revision_id": current_revision_id,
                "created_at": draft.get("created_at"),
                "status": draft.get("status"),
                "approved_at": draft.get("approved_at"),
                "current": current,
                "stale": not current,
                "model_id": draft.get("model_id"),
                "provider": "Gemini" if draft.get("model_id") else None,
                "prompt_version": draft.get("prompt_version"),
                "target_count": target_count,
                "valid_count": int(draft.get("valid_count") or 0),
                "invalid_count": int(draft.get("invalid_count") or 0),
                "review_count": review_count,
                "human_decision_summary": (
                    f"Đã duyệt {review_count}/{target_count} dòng"
                    if target_count
                    else "Không cần quyết định của người dùng"
                ),
                "impact_reason": (
                    f"Tương thích với Revision {current_revision_id} hiện tại."
                    if current
                    else (
                        f"Chỉ là lịch sử: Revision {source_revision_id} không khớp "
                        f"Revision {current_revision_id} hiện tại."
                    )
                ),
            }
        )
    history.extend(_analysis_history(db, chapter_id))
    history.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)

    status = ANALYSIS_REQUIRED
    approved_source: str | None = None
    remaining_review_count = 0
    if current_plan:
        status = APPROVED_CURRENT
        approved_source = "casting_plan"
    elif current_draft and str(current_draft.get("status") or "").lower() == "approved":
        status = APPROVED_CURRENT
        approved_source = "speaker_draft"
    elif not unresolved_targets:
        status = NO_REVIEW_REQUIRED
    elif current_draft:
        target_count = int(current_draft.get("target_count") or 0)
        remaining_review_count = max(
            0,
            target_count - review_counts.get(int(current_draft["id"]), 0),
        )
        status = CURRENT_REVIEW_REQUIRED

    return {
        "status": status,
        "current_revision_id": current_revision_id,
        "unresolved_count": len(unresolved_targets),
        "unresolved_targets": unresolved_targets,
        "remaining_review_count": remaining_review_count,
        "current_draft_id": int(current_draft["id"]) if current_draft else None,
        "current_draft_status": current_draft.get("status") if current_draft else None,
        "current_plan_id": int(current_plan["id"]) if current_plan else None,
        "current_plan_revision": (
            int(current_plan["plan_revision"]) if current_plan else None
        ),
        "approved_source": approved_source,
        "narrator_only": status == NO_REVIEW_REQUIRED,
        "blocks_progress": status in {CURRENT_REVIEW_REQUIRED, ANALYSIS_REQUIRED},
        "history": history,
    }


__all__ = [
    "ANALYSIS_REQUIRED",
    "APPROVED_CURRENT",
    "CURRENT_REVIEW_REQUIRED",
    "NO_REVIEW_REQUIRED",
    "resolve_chapter_speaker_state",
]
