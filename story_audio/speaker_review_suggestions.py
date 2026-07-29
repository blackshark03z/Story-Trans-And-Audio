from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .casting import CHUNKER_VERSION, split_utterances
from .character_assignment import (
    UNRESOLVED_DIALOGUE_STATUS,
    apply_speaker_character_mapping,
    clear_speaker_character_mapping,
    create_assignment_character,
)
from .character_bible import normalize_identity
from .config import Settings
from .db import Database, utcnow
from .files import sha256_text
from .gemini import suggest_speaker_review
from .gemini_cache import GeminiRepairCache, canonical_json
from .storage import ContentStore
from .voice_eligibility import EffectiveVoiceCatalog
from .voice_profile import get_book_voice_profile, resolve_voice, set_character_voice_override
from .voice_ref import CustomVoiceContext


REQUEST_SCHEMA = "story-audio-gemini-speaker-review-request/v1"
SUGGESTION_SCHEMA = "story-audio-gemini-speaker-review-suggestions/v1"
RUN_SCHEMA = "story-audio-gemini-speaker-review-run/v1"
QUEUE_SCHEMA = "story-audio-gemini-speaker-review-queue/v1"
ANALYSIS_EVENT = "speaker_review_analysis_generated"
ANALYSIS_FAILED_EVENT = "speaker_review_analysis_failed"
DECISION_EVENT = "speaker_review_suggestion_reviewed"
PROMPT_VERSION = "speaker-review-suggestions-v1"
GENERATION_SETTINGS = {"temperature": 0, "response_mime_type": "application/json"}
RESOLUTIONS = {
    "EXISTING_CHARACTER",
    "NEW_CHARACTER",
    "NARRATOR",
    "UNKNOWN_SPEAKER",
    "NEEDS_HUMAN_DECISION",
}
VOICE_HANDLING = {
    "INHERIT_EXISTING_CONFIGURATION",
    "USE_BOOK_DEFAULT",
    "SUGGEST_AVAILABLE_VOICE",
    "LEAVE_UNASSIGNED",
}
DECISIONS = {"ACCEPTED", "EDITED_AND_ACCEPTED", "DEFERRED"}


class SpeakerReviewSuggestionError(ValueError):
    """Fail-closed contract error for AI speaker review suggestions."""


def _book_row(db: Database, book_id: int) -> dict[str, Any]:
    row = db.fetch_one("SELECT * FROM books WHERE id=?", (int(book_id),))
    if not row:
        raise SpeakerReviewSuggestionError("Book not found")
    return dict(row)


def _active_chapters(
    db: Database,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    skip_completed: bool,
) -> list[dict[str, Any]]:
    if from_chapter > to_chapter:
        raise SpeakerReviewSuggestionError("from_chapter must be less than or equal to to_chapter")
    rows = db.fetch_all(
        """
        SELECT id,book_id,chapter_number,title,active_text_revision_id,audio_status
        FROM chapters
        WHERE book_id=? AND chapter_number BETWEEN ? AND ?
        ORDER BY chapter_number,id
        """,
        (int(book_id), int(from_chapter), int(to_chapter)),
    )
    chapters = [dict(row) for row in rows]
    if skip_completed:
        chapters = [
            chapter
            for chapter in chapters
            if str(chapter.get("audio_status") or "") != "completed"
        ]
    if not chapters:
        raise SpeakerReviewSuggestionError("No chapters found for speaker review")
    return chapters


def _text_revision(
    db: Database, store: ContentStore, chapter: Mapping[str, Any]
) -> tuple[dict[str, Any], str]:
    revision_id = int(chapter.get("active_text_revision_id") or 0)
    row = db.fetch_one(
        "SELECT * FROM text_revisions WHERE id=? AND chapter_id=? AND status='approved'",
        (revision_id, int(chapter["id"])),
    )
    if not row:
        raise SpeakerReviewSuggestionError(
            f"Chapter {int(chapter['chapter_number'])} does not have an approved active TextRevision"
        )
    revision = dict(row)
    text = store.read_text(str(revision["content_path"]))
    if sha256_text(text) != str(revision["content_sha256"]):
        raise SpeakerReviewSuggestionError(
            f"TextRevision hash mismatch for Chapter {int(chapter['chapter_number'])}"
        )
    return revision, text


def _voice_payload(
    voice_id: str | None,
    catalog: EffectiveVoiceCatalog,
) -> dict[str, Any] | None:
    normalized = str(voice_id or "").strip()
    if not normalized:
        return None
    item = next(
        (
            dict(candidate)
            for candidate in catalog.items
            if str(candidate.get("assignment_key")) == normalized
        ),
        {},
    )
    return {
        "id": normalized,
        "display_name": str(item.get("display_name") or normalized),
        "available": normalized in catalog.selectable_ids,
        "source_kind": item.get("source_kind"),
        "preview_url": item.get("preview_url") or item.get("preview_asset_url"),
    }


def _characters_by_id(registry: Mapping[str, Any]) -> dict[int, dict[str, Any]]:
    return {
        int(item["id"]): dict(item)
        for item in registry.get("characters") or []
        if isinstance(item, Mapping) and item.get("id") is not None
    }


def _character_voice(
    *,
    db: Database,
    registry: Mapping[str, Any],
    character_id: int,
    book_profile: Mapping[str, Any] | None,
    catalog: EffectiveVoiceCatalog,
    custom_voice_context: CustomVoiceContext | None,
) -> tuple[dict[str, Any] | None, str]:
    key = f"character:{int(character_id)}"
    row = next(
        (
            item
            for item in registry.get("rows") or []
            if isinstance(item, Mapping) and str(item.get("speaker_key")) == key
        ),
        None,
    )
    if row:
        voice = row.get("effective_voice") or row.get("current_book_default_voice")
        source = row.get("assignment_source") or "book default"
        return dict(voice) if isinstance(voice, Mapping) else None, str(source)
    character = _characters_by_id(registry).get(int(character_id))
    db_character = db.fetch_one(
        "SELECT * FROM characters WHERE id=? AND active=1",
        (int(character_id),),
    )
    if db_character:
        character = {**(character or {}), **dict(db_character)}
    if not character or not book_profile:
        return None, "Chưa có giọng"
    resolution = resolve_voice(
        speaker_type="character",
        book_voice_profile=book_profile,
        character=character,
        custom_voice_context=custom_voice_context,
    )
    voice_id = str(resolution.get("resolved_voice_id") or "").strip() or None
    return _voice_payload(voice_id, catalog), str(resolution.get("resolution_source") or "book default")


