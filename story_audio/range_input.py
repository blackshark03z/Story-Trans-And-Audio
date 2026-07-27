"""Range-oriented input preparation over immutable per-chapter workflows."""

from __future__ import annotations

from typing import Any, Callable

from .casting import (
    CastingError,
    approve_plan,
    create_casting_draft,
    get_plan,
    validate_approved_plan,
)
from .config import Settings
from .db import Database
from .range_readiness import get_range_readiness
from .speaker_assignment import (
    SpeakerAssignmentError,
    generate_speaker_assignment_draft,
)
from .speaker_review import (
    SpeakerReviewConflict,
    SpeakerReviewError,
    SpeakerReviewNotFound,
    approve_speaker_assignment_draft_only,
    create_casting_plan_draft_from_speaker_review,
    get_speaker_review_draft,
    review_speaker_assignment_row,
)
from .storage import ContentStore
from .voice_eligibility import (
    EffectiveVoiceCatalog,
    VoiceEligibilityBlocked,
    require_casting_plan_eligible,
)
from .voice_profile import (
    VoiceProfileError,
    get_book_voice_profile,
    resolve_voice,
)
from .voice_ref import CustomVoiceContext


MAX_RANGE_INPUT_CHAPTERS = 50
SKIPPED_INPUT_STATES = {
    "COMPLETE",
    "PREPARED",
    "RENDERING_OR_PAUSED",
    "RENDERED_NOT_QA",
}


class RangeInputError(ValueError):
    pass


def _chapter_ref(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "chapter_id": int(item["chapter_id"]),
        "chapter_number": int(item["chapter_number"]),
        "chapter_title": item.get("chapter_title") or "",
    }


def _validate_scope(readiness: dict[str, Any]) -> None:
    count = int((readiness.get("scope") or {}).get("chapter_count") or 0)
    if count < 1:
        raise RangeInputError("The selected range is empty.")
    if count > MAX_RANGE_INPUT_CHAPTERS:
        raise RangeInputError(
            f"Range input preparation is limited to {MAX_RANGE_INPUT_CHAPTERS} chapters."
        )


def _is_speaker_exception(row: dict[str, Any]) -> bool:
    suggestion = row.get("suggestion")
    if row.get("invalid_item") or not isinstance(suggestion, dict):
        return True
    if suggestion.get("speaker_type") == "unknown":
        return True
    return str(suggestion.get("confidence_level") or "").lower() != "high"


def _speaker_exception(
    chapter: dict[str, Any],
    draft: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    suggestion = row.get("suggestion") or {}
    return {
        **_chapter_ref(chapter),
        "draft_id": int(draft["id"]),
        "draft_status": draft.get("status"),
        "draft_fingerprint": draft.get("input_fingerprint"),
        "text_revision_id": int(draft["text_revision_id"]),
        "utterance_id": str(row["utterance_id"]),
        "sequence": int(row["sequence"]),
        "source_text": row.get("text") or "",
        "context": list(row.get("context") or []),
        "detected_speaker": {
            "speaker_type": suggestion.get("speaker_type"),
            "character_id": suggestion.get("character_id"),
        },
        "suggested_character_id": suggestion.get("character_id"),
        "confidence": suggestion.get("confidence"),
        "confidence_level": suggestion.get("confidence_level"),
        "reason": suggestion.get("reason")
        or (row.get("invalid_item") or {}).get("error_code")
        or "No trustworthy speaker proposal is available.",
        "alternatives": list(suggestion.get("alternatives") or []),
        "current_decision": row.get("human_review"),
        "characters": list(draft.get("characters") or []),
    }


def _latest_plan_row(db: Database, chapter_id: int) -> dict[str, Any] | None:
    row = db.fetch_one(
        """SELECT id,chapter_id,text_revision_id,plan_revision,status,approved_at
           FROM casting_plans
           WHERE chapter_id=?
           ORDER BY plan_revision DESC,id DESC
           LIMIT 1""",
        (chapter_id,),
    )
    return dict(row) if row else None


def _chapter_in_snapshot_scope(
    db: Database,
    snapshot: dict[str, Any],
    chapter_id: int,
) -> dict[str, Any] | None:
    scope = snapshot.get("scope") or {}
    row = db.fetch_one(
        """SELECT id AS chapter_id,book_id,chapter_number,title AS chapter_title
           FROM chapters
           WHERE id=?""",
        (chapter_id,),
    )
    if not row:
        return None
    chapter = dict(row)
    if int(chapter["book_id"]) != int(scope.get("book_id") or 0):
        return None
    number = int(chapter["chapter_number"])
    if not (
        int(scope.get("from_chapter") or -1)
        <= number
        <= int(scope.get("to_chapter") or -1)
    ):
        return None
    return chapter


def _speaker_roles(detail: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "utterance_id": str(item["utterance_id"]),
            "speaker_type": str(item["speaker_type"]),
            "character_id": item.get("character_id"),
            "decision_source": str(item["decision_source"]),
        }
        for item in detail.get("row_reviews") or []
    ]


