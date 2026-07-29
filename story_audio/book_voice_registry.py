from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .casting import CastingError, get_plan, list_characters, split_utterances
from .character_assignment import (
    UNRESOLVED_DIALOGUE_ROLE,
    UNRESOLVED_DIALOGUE_STATUS,
    UnresolvedDialogueReference,
    is_unresolved_dialogue_text,
)
from .config import Settings
from .db import Database
from .speaker_assignment import SpeakerAssignmentError
from .speaker_review import SpeakerReviewError, get_speaker_review_draft
from .storage import ContentStore
from .voice_eligibility import EffectiveVoiceCatalog
from .voice_profile import VoiceProfileError, get_book_voice_profile, resolve_voice
from .voice_ref import CustomVoiceContext


REGISTRY_SCHEMA = "story-audio-book-voice-registry/v1"
REGISTRY_STATUSES = {
    "READY",
    "NEW_CHARACTER",
    "UNASSIGNED",
    "CONFLICT",
    "VOICE_UNAVAILABLE",
    "OVERRIDDEN",
    UNRESOLVED_DIALOGUE_STATUS,
}
UNRESOLVED_STATUSES = {
    "NEW_CHARACTER",
    "UNASSIGNED",
    "CONFLICT",
    "VOICE_UNAVAILABLE",
    UNRESOLVED_DIALOGUE_STATUS,
}


class BookVoiceRegistryError(ValueError):
    pass


@dataclass
class _RegistryRow:
    speaker_key: str
    display_name: str
    role: str
    role_label: str
    character_id: int | None = None
    aliases: list[str] = field(default_factory=list)
    gender: str | None = None
    character: dict[str, Any] | None = None
    chapter_numbers: set[int] = field(default_factory=set)
    chapter_ids: set[int] = field(default_factory=set)
    line_count: int = 0
    first_appearance: int | None = None
    plan_voice_ids: set[str] = field(default_factory=set)
    plan_voice_chapters: dict[str, set[int]] = field(default_factory=lambda: defaultdict(set))
    plan_statuses: set[str] = field(default_factory=set)
    last_plan_id: int | None = None
    last_plan_revision: int | None = None
    last_plan_status: str | None = None
    last_reviewed_at: str | None = None
    sample_lines: list[dict[str, Any]] = field(default_factory=list)
    target_utterances: list[dict[str, Any]] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)

    def touch(self, chapter: Mapping[str, Any], *, voice_id: str | None = None) -> None:
        chapter_id = int(chapter["id"])
        chapter_number = int(chapter["chapter_number"])
        self.chapter_ids.add(chapter_id)
        self.chapter_numbers.add(chapter_number)
        self.line_count += 1
        if self.first_appearance is None or chapter_number < self.first_appearance:
            self.first_appearance = chapter_number
        if voice_id:
            normalized = str(voice_id).strip()
            if normalized:
                self.plan_voice_ids.add(normalized)
                self.plan_voice_chapters[normalized].add(chapter_number)

    def touch_reference(
        self,
        chapter: Mapping[str, Any],
        reference: UnresolvedDialogueReference,
        *,
        voice_id: str | None = None,
        plan: Mapping[str, Any] | None = None,
    ) -> None:
        self.touch(chapter, voice_id=voice_id)
        payload = reference.public_payload()
        self.target_utterances.append(payload)
        if len(self.sample_lines) < 5:
            self.sample_lines.append(payload)
        if plan:
            self.plan_touch(plan)
            self.provenance.append(
                {
                    "source": "casting_plan_dialogue_detection",
                    "chapter_id": int(chapter["id"]),
                    "chapter_number": int(chapter["chapter_number"]),
                    "casting_plan_id": int(plan["id"]) if plan.get("id") is not None else None,
                    "plan_revision": int(plan["plan_revision"]) if plan.get("plan_revision") is not None else None,
                    "status": plan.get("status"),
                    "utterance_id": reference.utterance_id,
                }
            )
        else:
            self.provenance.append(
                {
                    "source": "text_dialogue_detection",
                    "chapter_id": int(chapter["id"]),
                    "chapter_number": int(chapter["chapter_number"]),
                    "utterance_id": reference.utterance_id,
                }
            )

    def plan_touch(self, plan: Mapping[str, Any]) -> None:
        self.plan_statuses.add(str(plan.get("status") or ""))
        plan_id = int(plan["id"]) if plan.get("id") is not None else None
        revision = int(plan["plan_revision"]) if plan.get("plan_revision") is not None else None
        if plan_id is not None and (self.last_plan_id is None or plan_id >= self.last_plan_id):
            self.last_plan_id = plan_id
            self.last_plan_revision = revision
            self.last_plan_status = str(plan.get("status") or "")
            self.last_reviewed_at = plan.get("approved_at") or plan.get("created_at")


