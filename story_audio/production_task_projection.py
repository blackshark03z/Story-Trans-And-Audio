"""Canonical, read-only projection for the daily production workbench."""

from __future__ import annotations

from collections import Counter
import json
from typing import Any, Iterable

from .casting import get_plan
from .db import Database
from .human_approval import resolve_authoritative_human_approval
from .pipeline import JOB_ACTIVE_STATUSES, JOB_PREPARED_STATUS
from .range_input import get_range_input_snapshot
from .range_readiness import get_range_readiness
from .storage import ContentStore
from .config import Settings
from .voice_ref import CustomVoiceContext
from .voice_eligibility import EffectiveVoiceCatalog


_ACTIVE_OR_RECOVERABLE = set(JOB_ACTIVE_STATUSES) | {
    "failed",
    "completed_with_errors",
}
_COMPLETE_STATES = {"COMPLETE"}
_READY_STATES = {"READY_TO_PREPARE"}
_INPUT_TASK_PRIORITY = {
    "REVIEW_TEXT": 0,
    "CREATE_SPEAKER_PROPOSAL": 1,
    "RESOLVE_SPEAKER": 1,
    "APPROVE_SPEAKER_DRAFT": 1,
    "ASSIGN_VOICE": 2,
    "REVIEW_CASTING_PLAN": 3,
}
_SPEAKER_TASKS = {
    "CREATE_SPEAKER_PROPOSAL",
    "RESOLVE_SPEAKER",
    "APPROVE_SPEAKER_DRAFT",
    "PREPARE_RANGE_INPUTS",
    "REVIEW_RANGE_SPEAKER_EXCEPTIONS",
    "APPROVE_READY_SPEAKER_DRAFTS",
    "RESOLVE_SPEAKER_EXCEPTION",
}
_CASTING_TASKS = {
    "ASSIGN_VOICE",
    "REVIEW_CASTING_PLAN",
    "REVIEW_RANGE_VOICE_EXCEPTIONS",
    "RESOLVE_VOICE_EXCEPTION",
    "APPROVE_RANGE_CASTING_PLANS",
}
_RENDER_TASKS = {"START_RENDER_RANGE", "MONITOR_RENDER", "RECOVER_RENDER"}


def _effective_voice_summary(
    db: Database,
    store: ContentStore,
    plan_id: int | None,
    voice_catalog: EffectiveVoiceCatalog | None,
) -> list[dict[str, Any]]:
    if not plan_id:
        return []
    result = get_plan(db, store, int(plan_id))
    utterances = list((result.get("plan") or {}).get("utterances") or [])
    character_ids = sorted(
        {
            int(item["character_id"])
            for item in utterances
            if item.get("character_id") not in (None, "")
        }
    )
    character_names: dict[int, str] = {}
    if character_ids:
        marks = ",".join("?" for _ in character_ids)
        rows = db.fetch_all(
            f"SELECT id,display_name FROM characters WHERE id IN ({marks})",
            tuple(character_ids),
        )
        character_names = {
            int(row["id"]): str(row["display_name"])
            for row in rows
        }
    catalog_items = {
        str(item.get("assignment_key")): item
        for item in (voice_catalog.items if voice_catalog else ())
    }
    grouped: Counter[tuple[str, int | None, str, str]] = Counter()
    for item in utterances:
        role = str(item.get("role") or "unknown")
        character_id = (
            int(item["character_id"])
            if item.get("character_id") not in (None, "")
            else None
        )
        voice_id = str(item.get("resolved_voice_id") or "")
        source = str(item.get("resolution_source") or "pinned_plan")
        grouped[(role, character_id, voice_id, source)] += 1
    summary: list[dict[str, Any]] = []
    for (role, character_id, voice_id, source), line_count in grouped.items():
        if role == "narrator":
            speaker_name = "Người kể chuyện"
            speaker_key = "narrator"
        elif role == "character" and character_id:
            speaker_name = character_names.get(character_id, f"Nhân vật {character_id}")
            speaker_key = f"character:{character_id}"
        else:
            speaker_name = "Người nói chưa rõ"
            speaker_key = "unknown"
        voice = catalog_items.get(voice_id, {})
        summary.append(
            {
                "speaker_key": speaker_key,
                "speaker_name": speaker_name,
                "voice_name": str(voice.get("display_name") or voice_id or "Chưa có"),
                "assignment_source": source,
                "line_count": int(line_count),
                "available": bool(
                    voice_id
                    and (
                        voice_catalog is None
                        or voice_id in voice_catalog.selectable_ids
                    )
                ),
            }
        )
    summary.sort(key=lambda item: (item["speaker_key"], item["voice_name"]))
    return summary


def _safe_effective_voice_summary(
    db: Database,
    store: ContentStore,
    plan_id: int | None,
    voice_catalog: EffectiveVoiceCatalog | None,
) -> list[dict[str, Any]]:
    try:
        return _effective_voice_summary(db, store, plan_id, voice_catalog)
    except (LookupError, ValueError, json.JSONDecodeError):
        return []