def _voice_exceptions(
    db: Database,
    *,
    book_id: int,
    draft: dict[str, Any],
    chapter: dict[str, Any],
    catalog: EffectiveVoiceCatalog,
    custom_voice_context: CustomVoiceContext | None,
) -> tuple[list[dict[str, Any]], set[str]]:
    inherited: set[str] = set()
    profile = get_book_voice_profile(db, book_id)
    if not profile:
        return ([{
            **_chapter_ref(chapter),
            "kind": "book_profile_missing",
            "speaker_key": "book_profile",
            "speaker_name": "Cấu hình giọng của sách",
            "character_id": None,
            "current_voice_id": None,
            "reason": "Sách chưa có cấu hình giọng mặc định.",
            "draft_id": int(draft["id"]),
        }], inherited)

    result: list[dict[str, Any]] = []
    profile_voice_ids = {
        str(profile.get("narrator_voice_id") or ""),
        str(profile.get("male_dialogue_voice_id") or ""),
        str(profile.get("female_dialogue_voice_id") or ""),
    }
    if profile.get("unknown_fallback") == "explicit_voice":
        profile_voice_ids.add(str(profile.get("unknown_voice_id") or ""))
    unavailable = sorted(
        voice_id
        for voice_id in profile_voice_ids
        if not voice_id or voice_id not in catalog.selectable_ids
    )
    for voice_id in unavailable:
        result.append({
            **_chapter_ref(chapter),
            "kind": "unavailable_profile_voice",
            "speaker_key": "book_profile",
            "speaker_name": "Cấu hình giọng của sách",
            "character_id": None,
            "current_voice_id": voice_id or None,
            "reason": "Giọng mặc định không còn khả dụng trong catalog hiện tại.",
            "draft_id": int(draft["id"]),
        })
    if str(profile.get("narrator_voice_id") or "") in catalog.selectable_ids:
        inherited.add(f"narrator:{profile['narrator_voice_id']}")

    roles = _speaker_roles(draft)
    if any(item["speaker_type"] == "unknown" for item in roles):
        resolution = resolve_voice(
            speaker_type="dialogue",
            book_voice_profile=profile,
            custom_voice_context=custom_voice_context,
        )
        voice_id = str(resolution.get("resolved_voice_id") or "")
        if voice_id in catalog.selectable_ids:
            inherited.add(f"unknown:{voice_id}")

    character_ids = sorted({
        int(item["character_id"])
        for item in roles
        if item["speaker_type"] == "character" and item.get("character_id") is not None
    })
    for character_id in character_ids:
        character_row = db.fetch_one(
            "SELECT * FROM characters WHERE id=? AND book_id=? AND active=1",
            (character_id, book_id),
        )
        if not character_row:
            result.append({
                **_chapter_ref(chapter),
                "kind": "missing_character",
                "speaker_key": f"character:{character_id}",
                "speaker_name": f"Nhân vật #{character_id}",
                "character_id": character_id,
                "current_voice_id": None,
                "reason": "Nhân vật không còn khả dụng trong sách.",
                "draft_id": int(draft["id"]),
            })
            continue
        character = dict(character_row)
        try:
            resolution = resolve_voice(
                speaker_type="character",
                book_voice_profile=profile,
                character=character,
                custom_voice_context=custom_voice_context,
            )
        except VoiceProfileError as exc:
            result.append({
                **_chapter_ref(chapter),
                "kind": "voice_resolution_error",
                "speaker_key": f"character:{character_id}",
                "speaker_name": character["display_name"],
                "character_id": character_id,
                "current_voice_id": character.get("voice_override_id"),
                "reason": str(exc),
                "draft_id": int(draft["id"]),
            })
            continue
        voice_id = str(resolution.get("resolved_voice_id") or "")
        if voice_id not in catalog.selectable_ids:
            kind = "unavailable_character_voice"
            reason = "Giọng kế thừa hoặc override không còn khả dụng."
        elif resolution.get("needs_review") and not character.get("voice_override_id"):
            kind = "new_character_without_voice"
            reason = "Nhân vật mới đang dùng fallback và cần chọn giọng rõ ràng."
        else:
            inherited.add(f"character:{character_id}:{voice_id}")
            continue
        result.append({
            **_chapter_ref(chapter),
            "kind": kind,
            "speaker_key": f"character:{character_id}",
            "speaker_name": character["display_name"],
            "character_id": character_id,
            "current_voice_id": voice_id or None,
            "resolution_source": resolution.get("resolution_source"),
            "reason": reason,
            "draft_id": int(draft["id"]),
        })
    return result, inherited


