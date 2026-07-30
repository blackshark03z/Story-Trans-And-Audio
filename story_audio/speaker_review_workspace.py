"""Pure contracts for the production speaker-review workspace.

The workspace is a projection over immutable analysis and decision events.  It
must never treat a polling response as permission to mutate a Casting Plan or
start production work.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping


QUEUE_VIEWS = (
    "NEEDS_REVIEW",
    "NEEDS_DECISION",
    "EDITED",
    "APPROVED",
    "DEFERRED",
    "ERROR",
    "ALL",
)

APPROVED_STATES = frozenset({"ACCEPTED", "EDITED_AND_ACCEPTED", "CORRECTED"})
DEFERRED_STATES = frozenset({"DEFERRED"})
ERROR_STATES = frozenset({"ERROR", "FAILED", "REJECTED"})
DECISION_REQUIRED_STATES = frozenset({"MARKED_UNCERTAIN"})

QUEUE_VIEW_LABELS = {
    "NEEDS_REVIEW": "Cần duyệt",
    "NEEDS_DECISION": "Cần quyết định",
    "EDITED": "Đã chỉnh sửa",
    "APPROVED": "Đã duyệt",
    "DEFERRED": "Để sau",
    "ERROR": "Có lỗi",
    "ALL": "Tất cả",
}


def queue_view_for(item: Mapping[str, Any]) -> str:
    """Return the stable operator queue for one suggestion."""

    state = str(item.get("review_state") or "PENDING_REVIEW").upper()
    if state in APPROVED_STATES:
        return "APPROVED"
    if state in DEFERRED_STATES:
        return "DEFERRED"
    if state in ERROR_STATES or item.get("error") or item.get("error_code"):
        return "ERROR"
    if state == "REPLACEMENT_DRAFT" or item.get("human_edit"):
        return "EDITED"
    if state in DECISION_REQUIRED_STATES or str(
        item.get("proposed_resolution") or ""
    ).upper() == "NEEDS_HUMAN_DECISION":
        return "NEEDS_DECISION"
    return "NEEDS_REVIEW"


def queue_view_counts(items: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build count metadata for every view, including an always-complete ALL."""

    counts = {key: 0 for key in QUEUE_VIEWS}
    for item in items:
        counts["ALL"] += 1
        state = str(item.get("review_state") or "PENDING_REVIEW").upper()
        primary = queue_view_for(item)
        counts[primary] += 1
        if state in {"EDITED_AND_ACCEPTED", "CORRECTED"} and primary != "EDITED":
            counts["EDITED"] += 1
        if state == "REPLACEMENT_DRAFT":
            source_state = str(
                ((item.get("human_review") or {}).get("source_suggestion") or {}).get(
                    "review_state"
                )
                or ""
            ).upper()
            if source_state in APPROVED_STATES:
                counts["APPROVED"] += 1
    return {
        key: {"key": key, "label": QUEUE_VIEW_LABELS[key], "count": count}
        for key, count in counts.items()
    }


def batch_exclusion_reasons(
    item: Mapping[str, Any],
    *,
    unsaved_edit: bool = False,
) -> list[str]:
    """Return deterministic reasons why a suggestion cannot enter a batch.

    The server owns this check.  The UI uses the same fields only to explain
    the impact preview before submitting the command.
    """

    reasons: list[str] = []
    if str(item.get("confidence") or "").upper() != "HIGH":
        reasons.append("confidence_not_high")
    if str(item.get("review_state") or "PENDING_REVIEW").upper() != "PENDING_REVIEW":
        reasons.append("already_reviewed")
    if not str(item.get("unresolved_key") or "").strip():
        reasons.append("missing_unresolved_key")
    resolution = str(item.get("proposed_resolution") or "").upper()
    if resolution not in {
        "EXISTING_CHARACTER",
        "NEW_CHARACTER",
        "BACKGROUND_GROUP",
        "NARRATOR",
    }:
        reasons.append("human_decision_required")
    if resolution == "EXISTING_CHARACTER" and not item.get("existing_character_id"):
        reasons.append("existing_character_missing")
    if resolution == "NEW_CHARACTER" and not str(item.get("proposed_character_name") or "").strip():
        reasons.append("new_character_name_missing")
    if resolution == "BACKGROUND_GROUP":
        if str(item.get("speaker_classification") or "").upper() != "BACKGROUND_GROUP":
            reasons.append("background_classification_mismatch")
        if str(item.get("gender_hint") or "").upper() not in {
            "MALE",
            "FEMALE",
            "NEUTRAL_OR_UNKNOWN",
        }:
            reasons.append("background_gender_invalid")
        if item.get("continuity_required") is not False:
            reasons.append("background_continuity_conflict")
        if not str(item.get("generic_speaker_evidence") or "").strip():
            reasons.append("background_evidence_missing")
    if unsaved_edit:
        reasons.append("unsaved_human_edit")
    if item.get("alternative_candidates"):
        reasons.append("alternative_candidate_conflict")
    if item.get("possible_duplicates"):
        reasons.append("duplicate_character_warning")
    if item.get("warnings"):
        reasons.append("warning_requires_review")
    if item.get("continuity_conflict"):
        reasons.append("continuity_conflict")
    if item.get("approved_final_voice_map_available") is False:
        reasons.append("approved_final_voice_map_missing")
    if item.get("stale") or item.get("source_revision_current") is False:
        reasons.append("stale_source_revision")
    voice = item.get("effective_inherited_voice")
    suggested_voice = item.get("suggested_voice")
    if resolution == "BACKGROUND_GROUP" and not voice and not suggested_voice:
        reasons.append("background_voice_unassigned")
    if voice and voice.get("available") is False:
        reasons.append("unavailable_effective_voice")
    if suggested_voice and suggested_voice.get("available") is False:
        reasons.append("unavailable_suggested_voice")
    return reasons


def command_lifecycle_label(status: str) -> str:
    """Human-readable lifecycle label without exposing internal enums."""

    return {
        "IDLE": "Sẵn sàng",
        "SUBMITTING": "Đang lưu quyết định…",
        "VERIFYING": "Đang xác minh kết quả…",
        "VERIFYING_UNKNOWN": "Đang xác minh kết quả…",
        "APPLIED": "Đã lưu và cập nhật Preflight",
        "PARTIAL": "Đã lưu một phần, cần kiểm tra",
        "FAILED": "Chưa lưu được, có thể thử lại an toàn",
        "ACCEPTED_ASYNC": "Đã tiếp nhận, đang xử lý",
    }.get(str(status or "").upper(), "Cần kiểm tra")


__all__ = [
    "APPROVED_STATES",
    "DECISION_REQUIRED_STATES",
    "DEFERRED_STATES",
    "ERROR_STATES",
    "QUEUE_VIEW_LABELS",
    "QUEUE_VIEWS",
    "batch_exclusion_reasons",
    "command_lifecycle_label",
    "queue_view_counts",
    "queue_view_for",
]