def _voice_map_diff(
    previous: list[dict[str, Any]],
    current: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    previous_by_speaker = {item["speaker_key"]: item for item in previous}
    current_by_speaker = {item["speaker_key"]: item for item in current}
    result = []
    for speaker_key in sorted(set(previous_by_speaker) | set(current_by_speaker)):
        before = previous_by_speaker.get(speaker_key)
        after = current_by_speaker.get(speaker_key)
        if before == after:
            continue
        result.append(
            {
                "speaker_name": (after or before or {}).get("speaker_name"),
                "before_voice_name": (before or {}).get("voice_name"),
                "after_voice_name": (after or {}).get("voice_name"),
                "before_line_count": (before or {}).get("line_count", 0),
                "after_line_count": (after or {}).get("line_count", 0),
            }
        )
    return result


def _action(key: str | None, label: str, target: str) -> dict[str, str] | None:
    if not key:
        return None
    return {"key": key, "label": label, "target": target}


def _chapter_ref(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(item["chapter_id"]),
        "number": int(item["chapter_number"]),
        "title": item.get("chapter_title") or item.get("title") or "",
    }


def _review_summary(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("speaker_review") or {}
    target_count = int(
        raw.get("target_count", item.get("latest_speaker_draft_target_count") or 0)
        or 0
    )
    invalid_count = int(
        raw.get("invalid_count", item.get("latest_speaker_draft_invalid_count") or 0)
        or 0
    )
    remaining = int(
        raw.get(
            "remaining_unreviewed_count",
            item.get("latest_speaker_draft_remaining_unreviewed_count") or 0,
        )
        or 0
    )
    return {
        "target_count": target_count,
        "invalid_count": invalid_count,
        "remaining_unreviewed_count": max(0, remaining),
        "stale": bool(raw.get("stale", item.get("latest_speaker_draft_stale", False))),
    }


def _chapter_task(item: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first canonical chapter task, or None when it is eligible."""

    ref = _chapter_ref(item)
    chapter = f"Ch\u01b0\u01a1ng {ref['number']}"
    state = str(item.get("state") or "")
    blockers = list(item.get("blockers") or [])
    blocker = blockers[0] if blockers else None

    if state == "RENDERED_NOT_QA":
        return {
            "task_type": "HUMAN_QA",
            "user_stage": 5,
            "title": "\u0110\u00e1nh gi\u00e1 audio",
            "summary": f"{chapter} c\u00f3 audio ch\u1edd b\u1ea1n nghe v\u00e0 duy\u1ec7t.",
            "action": None,
            "blocker": blocker,
            "next": "Sau khi duy\u1ec7t, ph\u1ea1m vi s\u1eb5n s\u00e0ng cho ch\u1eb7ng ti\u1ebfp theo.",
            "stage_key": "qa",
        }

    if state == "REPAIR_REQUIRED":
        return {
            "task_type": "REPAIR_REQUIRED",
            "user_stage": 5,
            "title": "Cần sửa và tạo bản thay thế",
            "summary": f"{chapter} có audio bị từ chối. Hoàn tất đầu vào rồi tạo một bản thay thế mới.",
            "action": None,
            "blocker": blocker,
            "next": "Bản audio cũ vẫn được giữ làm bằng chứng lịch sử trong khi đầu vào bản thay thế được hoàn tất.",
            "stage_key": "repair",
        }

    if state == "TEXT_BLOCKED":
        return {
            "task_type": "REVIEW_TEXT",
            "user_stage": 2,
            "title": "C\u1ea7n duy\u1ec7t v\u0103n b\u1ea3n",
            "summary": f"{chapter} c\u00f3 v\u0103n b\u1ea3n active ch\u01b0a h\u1ee3p l\u1ec7.",
            "action": _action("REVIEW_TEXT", "Ki\u1ec3m tra v\u0103n b\u1ea3n", "text"),
            "blocker": blocker or "Active Text Revision ch\u01b0a \u0111\u01b0\u1ee3c duy\u1ec7t.",
            "next": "S\u1eeda ho\u1eb7c duy\u1ec7t l\u1ea1i v\u0103n b\u1ea3n tr\u01b0\u1edbc khi g\u00e1n gi\u1ecdng.",
            "stage_key": "text",
        }

    if not item.get("latest_speaker_draft_id"):
        return {
            "task_type": "CREATE_SPEAKER_PROPOSAL",
            "user_stage": 2,
            "title": "T\u1ea1o \u0111\u1ec1 xu\u1ea5t ng\u01b0\u1eddi n\u00f3i",
            "summary": f"{chapter} ch\u01b0a c\u00f3 b\u1ea3n \u0111\u1ec1 xu\u1ea5t ng\u01b0\u1eddi n\u00f3i.",
            "action": _action(
                "CREATE_SPEAKER_PROPOSAL",
                "T\u1ea1o \u0111\u1ec1 xu\u1ea5t ng\u01b0\u1eddi n\u00f3i",
                "speakers",
            ),
            "blocker": "Ch\u01b0a c\u00f3 Speaker Draft cho Text Revision active.",
            "next": "Sau khi t\u1ea1o, x\u00e1c nh\u1eadn t\u1eebng d\u00f2ng ch\u01b0a r\u00f5.",
            "stage_key": "speakers",
        }

    draft_status = str(item.get("latest_speaker_draft_status") or "").lower()
    if draft_status != "approved":
        review = _review_summary(item)
        if review["stale"] or review["remaining_unreviewed_count"]:
            detail = (
                f"C\u00f2n {review['remaining_unreviewed_count']} d\u00f2ng ch\u01b0a x\u00e1c nh\u1eadn"
                if review["remaining_unreviewed_count"]
                else f"C\u00f3 {review['invalid_count']} d\u00f2ng c\u1ea7n x\u1eed l\u00fd"
            )
            return {
                "task_type": "RESOLVE_SPEAKER",
                "user_stage": 2,
                "title": "X\u00e1c nh\u1eadn ng\u01b0\u1eddi n\u00f3i",
                "summary": f"{chapter}: {detail}.",
                "action": _action("RESOLVE_SPEAKER", "X\u00e1c nh\u1eadn v\u00e0 ti\u1ebfp t\u1ee5c", "speakers"),
                "blocker": blocker or "Speaker Draft ch\u01b0a \u0111\u01b0\u1ee3c x\u00e1c nh\u1eadn \u0111\u1ea7y \u0111\u1ee7.",
                "next": "Sau khi x\u00e1c nh\u1eadn \u0111\u1ee7, duy\u1ec7t Speaker Draft.",
                "stage_key": "speakers",
            }
        return {
            "task_type": "APPROVE_SPEAKER_DRAFT",
            "user_stage": 2,
            "title": "Duy\u1ec7t \u0111\u1ec1 xu\u1ea5t ng\u01b0\u1eddi n\u00f3i",
            "summary": f"{chapter} \u0111\u00e3 \u0111\u1ee7 d\u00f2ng \u0111\u1ec3 duy\u1ec7t.",
            "action": _action("APPROVE_SPEAKER_DRAFT", "Duy\u1ec7t Speaker Draft", "speakers"),
            "blocker": blocker or "Speaker Draft \u0111ang ch\u1edd duy\u1ec7t.",
            "next": "Sau khi duy\u1ec7t, t\u1ea1o v\u00e0 ki\u1ec3m tra Final Voice Map.",
            "stage_key": "speakers",
        }

    if state == "VOICE_BLOCKED":
        return {
            "task_type": "ASSIGN_VOICE",
            "user_stage": 3,
            "title": "C\u1ea7n g\u00e1n gi\u1ecdng",
            "summary": f"{chapter} c\u00f3 gi\u1ecdng thi\u1ebfu ho\u1eb7c kh\u00f4ng h\u1ee3p l\u1ec7.",
            "action": _action("ASSIGN_VOICE", "G\u00e1n gi\u1ecdng", "voices"),
            "blocker": blocker or "Final Voice Map ch\u01b0a c\u00f3 gi\u1ecdng h\u1ee3p l\u1ec7.",
            "next": "Sau khi g\u00e1n \u0111\u1ee7 gi\u1ecdng, ki\u1ec3m tra Final Voice Map.",
            "stage_key": "voices",
        }

    if state == "CASTING_REVIEW":
        return {
            "task_type": "REVIEW_CASTING_PLAN",
            "user_stage": 3,
            "title": "Ki\u1ec3m tra b\u1ea3n \u0111\u1ed3 gi\u1ecdng",
            "summary": f"{chapter} c\u00f3 Final Voice Map ch\u01b0a \u0111\u01b0\u1ee3c duy\u1ec7t.",
            "action": _action("REVIEW_CASTING_PLAN", "Ki\u1ec3m tra b\u1ea3n \u0111\u1ed3 gi\u1ecdng", "voice_map"),
            "blocker": blocker or "Final Voice Map \u0111ang ch\u1edd duy\u1ec7t.",
            "next": "Sau khi duy\u1ec7t, ph\u1ea1m vi s\u1eb5n s\u00e0ng \u0111\u1ec3 chu\u1ea9n b\u1ecb.",
            "stage_key": "voice_map",
        }

    if state in {"PREPARED", "RENDERING_OR_PAUSED"}:
        return {
            "task_type": "MONITOR_RENDER",
            "user_stage": 4,
            "title": "Theo d\u00f5i render",
            "summary": f"{chapter} \u0111ang c\u00f3 c\u00f4ng vi\u1ec7c production.",
            "action": _action("MONITOR_RENDER", "Theo d\u00f5i c\u00f4ng vi\u1ec7c", "render"),
            "blocker": blocker,
            "next": "Ch\u1edd render ho\u00e0n t\u1ea5t, sau \u0111\u00f3 nghe v\u00e0 duy\u1ec7t.",
            "stage_key": "render",
        }
    if state == "STATE_UNRESOLVED":
        return {
            "task_type": "REVIEW_TEXT",
            "user_stage": 2,
            "title": "C\u1ea7n ki\u1ec3m tra tr\u1ea1ng th\u00e1i",
            "summary": f"{chapter} c\u00f3 d\u1eef li\u1ec7u ch\u01b0a x\u00e1c \u0111\u1ecbnh.",
            "action": _action("REVIEW_TEXT", "Ki\u1ec3m tra tr\u1ea1ng th\u00e1i", "text"),
            "blocker": blocker or "Kh\u00f4ng th\u1ec3 x\u00e1c \u0111\u1ecbnh tr\u1ea1ng th\u00e1i canonical.",
            "next": "M\u1edf chi ti\u1ebft k\u1ef9 thu\u1eadt \u0111\u1ec3 xem nguy\u00ean nh\u00e2n.",
            "stage_key": "text",
        }
    return None


def _repair_blocker_details(source: dict[str, Any]) -> list[dict[str, Any]]:
    chapter_number = int(source.get("chapter_number") or 0)
    raw_blockers = [str(item) for item in source.get("repair_input_blockers") or []]
    speaker_blocked = any("speaker draft" in item.casefold() for item in raw_blockers)
    details: list[dict[str, Any]] = []
    for message in raw_blockers:
        normalized = message.casefold()
        if "speaker draft" in normalized:
            stale = "stale" in normalized
            details.append({
                "code": "SPEAKER_DRAFT_STALE" if stale else "SPEAKER_DRAFT_NOT_APPROVED",
                "title": (
                    "Bản xác định người nói cần được làm mới"
                    if stale
                    else "Bản xác định người nói mới nhất chưa được duyệt"
                ),
                "explanation": "Cần xác nhận ai đang nói trước khi tạo bản audio thay thế.",
                "action_label": f"Duyệt người nói Chương {chapter_number}",
                "target": "assignment",
                "assignment_focus": "review",
                "technical_reason": message,
            })
        elif "final voice map" in normalized or "casting plan" in normalized:
            details.append({
                "code": "VOICE_MAP_DEPENDS_ON_SPEAKER" if speaker_blocked else "VOICE_MAP_NOT_READY",
                "title": (
                    "Bản đồ giọng cuối cùng sẽ được tạo sau khi duyệt người nói"
                    if speaker_blocked
                    else f"Chương {chapter_number} chưa có bản đồ giọng cuối cùng"
                ),
                "explanation": (
                    "Sau khi duyệt người nói, hãy chọn giọng cho các vai rồi tạo và duyệt bản đồ giọng cuối cùng."
                    if speaker_blocked
                    else "Cần hoàn tất người nói và giọng hiệu lực trước khi PREPARE bản thay thế."
                ),
                "action_label": None if speaker_blocked else f"Hoàn tất giọng cho Chương {chapter_number}",
                "target": "assignment",
                "assignment_focus": "voices",
                "technical_reason": message,
                "dependent": speaker_blocked,
            })
        else:
            details.append({
                "code": "REPAIR_INPUT_BLOCKED",
                "title": "Đầu vào bản thay thế chưa sẵn sàng",
                "explanation": message,
                "action_label": f"Kiểm tra Chương {chapter_number}",
                "target": "production",
                "assignment_focus": None,
                "technical_reason": message,
            })
    return details


def _repair_phases(repair: dict[str, Any]) -> list[dict[str, Any]]:
    details = list(repair.get("input_blocker_details") or [])
    codes = {str(item.get("code") or "") for item in details}
    current = 1 if any("SPEAKER" in code for code in codes) else 2 if details else 3
    labels = [
        "Xác nhận nội dung và người nói",
        "Hoàn tất cấu hình giọng",
        "Chuẩn bị bản thay thế",
        "Render bản thay thế",
        "Nghe và duyệt bản mới",
    ]
    return [
        {
            "number": number,
            "key": f"repair-{number}",
            "label": label,
            "current": number == current,
            "complete": number < current,
            "locked": number > current,
            "state": "current" if number == current else "complete" if number < current else "locked",
            "summary": "Đang thực hiện" if number == current else "Đã xong" if number < current else "Sẽ thực hiện sau",
        }
        for number, label in enumerate(labels, 1)
    ]


def _phases(user_stage: int, completed: bool = False) -> list[dict[str, Any]]:
    labels = [
        "Ch\u1ecdn ph\u1ea1m vi",
        "Ki\u1ec3m tra n\u1ed9i dung v\u00e0 ng\u01b0\u1eddi n\u00f3i",
        "Ki\u1ec3m tra nh\u00e2n v\u1eadt v\u00e0 gi\u1ecdng",
        "Chu\u1ea9n b\u1ecb v\u00e0 render",
        "Nghe v\u00e0 duy\u1ec7t",
        "Ho\u00e0n t\u1ea5t v\u00e0 t\u1ea3i xu\u1ed1ng",
    ]
    return [
        {
            "number": number,
            "key": f"stage-{number}",
            "label": label,
            "current": number == user_stage and not completed,
            "complete": completed or number < user_stage,
            "locked": not completed and number > user_stage,
            "state": "current" if number == user_stage and not completed else "complete" if completed or number < user_stage else "locked",
            "summary": "\u0110ang th\u1ef1c hi\u1ec7n" if number == user_stage and not completed else "\u0110\u00e3 xong" if completed or number < user_stage else "S\u1ebd th\u1ef1c hi\u1ec7n sau",
        }
        for number, label in enumerate(labels, 1)
    ]


def _typed_task_sections(
    *,
    task_type: str,
    readiness: dict[str, Any],
    affected: dict[str, Any] | None,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    sections = {
        "speaker": None,
        "casting": None,
        "range_prepare": None,
        "render": None,
        "qa": None,
        "repair": None,
    }
    source = payload or {}
    if task_type in _SPEAKER_TASKS:
        if task_type in {
            "PREPARE_RANGE_INPUTS",
            "REVIEW_RANGE_SPEAKER_EXCEPTIONS",
            "APPROVE_READY_SPEAKER_DRAFTS",
            "RESOLVE_SPEAKER_EXCEPTION",
        }:
            sections["speaker"] = {
                "summary": dict(source.get("summary") or {}),
                "proposal_chapters": list(source.get("proposal_chapters") or []),
                "exception_queue": list(
                    source.get("speaker_exception_queue") or []
                ),
                "ready_drafts": list(source.get("ready_speaker_drafts") or []),
                "casting_generation_ready": list(
                    source.get("casting_generation_ready") or []
                ),
            }
        else:
            review = _review_summary(source)
            sections["speaker"] = {
                "chapter_id": affected["id"] if affected else None,
                "draft_id": source.get("latest_speaker_draft_id"),
                "draft_status": source.get("latest_speaker_draft_status"),
                **review,
            }
    elif task_type in _CASTING_TASKS:
        if task_type in {
            "REVIEW_RANGE_VOICE_EXCEPTIONS",
            "RESOLVE_VOICE_EXCEPTION",
            "APPROVE_RANGE_CASTING_PLANS",
        }:
            sections["casting"] = {
                "summary": dict(source.get("summary") or {}),
                "voice_exception_queue": list(
                    source.get("voice_exception_queue") or []
                ),
                "plans_awaiting_approval": list(
                    source.get("casting_approvals") or []
                ),
            }
        else:
            sections["casting"] = {
                "chapter_id": affected["id"] if affected else None,
                "plan_id": source.get("latest_casting_plan_id"),
                "plan_revision": source.get("latest_casting_plan_revision"),
                "plan_status": source.get("latest_casting_plan_status"),
                "voice_issues": list(source.get("voice_issues") or []),
            }
    elif task_type == "PREPARE_RANGE":
        scope = readiness.get("scope") or {}
        sections["range_prepare"] = {
            "book_id": scope.get("book_id"),
            "from_chapter": scope.get("from_chapter"),
            "to_chapter": scope.get("to_chapter"),
            "chapter_count": scope.get("chapter_count"),
        }
    elif task_type in _RENDER_TASKS:
        sections["render"] = {
            "job_id": source.get("id") or source.get("job_id"),
            "job_status": source.get("status"),
            "replacement_for_artifact_id": source.get(
                "replacement_for_artifact_id"
            ),
            "replacement": bool(source.get("replacement_for_artifact_id")),
        }
    elif task_type == "HUMAN_QA":
        sections["qa"] = {
            "chapter_id": affected["id"] if affected else None,
            "artifact_id": source.get("active_artifact_id"),
            "job_id": source.get("active_output_job_id"),
            "human_qa_status": source.get("human_qa_status"),
            "duration_ms": source.get("artifact_duration_ms"),
            "size_bytes": source.get("artifact_size_bytes"),
        }
    elif task_type == "REPAIR_REQUIRED":
        blocker_details = _repair_blocker_details(source)
        sections["repair"] = {
            "chapter_id": affected["id"] if affected else None,
            "artifact_id": source.get("active_artifact_id"),
            "job_id": source.get("active_output_job_id"),
            "duration_ms": source.get("artifact_duration_ms"),
            "size_bytes": source.get("artifact_size_bytes"),
            "created_at": source.get("artifact_created_at"),
            "qa_note": source.get("human_qa_note"),
            "qa_recorded_at": source.get("human_qa_recorded_at"),
            "active_text_revision_id": source.get("active_text_revision_id"),
            "active_output_text_revision_id": source.get(
                "active_output_text_revision_id"
            ),
            "current_casting_plan_id": source.get("latest_casting_plan_id"),
            "current_casting_plan_revision": source.get(
                "latest_casting_plan_revision"
            ),
            "current_casting_plan_status": source.get("latest_casting_plan_status"),
            "rejected_casting_plan_id": source.get(
                "active_output_casting_plan_id"
            ),
            "rejected_casting_plan_revision": source.get(
                "active_output_casting_plan_revision"
            ),
            "prepare_ready": bool(source.get("repair_prepare_ready")),
            "input_blockers": list(source.get("repair_input_blockers") or []),
            "input_blocker_details": blocker_details,
            "effective_voice_map": list(source.get("effective_voice_map") or []),
            "voice_map_diff": list(source.get("voice_map_diff") or []),
        }
    return sections


def _base_projection(
    *,
    readiness: dict[str, Any],
    task_scope: str,
    task_type: str,
    task_key: str,
    user_stage: int,
    title: str,
    summary: str,
    affected: dict[str, Any] | None,
    action: dict[str, str] | None,
    blocker: str | None,
    next_hint: str,
    queue: list[dict[str, Any]],
    technical: Iterable[str],
    range_task: bool,
    task_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scope = dict(readiness.get("scope") or {})
    range_identity = (
        f"book:{scope.get('book_id')}:{scope.get('from_chapter')}-{scope.get('to_chapter')}"
    )
    range_summary = dict(readiness.get("summary") or {})
    range_summary["eligible"] = not blocker and all(
        row.get("status") in {"complete", "ready"} for row in queue
    )
    sections = _typed_task_sections(
        task_type=task_type,
        readiness=readiness,
        affected=affected,
        payload=task_payload,
    )
    canonical_task = {
        "task_scope": task_scope,
        "task_type": task_type,
        "task_key": task_key,
        "user_stage": user_stage,
        "title": title,
        "summary": summary,
        "affected_chapter": affected,
        "primary_action": action,
        "blocker": blocker,
        "next_task_hint": next_hint,
        "technical_details": list(technical),
        "current_stage_key": "repair" if task_type == "REPAIR_REQUIRED" else {
            1: "scope",
            2: "speakers",
            3: "voice_map",
            4: "prepare",
            5: "qa",
            6: "done",
        }[user_stage],
        "input_summary": dict((task_payload or {}).get("summary") or {}),
        **sections,
    }
    result = {
        "range_identity": range_identity,
        "task_scope": task_scope,
        "task_type": task_type,
        "task_key": task_key,
        "user_stage": user_stage,
        "title": title,
        "summary": summary,
        "task_title": title,
        "task_summary": summary,
        "affected_chapter": affected,
        "chapter_queue": queue,
        "queue": queue,
        "primary_action": action,
        "secondary_actions": [],
        "secondary_links": [],
        "blocker": blocker,
        "range_readiness": {"scope": scope, "summary": range_summary},
        "next_task_hint": next_hint,
        "next_task_after_success": next_hint,
        "technical_details": list(canonical_task["technical_details"]),
        "range_task": range_task,
        "current_stage_key": canonical_task["current_stage_key"],
        "conceptual_state": task_type,
        "input_summary": dict(canonical_task["input_summary"]),
        "phases": (
            _repair_phases(sections["repair"] or {})
            if task_type == "REPAIR_REQUIRED"
            else _phases(user_stage, task_type == "COMPLETE")
        ),
        "canonical_task": canonical_task,
        "inspected_chapter": None,
        "inspection_summary": None,
    }
    return result


def _finalize_projection(
    projection: dict[str, Any],
    *,
    rows: list[dict[str, Any]],
    inspected_chapter_id: int | None,
) -> dict[str, Any]:
    canonical_id = (projection.get("affected_chapter") or {}).get("id")
    inspected = next(
        (
            row
            for row in rows
            if inspected_chapter_id
            and int(row.get("chapter_id") or 0) == int(inspected_chapter_id)
        ),
        None,
    )
    if inspected:
        ref = _chapter_ref(inspected)
        task = _chapter_task(inspected)
        projection["inspected_chapter"] = ref
        projection["inspection_summary"] = {
            "read_only": True,
            "task_type": task["task_type"] if task else "READY_TO_PREPARE",
            "title": task["title"] if task else "S\u1eb5n s\u00e0ng chu\u1ea9n b\u1ecb",
            "summary": (
                task["summary"]
                if task
                else f"Ch\u01b0\u01a1ng {ref['number']} \u0111\u00e3 \u0111\u1ee7 \u0111i\u1ec1u ki\u1ec7n."
            ),
            "blocker": task["blocker"] if task else None,
        }
    for item in projection.get("chapter_queue") or []:
        item["canonical_task"] = bool(
            canonical_id and int(item["chapter_id"]) == int(canonical_id)
        )
        item["inspected"] = bool(
            inspected_chapter_id
            and int(item["chapter_id"]) == int(inspected_chapter_id)
        )
    return projection


def project_production_task(state: dict[str, Any]) -> dict[str, Any]:
    """Purely project a normalized production state.

    The input is a read-only snapshot. No database or runtime objects are used
    here, which makes the precedence and range gates directly testable.
    """

    readiness = dict(state.get("readiness") or {})
    scope = dict(readiness.get("scope") or state.get("scope") or {})
    rows = [dict(row) for row in readiness.get("chapters") or state.get("chapters") or []]
    inspected_chapter_id = state.get("inspected_chapter_id")

    def finish(projection: dict[str, Any]) -> dict[str, Any]:
        return _finalize_projection(
            projection,
            rows=rows,
            inspected_chapter_id=inspected_chapter_id,
        )

    if not rows:
        return finish(_base_projection(
            readiness={"scope": scope, "summary": {}},
            task_scope="chapter",
            task_type="REVIEW_TEXT",
            task_key="scope:missing",
            user_stage=1,
            title="Ch\u1ecdn s\u00e1ch v\u00e0 ch\u01b0\u01a1ng",
            summary="Ch\u1ecdn ph\u1ea1m vi \u0111\u1ec3 b\u1eaft \u0111\u1ea7u.",
            affected=None,
            action=_action("SELECT_SCOPE", "Ch\u1ecdn s\u00e1ch v\u00e0 ch\u01b0\u01a1ng", "scope"),
            blocker=None,
            next_hint="Sau khi ch\u1ecdn, h\u1ec7 th\u1ed1ng s\u1ebd ki\u1ec3m tra ph\u1ea1m vi.",
            queue=[],
            technical=["projection:no_scope"],
            range_task=False,
        ))

    range_jobs = [dict(job) for job in state.get("range_jobs") or []]
    exact_jobs = [
        job
        for job in range_jobs
        if int(job.get("chapter_count") or 0) == len(rows)
        and job.get("all_chapters_match", True)
        and str(job.get("status") or "").lower()
        in ({JOB_PREPARED_STATUS} | _ACTIVE_OR_RECOVERABLE)
    ]
    exact_jobs.sort(key=lambda job: int(job.get("id") or job.get("job_id") or 0), reverse=True)
    rejected_output_job_ids = [
        int(row.get("active_output_job_id") or 0)
        for row in rows
        if row.get("state") == "REPAIR_REQUIRED" and row.get("active_output_job_id")
    ]
    if rejected_output_job_ids:
        newest_rejected_output_job_id = max(rejected_output_job_ids)
        exact_jobs = [
            job
            for job in exact_jobs
            if str(job.get("status") or "").lower() not in {"failed", "completed_with_errors"}
            or int(job.get("id") or job.get("job_id") or 0) > newest_rejected_output_job_id
        ]
    exact_job = exact_jobs[0] if len(exact_jobs) == 1 else None
    scope_key = (
        f"range:{scope.get('book_id')}:{scope.get('from_chapter')}-{scope.get('to_chapter')}"
    )

    queue: list[dict[str, Any]] = []
    for row in rows:
        task = _chapter_task(row)
        if row.get("state") == "COMPLETE":
            status = "complete"
        elif task:
            status = "pending"
        else:
            status = "ready"
        queue.append(
            {
                "chapter_id": int(row["chapter_id"]),
                "chapter_number": int(row["chapter_number"]),
                "title": row.get("chapter_title") or row.get("title") or "",
                "status": status,
                "state": row.get("state"),
                "user_stage": task["user_stage"] if task else 4,
                "task_type": task["task_type"] if task else None,
                "task_key": (
                    f"chapter:{int(row['chapter_id'])}:{task['task_type']}"
                    if task
                    else f"chapter:{int(row['chapter_id'])}:READY"
                ),
            }
        )

    def repair_projection_or_none() -> dict[str, Any] | None:
        repair_candidates = [
            (row, task)
            for row in rows
            if (task := _chapter_task(row)) and task["task_type"] == "REPAIR_REQUIRED"
        ]
        if not repair_candidates:
            return None
        row, task = min(
            repair_candidates,
            key=lambda item: int(item[0]["chapter_number"]),
        )
        ref = _chapter_ref(row)
        for queue_item in queue:
            if int(queue_item["chapter_id"]) == ref["id"]:
                queue_item["status"] = "current"
            elif queue_item["status"] == "pending":
                queue_item["status"] = "blocked"
        return finish(_base_projection(
            readiness=readiness,
            task_scope="chapter",
            task_type=task["task_type"],
            task_key=(
                f"chapter:{ref['id']}:REPAIR_REQUIRED:"
                f"artifact:{int(row.get('active_artifact_id') or 0)}:"
                f"plan:{int(row.get('latest_casting_plan_id') or 0)}"
            ),
            user_stage=task["user_stage"],
            title=task["title"],
            summary=task["summary"],
            affected=ref,
            action=task["action"],
            blocker=task["blocker"],
            next_hint=task["next"],
            queue=queue,
            technical=[
                f"chapter_state:{row.get('state')}",
                f"artifact_id:{int(row.get('active_artifact_id') or 0)}",
                f"current_casting_plan_id:{int(row.get('latest_casting_plan_id') or 0)}",
            ],
            range_task=False,
            task_payload=row,
        ))

    # A rejected active artifact is the immediate operator task. Do not let stale
    # range-input preparation hide the repair decision unless a live exact job
    # already needs attention below.
    if len(exact_jobs) < 2 and exact_job is None:
        repair_projection = repair_projection_or_none()
        if repair_projection:
            return repair_projection

    range_inputs = state.get("range_inputs")
    if isinstance(range_inputs, dict):
        text_candidates = []
        for row in rows:
            task = _chapter_task(row)
            if task and task["task_type"] == "REVIEW_TEXT":
                text_candidates.append((int(row["chapter_number"]), row, task))
        if text_candidates:
            _, row, task = min(text_candidates, key=lambda item: item[0])
            ref = _chapter_ref(row)
            for queue_item in queue:
                queue_item["status"] = (
                    "current"
                    if int(queue_item["chapter_id"]) == ref["id"]
                    else "blocked"
                    if queue_item["status"] == "pending"
                    else queue_item["status"]
                )
            return finish(_base_projection(
                readiness=readiness,
                task_scope="chapter",
                task_type=task["task_type"],
                task_key=(
                    f"chapter:{ref['id']}:{task['task_type']}:"
                    f"artifact:{int(row.get('active_artifact_id') or 0)}"
                    if task["task_type"] == "HUMAN_QA"
                    else f"chapter:{ref['id']}:{task['task_type']}"
                ),
                user_stage=task["user_stage"],
                title=task["title"],
                summary=task["summary"],
                affected=ref,
                action=task["action"],
                blocker=task["blocker"],
                next_hint=task["next"],
                queue=queue,
                technical=[
                    f"state:{row.get('state')}",
                    f"chapter_id:{ref['id']}",
                ],
                range_task=False,
                task_payload=row,
            ))

        input_summary = dict(range_inputs.get("summary") or {})
        proposals = list(range_inputs.get("proposal_chapters") or [])
        speaker_exceptions = list(
            range_inputs.get("speaker_exception_queue") or []
        )
        ready_drafts = list(range_inputs.get("ready_speaker_drafts") or [])
        voice_exceptions = list(range_inputs.get("voice_exception_queue") or [])
        casting_ready = list(
            range_inputs.get("casting_generation_ready") or []
        )
        casting_approvals = list(range_inputs.get("casting_approvals") or [])
        total = int(input_summary.get("total_chapters") or len(rows))

        def range_input_task(
            *,
            task_type: str,
            task_key: str,
            user_stage: int,
            title: str,
            summary: str,
            action_label: str,
            next_hint: str,
            affected_item: dict[str, Any] | None = None,
            blocker: str | None = None,
        ) -> dict[str, Any]:
            affected = None
            if affected_item:
                affected = {
                    "id": int(affected_item["chapter_id"]),
                    "number": int(affected_item["chapter_number"]),
                    "title": affected_item.get("chapter_title") or "",
                }
                for queue_item in queue:
                    if int(queue_item["chapter_id"]) == affected["id"]:
                        queue_item["status"] = "current"
                    elif queue_item["status"] == "pending":
                        queue_item["status"] = "blocked"
            return finish(_base_projection(
                readiness=readiness,
                task_scope="exception" if affected else "range",
                task_type=task_type,
                task_key=task_key,
                user_stage=user_stage,
                title=title,
                summary=summary,
                affected=affected,
                action=_action(task_type, action_label, "speakers" if user_stage == 2 else "voices"),
                blocker=blocker,
                next_hint=next_hint,
                queue=queue,
                technical=[
                    f"range_input_task:{task_type}",
                    f"speaker_exceptions:{len(speaker_exceptions)}",
                    f"voice_exceptions:{len(voice_exceptions)}",
                ],
                range_task=True,
                task_payload=range_inputs,
            ))

        if proposals:
            return range_input_task(
                task_type="PREPARE_RANGE_INPUTS",
                task_key=f"{scope_key}:prepare-inputs:{len(proposals)}",
                user_stage=2,
                title="Chuẩn bị dữ liệu đầu vào",
                summary=f"{len(proposals)} trong {total} chương cần tạo hoặc làm mới đề xuất người nói.",
                action_label=f"Chuẩn bị dữ liệu cho {total} chương",
                next_hint="Sau khi phân tích, hệ thống chỉ đưa các trường hợp ngoại lệ vào hàng chờ.",
            )
        if speaker_exceptions:
            first = speaker_exceptions[0]
            chapters = len({
                int(item["chapter_id"]) for item in speaker_exceptions
            })
            return range_input_task(
                task_type="REVIEW_RANGE_SPEAKER_EXCEPTIONS",
                task_key=(
                    f"{scope_key}:speaker-exception:"
                    f"{first['draft_id']}:{first['utterance_id']}:"
                    f"{len(speaker_exceptions)}"
                ),
                user_stage=2,
                title="Kiểm tra ngoại lệ người nói",
                summary=(
                    f"{len(speaker_exceptions)} trường hợp cần kiểm tra "
                    f"trong {chapters} chương."
                ),
                action_label=(
                    "Lưu và duyệt chương"
                    if sum(
                        1
                        for item in speaker_exceptions
                        if int(item["chapter_id"]) == int(first["chapter_id"])
                    ) == 1
                    else "Lưu và sang câu tiếp theo"
                ),
                next_hint="Sau mỗi quyết định, hệ thống mở ngoại lệ tiếp theo theo thứ tự chương.",
                affected_item=first,
            )
        if ready_drafts:
            return range_input_task(
                task_type="APPROVE_READY_SPEAKER_DRAFTS",
                task_key=f"{scope_key}:approve-speakers:{','.join(str(item['draft_id']) for item in ready_drafts)}",
                user_stage=2,
                title="Duyệt chương không có ngoại lệ",
                summary=f"{len(ready_drafts)} chương không còn ngoại lệ người nói.",
                action_label=f"Duyệt {len(ready_drafts)} chương",
                next_hint="Các đề xuất high-confidence sẽ chỉ được chấp nhận khi bạn bấm duyệt.",
            )
        if voice_exceptions:
            first = voice_exceptions[0]
            return range_input_task(
                task_type="REVIEW_RANGE_VOICE_EXCEPTIONS",
                task_key=(
                    f"{scope_key}:voice-exception:"
                    f"{first['speaker_key']}:{len(voice_exceptions)}"
                ),
                user_stage=3,
                title="Gán giọng cho ngoại lệ",
                summary=(
                    f"{input_summary.get('inherited_voice_count', 0)} người nói đã kế thừa giọng; "
                    f"{len(voice_exceptions)} cần chọn."
                ),
                action_label=f"Gán giọng cho {len(voice_exceptions)} người",
                next_hint="Giọng narrator và nhân vật đã biết được giữ lại; chỉ ngoại lệ cần thao tác.",
                affected_item=first,
            )
        if casting_ready:
            return range_input_task(
                task_type="PREPARE_RANGE_INPUTS",
                task_key=f"{scope_key}:create-casting-drafts:{','.join(str(item['draft_id']) for item in casting_ready)}",
                user_stage=3,
                title="Tạo bản đồ giọng theo phạm vi",
                summary=f"{len(casting_ready)} chương đã đủ người nói và giọng để tạo bản nháp.",
                action_label=f"Chuẩn bị bản đồ giọng cho {len(casting_ready)} chương",
                next_hint="Bản nháp vẫn chưa được duyệt và chưa thể dùng để PREPARE.",
            )
        if casting_approvals:
            return range_input_task(
                task_type="APPROVE_RANGE_CASTING_PLANS",
                task_key=f"{scope_key}:approve-casting:{','.join(str(item['plan_id']) for item in casting_approvals)}",
                user_stage=3,
                title="Duyệt bản đồ giọng",
                summary=f"{len(casting_approvals)} chương có bản đồ giọng hợp lệ đang chờ duyệt.",
                action_label=f"Duyệt bản đồ giọng cho {len(casting_approvals)} chương",
                next_hint="Chỉ sau bước duyệt này phạm vi mới có thể sẵn sàng PREPARE.",
            )

    first_task: tuple[dict[str, Any], dict[str, Any]] | None = None
    input_candidates: list[
        tuple[int, int, dict[str, Any], dict[str, Any]]
    ] = []
    for row in rows:
        task = _chapter_task(row)
        priority = _INPUT_TASK_PRIORITY.get(task["task_type"]) if task else None
        if priority is not None:
            input_candidates.append(
                (priority, int(row["chapter_number"]), row, task)
            )
    if input_candidates:
        _, _, row, task = min(input_candidates, key=lambda item: (item[0], item[1]))
        first_task = (row, task)
    if first_task:
        row, task = first_task
        ref = _chapter_ref(row)
        for queue_item in queue:
            if int(queue_item["chapter_id"]) == ref["id"]:
                queue_item["status"] = "current"
            elif queue_item["status"] == "pending":
                queue_item["status"] = "blocked"
        return finish(_base_projection(
            readiness=readiness,
            task_scope="chapter",
            task_type=task["task_type"],
            task_key=(
                f"chapter:{ref['id']}:{task['task_type']}:"
                f"artifact:{int(row.get('active_artifact_id') or 0)}"
                if task["task_type"] == "HUMAN_QA"
                else f"chapter:{ref['id']}:{task['task_type']}"
            ),
            user_stage=task["user_stage"],
            title=task["title"],
            summary=task["summary"],
            affected=ref,
            action=task["action"],
            blocker=task["blocker"],
            next_hint=task["next"],
            queue=queue,
            technical=[
                f"range:{scope.get('from_chapter')}-{scope.get('to_chapter')}",
                f"chapter_state:{row.get('state')}",
            ],
            range_task=False,
            task_payload=row,
        ))

    all_complete = all(row.get("state") in _COMPLETE_STATES for row in rows)
    if all_complete:
        return finish(_base_projection(
            readiness=readiness,
            task_scope="range",
            task_type="COMPLETE",
            task_key=f"{scope_key}:COMPLETE",
            user_stage=6,
            title="Ph\u1ea1m vi \u0111\u00e3 ho\u00e0n t\u1ea5t",
            summary="T\u1ea5t c\u1ea3 ch\u01b0\u01a1ng trong ph\u1ea1m vi \u0111\u00e3 c\u00f3 audio \u0111\u01b0\u1ee3c duy\u1ec7t.",
            affected=None,
            action=None,
            blocker=None,
            next_hint="Ch\u1ecdn ph\u1ea1m vi ti\u1ebfp theo khi b\u1ea1n mu\u1ed1n ti\u1ebfp t\u1ee5c.",
            queue=queue,
            technical=["range_gate:complete"],
            range_task=True,
        ))

    if len(exact_jobs) > 1:
        job_ids = [int(job.get("id") or job.get("job_id")) for job in exact_jobs]
        return finish(_base_projection(
            readiness=readiness,
            task_scope="range",
            task_type="RECOVER_RENDER",
            task_key=f"{scope_key}:RECOVER_RENDER:conflict",
            user_stage=4,
            title="C\u1ea7n x\u1eed l\u00fd xung \u0111\u1ed9t render",
            summary="Ph\u1ea1m vi c\u00f3 nhi\u1ec1u Job tr\u00f9ng kh\u1edbp n\u00ean ch\u01b0a th\u1ec3 b\u1eaft \u0111\u1ea7u ho\u1eb7c chu\u1ea9n b\u1ecb th\u00eam.",
            affected=None,
            action=None,
            blocker="H\u00e3y x\u1eed l\u00fd c\u00e1c Job tr\u00f9ng ph\u1ea1m vi tr\u01b0\u1edbc khi ti\u1ebfp t\u1ee5c.",
            next_hint="M\u1edf C\u00f4ng vi\u1ec7c \u0111\u1ec3 x\u00e1c \u0111\u1ecbnh Job h\u1ee3p l\u1ec7 c\u1ea7n ti\u1ebfp t\u1ee5c.",
            queue=queue,
            technical=[
                f"job_ids:{','.join(str(job_id) for job_id in job_ids)}",
                "blocker_code:MULTIPLE_EXACT_RANGE_JOBS",
                "range_gate:multiple_exact_jobs",
            ],
            range_task=True,
        ))

    if exact_job:
        job_id = int(exact_job.get("id") or exact_job.get("job_id"))
        status = str(exact_job.get("status") or "").lower()
        repair_row = next(
            (
                row
                for row in rows
                if row.get("state") == "REPAIR_REQUIRED"
                and row.get("replacement_for_artifact_id")
            ),
            None,
        )
        if repair_row:
            exact_job["replacement_for_artifact_id"] = int(
                repair_row["replacement_for_artifact_id"]
            )
        if status == JOB_PREPARED_STATUS:
            action = _action(
                "START_RENDER_RANGE",
                (
                    f"Bắt đầu render lại Chương {int(repair_row['chapter_number'])}"
                    if repair_row
                    else "B\u1eaft \u0111\u1ea7u render"
                ),
                "render",
            )
            task_type = "START_RENDER_RANGE"
            title = "Bắt đầu render lại" if repair_row else "B\u1eaft \u0111\u1ea7u render"
            summary = (
                "Job replacement đã ghim đúng văn bản và bản đồ giọng; bản audio cũ vẫn được giữ trong lịch sử."
                if repair_row
                else "Ph\u1ea1m vi \u0111\u00e3 \u0111\u01b0\u1ee3c chu\u1ea9n b\u1ecb; render l\u00e0 thao t\u00e1c ri\u00eang."
            )
            stage = 4
        elif status in {"paused", "interrupted", "failed", "completed_with_errors"}:
            action = _action("RECOVER_RENDER", "X\u1eed l\u00fd render", "render")
            task_type = "RECOVER_RENDER"
            title = "C\u1ea7n x\u1eed l\u00fd render"
            summary = f"Ph\u1ea1m vi c\u00f3 Job #{job_id} c\u1ea7n x\u1eed l\u00fd ti\u1ebfp."
            stage = 4
        else:
            action = _action("MONITOR_RENDER", "Theo d\u00f5i render", "render")
            task_type = "MONITOR_RENDER"
            title = "Theo d\u00f5i render"
            summary = f"Ph\u1ea1m vi \u0111ang \u0111\u01b0\u1ee3c render trong Job #{job_id}."
            stage = 4
        return finish(_base_projection(
            readiness=readiness,
            task_scope="range",
            task_type=task_type,
            task_key=f"{scope_key}:{task_type}:job:{job_id}",
            user_stage=stage,
            title=title,
            summary=summary,
            affected=None,
            action=action,
            blocker=None,
            next_hint="Sau khi render xong, nghe v\u00e0 duy\u1ec7t t\u1eebng audio.",
            queue=queue,
            technical=[f"job:{job_id}", f"job_status:{status}", "range_gate:exact_job"],
            range_task=True,
            task_payload=exact_job,
        ))

    repair_projection = repair_projection_or_none()
    if repair_projection:
        return repair_projection

    eligible = all(row.get("state") in _COMPLETE_STATES | _READY_STATES for row in rows)
    if eligible and any(row.get("state") == "READY_TO_PREPARE" for row in rows):
        count = len(rows)
        return finish(_base_projection(
            readiness=readiness,
            task_scope="range",
            task_type="PREPARE_RANGE",
            task_key=f"{scope_key}:PREPARE_RANGE",
            user_stage=4,
            title="Chu\u1ea9n b\u1ecb ph\u1ea1m vi audio",
            summary=f"Ph\u1ea1m vi {count} ch\u01b0\u01a1ng \u0111\u00e3 \u0111\u1ee7 \u0111i\u1ec1u ki\u1ec7n \u0111\u1ec3 ghim \u0111\u1ea7u v\u00e0o.",
            affected=None,
            action=_action("PREPARE_RANGE", "Chu\u1ea9n b\u1ecb audio", "prepare"),
            blocker=None,
            next_hint="Sau khi chu\u1ea9n b\u1ecb, b\u1ea1n ph\u1ea3i b\u1ea5m B\u1eaft \u0111\u1ea7u render ri\u00eang.",
            queue=queue,
            technical=["range_gate:all_eligible", "worker_wake:after_explicit_start_only"],
            range_task=True,
        ))

    qa_candidates = [
        (row, task)
        for row in rows
        if (task := _chapter_task(row)) and task["task_type"] == "HUMAN_QA"
    ]
    if qa_candidates:
        row, task = min(
            qa_candidates,
            key=lambda item: int(item[0]["chapter_number"]),
        )
        ref = _chapter_ref(row)
        for queue_item in queue:
            if int(queue_item["chapter_id"]) == ref["id"]:
                queue_item["status"] = "current"
            elif queue_item["status"] == "pending":
                queue_item["status"] = "blocked"
        return finish(_base_projection(
            readiness=readiness,
            task_scope="chapter",
            task_type=task["task_type"],
            task_key=(
                f"chapter:{ref['id']}:{task['task_type']}:"
                f"artifact:{int(row.get('active_artifact_id') or 0)}"
                if task["task_type"] == "HUMAN_QA"
                else f"chapter:{ref['id']}:{task['task_type']}"
            ),
            user_stage=task["user_stage"],
            title=task["title"],
            summary=task["summary"],
            affected=ref,
            action=task["action"],
            blocker=task["blocker"],
            next_hint=task["next"],
            queue=queue,
            technical=[
                f"range:{scope.get('from_chapter')}-{scope.get('to_chapter')}",
                f"chapter_state:{row.get('state')}",
            ],
            range_task=False,
            task_payload=row,
        ))

    return finish(_base_projection(
        readiness=readiness,
        task_scope="range",
        task_type="REVIEW_TEXT",
        task_key=f"{scope_key}:BLOCKED",
        user_stage=2,
        title="Ph\u1ea1m vi ch\u01b0a s\u1eb5n s\u00e0ng",
        summary="Ph\u1ea1m vi ch\u01b0a \u0111\u1ea1t \u0111i\u1ec1u ki\u1ec7n canonical.",
        affected=None,
        action=None,
        blocker="Ph\u1ea1m vi c\u00f3 ch\u01b0\u01a1ng ch\u01b0a \u0111\u1ee7 \u0111i\u1ec1u ki\u1ec7n.",
        next_hint="X\u1eed l\u00fd ch\u01b0\u01a1ng \u0111ang b\u1ecb ch\u1eb7n trong h\u00e0ng ch\u1edd.",
        queue=queue,
        technical=["range_gate:not_eligible"],
        range_task=True,
    ))


def _exact_range_jobs(
    db: Database,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    chapter_ids: list[int],
) -> list[dict[str, Any]]:
    rows = db.fetch_all(
        """
        SELECT id,status,book_id,from_chapter,to_chapter
        FROM jobs
        WHERE book_id=? AND from_chapter=? AND to_chapter=?
        ORDER BY id DESC
        """,
        (book_id, from_chapter, to_chapter),
    )
    result = []
    for row in rows:
        job_id = int(row["id"])
        assigned = db.fetch_all(
            "SELECT chapter_id FROM job_chapters WHERE job_id=? ORDER BY sequence,id",
            (job_id,),
        )
        assigned_ids = [int(item["chapter_id"]) for item in assigned]
        if assigned_ids != chapter_ids:
            continue
        item = dict(row)
        item["chapter_count"] = len(assigned_ids)
        item["all_chapters_match"] = assigned_ids == chapter_ids
        result.append(item)
    return result


def get_production_task_projection(
    db: Database,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    inspected_chapter_id: int | None = None,
    voice_catalog: EffectiveVoiceCatalog | None = None,
    store: ContentStore | None = None,
    config: Settings | None = None,
    custom_voice_context: CustomVoiceContext | None = None,
) -> dict[str, Any]:
    """Build the projection from canonical read-only application state."""

    readiness = get_range_readiness(
        db,
        book_id=book_id,
        from_chapter=from_chapter,
        to_chapter=to_chapter,
        voice_catalog=voice_catalog,
        store=store,
    )
    chapter_ids = [int(item["chapter_id"]) for item in readiness["chapters"]]
    for item in readiness["chapters"]:
        draft_id = item.get("latest_speaker_draft_id")
        if draft_id:
            draft = db.fetch_one(
                "SELECT target_count,invalid_count,status,text_revision_id FROM speaker_assignment_drafts WHERE id=?",
                (int(draft_id),),
            )
            if draft:
                reviewed = db.fetch_one(
                    "SELECT COUNT(*) AS count FROM speaker_assignment_reviews WHERE draft_id=?",
                    (int(draft_id),),
                )
                item["speaker_review"] = {
                    "target_count": int(draft["target_count"] or 0),
                    "invalid_count": int(draft["invalid_count"] or 0),
                    "remaining_unreviewed_count": max(
                        0,
                        int(draft["target_count"] or 0)
                        - int(reviewed["count"] or 0),
                    ),
                    "stale": int(draft["text_revision_id"] or 0)
                    != int(item.get("active_text_revision_id") or 0),
                }
        artifact_id = item.get("active_artifact_id")
        if artifact_id:
            artifact = db.fetch_one(
                "SELECT duration_ms,size_bytes,created_at FROM artifacts WHERE id=?",
                (int(artifact_id),),
            )
            if artifact:
                item["artifact_duration_ms"] = artifact["duration_ms"]
                item["artifact_size_bytes"] = artifact["size_bytes"]
                item["artifact_created_at"] = artifact["created_at"]
        if item.get("human_qa_status") == "needs_fixes":
            approval = resolve_authoritative_human_approval(
                db,
                int(item["chapter_id"]),
                active_artifact_id=int(artifact_id or 0),
            )
            if approval and int(approval.get("artifact_id") or 0) == int(artifact_id or 0):
                item["human_qa_note"] = str(approval.get("notes") or "")
                item["human_qa_recorded_at"] = approval.get("recorded_at")
            if store is not None:
                current_summary = _safe_effective_voice_summary(
                    db,
                    store,
                    item.get("latest_casting_plan_id"),
                    voice_catalog,
                )
                rejected_summary = _safe_effective_voice_summary(
                    db,
                    store,
                    item.get("active_output_casting_plan_id"),
                    voice_catalog,
                )
                item["effective_voice_map"] = [
                    {
                        key: value
                        for key, value in row.items()
                        if key != "speaker_key"
                    }
                    for row in current_summary
                ]
                item["voice_map_diff"] = _voice_map_diff(
                    rejected_summary,
                    current_summary,
                )
    range_jobs = _exact_range_jobs(
        db,
        book_id=book_id,
        from_chapter=from_chapter,
        to_chapter=to_chapter,
        chapter_ids=chapter_ids,
    )
    range_inputs = None
    if voice_catalog is not None and store is not None and config is not None:
        range_inputs = get_range_input_snapshot(
            db,
            store,
            config,
            book_id=book_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
            voice_catalog=voice_catalog,
            custom_voice_context=custom_voice_context,
            skip_completed=True,
        )
    projection = project_production_task(
        {
            "readiness": readiness,
            "range_jobs": range_jobs,
            "range_inputs": range_inputs,
            "inspected_chapter_id": inspected_chapter_id,
        }
    )
    projection["inspected_chapter_id"] = inspected_chapter_id
    return projection