def get_range_input_snapshot(
    db: Database,
    store: ContentStore,
    config: Settings,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    voice_catalog: EffectiveVoiceCatalog,
    custom_voice_context: CustomVoiceContext | None = None,
    skip_completed: bool = True,
) -> dict[str, Any]:
    readiness = get_range_readiness(
        db,
        book_id=book_id,
        from_chapter=from_chapter,
        to_chapter=to_chapter,
        voice_catalog=voice_catalog,
        store=store,
    )
    _validate_scope(readiness)

    proposals: list[dict[str, Any]] = []
    speaker_exceptions: list[dict[str, Any]] = []
    ready_speaker_drafts: list[dict[str, Any]] = []
    voice_exceptions: list[dict[str, Any]] = []
    casting_generation_ready: list[dict[str, Any]] = []
    casting_approvals: list[dict[str, Any]] = []
    inherited_voice_keys: set[str] = set()
    blocked: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for chapter in readiness["chapters"]:
        ref = _chapter_ref(chapter)
        state = str(chapter.get("state") or "")
        if state in SKIPPED_INPUT_STATES and skip_completed:
            skipped.append({**ref, "state": state})
            continue
        if state == "TEXT_BLOCKED":
            blocked.append({
                **ref,
                "kind": "text",
                "reason": (chapter.get("blockers") or ["Văn bản chưa sẵn sàng."])[0],
            })
            continue

        draft_id = chapter.get("latest_speaker_draft_id")
        if not draft_id:
            proposals.append({**ref, "reason": "missing", "draft_id": None})
            continue
        try:
            detail = get_speaker_review_draft(
                db,
                store,
                config,
                chapter_id=ref["chapter_id"],
                draft_id=int(draft_id),
            )
        except (SpeakerReviewError, SpeakerAssignmentError, OSError) as exc:
            blocked.append({**ref, "kind": "speaker_draft", "reason": str(exc)})
            continue
        if detail["stale"]:
            proposals.append({
                **ref,
                "reason": "stale",
                "draft_id": int(detail["id"]),
                "stale_reasons": list(detail.get("stale_reasons") or []),
            })
            continue

        if str(detail.get("status") or "").lower() != "approved":
            unresolved = [
                row
                for row in detail.get("review_rows") or []
                if not row.get("reviewed")
            ]
            exceptions = [
                _speaker_exception(chapter, detail, row)
                for row in unresolved
                if _is_speaker_exception(row)
            ]
            speaker_exceptions.extend(exceptions)
            if not exceptions:
                ready_speaker_drafts.append({
                    **ref,
                    "draft_id": int(detail["id"]),
                    "draft_status": detail["status"],
                    "text_revision_id": int(detail["text_revision_id"]),
                    "draft_fingerprint": detail["input_fingerprint"],
                    "draft_revision": int(detail["id"]),
                    "unresolved_count": len(unresolved),
                    "proposal_source": "Gemini speaker proposal",
                })
            continue

        replacement_plan_id = None
        plan_row = _latest_plan_row(db, ref["chapter_id"])
        if plan_row and int(plan_row["text_revision_id"]) == int(
            chapter.get("active_text_revision_id") or 0
        ):
            plan = get_plan(db, store, int(plan_row["id"]))
            plan_eligible = True
            try:
                require_casting_plan_eligible(
                    plan["plan"],
                    voice_catalog,
                    chapter_id=ref["chapter_id"],
                )
            except VoiceEligibilityBlocked:
                plan_eligible = False
                replacement_plan_id = int(plan_row["id"])
            if plan_row["status"] == "draft" and plan_eligible:
                casting_approvals.append({
                    **ref,
                    "plan_id": int(plan_row["id"]),
                    "plan_revision": int(plan_row["plan_revision"]),
                    "plan_status": "draft",
                    "narrator_voice_id": plan["plan"].get("narrator_voice_id"),
                    "changed_character_voices": [
                        {
                            "character_id": item.get("character_id"),
                            "voice_id": item.get("resolved_voice_id"),
                        }
                        for item in plan["plan"].get("utterances") or []
                        if item.get("role") == "character"
                    ],
                    "unresolved_count": sum(
                        1
                        for item in plan["plan"].get("utterances") or []
                        if not str(item.get("resolved_voice_id") or "").strip()
                    ),
                })
                continue
            if plan_row["status"] == "approved" and plan_eligible:
                for item in plan["plan"].get("utterances") or []:
                    if item.get("role") == "character":
                        inherited_voice_keys.add(
                            f"character:{item.get('character_id')}:{item.get('resolved_voice_id')}"
                        )
                continue

        chapter_voice_exceptions, chapter_inherited = _voice_exceptions(
            db,
            book_id=book_id,
            draft=detail,
            chapter=chapter,
            catalog=voice_catalog,
            custom_voice_context=custom_voice_context,
        )
        inherited_voice_keys.update(chapter_inherited)
        voice_exceptions.extend(chapter_voice_exceptions)
        if not chapter_voice_exceptions:
            casting_generation_ready.append({
                **ref,
                "draft_id": int(detail["id"]),
                "draft_revision": int(detail["id"]),
                "text_revision_id": int(detail["text_revision_id"]),
                "draft_fingerprint": detail["input_fingerprint"],
                "base_casting_plan_id": detail.get("base_casting_plan_id"),
                "replace_plan_id": replacement_plan_id,
            })

    speaker_exceptions.sort(
        key=lambda item: (
            int(item["chapter_number"]),
            int(item["sequence"]),
            str(item["utterance_id"]),
        )
    )
    voice_by_key: dict[str, dict[str, Any]] = {}
    for item in voice_exceptions:
        key = str(item["speaker_key"])
        existing = voice_by_key.get(key)
        if existing:
            existing["chapter_ids"].append(item["chapter_id"])
            existing["chapter_numbers"].append(item["chapter_number"])
        else:
            voice_by_key[key] = {
                **item,
                "chapter_ids": [item["chapter_id"]],
                "chapter_numbers": [item["chapter_number"]],
            }
    normalized_voice_exceptions = sorted(
        voice_by_key.values(),
        key=lambda item: (
            min(item["chapter_numbers"]),
            str(item["speaker_key"]),
        ),
    )
    awaiting_speaker_chapters = sorted({
        item["chapter_id"] for item in ready_speaker_drafts
    })
    awaiting_casting_chapters = sorted({
        item["chapter_id"] for item in casting_approvals
    })
    summary = {
        "total_chapters": int(readiness["scope"]["chapter_count"]),
        "ready_chapters": int(readiness["summary"]["ready_to_prepare"]),
        "blocked_chapters": len(blocked),
        "proposal_required_chapters": len(proposals),
        "speaker_exception_count": len(speaker_exceptions),
        "voice_exception_count": len(normalized_voice_exceptions),
        "chapters_awaiting_speaker_approval": len(awaiting_speaker_chapters),
        "chapters_awaiting_casting_approval": len(awaiting_casting_chapters),
        "casting_generation_ready_chapters": len(casting_generation_ready),
        "inherited_voice_count": len(inherited_voice_keys),
        "skipped_chapters": len(skipped),
    }
    return {
        "scope": dict(readiness["scope"]),
        "summary": summary,
        "proposal_chapters": proposals,
        "speaker_exception_queue": speaker_exceptions,
        "ready_speaker_drafts": ready_speaker_drafts,
        "voice_exception_queue": normalized_voice_exceptions,
        "casting_generation_ready": casting_generation_ready,
        "casting_approvals": casting_approvals,
        "blocked": blocked,
        "skipped": skipped,
    }


