"""Read-only operator projection for a selected production range."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from .batch_plan import build_batch_plan
from .casting import get_plan
from .config import Settings
from .db import Database
from .production_task_projection import get_production_task_projection
from .range_readiness import get_range_readiness
from .storage import ContentStore
from .voice_eligibility import EffectiveVoiceCatalog
from .voice_ref import CustomVoiceContext


PREFLIGHT_SCHEMA = "story-audio-production-preflight/v1"
_LOCKED_INPUT_STATES = {
    "COMPLETE",
    "PREPARED",
    "RENDERING_OR_PAUSED",
    "RENDERED_NOT_QA",
    "REPAIR_REQUIRED",
}
_LIFECYCLE_ACTIONS = {
    "START_RENDER_RANGE": (
        "START_RENDER_RANGE",
        "B\u1eaft \u0111\u1ea7u render ph\u1ea1m vi",
        "render",
    ),
    "MONITOR_RENDER": (
        "MONITOR_RENDER",
        "Theo d\u00f5i render",
        "render",
    ),
    "RECOVER_RENDER": (
        "RECOVER_RENDER",
        "X\u1eed l\u00fd render",
        "render",
    ),
    "HUMAN_QA": (
        "HUMAN_QA",
        "Nghe v\u00e0 duy\u1ec7t audio",
        "qa",
    ),
    "REPAIR_REQUIRED": (
        "CHOOSE_REPAIR_PATH",
        "Chọn cách sửa audio",
        "qa",
    ),
    "COMPLETE": (
        "COMPLETE",
        "Ph\u1ea1m vi \u0111\u00e3 ho\u00e0n t\u1ea5t",
        "audio",
    ),
}


def _action(key: str, label: str, target: str) -> dict[str, str]:
    return {"key": key, "label": label, "target": target}


def decide_preflight_next_action(state: Mapping[str, Any]) -> dict[str, str]:
    """Choose one action while preserving Task Projection lifecycle authority."""

    task_type = str(state.get("task_type") or "")
    lifecycle = _LIFECYCLE_ACTIONS.get(task_type)
    if lifecycle:
        return _action(*lifecycle)
    if not state.get("data_ready"):
        blocker = state.get("first_blocker")
        if isinstance(blocker, Mapping):
            return _action(
                str(blocker.get("next_task") or "RESOLVE_PRODUCTION_BLOCKER"),
                str(blocker.get("action_label") or "X\u1eed l\u00fd ch\u01b0\u01a1ng c\u00f2n l\u1ed7i"),
                str(blocker.get("target") or "production"),
            )
        return _action(
            "RESOLVE_PRODUCTION_BLOCKER",
            "X\u1eed l\u00fd ch\u01b0\u01a1ng c\u00f2n l\u1ed7i",
            "production",
        )
    if not state.get("authorization_ready"):
        return _action(
            "AUTHENTICATE_EXECUTION",
            "X\u00e1c th\u1ef1c \u0111\u1ec3 chu\u1ea9n b\u1ecb",
            "authentication",
        )
    return _action("PREPARE_RANGE", "Chu\u1ea9n b\u1ecb ph\u1ea1m vi", "prepare")


def _checklist(rows: list[dict[str, Any]], task_type: str) -> dict[str, Any]:
    checks = {
        "text": {"label": "V\u0103n b\u1ea3n", "passed": 0, "total": len(rows), "failed_chapters": []},
        "speaker": {"label": "Ng\u01b0\u1eddi n\u00f3i", "passed": 0, "total": len(rows), "failed_chapters": []},
        "casting": {"label": "B\u1ea3n \u0111\u1ed3 gi\u1ecdng", "passed": 0, "total": len(rows), "failed_chapters": []},
        "voice": {"label": "Gi\u1ecdng kh\u1ea3 d\u1ee5ng", "passed": 0, "total": len(rows), "failed_chapters": []},
        "conflict": {"label": "Job xung \u0111\u1ed9t", "passed": 0, "total": len(rows), "failed_chapters": []},
    }
    for row in rows:
        number = int(row["chapter_number"])
        state = str(row.get("state") or "STATE_UNRESOLVED")
        locked = state in _LOCKED_INPUT_STATES
        outcomes = {
            "text": locked or state not in {"TEXT_BLOCKED", "STATE_UNRESOLVED"},
            "speaker": locked or state not in {
                "TEXT_BLOCKED", "SPEAKER_EXCEPTIONS", "STATE_UNRESOLVED",
            },
            "casting": locked or state not in {
                "TEXT_BLOCKED", "SPEAKER_EXCEPTIONS", "CASTING_REVIEW", "STATE_UNRESOLVED",
            },
            "voice": locked or (
                state not in {
                    "TEXT_BLOCKED", "SPEAKER_EXCEPTIONS", "CASTING_REVIEW",
                    "VOICE_BLOCKED", "STATE_UNRESOLVED",
                }
                and not row.get("voice_issues")
            ),
            "conflict": not any(
                "multiple live jobs" in str(message).lower()
                for message in row.get("blockers") or []
            ),
        }
        if task_type == "RECOVER_RENDER" and not row.get("live_job_id"):
            outcomes["conflict"] = False
        for key, passed in outcomes.items():
            if passed:
                checks[key]["passed"] += 1
            else:
                checks[key]["failed_chapters"].append(number)
    return checks


def _blockers(
    rows: list[dict[str, Any]],
    task_projection: Mapping[str, Any],
) -> list[dict[str, Any]]:
    queue_by_chapter = {
        int(item["chapter_id"]): item
        for item in task_projection.get("chapter_queue") or []
        if item.get("chapter_id") is not None
    }
    canonical = dict(task_projection.get("canonical_task") or {})
    result: list[dict[str, Any]] = []
    for row in rows:
        state = str(row.get("state") or "")
        if state in {
            "READY_TO_PREPARE",
            "COMPLETE",
            "PREPARED",
            "RENDERING_OR_PAUSED",
            "RENDERED_NOT_QA",
            "REPAIR_REQUIRED",
        }:
            continue
        queue = queue_by_chapter.get(int(row["chapter_id"]), {})
        is_canonical = bool(queue.get("canonical_task"))
        next_task = (
            canonical.get("task_type")
            if is_canonical
            else queue.get("task_type") or row.get("next_action") or "RESOLVE_PRODUCTION_BLOCKER"
        )
        action = canonical.get("primary_action") if is_canonical else None
        result.append(
            {
                "chapter_id": int(row["chapter_id"]),
                "chapter_number": int(row["chapter_number"]),
                "chapter_title": row.get("chapter_title") or "",
                "state": state,
                "reason": str((row.get("blockers") or [row.get("next_action")])[0]),
                "next_task": str(next_task),
                "action_label": str(
                    (action or {}).get("label")
                    or "X\u1eed l\u00fd ch\u01b0\u01a1ng c\u00f2n l\u1ed7i"
                ),
                "target": str((action or {}).get("target") or "production"),
            }
        )
    result.sort(key=lambda item: (item["chapter_number"], item["chapter_id"]))
    return result


def _assignment_source(raw: Any, role: str) -> str:
    source = str(raw or "").lower()
    if "override" in source:
        return "override"
    if role == "narrator":
        return "book_default"
    return "inherited"


def aggregate_effective_voice_map(
    plan_payloads: list[dict[str, Any]],
    *,
    character_names: Mapping[int, str],
    voice_catalog: EffectiveVoiceCatalog,
) -> tuple[list[dict[str, Any]], list[str], int]:
    catalog = {
        str(item["assignment_key"]): dict(item)
        for item in voice_catalog.items
    }
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    warnings: list[str] = []
    segment_count = 0
    for item in plan_payloads:
        chapter_number = int(item["chapter_number"])
        utterances = item.get("utterances")
        if not isinstance(utterances, list):
            warnings.append(
                f"Chapter {chapter_number} has no readable Casting Plan utterances."
            )
            continue
        segment_count += len(utterances)
        for utterance in utterances:
            if not isinstance(utterance, Mapping):
                warnings.append(
                    f"Chapter {chapter_number} has a malformed Casting Plan utterance."
                )
                continue
            role = str(utterance.get("role") or "unknown")
            character_id = (
                int(utterance["character_id"])
                if utterance.get("character_id") not in (None, "")
                else None
            )
            voice_id = str(utterance.get("resolved_voice_id") or "")
            source = _assignment_source(utterance.get("resolution_source"), role)
            if role == "narrator":
                speaker_name = "Ng\u01b0\u1eddi k\u1ec3 chuy\u1ec7n"
            elif role == "character":
                speaker_name = character_names.get(
                    int(character_id or 0),
                    "Nh\u00e2n v\u1eadt kh\u00f4ng c\u00f3 t\u00ean",
                )
            else:
                speaker_name = "Ng\u01b0\u1eddi n\u00f3i ch\u01b0a x\u00e1c \u0111\u1ecbnh"
            voice = catalog.get(voice_id)
            available = bool(voice and voice_id in voice_catalog.selectable_ids)
            voice_name = (
                str(voice.get("display_name") or voice_id)
                if voice
                else "Gi\u1ecdng kh\u00f4ng kh\u1ea3 d\u1ee5ng"
            )
            warning = None
            if not available:
                warning = (
                    f"{speaker_name} in Chapter {chapter_number} uses an unavailable voice."
                )
                warnings.append(warning)
            key = (role, character_id, voice_id, source)
            row = grouped.setdefault(
                key,
                {
                    "speaker_name": speaker_name,
                    "role": role,
                    "effective_voice_name": voice_name,
                    "assignment_source": source,
                    "affected_chapters": set(),
                    "line_count": 0,
                    "available": available,
                    "warning": warning,
                },
            )
            row["affected_chapters"].add(chapter_number)
            row["line_count"] += 1
            row["available"] = bool(row["available"] and available)
            if warning:
                row["warning"] = warning
    role_order = {"narrator": 0, "character": 1, "unknown": 2}
    result = []
    for row in grouped.values():
        row["affected_chapters"] = sorted(row["affected_chapters"])
        result.append(row)
    result.sort(
        key=lambda row: (
            role_order.get(str(row["role"]), 9),
            str(row["speaker_name"]).casefold(),
            str(row["effective_voice_name"]).casefold(),
        )
    )
    return result, list(dict.fromkeys(warnings)), segment_count


def project_production_preflight(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Build the stable public projection from an already-read snapshot."""

    readiness = dict(snapshot.get("readiness") or {})
    task_projection = dict(snapshot.get("task_projection") or {})
    task = dict(task_projection.get("canonical_task") or {})
    batch_plan = dict(snapshot.get("batch_plan") or {})
    runtime = dict(snapshot.get("runtime_readiness") or {})
    skip_completed = bool(snapshot.get("skip_completed", True))
    selected_rows = [dict(item) for item in readiness.get("chapters") or []]
    target_rows = [
        row for row in selected_rows
        if not (skip_completed and str(row.get("state")) == "COMPLETE")
    ]
    checks = _checklist(target_rows, str(task.get("task_type") or ""))
    blockers = _blockers(target_rows, task_projection)
    voice_map = [dict(item) for item in snapshot.get("effective_voice_map") or []]
    voice_warnings = list(snapshot.get("voice_warnings") or [])
    warning_chapters = {
        int(chapter_number)
        for item in voice_map
        if not item.get("available")
        for chapter_number in item.get("affected_chapters") or []
    }
    warning_chapters.update(
        int(chapter_number)
        for chapter_number in snapshot.get("voice_warning_chapters") or []
    )
    rows_by_number = {
        int(row["chapter_number"]): row
        for row in target_rows
    }
    voice_failed = set(checks["voice"]["failed_chapters"])
    voice_failed.update(warning_chapters)
    checks["voice"]["failed_chapters"] = sorted(voice_failed)
    checks["voice"]["passed"] = max(0, int(checks["voice"]["total"]) - len(voice_failed))
    for chapter_number in sorted(warning_chapters):
        if not any(item.get("chapter_number") == chapter_number for item in blockers):
            row = rows_by_number.get(chapter_number, {})
            blockers.append(
                {
                    "chapter_id": row.get("chapter_id"),
                    "chapter_number": chapter_number,
                    "chapter_title": row.get("chapter_title") or "",
                    "state": "VOICE_BLOCKED",
                    "reason": "Giọng hiệu lực không còn khả dụng.",
                    "next_task": "ASSIGN_VOICE",
                    "action_label": "Ki\u1ec3m tra gi\u1ecdng kh\u00f4ng kh\u1ea3 d\u1ee5ng",
                    "target": "voices",
                }
            )
    if voice_warnings and not warning_chapters and not blockers:
        blockers.append(
            {
                "chapter_id": None,
                "chapter_number": None,
                "chapter_title": "",
                "state": "VOICE_BLOCKED",
                "reason": voice_warnings[0],
                "next_task": "ASSIGN_VOICE",
                "action_label": "Ki\u1ec3m tra gi\u1ecdng kh\u00f4ng kh\u1ea3 d\u1ee5ng",
                "target": "voices",
            }
        )
    blockers.sort(
        key=lambda item: (
            item.get("chapter_number") is None,
            int(item.get("chapter_number") or 0),
            int(item.get("chapter_id") or 0),
        )
    )
    data_ready = all(
        int(check["passed"]) == int(check["total"])
        for check in checks.values()
    ) and not blockers and not voice_warnings
    schema_ready = (
        int(runtime.get("schema_version") or 0)
        == int(runtime.get("required_schema_version") or 15)
        == 15
    )
    authorization_ready = bool(
        runtime.get("mutation_authorized")
        and runtime.get("authentication_state") == "AUTH_CONFIGURED"
    )
    kill_switch_clear = not bool(runtime.get("kill_switch_active"))
    conflict_free = int(checks["conflict"]["passed"]) == int(checks["conflict"]["total"])
    task_type = str(task.get("task_type") or "")
    next_action = decide_preflight_next_action(
        {
            "task_type": task_type,
            "data_ready": data_ready,
            "authorization_ready": (
                authorization_ready and schema_ready and kill_switch_clear
            ),
            "first_blocker": blockers[0] if blockers else None,
        }
    )
    scope = dict(readiness.get("scope") or {})
    included = [dict(item) for item in batch_plan.get("included") or []]
    excluded = [dict(item) for item in batch_plan.get("excluded") or []]
    prepared_job = None
    render = task.get("render")
    if isinstance(render, Mapping) and str(render.get("job_status") or "").lower() == "prepared":
        prepared_job = {
            "job_id": render.get("job_id"),
            "status": "prepared",
            "chapter_count": len(target_rows),
        }
    prepare_allowed = bool(
        task_type == "PREPARE_RANGE"
        and data_ready
        and authorization_ready
        and schema_ready
        and kill_switch_clear
        and conflict_free
    )
    render_allowed = bool(
        task_type == "START_RENDER_RANGE"
        and authorization_ready
        and schema_ready
        and kill_switch_clear
        and conflict_free
        and runtime.get("start_render_available")
    )
    effective_voice_ids = {
        str(item.get("technical_voice_id"))
        for item in snapshot.get("voice_technical") or []
        if item.get("technical_voice_id")
    }
    lifecycle_review = task_type in {
        "START_RENDER_RANGE",
        "MONITOR_RENDER",
        "RECOVER_RENDER",
        "HUMAN_QA",
        "REPAIR_REQUIRED",
    }
    preview_chapter_count = len(target_rows) if lifecycle_review else len(included)
    prepare_effect = (
        "PREPARE pins the approved text and effective voice map for the included chapters."
        if task_type == "PREPARE_RANGE"
        else "The prepared inputs remain pinned; this read-only review does not start or repeat render."
        if task_type == "START_RENDER_RANGE"
        else "Monitoring does not create another Job or issue a duplicate render start."
        if task_type in {"MONITOR_RENDER", "RECOVER_RENDER"}
        else "This read-only review does not change the active output or Human QA state."
    )
    return {
        "schema": PREFLIGHT_SCHEMA,
        "range": {
            "book": {
                "id": scope.get("book_id"),
                "title": scope.get("book_title") or "",
            },
            "from_chapter": scope.get("from_chapter"),
            "to_chapter": scope.get("to_chapter"),
            "selected_chapter_count": len(selected_rows),
            "included_chapters": [
                {
                    "chapter_number": item.get("chapter_number"),
                    "chapter_title": item.get("chapter_title") or "",
                }
                for item in included
            ],
            "excluded_chapters": [
                {
                    "chapter_number": item.get("chapter_number"),
                    "chapter_title": item.get("chapter_title") or "",
                    "reason": item.get("operator_message") or "",
                    "reason_codes": list(item.get("reason_codes") or []),
                }
                for item in excluded
            ],
            "skip_completed": skip_completed,
        },
        "data_readiness": {
            "ready": data_ready,
            **checks,
            "ordered_blockers": blockers,
        },
        "effective_voice_map": voice_map,
        "execution_readiness": {
            "prepare_allowed": prepare_allowed,
            "render_allowed": render_allowed,
            "authorization_ready": authorization_ready,
            "schema_ready": schema_ready,
            "kill_switch_clear": kill_switch_clear,
            "conflict_free": conflict_free,
            "prepared_job": prepared_job,
        },
        "execution_preview": {
            "chapter_count": preview_chapter_count,
            "estimated_segment_count": int(snapshot.get("estimated_segment_count") or 0),
            "voice_count": len(effective_voice_ids),
            "prepare_effect": prepare_effect,
            "tts_called": False,
            "next_action": next_action,
        },
        "technical_details": {
            "range_identity": task_projection.get("range_identity"),
            "task_key": task.get("task_key"),
            "task_type": task_type,
            "plan_fingerprint": batch_plan.get("plan_fingerprint"),
            "included_chapter_ids": [
                item.get("chapter_id") for item in included
            ],
            "casting_plan_ids": sorted(
                {
                    int(item["latest_casting_plan_id"])
                    for item in included
                    if item.get("latest_casting_plan_id") is not None
                }
            ),
            "voice_ids": sorted(effective_voice_ids),
            "authentication_state": runtime.get("authentication_state"),
            "runtime_status": runtime.get("status"),
            "runtime_reasons": list(runtime.get("reasons") or []),
            "voice_warnings": voice_warnings,
        },
    }