def _narrator_voice(
    *, book_profile: Mapping[str, Any] | None, catalog: EffectiveVoiceCatalog
) -> dict[str, Any] | None:
    if not book_profile:
        return None
    return _voice_payload(str(book_profile.get("narrator_voice_id") or ""), catalog)


def _duplicate_candidates(
    name: str | None,
    aliases: Iterable[str],
    registry: Mapping[str, Any],
) -> list[dict[str, Any]]:
    identities = {
        normalize_identity(value)
        for value in [name, *list(aliases)]
        if str(value or "").strip()
    }
    if not identities:
        return []
    duplicates: list[dict[str, Any]] = []
    for character in registry.get("characters") or []:
        if not isinstance(character, Mapping):
            continue
        values = [
            character.get("display_name"),
            character.get("canonical_name"),
            *(character.get("aliases") or []),
        ]
        if any(normalize_identity(value) in identities for value in values if value):
            duplicates.append(
                {
                    "character_id": int(character["id"]),
                    "display_name": character.get("display_name"),
                    "aliases": list(character.get("aliases") or []),
                }
            )
    return duplicates


def _context_for_target(
    text: str,
    utterances: list[Mapping[str, Any]],
    target_utterance_id: str,
    *,
    context_size: int,
) -> list[dict[str, Any]]:
    by_id = {str(item["utterance_id"]): index for index, item in enumerate(utterances)}
    if target_utterance_id not in by_id:
        raise SpeakerReviewSuggestionError(
            f"Unresolved target {target_utterance_id} no longer exists"
        )
    index = by_id[target_utterance_id]
    context: list[dict[str, Any]] = []
    for item in utterances[max(0, index - context_size) : index + context_size + 1]:
        context.append(
            {
                "utterance_id": str(item["utterance_id"]),
                "sequence": int(item["sequence"]),
                "text": text[int(item["start_offset"]) : int(item["end_offset"])],
                "is_target": str(item["utterance_id"]) == target_utterance_id,
            }
        )
    return context


def build_speaker_review_request(
    db: Database,
    store: ContentStore,
    config: Settings,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    skip_completed: bool,
    registry: Mapping[str, Any],
    voice_catalog: EffectiveVoiceCatalog,
    unresolved_keys: Iterable[str] | None = None,
) -> dict[str, Any]:
    book = _book_row(db, book_id)
    chapters = _active_chapters(
        db,
        book_id=book_id,
        from_chapter=from_chapter,
        to_chapter=to_chapter,
        skip_completed=skip_completed,
    )
    chapters_by_id = {int(chapter["id"]): chapter for chapter in chapters}
    requested_keys = [str(item).strip() for item in (unresolved_keys or []) if str(item).strip()]
    requested_set = set(requested_keys)
    revision_payloads: list[dict[str, Any]] = []
    text_by_chapter: dict[int, str] = {}
    utterances_by_chapter: dict[int, list[dict[str, Any]]] = {}
    for chapter in chapters:
        revision, text = _text_revision(db, store, chapter)
        text_by_chapter[int(chapter["id"])] = text
        utterances_by_chapter[int(chapter["id"])] = split_utterances(
            text,
            maximum=config.tts_max_chars,
        )
        revision_payloads.append(
            {
                "chapter_id": int(chapter["id"]),
                "chapter_number": int(chapter["chapter_number"]),
                "text_revision_id": int(revision["id"]),
                "text_revision_sha256": str(revision["content_sha256"]),
            }
        )
    targets: list[dict[str, Any]] = []
    for row in registry.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("status") or "") != UNRESOLVED_DIALOGUE_STATUS:
            continue
        speaker_key = str(row.get("speaker_key") or "")
        if requested_set and speaker_key not in requested_set:
            continue
        target_rows = [
            item for item in row.get("target_utterances") or [] if isinstance(item, Mapping)
        ]
        if not target_rows:
            continue
        target = target_rows[0]
        chapter_id = int(target["chapter_id"])
        if chapter_id not in chapters_by_id:
            continue
        utterance_id = str(target["utterance_id"])
        context = _context_for_target(
            text_by_chapter[chapter_id],
            utterances_by_chapter[chapter_id],
            utterance_id,
            context_size=config.speaker_assignment_context_size,
        )
        target_text = str(target.get("text") or "")
        targets.append(
            {
                "unresolved_key": speaker_key,
                "chapter_id": chapter_id,
                "chapter_number": int(target["chapter_number"]),
                "utterance_id": utterance_id,
                "sequence": int(target.get("sequence") or 0),
                "dialogue_text": target_text,
                "dialogue_text_sha256": sha256_text(target_text),
                "context": context,
                "current_speaker_annotation": {
                    "role": target.get("role") or "narrator",
                    "character_id": target.get("character_id"),
                    "registry_status": row.get("status"),
                },
            }
        )
    if requested_keys:
        found = {item["unresolved_key"] for item in targets}
        missing = [item for item in requested_keys if item not in found]
        if missing:
            raise SpeakerReviewSuggestionError(f"Unresolved key not found: {missing[0]}")
    targets.sort(key=lambda item: (int(item["chapter_number"]), int(item["sequence"]), item["unresolved_key"]))
    if not targets:
        raise SpeakerReviewSuggestionError("No unresolved dialogue targets in this scope")
    target_keys = [item["unresolved_key"] for item in targets]
    if len(target_keys) != len(set(target_keys)):
        raise SpeakerReviewSuggestionError("Unresolved targets are not unique")
    voice_catalog_payload = [
        {
            "assignment_key": item.get("assignment_key"),
            "display_name": item.get("display_name"),
            "source_kind": item.get("source_kind"),
            "selectable": bool(item.get("selectable")),
        }
        for item in voice_catalog.items
    ]
    book_profile = get_book_voice_profile(db, book_id)
    identity = {
        "book_id": int(book_id),
        "book_title": book["title"],
        "from_chapter": int(from_chapter),
        "to_chapter": int(to_chapter),
        "skip_completed": bool(skip_completed),
        "effective_chapter_ids": [int(chapter["id"]) for chapter in chapters],
        "text_revisions": revision_payloads,
        "target_keys": target_keys,
        "target_text_sha256": [
            {"unresolved_key": item["unresolved_key"], "sha256": item["dialogue_text_sha256"]}
            for item in targets
        ],
        "utterance_chunker": CHUNKER_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model_id": config.gemini_model,
        "generation_settings": GENERATION_SETTINGS,
        "response_schema": SUGGESTION_SCHEMA,
    }
    return {
        "schema": REQUEST_SCHEMA,
        "identity": identity,
        "input_fingerprint": sha256_text(canonical_json(identity)),
        "scope": {
            "book_id": int(book_id),
            "book_title": book["title"],
            "from_chapter": int(from_chapter),
            "to_chapter": int(to_chapter),
            "skip_completed": bool(skip_completed),
            "effective_from_chapter": int(chapters[0]["chapter_number"]),
            "effective_to_chapter": int(chapters[-1]["chapter_number"]),
            "effective_chapter_count": len(chapters),
        },
        "book": {"id": int(book["id"]), "title": book["title"]},
        "text_revisions": revision_payloads,
        "known_characters": list(registry.get("characters") or []),
        "voice_configuration": {
            "book_voice_profile": dict(book_profile) if book_profile else None,
            "voice_catalog": voice_catalog_payload,
            "narrator_voice_id": (
                str(book_profile.get("narrator_voice_id") or "") if book_profile else None
            ),
        },
        "previously_approved_speaker_rows": [
            {
                "speaker_key": item.get("speaker_key"),
                "character_id": item.get("character_id"),
                "display_name": item.get("display_name"),
                "aliases": item.get("aliases") or [],
                "chapter_numbers": item.get("chapter_numbers") or [],
                "line_count": item.get("line_count") or 0,
            }
            for item in registry.get("rows") or []
            if isinstance(item, Mapping) and item.get("character_id") is not None
        ],
        "targets": targets,
    }