def _voice_index(catalog: EffectiveVoiceCatalog) -> dict[str, dict[str, Any]]:
    return {str(item["assignment_key"]): dict(item) for item in catalog.items}


def _voice_payload(
    voice_id: str | None,
    *,
    catalog: EffectiveVoiceCatalog,
    index: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    normalized = str(voice_id or "").strip()
    if not normalized:
        return None
    item = dict(index.get(normalized) or {})
    display = (
        item.get("display_name")
        or item.get("name")
        or item.get("label")
        or ("Giọng tùy chỉnh đã lưu" if normalized.startswith("custom:") else "Giọng đã lưu")
    )
    preview = (
        item.get("preview_url")
        or item.get("preview_asset_url")
        or item.get("preview_path")
        or item.get("reference_audio_url")
    )
    return {
        "id": normalized,
        "display_name": str(display),
        "available": normalized in catalog.selectable_ids,
        "source_kind": item.get("source_kind"),
        "preview_url": preview,
    }


def _voice_name(voice: dict[str, Any] | None) -> str | None:
    return str(voice.get("display_name")) if voice else None


def _book_row(db: Database, book_id: int) -> dict[str, Any]:
    row = db.fetch_one("SELECT * FROM books WHERE id=?", (book_id,))
    if not row:
        raise LookupError("Book not found")
    return dict(row)


def _range_chapters(
    db: Database,
    *,
    book_id: int,
    from_chapter: int | None,
    to_chapter: int | None,
    skip_completed: bool = False,
) -> list[dict[str, Any]]:
    start = int(from_chapter or 0)
    end = int(to_chapter if to_chapter is not None else start)
    if start <= 0 or end <= 0:
        rows = db.fetch_all(
            """
            SELECT id,book_id,chapter_number,title,active_text_revision_id,audio_status
            FROM chapters
            WHERE book_id=?
            ORDER BY chapter_number,id
            """,
            (book_id,),
        )
    else:
        if start > end:
            raise BookVoiceRegistryError("from_chapter must be less than or equal to to_chapter")
        rows = db.fetch_all(
            """
            SELECT id,book_id,chapter_number,title,active_text_revision_id,audio_status
            FROM chapters
            WHERE book_id=? AND chapter_number BETWEEN ? AND ?
            ORDER BY chapter_number,id
            """,
            (book_id, start, end),
        )
    chapters = [dict(row) for row in rows]
    if skip_completed:
        chapters = [
            chapter for chapter in chapters
            if str(chapter.get("audio_status") or "") != "completed"
        ]
    if not chapters:
        raise LookupError("No chapters found for the selected range")
    return chapters


def _latest_plan_row(db: Database, chapter_id: int) -> dict[str, Any] | None:
    row = db.fetch_one(
        """
        SELECT * FROM casting_plans
        WHERE chapter_id=?
        ORDER BY plan_revision DESC,id DESC
        LIMIT 1
        """,
        (chapter_id,),
    )
    return dict(row) if row else None


def _latest_approved_speaker_draft_row(db: Database, chapter_id: int) -> dict[str, Any] | None:
    row = db.fetch_one(
        """
        SELECT *
        FROM speaker_assignment_drafts
        WHERE chapter_id=? AND status='approved'
        ORDER BY approved_at DESC,created_at DESC,id DESC
        LIMIT 1
        """,
        (chapter_id,),
    )
    return dict(row) if row else None


def _prior_character_ids(db: Database, *, book_id: int, before_chapter: int) -> set[int]:
    rows = db.fetch_all(
        """
        SELECT DISTINCT cpc.character_id
        FROM casting_plan_characters cpc
        JOIN casting_plans cp ON cp.id=cpc.casting_plan_id
        JOIN chapters c ON c.id=cp.chapter_id
        WHERE c.book_id=? AND c.chapter_number<?
        """,
        (book_id, before_chapter),
    )
    return {int(row["character_id"]) for row in rows if row["character_id"] is not None}


def _character_map(db: Database, book_id: int) -> dict[int, dict[str, Any]]:
    return {int(item["id"]): dict(item) for item in list_characters(db, book_id)}


def _ensure_narrator(rows: dict[str, _RegistryRow]) -> _RegistryRow:
    row = rows.get("narrator")
    if row is None:
        row = _RegistryRow(
            speaker_key="narrator",
            display_name="Người kể chuyện",
            role="narrator",
            role_label="Người kể chuyện",
        )
        rows["narrator"] = row
    return row


def _ensure_unknown(rows: dict[str, _RegistryRow]) -> _RegistryRow:
    row = rows.get("unknown")
    if row is None:
        row = _RegistryRow(
            speaker_key="unknown",
            display_name="Người nói chưa rõ",
            role="unknown",
            role_label="Người nói chưa rõ",
        )
        rows["unknown"] = row
    return row


def _ensure_unresolved_dialogue(
    rows: dict[str, _RegistryRow],
    reference: UnresolvedDialogueReference,
) -> _RegistryRow:
    row = rows.get(reference.speaker_key)
    if row is not None:
        return row
    row = _RegistryRow(
        speaker_key=reference.speaker_key,
        display_name="Chưa xác định nhân vật",
        role=UNRESOLVED_DIALOGUE_ROLE,
        role_label="Chưa xác định nhân vật / người nói",
    )
    rows[reference.speaker_key] = row
    return row


def _ensure_character(
    rows: dict[str, _RegistryRow],
    characters: Mapping[int, Mapping[str, Any]],
    character_id: int,
) -> _RegistryRow:
    key = f"character:{character_id}"
    row = rows.get(key)
    if row is not None:
        return row
    character = dict(characters.get(character_id) or {})
    display_name = str(character.get("display_name") or f"Nhân vật #{character_id}")
    row = _RegistryRow(
        speaker_key=key,
        character_id=character_id,
        display_name=display_name,
        role="character",
        role_label="Nhân vật",
        aliases=[str(item) for item in character.get("aliases") or []],
        gender=character.get("gender"),
        character=character if character else None,
    )
    rows[key] = row
    return row


def _collect_from_plan(
    rows: dict[str, _RegistryRow],
    *,
    plan: Mapping[str, Any],
    chapter: Mapping[str, Any],
    characters: Mapping[int, Mapping[str, Any]],
    text: str,
) -> None:
    for utterance in plan.get("plan", {}).get("utterances") or []:
        role = str(utterance.get("role") or "narrator")
        voice_id = str(utterance.get("resolved_voice_id") or "").strip() or None
        segment = text[int(utterance["start_offset"]) : int(utterance["end_offset"])].strip()
        if role == "narrator" and is_unresolved_dialogue_text(segment):
            reference = UnresolvedDialogueReference(
                chapter_id=int(chapter["id"]),
                chapter_number=int(chapter["chapter_number"]),
                utterance_id=str(utterance["utterance_id"]),
                sequence=int(utterance["sequence"]),
                text=segment,
                role=role,
                character_id=None,
            )
            row = _ensure_unresolved_dialogue(rows, reference)
            row.touch_reference(chapter, reference, plan=plan)
            continue
        if role == "character" and utterance.get("character_id") is not None:
            row = _ensure_character(rows, characters, int(utterance["character_id"]))
        elif role == "unknown":
            row = _ensure_unknown(rows)
        else:
            row = _ensure_narrator(rows)
        row.touch(chapter, voice_id=voice_id)
        row.plan_touch(plan)


def _collect_from_speaker_draft(
    rows: dict[str, _RegistryRow],
    *,
    db: Database,
    store: ContentStore,
    config: Settings,
    chapter: Mapping[str, Any],
    draft_id: int,
    characters: Mapping[int, Mapping[str, Any]],
) -> None:
    detail = get_speaker_review_draft(
        db,
        store,
        config,
        chapter_id=int(chapter["id"]),
        draft_id=draft_id,
    )
    reviews = {str(item["utterance_id"]): item for item in detail.get("row_reviews") or []}
    for review_row in detail.get("review_rows") or []:
        decision = reviews.get(str(review_row["utterance_id"]))
        if not decision:
            continue
        speaker_type = str(decision.get("speaker_type") or "")
        review_text = str(review_row.get("text") or "")
        if speaker_type == "narrator" and is_unresolved_dialogue_text(review_text):
            reference = UnresolvedDialogueReference(
                chapter_id=int(chapter["id"]),
                chapter_number=int(chapter["chapter_number"]),
                utterance_id=str(review_row["utterance_id"]),
                sequence=int(review_row.get("sequence") or 0),
                text=review_text,
                role="narrator",
                character_id=None,
            )
            row = _ensure_unresolved_dialogue(rows, reference)
            row.touch_reference(chapter, reference)
            continue
        if speaker_type == "character" and decision.get("character_id") is not None:
            row = _ensure_character(rows, characters, int(decision["character_id"]))
        elif speaker_type == "unknown":
            row = _ensure_unknown(rows)
        else:
            row = _ensure_narrator(rows)
        row.touch(chapter)


def _collect_from_text(
    rows: dict[str, _RegistryRow],
    *,
    chapter: Mapping[str, Any],
    text: str,
) -> None:
    for utterance in split_utterances(text):
        segment = text[int(utterance["start_offset"]) : int(utterance["end_offset"])].strip()
        if is_unresolved_dialogue_text(segment):
            reference = UnresolvedDialogueReference(
                chapter_id=int(chapter["id"]),
                chapter_number=int(chapter["chapter_number"]),
                utterance_id=str(utterance["utterance_id"]),
                sequence=int(utterance["sequence"]),
                text=segment,
                role="narrator",
                character_id=None,
            )
            row = _ensure_unresolved_dialogue(rows, reference)
            row.touch_reference(chapter, reference)
        else:
            _ensure_narrator(rows).touch(chapter)


def _assignment_source(
    *,
    role: str,
    resolution: Mapping[str, Any] | None,
    plan_voices: set[str],
    effective_voice_id: str | None,
    range_size: int,
) -> str:
    if role == UNRESOLVED_DIALOGUE_ROLE:
        return "unresolved dialogue"
    if plan_voices and effective_voice_id and (
        len(plan_voices) > 1
        or any(voice != effective_voice_id for voice in plan_voices)
    ):
        return "range override" if range_size > 1 else "chapter override"
    source = str((resolution or {}).get("resolution_source") or "")
    if source == "character_override":
        return "book default"
    if role == "narrator" and source == "narrator":
        return "book default"
    return "inherited"


def _resolve_row_voice(
    row: _RegistryRow,
    *,
    profile: Mapping[str, Any] | None,
    custom_voice_context: CustomVoiceContext | None,
) -> tuple[dict[str, Any] | None, str | None]:
    if not profile:
        character_voice = row.character.get("voice_override_id") if row.character else None
        if row.role == "narrator":
            return None, None
        return (
            {
                "resolved_voice_id": str(character_voice),
                "resolution_source": "character_override",
                "needs_review": False,
            },
            str(character_voice) if character_voice else None,
        )
    if row.role == "narrator":
        resolution = resolve_voice(
            speaker_type="narrator",
            book_voice_profile=profile,
            custom_voice_context=custom_voice_context,
        )
    elif row.role == UNRESOLVED_DIALOGUE_ROLE:
        return None, None
    elif row.role == "unknown":
        resolution = resolve_voice(
            speaker_type="dialogue",
            book_voice_profile=profile,
            custom_voice_context=custom_voice_context,
        )
    elif row.character:
        resolution = resolve_voice(
            speaker_type="character",
            book_voice_profile=profile,
            character=row.character,
            custom_voice_context=custom_voice_context,
        )
    else:
        return None, None
    return resolution, str(resolution.get("resolved_voice_id") or "").strip() or None


def _row_status(
    row: _RegistryRow,
    *,
    base_voice_id: str | None,
    effective_voice_id: str | None,
    effective_voice_available: bool,
    resolution: Mapping[str, Any] | None,
    prior_character_ids: set[int],
) -> str:
    if row.role == UNRESOLVED_DIALOGUE_ROLE:
        return UNRESOLVED_DIALOGUE_STATUS
    if len(row.plan_voice_ids) > 1:
        return "CONFLICT"
    if not effective_voice_id:
        return "UNASSIGNED"
    if not effective_voice_available:
        return "VOICE_UNAVAILABLE"
    if row.role == "unknown":
        return "UNASSIGNED"
    if row.character_id is not None and row.character_id not in prior_character_ids:
        if not (row.character or {}).get("voice_override_id"):
            return "NEW_CHARACTER"
    if resolution and resolution.get("needs_review") and not (row.character or {}).get("voice_override_id"):
        return "NEW_CHARACTER"
    if row.plan_voice_ids and any(voice != base_voice_id for voice in row.plan_voice_ids):
        return "OVERRIDDEN"
    return "READY"


def _row_to_payload(
    row: _RegistryRow,
    *,
    profile: Mapping[str, Any] | None,
    catalog: EffectiveVoiceCatalog,
    index: Mapping[str, Mapping[str, Any]],
    custom_voice_context: CustomVoiceContext | None,
    prior_character_ids: set[int],
    range_size: int,
) -> dict[str, Any]:
    try:
        resolution, base_voice_id = _resolve_row_voice(
            row,
            profile=profile,
            custom_voice_context=custom_voice_context,
        )
    except VoiceProfileError:
        resolution, base_voice_id = None, None

    if len(row.plan_voice_ids) == 1:
        effective_voice_id = next(iter(row.plan_voice_ids))
    else:
        effective_voice_id = base_voice_id
    saved_voice_id = None
    if row.role == "narrator" and profile:
        saved_voice_id = str(profile.get("narrator_voice_id") or "") or None
    elif row.character:
        saved_voice_id = str(row.character.get("voice_override_id") or "") or None
    elif row.role == "unknown":
        saved_voice_id = base_voice_id

    effective_voice = _voice_payload(effective_voice_id, catalog=catalog, index=index)
    saved_voice = _voice_payload(saved_voice_id, catalog=catalog, index=index)
    base_voice = _voice_payload(base_voice_id, catalog=catalog, index=index)
    book_default_voice = saved_voice or base_voice
    status = _row_status(
        row,
        base_voice_id=base_voice_id,
        effective_voice_id=effective_voice_id,
        effective_voice_available=bool(effective_voice and effective_voice["available"]),
        resolution=resolution,
        prior_character_ids=prior_character_ids,
    )
    if status not in REGISTRY_STATUSES:
        status = "UNASSIGNED"
    plan_override_voice = (
        _voice_payload(next(iter(row.plan_voice_ids)), catalog=catalog, index=index)
        if len(row.plan_voice_ids) == 1 and next(iter(row.plan_voice_ids)) != base_voice_id
        else None
    )
    conflict_voices = [
        {
            "voice": _voice_payload(voice, catalog=catalog, index=index),
            "chapter_numbers": sorted(row.plan_voice_chapters.get(voice) or []),
        }
        for voice in sorted(row.plan_voice_ids)
    ] if len(row.plan_voice_ids) > 1 else []
    assignment_source = _assignment_source(
        role=row.role,
        resolution=resolution,
        plan_voices=row.plan_voice_ids,
        effective_voice_id=base_voice_id,
        range_size=range_size,
    )
    chapter_voice_details = []
    for voice in sorted(row.plan_voice_chapters):
        for chapter_number in sorted(row.plan_voice_chapters.get(voice) or []):
            voice_payload = _voice_payload(voice, catalog=catalog, index=index)
            override_voice = (
                voice_payload
                if base_voice_id and voice != base_voice_id
                else None
            )
            chapter_voice_details.append(
                {
                    "chapter_number": chapter_number,
                    "inherited_voice": base_voice,
                    "chapter_override_voice": override_voice,
                    "effective_voice": voice_payload or base_voice,
                    "assignment_source": (
                        "chapter override"
                        if override_voice
                        else "book default" if row.role == "narrator" else "inherited"
                    ),
                }
            )
    return {
        "speaker_key": row.speaker_key,
        "character_id": row.character_id,
        "display_name": row.display_name,
        "aliases": list(row.aliases),
        "role": row.role,
        "role_label": row.role_label,
        "character_role": (row.character or {}).get("role"),
        "gender": row.gender,
        "chapter_ids": sorted(row.chapter_ids),
        "chapter_numbers": sorted(row.chapter_numbers),
        "chapter_range_label": _chapter_range_label(sorted(row.chapter_numbers)),
        "line_count": int(row.line_count),
        "first_appearance": row.first_appearance,
        "current_book_default_voice": book_default_voice,
        "saved_voice": saved_voice,
        "base_resolved_voice": base_voice,
        "range_override_voice": plan_override_voice if range_size > 1 else None,
        "chapter_override_voice": plan_override_voice if range_size == 1 else None,
        "conflict_voices": conflict_voices,
        "chapter_voice_details": chapter_voice_details,
        "effective_voice": effective_voice,
        "effective_voice_display_name": _voice_name(effective_voice),
        "voice_available": bool(effective_voice and effective_voice["available"]),
        "status": status,
        "assignment_source": assignment_source,
        "resolution_source": (resolution or {}).get("resolution_source"),
        "needs_review": bool((resolution or {}).get("needs_review")),
        "last_reviewed": {
            "casting_plan_id": row.last_plan_id,
            "plan_revision": row.last_plan_revision,
            "status": row.last_plan_status,
            "reviewed_at": row.last_reviewed_at,
        },
        "sample_lines": list(row.sample_lines),
        "target_utterances": list(row.target_utterances),
        "provenance": list(row.provenance),
        "actions": {
            "can_save_book_default": row.role in {"narrator", "unknown"} or row.character_id is not None,
            "can_create_range_or_chapter_override": row.role in {"narrator", "unknown"} or row.character_id is not None,
            "can_remove_override": bool(plan_override_voice),
            "can_preview_effective_voice": bool(effective_voice and effective_voice.get("preview_url")),
            "can_map_to_character": row.role in {UNRESOLVED_DIALOGUE_ROLE, "unknown"},
            "can_create_character": row.role == UNRESOLVED_DIALOGUE_ROLE,
            "future_render_only": True,
        },
    }


def _chapter_range_label(chapters: Iterable[int]) -> str:
    numbers = sorted(set(int(value) for value in chapters))
    if not numbers:
        return "Chưa xuất hiện trong phạm vi"
    if len(numbers) == 1:
        return f"Chương {numbers[0]}"
    ranges: list[str] = []
    start = previous = numbers[0]
    for number in numbers[1:]:
        if number == previous + 1:
            previous = number
            continue
        ranges.append(f"{start}" if start == previous else f"{start}-{previous}")
        start = previous = number
    ranges.append(f"{start}" if start == previous else f"{start}-{previous}")
    return "Chương " + ", ".join(ranges)


def _sort_rows(item: dict[str, Any]) -> tuple[int, int, int, str]:
    if item["speaker_key"] == "narrator":
        return (0, 0, 0, "")
    status = str(item.get("status") or "")
    priority = {
        "CONFLICT": 0,
        "VOICE_UNAVAILABLE": 1,
        UNRESOLVED_DIALOGUE_STATUS: 2,
        "NEW_CHARACTER": 2,
        "UNASSIGNED": 3,
        "OVERRIDDEN": 4,
        "READY": 5,
    }.get(status, 6)
    group = 1 if status in UNRESOLVED_STATUSES else 2
    first = int(item.get("first_appearance") or 999_999)
    return (group, priority, first, str(item.get("display_name") or "").casefold())


def get_book_voice_registry(
    db: Database,
    store: ContentStore,
    config: Settings,
    *,
    book_id: int,
    from_chapter: int | None = None,
    to_chapter: int | None = None,
    skip_completed: bool = False,
    voice_catalog: EffectiveVoiceCatalog,
    custom_voice_context: CustomVoiceContext | None = None,
) -> dict[str, Any]:
    book = _book_row(db, book_id)
    chapters = _range_chapters(
        db,
        book_id=book_id,
        from_chapter=from_chapter,
        to_chapter=to_chapter,
        skip_completed=skip_completed,
    )
    first_chapter = int(chapters[0]["chapter_number"])
    range_size = max(1, len(chapters))
    profile = get_book_voice_profile(db, book_id)
    characters = _character_map(db, book_id)
    catalog_index = _voice_index(voice_catalog)
    rows: dict[str, _RegistryRow] = {}
    _ensure_narrator(rows)
    checked_revisions: list[dict[str, Any]] = []

    for chapter in chapters:
        revision = db.fetch_one(
            "SELECT id,content_path FROM text_revisions WHERE id=?",
            (int(chapter.get("active_text_revision_id") or 0),),
        )
        text = ""
        if revision:
            try:
                text = store.read_text(str(revision["content_path"]))
                checked_revisions.append(
                    {
                        "chapter_id": int(chapter["id"]),
                        "chapter_number": int(chapter["chapter_number"]),
                        "text_revision_id": int(revision["id"]),
                    }
                )
            except OSError:
                text = ""
        plan_row = _latest_plan_row(db, int(chapter["id"]))
        plan_collected = False
        if plan_row and int(plan_row["text_revision_id"]) == int(chapter.get("active_text_revision_id") or 0):
            try:
                plan = get_plan(db, store, int(plan_row["id"]))
                _collect_from_plan(
                    rows,
                    plan=plan,
                    chapter=chapter,
                    characters=characters,
                    text=text,
                )
                plan_collected = True
            except (CastingError, OSError, ValueError):
                plan_collected = False
        if plan_collected:
            continue
        draft = _latest_approved_speaker_draft_row(db, int(chapter["id"]))
        if not draft:
            if text:
                _collect_from_text(rows, chapter=chapter, text=text)
            continue
        try:
            _collect_from_speaker_draft(
                rows,
                db=db,
                store=store,
                config=config,
                chapter=chapter,
                draft_id=int(draft["id"]),
                characters=characters,
            )
        except (SpeakerReviewError, SpeakerAssignmentError, OSError, ValueError):
            if text:
                _collect_from_text(rows, chapter=chapter, text=text)
            continue

    prior_ids = _prior_character_ids(db, book_id=book_id, before_chapter=first_chapter)
    payload_rows = [
        _row_to_payload(
            row,
            profile=profile,
            catalog=voice_catalog,
            index=catalog_index,
            custom_voice_context=custom_voice_context,
            prior_character_ids=prior_ids,
            range_size=range_size,
        )
        for row in rows.values()
        if row.speaker_key == "narrator" or row.line_count > 0
    ]
    payload_rows.sort(key=_sort_rows)
    status_counts: dict[str, int] = {status: 0 for status in sorted(REGISTRY_STATUSES)}
    for row in payload_rows:
        status_counts[str(row["status"])] = status_counts.get(str(row["status"]), 0) + 1
    blockers = [
        row
        for row in payload_rows
        if row["status"] in UNRESOLVED_STATUSES
    ]
    return {
        "schema": REGISTRY_SCHEMA,
        "book": {
            "id": int(book["id"]),
            "title": book["title"],
            "chapter_count": int(book.get("chapter_count") or 0),
        },
        "range": {
            "from_chapter": int(chapters[0]["chapter_number"]),
            "to_chapter": int(chapters[-1]["chapter_number"]),
            "chapter_count": len(chapters),
            "chapter_ids": [int(item["id"]) for item in chapters],
            "focused_chapter_id": None,
        },
        "persistence": {
            "migration_required": False,
            "uses_existing_model": True,
            "model": "book_voice_profiles + characters/aliases + casting_plan_revisions",
            "book_profile_config_version": int(profile["config_version"]) if profile else None,
        },
        "voice_catalog": {
            "selectable_count": len(voice_catalog.selectable_ids),
            "narrator_voice_id": profile.get("narrator_voice_id") if profile else None,
        },
        "characters": [
            {
                "id": int(character["id"]),
                "display_name": character.get("display_name"),
                "canonical_name": character.get("canonical_name"),
                "role": character.get("role"),
                "gender": character.get("gender"),
                "aliases": list(character.get("aliases") or []),
                "active": bool(character.get("active", 1)),
            }
            for character in sorted(characters.values(), key=lambda item: str(item.get("display_name") or ""))
        ],
        "rows": payload_rows,
        "summary": {
            "total_rows": len(payload_rows),
            "blocking_rows": len(blockers),
            "status_counts": status_counts,
            "new_character": status_counts.get("NEW_CHARACTER", 0),
            "unassigned": status_counts.get("UNASSIGNED", 0),
            "conflict": status_counts.get("CONFLICT", 0),
            "voice_unavailable": status_counts.get("VOICE_UNAVAILABLE", 0),
            "overridden": status_counts.get("OVERRIDDEN", 0),
            "ready": status_counts.get("READY", 0),
            "unresolved_dialogue": status_counts.get(UNRESOLVED_DIALOGUE_STATUS, 0),
        },
        "content_evidence": {
            "checked_revisions": checked_revisions,
            "dialogue_detection": "dash-led dialogue utterances marked unresolved when still assigned narrator",
            "unresolved_dialogue_count": status_counts.get(UNRESOLVED_DIALOGUE_STATUS, 0),
        },
    }