def get_production_preflight(
    db: Database,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    skip_completed: bool,
    voice_catalog: EffectiveVoiceCatalog,
    store: ContentStore,
    config: Settings,
    runtime_readiness: Mapping[str, Any],
    custom_voice_context: CustomVoiceContext | None = None,
) -> dict[str, Any]:
    """Read canonical inputs and produce a side-effect-free operator projection."""

    readiness = get_range_readiness(
        db,
        book_id=book_id,
        from_chapter=from_chapter,
        to_chapter=to_chapter,
        voice_catalog=voice_catalog,
        store=store,
    )
    task_projection = get_production_task_projection(
        db,
        book_id=book_id,
        from_chapter=from_chapter,
        to_chapter=to_chapter,
        voice_catalog=voice_catalog,
        store=store,
        config=config,
        custom_voice_context=custom_voice_context,
    )
    batch_plan = build_batch_plan(readiness, target_phase="PREPARE")
    plan_payloads: list[dict[str, Any]] = []
    voice_technical: list[dict[str, str]] = []
    character_ids: set[int] = set()
    diagnostics: list[str] = []
    diagnostic_chapters: set[int] = set()
    for row in readiness.get("chapters") or []:
        if skip_completed and str(row.get("state") or "") == "COMPLETE":
            continue
        plan_id = row.get("latest_casting_plan_id")
        if plan_id is None or str(row.get("latest_casting_plan_status") or "").lower() != "approved":
            continue
        try:
            plan = get_plan(db, store, int(plan_id))
        except Exception as exc:
            diagnostic_chapters.add(int(row["chapter_number"]))
            diagnostics.append(
                f"Chapter {int(row['chapter_number'])} Casting Plan could not be read: {exc}"
            )
            continue
        utterances = plan.get("plan", {}).get("utterances")
        plan_payloads.append(
            {
                "chapter_number": int(row["chapter_number"]),
                "utterances": utterances,
            }
        )
        for utterance in utterances or []:
            if not isinstance(utterance, Mapping):
                continue
            if utterance.get("character_id") not in (None, ""):
                character_ids.add(int(utterance["character_id"]))
            voice_id = str(utterance.get("resolved_voice_id") or "")
            if voice_id:
                voice_technical.append({"technical_voice_id": voice_id})
    character_names: dict[int, str] = {}
    if character_ids:
        placeholders = ",".join("?" for _ in character_ids)
        rows = db.fetch_all(
            f"SELECT id,display_name FROM characters WHERE id IN ({placeholders})",
            tuple(sorted(character_ids)),
        )
        character_names = {
            int(row["id"]): str(row["display_name"])
            for row in rows
        }
    voice_map, voice_warnings, segment_count = aggregate_effective_voice_map(
        plan_payloads,
        character_names=character_names,
        voice_catalog=voice_catalog,
    )
    voice_warnings.extend(diagnostics)
    return project_production_preflight(
        {
            "readiness": readiness,
            "task_projection": task_projection,
            "batch_plan": batch_plan,
            "runtime_readiness": dict(runtime_readiness),
            "skip_completed": skip_completed,
            "effective_voice_map": voice_map,
            "voice_warnings": voice_warnings,
            "voice_warning_chapters": sorted(diagnostic_chapters),
            "voice_technical": voice_technical,
            "estimated_segment_count": segment_count,
        }
    )


__all__ = [
    "PREFLIGHT_SCHEMA",
    "aggregate_effective_voice_map",
    "decide_preflight_next_action",
    "get_production_preflight",
    "project_production_preflight",
]