def _string_list(value: Any, *, field: str, maximum: int = 8) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise SpeakerReviewSuggestionError(f"{field} must be a short list")
    result = []
    for item in value:
        if not isinstance(item, str):
            raise SpeakerReviewSuggestionError(f"{field} contains a non-string value")
        cleaned = " ".join(item.strip().split())
        if cleaned:
            result.append(cleaned[:600])
    return result


def _optional_string(value: Any, *, maximum: int = 240) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SpeakerReviewSuggestionError("optional string field is invalid")
    cleaned = " ".join(value.strip().split())
    return cleaned[:maximum] if cleaned else None


def _validate_alternatives(value: Any, allowed_character_ids: set[int]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 5:
        raise SpeakerReviewSuggestionError("alternative_candidates is invalid")
    alternatives: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise SpeakerReviewSuggestionError("alternative candidate is invalid")
        resolution = str(item.get("resolution") or "").strip().upper()
        if resolution not in RESOLUTIONS:
            raise SpeakerReviewSuggestionError("alternative resolution is invalid")
        character_id = item.get("character_id")
        if resolution == "EXISTING_CHARACTER":
            if isinstance(character_id, bool) or not isinstance(character_id, int):
                raise SpeakerReviewSuggestionError("alternative character_id is invalid")
            if character_id not in allowed_character_ids:
                raise SpeakerReviewSuggestionError("alternative character_id is not in this book")
        elif character_id is not None:
            raise SpeakerReviewSuggestionError("alternative character_id must be null")
        score = item.get("confidence_score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= float(score) <= 1:
            raise SpeakerReviewSuggestionError("alternative confidence_score is invalid")
        alternatives.append(
            {
                "resolution": resolution,
                "character_id": character_id if resolution == "EXISTING_CHARACTER" else None,
                "character_name": _optional_string(item.get("character_name"), maximum=120),
                "confidence_score": float(score),
                "note": _optional_string(item.get("note"), maximum=240) or "",
            }
        )
    return alternatives


def validate_speaker_review_response(
    payload: Mapping[str, Any],
    *,
    target_keys: list[str],
    target_chapter_numbers_by_key: Mapping[str, int] | None = None,
    allowed_character_ids: set[int],
    selectable_voice_ids: set[str],
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise SpeakerReviewSuggestionError("Gemini response is not an object")
    if set(payload) != {"schema", "suggestions"}:
        raise SpeakerReviewSuggestionError("Gemini response top-level fields are invalid")
    if payload.get("schema") != SUGGESTION_SCHEMA:
        raise SpeakerReviewSuggestionError("Gemini response schema is invalid")
    raw_suggestions = payload.get("suggestions")
    if not isinstance(raw_suggestions, list):
        raise SpeakerReviewSuggestionError("Gemini suggestions must be a list")
    target_set = set(target_keys)
    target_chapter_numbers = {
        str(key): int(value)
        for key, value in (target_chapter_numbers_by_key or {}).items()
    }
    seen: set[str] = set()
    suggestions: list[dict[str, Any]] = []
    for item in raw_suggestions:
        if not isinstance(item, Mapping):
            raise SpeakerReviewSuggestionError("Suggestion item is invalid")
        required = {
            "unresolved_key",
            "chapter_number",
            "proposed_resolution",
            "existing_character_id",
            "proposed_character_name",
            "proposed_aliases",
            "confidence",
            "confidence_score",
            "evidence_summary",
            "context_evidence",
            "alternative_candidates",
            "continuity_notes",
            "proposed_voice_handling",
            "suggested_voice_id",
            "voice_rationale",
            "warnings",
        }
        if set(item) != required:
            raise SpeakerReviewSuggestionError("Suggestion fields are invalid")
        unresolved_key = str(item.get("unresolved_key") or "").strip()
        if unresolved_key not in target_set or unresolved_key in seen:
            raise SpeakerReviewSuggestionError("Suggestion unresolved_key is unknown or duplicated")
        chapter_number = item.get("chapter_number")
        if isinstance(chapter_number, bool) or not isinstance(chapter_number, int):
            raise SpeakerReviewSuggestionError("chapter_number is required")
        if (
            unresolved_key in target_chapter_numbers
            and int(chapter_number) != target_chapter_numbers[unresolved_key]
        ):
            raise SpeakerReviewSuggestionError("chapter_number does not match unresolved target")
        resolution = str(item.get("proposed_resolution") or "").strip().upper()
        if resolution not in RESOLUTIONS:
            raise SpeakerReviewSuggestionError("Suggestion resolution is invalid")
        existing_character_id = item.get("existing_character_id")
        warnings = _string_list(item.get("warnings"), field="warnings", maximum=8)
        if resolution == "EXISTING_CHARACTER":
            if existing_character_id is None:
                warnings.append("existing_character_id is missing; human decision required.")
                resolution = "NEEDS_HUMAN_DECISION"
            else:
                if isinstance(existing_character_id, bool) or not isinstance(existing_character_id, int):
                    raise SpeakerReviewSuggestionError("existing_character_id is required")
                if existing_character_id not in allowed_character_ids:
                    raise SpeakerReviewSuggestionError("existing_character_id is not in this book")
        elif existing_character_id is not None:
            raise SpeakerReviewSuggestionError("existing_character_id must be null")
        character_name = _optional_string(item.get("proposed_character_name"), maximum=120)
        if resolution == "NEW_CHARACTER" and not character_name:
            raise SpeakerReviewSuggestionError("proposed_character_name is required")
        aliases = _string_list(item.get("proposed_aliases"), field="proposed_aliases", maximum=8)
        confidence = str(item.get("confidence") or "").strip().upper()
        if confidence not in {"HIGH", "MEDIUM", "LOW"}:
            raise SpeakerReviewSuggestionError("confidence is invalid")
        confidence_score = item.get("confidence_score")
        if (
            isinstance(confidence_score, bool)
            or not isinstance(confidence_score, (int, float))
            or not 0 <= float(confidence_score) <= 1
        ):
            raise SpeakerReviewSuggestionError("confidence_score is invalid")
        evidence = _optional_string(item.get("evidence_summary"), maximum=500)
        if not evidence:
            raise SpeakerReviewSuggestionError("evidence_summary is required")
        voice_handling = str(item.get("proposed_voice_handling") or "").strip().upper()
        if voice_handling not in VOICE_HANDLING:
            raise SpeakerReviewSuggestionError("proposed_voice_handling is invalid")
        suggested_voice_id = _optional_string(item.get("suggested_voice_id"), maximum=200)
        if voice_handling == "SUGGEST_AVAILABLE_VOICE":
            if not suggested_voice_id or suggested_voice_id not in selectable_voice_ids:
                raise SpeakerReviewSuggestionError("suggested_voice_id is not selectable")
        elif suggested_voice_id and suggested_voice_id not in selectable_voice_ids:
            raise SpeakerReviewSuggestionError("suggested_voice_id is not selectable")
        suggestions.append(
            {
                "unresolved_key": unresolved_key,
                "chapter_number": int(chapter_number),
                "proposed_resolution": resolution,
                "existing_character_id": (
                    int(existing_character_id) if resolution == "EXISTING_CHARACTER" else None
                ),
                "proposed_character_name": character_name,
                "proposed_aliases": aliases,
                "confidence": confidence,
                "confidence_score": float(confidence_score),
                "evidence_summary": evidence,
                "context_evidence": _string_list(
                    item.get("context_evidence"),
                    field="context_evidence",
                    maximum=8,
                ),
                "alternative_candidates": _validate_alternatives(
                    item.get("alternative_candidates"), allowed_character_ids
                ),
                "continuity_notes": _optional_string(
                    item.get("continuity_notes"),
                    maximum=500,
                )
                or "",
                "proposed_voice_handling": voice_handling,
                "suggested_voice_id": suggested_voice_id,
                "voice_rationale": _optional_string(item.get("voice_rationale"), maximum=400) or "",
                "warnings": warnings,
            }
        )
        seen.add(unresolved_key)
    missing = [key for key in target_keys if key not in seen]
    if missing:
        raise SpeakerReviewSuggestionError(f"missing suggestion for {missing[0]}")
    suggestions.sort(key=lambda item: target_keys.index(item["unresolved_key"]))
    return {"schema": SUGGESTION_SCHEMA, "suggestions": suggestions}


def _provider_payload(request: Mapping[str, Any], targets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": REQUEST_SCHEMA,
        "scope": request["scope"],
        "book": request["book"],
        "known_characters": request["known_characters"],
        "previously_approved_speaker_rows": request["previously_approved_speaker_rows"],
        "voice_configuration": request["voice_configuration"],
        "target_unresolved_keys": [item["unresolved_key"] for item in targets],
        "targets": targets,
    }


def _provider_response(value: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(value, Mapping) and isinstance(value.get("response"), Mapping):
        return dict(value["response"]), dict(value.get("usage_metadata") or {})
    return dict(value), {}


def _latest_run_event(
    db: Database,
    *,
    input_fingerprint: str,
) -> dict[str, Any] | None:
    rows = db.fetch_all(
        """
        SELECT *
        FROM audit_events
        WHERE event_code=?
        ORDER BY id DESC
        """,
        (ANALYSIS_EVENT,),
    )
    for row in rows:
        try:
            details = json.loads(row["details_json"] or "{}")
        except (TypeError, ValueError):
            continue
        if details.get("input_fingerprint") == input_fingerprint:
            return {**dict(row), "details": details}
    return None


def _decision_events(db: Database, *, analysis_run_id: str) -> list[dict[str, Any]]:
    rows = db.fetch_all(
        """
        SELECT *
        FROM audit_events
        WHERE event_code=?
        ORDER BY id
        """,
        (DECISION_EVENT,),
    )
    events: list[dict[str, Any]] = []
    for row in rows:
        try:
            details = json.loads(row["details_json"] or "{}")
        except (TypeError, ValueError):
            continue
        if details.get("analysis_run_id") != analysis_run_id:
            continue
        events.append({**dict(row), "details": details})
    return events


def _load_run_from_event(store: ContentStore, event: Mapping[str, Any]) -> dict[str, Any]:
    details = dict(event.get("details") or {})
    payload = store.read_json(str(details["content_path"]))
    if sha256_text(canonical_json(payload)) != str(details["content_sha256"]):
        raise SpeakerReviewSuggestionError("Stored speaker suggestion run hash mismatch")
    return payload


def _clean_queue_state(db: Database, payload: dict[str, Any]) -> dict[str, Any]:
    decisions = {
        str(event["details"].get("unresolved_key")): dict(event["details"])
        for event in _decision_events(db, analysis_run_id=str(payload["analysis_run_id"]))
    }
    for item in payload.get("suggestions") or []:
        decision = decisions.get(str(item.get("unresolved_key")))
        item["review_state"] = (
            str(decision.get("decision") or "PENDING_REVIEW")
            if decision
            else "PENDING_REVIEW"
        )
        item["human_review"] = decision or None
    summary = _queue_summary(payload.get("suggestions") or [])
    payload["summary"] = {**dict(payload.get("summary") or {}), **summary}
    return payload


def _queue_summary(suggestions: list[Mapping[str, Any]]) -> dict[str, Any]:
    counts = {
        "total": len(suggestions),
        "high_confidence": 0,
        "medium_confidence": 0,
        "low_confidence": 0,
        "existing_character_matches": 0,
        "proposed_new_characters": 0,
        "narrator_proposals": 0,
        "still_unresolved": 0,
        "inherited_voice": 0,
        "suggested_new_voice": 0,
        "approved": 0,
        "deferred": 0,
    }
    for item in suggestions:
        confidence = str(item.get("confidence") or "").upper()
        if confidence == "HIGH":
            counts["high_confidence"] += 1
        elif confidence == "MEDIUM":
            counts["medium_confidence"] += 1
        elif confidence == "LOW":
            counts["low_confidence"] += 1
        resolution = str(item.get("proposed_resolution") or "")
        if resolution == "EXISTING_CHARACTER":
            counts["existing_character_matches"] += 1
        elif resolution == "NEW_CHARACTER":
            counts["proposed_new_characters"] += 1
        elif resolution == "NARRATOR":
            counts["narrator_proposals"] += 1
        elif resolution in {"UNKNOWN_SPEAKER", "NEEDS_HUMAN_DECISION"}:
            counts["still_unresolved"] += 1
        voice_handling = str(item.get("proposed_voice_handling") or "")
        if voice_handling in {"INHERIT_EXISTING_CONFIGURATION", "USE_BOOK_DEFAULT"}:
            counts["inherited_voice"] += 1
        elif voice_handling == "SUGGEST_AVAILABLE_VOICE":
            counts["suggested_new_voice"] += 1
        review_state = str(item.get("review_state") or "")
        if review_state in {"ACCEPTED", "EDITED_AND_ACCEPTED"}:
            counts["approved"] += 1
        elif review_state == "DEFERRED":
            counts["deferred"] += 1
    return counts


def _augment_suggestions(
    suggestions: list[dict[str, Any]],
    *,
    db: Database,
    request: Mapping[str, Any],
    registry: Mapping[str, Any],
    voice_catalog: EffectiveVoiceCatalog,
    custom_voice_context: CustomVoiceContext | None,
) -> list[dict[str, Any]]:
    book_profile = dict(request["voice_configuration"].get("book_voice_profile") or {})
    by_key = {item["unresolved_key"]: item for item in request["targets"]}
    characters = _characters_by_id(registry)
    augmented: list[dict[str, Any]] = []
    for item in suggestions:
        target = by_key.get(str(item["unresolved_key"])) or {}
        proposal = dict(item)
        resolution = str(proposal.get("proposed_resolution") or "")
        inherited_voice = None
        voice_source = "Chưa có giọng"
        if resolution == "EXISTING_CHARACTER" and proposal.get("existing_character_id") is not None:
            inherited_voice, voice_source = _character_voice(
                db=db,
                registry=registry,
                character_id=int(proposal["existing_character_id"]),
                book_profile=book_profile,
                catalog=voice_catalog,
                custom_voice_context=custom_voice_context,
            )
        elif resolution == "NARRATOR":
            inherited_voice = _narrator_voice(book_profile=book_profile, catalog=voice_catalog)
            voice_source = "Mặc định của sách"
        suggested_voice = _voice_payload(proposal.get("suggested_voice_id"), voice_catalog)
        duplicate_candidates = (
            _duplicate_candidates(
                proposal.get("proposed_character_name"),
                proposal.get("proposed_aliases") or [],
                registry,
            )
            if resolution == "NEW_CHARACTER"
            else []
        )
        if duplicate_candidates:
            proposal["warnings"] = [
                *list(proposal.get("warnings") or []),
                "Tên hoặc alias giống nhân vật đã có; cần duyệt thủ công.",
            ]
        proposal.update(
            {
                "target": target,
                "matched_character": (
                    characters.get(int(proposal["existing_character_id"]))
                    if proposal.get("existing_character_id") is not None
                    else None
                ),
                "effective_inherited_voice": inherited_voice,
                "effective_voice_source": voice_source,
                "suggested_voice": suggested_voice,
                "possible_duplicates": duplicate_candidates,
                "review_state": proposal.get("review_state") or "PENDING_REVIEW",
                "approval_eligible": (
                    proposal.get("confidence") == "HIGH"
                    and resolution in {"EXISTING_CHARACTER", "NEW_CHARACTER", "NARRATOR"}
                    and not duplicate_candidates
                    and not proposal.get("warnings")
                ),
            }
        )
        augmented.append(proposal)
    return augmented


def generate_speaker_review_suggestions(
    db: Database,
    store: ContentStore,
    config: Settings,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    skip_completed: bool,
    registry: Mapping[str, Any],
    voice_catalog: EffectiveVoiceCatalog,
    custom_voice_context: CustomVoiceContext | None = None,
    unresolved_keys: Iterable[str] | None = None,
    force_refresh: bool = False,
    expected_input_fingerprint: str | None = None,
    provider: Callable[..., dict[str, Any]] = suggest_speaker_review,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    request = build_speaker_review_request(
        db,
        store,
        config,
        book_id=book_id,
        from_chapter=from_chapter,
        to_chapter=to_chapter,
        skip_completed=skip_completed,
        registry=registry,
        voice_catalog=voice_catalog,
        unresolved_keys=unresolved_keys,
    )
    if (
        expected_input_fingerprint
        and str(expected_input_fingerprint).strip() != request["input_fingerprint"]
    ):
        raise SpeakerReviewSuggestionError("Speaker suggestion input is stale")
    existing_event = _latest_run_event(db, input_fingerprint=request["input_fingerprint"])
    if existing_event and not force_refresh:
        payload = _load_run_from_event(store, existing_event)
        payload = _clean_queue_state(db, payload)
        payload["reused"] = True
        return payload

    cache = GeminiRepairCache(store, config)
    allowed_character_ids = {
        int(item["id"])
        for item in request.get("known_characters") or []
        if isinstance(item, Mapping) and item.get("id") is not None
    }
    selectable_voice_ids = set(voice_catalog.selectable_ids)
    suggestions: list[dict[str, Any]] = []
    failed_chunks: list[dict[str, Any]] = []
    usage_metadata: list[dict[str, Any]] = []
    cache_hits = cache_misses = request_count = 0
    targets = list(request["targets"])
    chunk_size = max(1, int(config.speaker_assignment_batch_size))
    try:
        for offset in range(0, len(targets), chunk_size):
            batch = targets[offset : offset + chunk_size]
            batch_request = _provider_payload(request, batch)
            batch_fingerprint = sha256_text(
                canonical_json(
                    {
                        "request_input_fingerprint": request["input_fingerprint"],
                        "batch": batch_request,
                    }
                )
            )
            identity = cache.json_identity(
                task_kind="speaker_review_suggestion",
                input_fingerprint=batch_fingerprint,
                model=config.gemini_model,
                prompt_version=PROMPT_VERSION,
                response_schema=SUGGESTION_SCHEMA,
                settings=GENERATION_SETTINGS,
            )
            lookup = cache.lookup_json(identity) if not force_refresh else None
            if lookup and lookup.status == "hit":
                raw_response = lookup.payload or {}
                usage = {}
                cache_hits += 1
            else:
                api_key = config.gemini_key()
                if not api_key:
                    raise SpeakerReviewSuggestionError("Gemini API key is not configured")
                request_count += 1
                raw_response, usage = _provider_response(
                    provider(
                        api_key=api_key,
                        model=config.gemini_model,
                        request_data=batch_request,
                    )
                )
                cache.store_json(identity, raw_response)
                cache_misses += 1
            validated = validate_speaker_review_response(
                raw_response,
                target_keys=[item["unresolved_key"] for item in batch],
                target_chapter_numbers_by_key={
                    item["unresolved_key"]: int(item["chapter_number"])
                    for item in batch
                },
                allowed_character_ids=allowed_character_ids,
                selectable_voice_ids=selectable_voice_ids,
            )
            suggestions.extend(validated["suggestions"])
            usage_metadata.append(dict(usage or {}))
    except Exception as exc:
        details = {
            "schema": RUN_SCHEMA,
            "status": "failed",
            "input_fingerprint": request["input_fingerprint"],
            "scope": request["scope"],
            "error": str(exc),
            "idempotency_key": idempotency_key,
        }
        db.audit(
            ANALYSIS_FAILED_EVENT,
            chapter_id=int(targets[0]["chapter_id"]) if targets else None,
            details=details,
        )
        raise

    suggestions = _augment_suggestions(
        suggestions,
        db=db,
        request=request,
        registry=registry,
        voice_catalog=voice_catalog,
        custom_voice_context=custom_voice_context,
    )
    analysis_run_id = "gsr-" + sha256_text(
        canonical_json(
            {
                "input_fingerprint": request["input_fingerprint"],
                "suggestions": suggestions,
            }
        )
    )[:24]
    payload = {
        "schema": RUN_SCHEMA,
        "analysis_run_id": analysis_run_id,
        "status": "ready_for_human_review",
        "input_fingerprint": request["input_fingerprint"],
        "request_schema": REQUEST_SCHEMA,
        "suggestion_schema": SUGGESTION_SCHEMA,
        "prompt_version": PROMPT_VERSION,
        "model_id": config.gemini_model,
        "scope": request["scope"],
        "book": request["book"],
        "text_revisions": request["text_revisions"],
        "target_count": len(targets),
        "chunk_count": (len(targets) + chunk_size - 1) // chunk_size,
        "request_count": request_count,
        "cache_hit_count": cache_hits,
        "cache_miss_count": cache_misses,
        "provider_errors": failed_chunks,
        "usage_metadata": usage_metadata,
        "suggestions": suggestions,
        "created_at": utcnow(),
        "idempotency_key": idempotency_key,
    }
    payload["summary"] = _queue_summary(suggestions)
    content_path, content_sha = store.put_json(payload, namespace="speaker_review_suggestions")
    details = {
        "schema": RUN_SCHEMA,
        "analysis_run_id": analysis_run_id,
        "status": payload["status"],
        "input_fingerprint": request["input_fingerprint"],
        "content_path": content_path,
        "content_sha256": content_sha,
        "scope": request["scope"],
        "target_count": len(targets),
        "chunk_count": payload["chunk_count"],
        "request_count": request_count,
        "cache_hit_count": cache_hits,
        "cache_miss_count": cache_misses,
        "idempotency_key": idempotency_key,
    }
    with db.transaction() as connection:
        duplicate = connection.execute(
            """
            SELECT details_json
            FROM audit_events
            WHERE event_code=?
            ORDER BY id DESC
            """,
            (ANALYSIS_EVENT,),
        ).fetchall()
        for row in duplicate:
            try:
                existing = json.loads(row["details_json"] or "{}")
            except (TypeError, ValueError):
                continue
            if existing.get("input_fingerprint") == request["input_fingerprint"]:
                existing_event = {"details": existing}
                reused_payload = _load_run_from_event(store, existing_event)
                reused_payload = _clean_queue_state(db, reused_payload)
                reused_payload["reused"] = True
                return reused_payload
        connection.execute(
            """
            INSERT INTO audit_events(event_code,job_id,chapter_id,details_json,created_at)
            VALUES(?,?,?,?,?)
            """,
            (
                ANALYSIS_EVENT,
                None,
                int(targets[0]["chapter_id"]) if targets else None,
                json.dumps(details, ensure_ascii=False),
                utcnow(),
            ),
        )
    payload["content_path"] = content_path
    payload["content_sha256"] = content_sha
    payload["reused"] = False
    return payload


def get_speaker_review_queue(
    db: Database,
    store: ContentStore,
    config: Settings,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    skip_completed: bool,
    registry: Mapping[str, Any],
    voice_catalog: EffectiveVoiceCatalog,
    custom_voice_context: CustomVoiceContext | None = None,
    unresolved_keys: Iterable[str] | None = None,
) -> dict[str, Any]:
    request = build_speaker_review_request(
        db,
        store,
        config,
        book_id=book_id,
        from_chapter=from_chapter,
        to_chapter=to_chapter,
        skip_completed=skip_completed,
        registry=registry,
        voice_catalog=voice_catalog,
        unresolved_keys=unresolved_keys,
    )
    event = _latest_run_event(db, input_fingerprint=request["input_fingerprint"])
    if not event:
        return {
            "schema": QUEUE_SCHEMA,
            "status": "not_analyzed",
            "input_fingerprint": request["input_fingerprint"],
            "scope": request["scope"],
            "book": request["book"],
            "target_count": len(request["targets"]),
            "targets": request["targets"],
            "suggestions": [],
            "summary": {
                "total": 0,
                "analyzed": 0,
                "pending_review": len(request["targets"]),
            },
        }
    payload = _load_run_from_event(store, event)
    payload = _clean_queue_state(db, payload)
    payload["schema"] = QUEUE_SCHEMA
    payload["status"] = "ready_for_human_review"
    payload["suggestions"] = _augment_suggestions(
        [dict(item) for item in payload.get("suggestions") or []],
        db=db,
        request=request,
        registry=registry,
        voice_catalog=voice_catalog,
        custom_voice_context=custom_voice_context,
    )
    payload["summary"] = {
        **_queue_summary(payload["suggestions"]),
        "analyzed": len(payload["suggestions"]),
        "pending_review": sum(
            1
            for item in payload["suggestions"]
            if str(item.get("review_state")) == "PENDING_REVIEW"
        ),
    }
    return payload


def _latest_queue_for_run(
    db: Database,
    store: ContentStore,
    *,
    analysis_run_id: str,
) -> dict[str, Any]:
    rows = db.fetch_all(
        """
        SELECT *
        FROM audit_events
        WHERE event_code=?
        ORDER BY id DESC
        """,
        (ANALYSIS_EVENT,),
    )
    for row in rows:
        try:
            details = json.loads(row["details_json"] or "{}")
        except (TypeError, ValueError):
            continue
        if details.get("analysis_run_id") == analysis_run_id:
            payload = _load_run_from_event(store, {"details": details})
            return _clean_queue_state(db, payload)
    raise SpeakerReviewSuggestionError("Speaker review analysis run was not found")


def record_speaker_suggestion_decision(
    db: Database,
    store: ContentStore,
    *,
    analysis_run_id: str,
    unresolved_key: str,
    decision: str,
    reviewer_payload: Mapping[str, Any],
    idempotency_key: str,
) -> dict[str, Any]:
    normalized_decision = str(decision or "").strip().upper()
    if normalized_decision not in DECISIONS:
        raise SpeakerReviewSuggestionError("Unsupported speaker suggestion decision")
    payload = _latest_queue_for_run(db, store, analysis_run_id=analysis_run_id)
    suggestion = next(
        (
            item
            for item in payload.get("suggestions") or []
            if str(item.get("unresolved_key")) == str(unresolved_key)
        ),
        None,
    )
    if not suggestion:
        raise SpeakerReviewSuggestionError("Speaker suggestion target was not found")
    existing = next(
        (
            event
            for event in _decision_events(db, analysis_run_id=analysis_run_id)
            if event["details"].get("idempotency_key") == idempotency_key
        ),
        None,
    )
    if existing:
        return {"reused": True, "decision": existing["details"]}
    details = {
        "schema": QUEUE_SCHEMA,
        "analysis_run_id": analysis_run_id,
        "unresolved_key": unresolved_key,
        "decision": normalized_decision,
        "reviewer_payload": dict(reviewer_payload),
        "source_suggestion": suggestion,
        "idempotency_key": idempotency_key,
    }
    db.audit(
        DECISION_EVENT,
        chapter_id=int((suggestion.get("target") or {}).get("chapter_id") or 0) or None,
        details=details,
    )
    return {"reused": False, "decision": details}


def accept_speaker_review_suggestion(
    db: Database,
    store: ContentStore,
    config: Settings,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    analysis_run_id: str,
    unresolved_key: str,
    reviewer_payload: Mapping[str, Any],
    voice_catalog: EffectiveVoiceCatalog,
    custom_voice_context: CustomVoiceContext | None = None,
    idempotency_key: str,
) -> dict[str, Any]:
    payload = _latest_queue_for_run(db, store, analysis_run_id=analysis_run_id)
    suggestion = next(
        (
            item
            for item in payload.get("suggestions") or []
            if str(item.get("unresolved_key")) == str(unresolved_key)
        ),
        None,
    )
    if not suggestion:
        raise SpeakerReviewSuggestionError("Speaker suggestion target was not found")
    resolution = str(
        reviewer_payload.get("proposed_resolution")
        or suggestion.get("proposed_resolution")
        or ""
    ).upper()
    aliases = [
        str(item).strip()
        for item in (
            reviewer_payload.get("proposed_aliases")
            if "proposed_aliases" in reviewer_payload
            else suggestion.get("proposed_aliases") or []
        )
        if str(item).strip()
    ]
    applied: dict[str, Any]
    if resolution == "EXISTING_CHARACTER":
        character_id = reviewer_payload.get("existing_character_id") or suggestion.get("existing_character_id")
        if isinstance(character_id, bool) or not isinstance(character_id, int) or int(character_id) <= 0:
            raise SpeakerReviewSuggestionError("existing_character_id is required")
        character_id = int(character_id)
        applied = apply_speaker_character_mapping(
            db,
            store,
            book_id=book_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
            speaker_key=unresolved_key,
            character_id=character_id,
            aliases=aliases,
            voice_catalog=voice_catalog,
            idempotency_key=idempotency_key,
            custom_voice_context=custom_voice_context,
        )
    elif resolution == "NEW_CHARACTER":
        name = str(
            reviewer_payload.get("proposed_character_name")
            or suggestion.get("proposed_character_name")
            or ""
        ).strip()
        created = create_assignment_character(
            db,
            book_id=book_id,
            display_name=name,
            aliases=aliases,
            gender=str(reviewer_payload.get("gender") or "unknown"),
            role=str(reviewer_payload.get("role") or "unknown"),
            idempotency_key=f"{idempotency_key}:character",
        )
        character_id = int(created["character"]["id"])
        voice_id = str(reviewer_payload.get("suggested_voice_id") or "").strip()
        if voice_id:
            set_character_voice_override(
                db,
                character_id,
                voice_id,
                allowed_voice_ids=set(voice_catalog.selectable_ids),
                custom_voice_context=custom_voice_context,
            )
        applied = apply_speaker_character_mapping(
            db,
            store,
            book_id=book_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
            speaker_key=unresolved_key,
            character_id=character_id,
            aliases=[],
            voice_catalog=voice_catalog,
            idempotency_key=f"{idempotency_key}:mapping",
            custom_voice_context=custom_voice_context,
        )
        applied["created_character"] = created
    elif resolution == "NARRATOR":
        applied = clear_speaker_character_mapping(
            db,
            store,
            book_id=book_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
            speaker_key=unresolved_key,
            voice_catalog=voice_catalog,
            idempotency_key=idempotency_key,
            custom_voice_context=custom_voice_context,
        )
    else:
        raise SpeakerReviewSuggestionError("This suggestion requires manual deferral, not approval")
    review = record_speaker_suggestion_decision(
        db,
        store,
        analysis_run_id=analysis_run_id,
        unresolved_key=unresolved_key,
        decision=(
            "EDITED_AND_ACCEPTED"
            if reviewer_payload and dict(reviewer_payload) != suggestion
            else "ACCEPTED"
        ),
        reviewer_payload=reviewer_payload,
        idempotency_key=idempotency_key,
    )
    return {"applied": applied, "review": review}


def approve_high_confidence_suggestions(
    db: Database,
    store: ContentStore,
    config: Settings,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    analysis_run_id: str,
    unresolved_keys: Iterable[str],
    voice_catalog: EffectiveVoiceCatalog,
    custom_voice_context: CustomVoiceContext | None = None,
    idempotency_key: str,
) -> dict[str, Any]:
    payload = _latest_queue_for_run(db, store, analysis_run_id=analysis_run_id)
    keys = [str(item).strip() for item in unresolved_keys if str(item).strip()]
    if not keys:
        raise SpeakerReviewSuggestionError("No suggestions selected for batch approval")
    suggestions = {
        str(item.get("unresolved_key")): item
        for item in payload.get("suggestions") or []
    }
    for key in keys:
        suggestion = suggestions.get(key)
        if not suggestion:
            raise SpeakerReviewSuggestionError(f"Suggestion not found: {key}")
        if suggestion.get("confidence") != "HIGH":
            raise SpeakerReviewSuggestionError("Only HIGH-confidence suggestions can be batch approved")
        if not suggestion.get("approval_eligible", True):
            raise SpeakerReviewSuggestionError("A selected suggestion requires individual review")
        if suggestion.get("proposed_resolution") not in {"EXISTING_CHARACTER", "NARRATOR"}:
            raise SpeakerReviewSuggestionError(
                "Batch approval is limited to existing-character or narrator suggestions"
            )
    applied = []
    for key in keys:
        applied.append(
            accept_speaker_review_suggestion(
                db,
                store,
                config,
                book_id=book_id,
                from_chapter=from_chapter,
                to_chapter=to_chapter,
                analysis_run_id=analysis_run_id,
                unresolved_key=key,
                reviewer_payload=suggestions[key],
                voice_catalog=voice_catalog,
                custom_voice_context=custom_voice_context,
                idempotency_key=f"{idempotency_key}:{key}",
            )
        )
    return {"applied": applied, "submitted_count": len(keys)}


__all__ = [
    "ANALYSIS_EVENT",
    "DECISION_EVENT",
    "QUEUE_SCHEMA",
    "REQUEST_SCHEMA",
    "RUN_SCHEMA",
    "SUGGESTION_SCHEMA",
    "SpeakerReviewSuggestionError",
    "accept_speaker_review_suggestion",
    "approve_high_confidence_suggestions",
    "build_speaker_review_request",
    "generate_speaker_review_suggestions",
    "get_speaker_review_queue",
    "record_speaker_suggestion_decision",
    "validate_speaker_review_response",
]