def prepare_range_inputs(
    db: Database,
    store: ContentStore,
    config: Settings,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    voice_catalog: EffectiveVoiceCatalog,
    allowed_voice_ids: set[str],
    custom_voice_context: CustomVoiceContext | None = None,
    skip_completed: bool = True,
    provider: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    before = get_range_input_snapshot(
        db,
        store,
        config,
        book_id=book_id,
        from_chapter=from_chapter,
        to_chapter=to_chapter,
        voice_catalog=voice_catalog,
        custom_voice_context=custom_voice_context,
        skip_completed=skip_completed,
    )
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    proposals = list(before["proposal_chapters"])
    if proposals:
        for item in proposals:
            try:
                kwargs: dict[str, Any] = {}
                if provider is not None:
                    kwargs["provider"] = provider
                created = generate_speaker_assignment_draft(
                    db,
                    store,
                    config,
                    chapter_id=int(item["chapter_id"]),
                    mode="unassigned_only",
                    utterance_ids=None,
                    force_refresh=False,
                    **kwargs,
                )
                results.append({
                    **_chapter_ref(item),
                    "operation": "speaker_proposal",
                    "object_id": int(created["id"]),
                    "reused": bool(created.get("reused")),
                })
            except Exception as exc:
                failures.append({
                    **_chapter_ref(item),
                    "operation": "speaker_proposal",
                    "error": str(exc),
                })
    elif (
        before["casting_generation_ready"]
        and not before["speaker_exception_queue"]
        and not before["ready_speaker_drafts"]
    ):
        for item in before["casting_generation_ready"]:
            try:
                detail = get_speaker_review_draft(
                    db,
                    store,
                    config,
                    chapter_id=int(item["chapter_id"]),
                    draft_id=int(item["draft_id"]),
                )
                decisions = _speaker_roles(detail)
                replace_plan_id = item.get("replace_plan_id")
                if replace_plan_id:
                    replaced = get_plan(db, store, int(replace_plan_id))
                    created = create_casting_draft(
                        db,
                        store,
                        chapter_id=int(item["chapter_id"]),
                        text_revision_id=int(detail["text_revision_id"]),
                        narrator_voice_id=str(
                            replaced["plan"].get("narrator_voice_id") or ""
                        ),
                        assignments=[
                            {
                                "utterance_id": utterance["utterance_id"],
                                "role": utterance.get("role") or "narrator",
                                "character_id": utterance.get("character_id"),
                            }
                            for utterance in replaced["plan"].get("utterances") or []
                        ],
                        allowed_voice_ids=allowed_voice_ids,
                        maximum=config.tts_max_chars,
                        source_metadata={
                            "source": "range_voice_remediation",
                            "speaker_draft_id": int(item["draft_id"]),
                            "replaces_casting_plan_id": int(replace_plan_id),
                        },
                        base_utterances=replaced["plan"].get("utterances") or [],
                        custom_voice_context=custom_voice_context,
                    )
                    object_id = int(created["id"])
                    reused = False
                else:
                    created = create_casting_plan_draft_from_speaker_review(
                        db,
                        store,
                        config,
                        chapter_id=int(item["chapter_id"]),
                        draft_id=int(item["draft_id"]),
                        base_casting_plan_revision_id=detail.get(
                            "base_casting_plan_id"
                        ),
                        expected_draft_fingerprint=str(detail["input_fingerprint"]),
                        expected_text_revision_id=int(detail["text_revision_id"]),
                        decisions=decisions,
                        idempotency_key=(
                            f"range-input-draft-{int(item['draft_id'])}-"
                            f"{str(detail['input_fingerprint'])[:24]}"
                        ),
                        operator_note="Range input preparation; draft only.",
                        allowed_voice_ids=allowed_voice_ids,
                        custom_voice_context=custom_voice_context,
                    )
                    object_id = int(created["casting_plan_id"])
                    reused = bool(created.get("idempotent_reused"))
                results.append({
                    **_chapter_ref(item),
                    "operation": "casting_plan_draft",
                    "object_id": object_id,
                    "reused": reused,
                })
            except Exception as exc:
                failures.append({
                    **_chapter_ref(item),
                    "operation": "casting_plan_draft",
                    "error": str(exc),
                })
    return {
        "status": "partial" if failures and results else "failed" if failures else "complete",
        "results": results,
        "failures": failures,
        "snapshot": get_range_input_snapshot(
            db,
            store,
            config,
            book_id=book_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
            voice_catalog=voice_catalog,
            custom_voice_context=custom_voice_context,
            skip_completed=skip_completed,
        ),
    }


def approve_ready_speaker_drafts(
    db: Database,
    store: ContentStore,
    config: Settings,
    *,
    snapshot: dict[str, Any],
    requested: list[dict[str, int]],
) -> dict[str, Any]:
    ready = {
        (int(item["chapter_id"]), int(item["draft_id"])): item
        for item in snapshot["ready_speaker_drafts"]
    }
    ordered = sorted(
        requested,
        key=lambda item: (
            int(ready.get((int(item["chapter_id"]), int(item["draft_id"])), {}).get(
                "chapter_number", 10**9
            )),
            int(item["chapter_id"]),
        ),
    )
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for request in ordered:
        identity = (int(request["chapter_id"]), int(request["draft_id"]))
        if identity in seen:
            failures.append({
                "chapter_id": identity[0],
                "draft_id": identity[1],
                "error": "Duplicate chapter/draft request.",
            })
            continue
        seen.add(identity)
        item = ready.get(identity)
        if not item:
            chapter = _chapter_in_snapshot_scope(db, snapshot, identity[0])
            latest = db.fetch_one(
                """SELECT id,status
                   FROM speaker_assignment_drafts
                   WHERE chapter_id=?
                   ORDER BY created_at DESC,id DESC
                   LIMIT 1""",
                (identity[0],),
            )
            if (
                chapter
                and latest
                and int(latest["id"]) == identity[1]
                and str(latest["status"]).lower() == "approved"
            ):
                try:
                    detail = get_speaker_review_draft(
                        db,
                        store,
                        config,
                        chapter_id=identity[0],
                        draft_id=identity[1],
                    )
                    if detail["stale"]:
                        raise SpeakerReviewConflict(
                            "Approved Speaker Draft became stale."
                        )
                    results.append({
                        **_chapter_ref(chapter),
                        "draft_id": identity[1],
                        "status": "approved",
                        "reused": True,
                    })
                    continue
                except (
                    SpeakerReviewError,
                    SpeakerReviewConflict,
                    SpeakerReviewNotFound,
                ):
                    pass
            failures.append({
                "chapter_id": identity[0],
                "draft_id": identity[1],
                "error": "Draft is stale, unresolved, or outside the selected range.",
            })
            continue
        try:
            detail = get_speaker_review_draft(
                db,
                store,
                config,
                chapter_id=identity[0],
                draft_id=identity[1],
            )
            for row in detail.get("review_rows") or []:
                if row.get("reviewed"):
                    continue
                if _is_speaker_exception(row):
                    raise SpeakerReviewError(
                        "Speaker draft still contains a human-review exception."
                    )
                suggestion = row["suggestion"]
                speaker_type = str(suggestion["speaker_type"])
                review_speaker_assignment_row(
                    db,
                    store,
                    config,
                    chapter_id=identity[0],
                    draft_id=identity[1],
                    target_id=str(row["utterance_id"]),
                    speaker_type=speaker_type,
                    character_id=suggestion.get("character_id"),
                    decision_source=(
                        "manual_character"
                        if speaker_type == "character"
                        else "narrator"
                        if speaker_type == "narrator"
                        else "unknown"
                    ),
                    operator_note="Accepted from high-confidence range proposal.",
                )
            approved = approve_speaker_assignment_draft_only(
                db,
                store,
                config,
                chapter_id=identity[0],
                draft_id=identity[1],
            )
            results.append({
                **_chapter_ref(item),
                "draft_id": identity[1],
                "status": approved["status"],
                "reused": bool(approved.get("idempotent_reused")),
            })
        except Exception as exc:
            failures.append({
                **_chapter_ref(item),
                "draft_id": identity[1],
                "error": str(exc),
            })
    return {
        "status": "partial" if failures and results else "failed" if failures else "complete",
        "results": results,
        "failures": failures,
    }


def approve_ready_casting_plans(
    db: Database,
    store: ContentStore,
    *,
    snapshot: dict[str, Any],
    requested: list[dict[str, int]],
    voice_catalog: EffectiveVoiceCatalog,
    allowed_voice_ids: set[str],
    custom_voice_context: CustomVoiceContext | None = None,
) -> dict[str, Any]:
    ready = {
        (int(item["chapter_id"]), int(item["plan_id"])): item
        for item in snapshot["casting_approvals"]
        if int(item.get("unresolved_count") or 0) == 0
    }
    ordered = sorted(
        requested,
        key=lambda item: (
            int(ready.get((int(item["chapter_id"]), int(item["plan_id"])), {}).get(
                "chapter_number", 10**9
            )),
            int(item["chapter_id"]),
        ),
    )
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for request in ordered:
        identity = (int(request["chapter_id"]), int(request["plan_id"]))
        if identity in seen:
            failures.append({
                "chapter_id": identity[0],
                "plan_id": identity[1],
                "error": "Duplicate chapter/plan request.",
            })
            continue
        seen.add(identity)
        item = ready.get(identity)
        if not item:
            chapter = _chapter_in_snapshot_scope(db, snapshot, identity[0])
            latest = _latest_plan_row(db, identity[0])
            if (
                chapter
                and latest
                and int(latest["id"]) == identity[1]
                and str(latest["status"]).lower() == "approved"
            ):
                try:
                    candidate = get_plan(db, store, identity[1], include_text=True)
                    require_casting_plan_eligible(
                        candidate["plan"],
                        voice_catalog,
                        chapter_id=identity[0],
                    )
                    validate_approved_plan(
                        db,
                        store,
                        identity[1],
                        allowed_voice_ids,
                        custom_voice_context=custom_voice_context,
                    )
                    results.append({
                        **_chapter_ref(chapter),
                        "plan_id": identity[1],
                        "plan_revision": int(latest["plan_revision"]),
                        "status": "approved",
                        "reused": True,
                    })
                    continue
                except (CastingError, VoiceEligibilityBlocked):
                    pass
            failures.append({
                "chapter_id": identity[0],
                "plan_id": identity[1],
                "error": "Casting Plan is stale, invalid, or outside the selected range.",
            })
            continue
        try:
            candidate = get_plan(db, store, identity[1], include_text=True)
            require_casting_plan_eligible(
                candidate["plan"],
                voice_catalog,
                chapter_id=identity[0],
            )
            approved = approve_plan(db, store, identity[1])
            validate_approved_plan(
                db,
                store,
                identity[1],
                allowed_voice_ids,
                custom_voice_context=custom_voice_context,
            )
            results.append({
                **_chapter_ref(item),
                "plan_id": identity[1],
                "plan_revision": int(item["plan_revision"]),
                "status": approved["status"],
                "reused": False,
            })
        except (
            CastingError,
            VoiceEligibilityBlocked,
            SpeakerReviewError,
            SpeakerReviewConflict,
            SpeakerReviewNotFound,
        ) as exc:
            failures.append({
                **_chapter_ref(item),
                "plan_id": identity[1],
                "error": str(exc),
            })
    return {
        "status": "partial" if failures and results else "failed" if failures else "complete",
        "results": results,
        "failures": failures,
    }
