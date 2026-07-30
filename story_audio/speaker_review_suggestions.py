from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .casting import CHUNKER_VERSION, split_utterances
from .chapter_voice_overrides import apply_chapter_voice_override
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
from .voice_profile import get_book_voice_profile, resolve_voice
from .voice_ref import CustomVoiceContext
from .speaker_review_workspace import (
    APPROVED_STATES,
    batch_exclusion_reasons,
    queue_view_counts,
)


REQUEST_SCHEMA = "story-audio-gemini-speaker-review-request/v1"
SUGGESTION_SCHEMA = "story-audio-gemini-speaker-review-suggestions/v1"
RUN_SCHEMA = "story-audio-gemini-speaker-review-run/v1"
QUEUE_SCHEMA = "story-audio-gemini-speaker-review-queue/v1"
ANALYSIS_EVENT = "speaker_review_analysis_generated"
ANALYSIS_FAILED_EVENT = "speaker_review_analysis_failed"
DECISION_EVENT = "speaker_review_suggestion_reviewed"
NOTE_EVENT = "speaker_review_suggestion_noted"
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
DECISIONS = {
    "ACCEPTED",
    "EDITED_AND_ACCEPTED",
    "CORRECTED",
    "DEFERRED",
    "ERROR",
    "MARKED_UNCERTAIN",
    "REPLACEMENT_DRAFT",
    "RESTORED_PENDING",
}


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


def _text_revision_signatures(payload: Mapping[str, Any]) -> dict[int, tuple[int, str]]:
    signatures: dict[int, tuple[int, str]] = {}
    for item in payload.get("text_revisions") or []:
        if not isinstance(item, Mapping):
            continue
        chapter_number = int(item.get("chapter_number") or 0)
        revision_id = int(item.get("text_revision_id") or 0)
        revision_sha = str(item.get("text_revision_sha256") or "")
        if chapter_number and revision_id and revision_sha:
            signatures[chapter_number] = (revision_id, revision_sha)
    return signatures


def _run_payload_matches_request_contract(
    payload: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    config: Settings,
) -> bool:
    if str(payload.get("schema") or "") != RUN_SCHEMA:
        return False
    if str(payload.get("request_schema") or "") != REQUEST_SCHEMA:
        return False
    if str(payload.get("suggestion_schema") or "") != SUGGESTION_SCHEMA:
        return False
    if str(payload.get("prompt_version") or "") != PROMPT_VERSION:
        return False
    if str(payload.get("model_id") or "") != str(config.gemini_model):
        return False
    if int((payload.get("book") or {}).get("id") or 0) != int((request.get("book") or {}).get("id") or 0):
        return False
    return True


def _suggestion_matches_current_target(
    suggestion: Mapping[str, Any],
    *,
    target: Mapping[str, Any],
    run_revisions: Mapping[int, tuple[int, str]],
    request_revisions: Mapping[int, tuple[int, str]],
) -> bool:
    chapter_number = int(suggestion.get("chapter_number") or 0)
    if chapter_number != int(target.get("chapter_number") or 0):
        return False
    if run_revisions.get(chapter_number) != request_revisions.get(chapter_number):
        return False
    source_target = suggestion.get("target") if isinstance(suggestion.get("target"), Mapping) else {}
    if source_target:
        if str(source_target.get("utterance_id") or "") != str(target.get("utterance_id") or ""):
            return False
        if int(source_target.get("chapter_id") or 0) != int(target.get("chapter_id") or 0):
            return False
        if str(source_target.get("dialogue_text_sha256") or "") != str(target.get("dialogue_text_sha256") or ""):
            return False
    return True


def _strip_runtime_projection_fields(suggestion: Mapping[str, Any]) -> dict[str, Any]:
    runtime_fields = {
        "target",
        "matched_character",
        "effective_inherited_voice",
        "effective_voice_source",
        "suggested_voice",
        "possible_duplicates",
        "approval_eligible",
    }
    return {key: value for key, value in dict(suggestion).items() if key not in runtime_fields}


def _combined_run_from_existing_events(
    db: Database,
    store: ContentStore,
    config: Settings,
    *,
    request: Mapping[str, Any],
) -> dict[str, Any] | None:
    targets = list(request.get("targets") or [])
    if not targets:
        return None
    target_by_key = {str(item["unresolved_key"]): item for item in targets}
    request_revisions = _text_revision_signatures(request)
    suggestions_by_key: dict[str, dict[str, Any]] = {}
    source_runs: dict[str, dict[str, Any]] = {}
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
        try:
            payload = _load_run_from_event(store, {"details": details})
        except SpeakerReviewSuggestionError:
            continue
        if not _run_payload_matches_request_contract(payload, request=request, config=config):
            continue
        run_revisions = _text_revision_signatures(payload)
        payload = _clean_queue_state(db, payload)
        analysis_run_id = str(payload.get("analysis_run_id") or "")
        for suggestion in payload.get("suggestions") or []:
            key = str(suggestion.get("unresolved_key") or "")
            target = target_by_key.get(key)
            if not target or key in suggestions_by_key:
                continue
            if not _suggestion_matches_current_target(
                suggestion,
                target=target,
                run_revisions=run_revisions,
                request_revisions=request_revisions,
            ):
                continue
            projected = _strip_runtime_projection_fields(suggestion)
            projected.update(
                {
                    "source_analysis_run_id": analysis_run_id,
                    "source_audit_event_id": int(row["id"]),
                    "source_input_fingerprint": payload.get("input_fingerprint"),
                    "source_content_sha256": details.get("content_sha256"),
                    "source_request_count": int(payload.get("request_count") or 0),
                    "source_cache_hit_count": int(payload.get("cache_hit_count") or 0),
                    "source_cache_miss_count": int(payload.get("cache_miss_count") or 0),
                }
            )
            suggestions_by_key[key] = projected
            source_runs.setdefault(
                analysis_run_id,
                {
                    "analysis_run_id": analysis_run_id,
                    "audit_event_id": int(row["id"]),
                    "input_fingerprint": payload.get("input_fingerprint"),
                    "target_count": int(payload.get("target_count") or 0),
                    "chunk_count": int(payload.get("chunk_count") or 0),
                    "request_count": int(payload.get("request_count") or 0),
                    "cache_hit_count": int(payload.get("cache_hit_count") or 0),
                    "cache_miss_count": int(payload.get("cache_miss_count") or 0),
                },
            )
    missing = [str(item["unresolved_key"]) for item in targets if str(item["unresolved_key"]) not in suggestions_by_key]
    if missing:
        return None
    ordered_suggestions = [suggestions_by_key[str(item["unresolved_key"])] for item in targets]
    source_list = sorted(source_runs.values(), key=lambda item: int(item["audit_event_id"]))
    return {
        "schema": RUN_SCHEMA,
        "analysis_run_id": "combined-" + sha256_text(
            canonical_json(
                {
                    "input_fingerprint": request["input_fingerprint"],
                    "source_runs": source_list,
                }
            )
        )[:24],
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
        "chunk_count": sum(int(item.get("chunk_count") or 0) for item in source_list),
        "request_count": sum(int(item.get("request_count") or 0) for item in source_list),
        "cache_hit_count": sum(int(item.get("cache_hit_count") or 0) for item in source_list),
        "cache_miss_count": sum(int(item.get("cache_miss_count") or 0) for item in source_list),
        "provider_errors": [],
        "usage_metadata": [],
        "suggestions": ordered_suggestions,
        "created_at": utcnow(),
        "idempotency_key": None,
        "combined_from_existing_runs": True,
        "source_runs": source_list,
    }


def _latest_compatible_run_for_request(
    db: Database,
    store: ContentStore,
    config: Settings,
    *,
    request: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Project a prior full queue when accepted mappings remove current targets."""

    requested_scope = dict(request.get("scope") or {})
    requested_revisions = _text_revision_signatures(request)
    current_targets = {
        str(item["unresolved_key"]): item
        for item in request.get("targets") or []
    }
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
        try:
            payload = _load_run_from_event(store, {"details": details})
        except SpeakerReviewSuggestionError:
            continue
        if not _run_payload_matches_request_contract(
            payload,
            request=request,
            config=config,
        ):
            continue
        run_scope = dict(payload.get("scope") or {})
        if any(
            run_scope.get(key) != requested_scope.get(key)
            for key in ("book_id", "from_chapter", "to_chapter", "skip_completed")
        ):
            continue
        run_revisions = _text_revision_signatures(payload)
        if run_revisions != requested_revisions:
            continue
        suggestions = {
            str(item.get("unresolved_key") or ""): item
            for item in payload.get("suggestions") or []
        }
        if any(
            key not in suggestions
            or not _suggestion_matches_current_target(
                suggestions[key],
                target=target,
                run_revisions=run_revisions,
                request_revisions=requested_revisions,
            )
            for key, target in current_targets.items()
        ):
            continue
        projected = _clean_queue_state(db, payload)
        projected["source_input_fingerprint"] = projected.get("input_fingerprint")
        projected["input_fingerprint"] = request["input_fingerprint"]
        projected["projected_from_existing_run"] = True
        projected["scope"] = request["scope"]
        projected["text_revisions"] = request["text_revisions"]
        return projected
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


def _note_events(db: Database, *, analysis_run_id: str) -> list[dict[str, Any]]:
    rows = db.fetch_all(
        """
        SELECT *
        FROM audit_events
        WHERE event_code=?
        ORDER BY id
        """,
        (NOTE_EVENT,),
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


def _latest_decision_for_item(
    db: Database,
    *,
    analysis_run_id: str,
    source_analysis_run_id: str | None,
    unresolved_key: str,
) -> dict[str, Any] | None:
    """Resolve decisions for both direct and combined queue projections."""

    run_ids = {
        str(value).strip()
        for value in (analysis_run_id, source_analysis_run_id)
        if str(value or "").strip()
    }
    candidates: list[dict[str, Any]] = []
    for run_id in run_ids:
        candidates.extend(
            event
            for event in _decision_events(db, analysis_run_id=run_id)
            if str(event["details"].get("unresolved_key") or "") == str(unresolved_key)
        )
    candidates = [
        event
        for event in candidates
        if not (
            str(event["details"].get("decision") or "").upper() == "ERROR"
            and (
                event["details"].get("reviewer_payload") or {}
            ).get("batch_idempotency_key")
        )
    ]
    if not candidates:
        return None
    # Durable corrections/replacements outrank lower-confidence retry errors.
    # RESTORED_PENDING resets older history, but a later operator decision can
    # establish a new effective state.
    precedence = {
        "ERROR": 10,
        "MARKED_UNCERTAIN": 20,
        "DEFERRED": 30,
        "ACCEPTED": 40,
        "EDITED_AND_ACCEPTED": 50,
        "CORRECTED": 60,
        "REPLACEMENT_DRAFT": 70,
    }
    latest_restore = max(
        (
            item
            for item in candidates
            if str(item["details"].get("decision") or "").upper()
            == "RESTORED_PENDING"
        ),
        key=lambda item: int(item.get("id") or 0),
        default=None,
    )
    if latest_restore is not None:
        post_restore = [
            item
            for item in candidates
            if int(item.get("id") or 0) > int(latest_restore.get("id") or 0)
        ]
        if not post_restore:
            event = latest_restore
        else:
            candidates = post_restore
            event = max(
                candidates,
                key=lambda item: (
                    precedence.get(
                        str(item["details"].get("decision") or "").upper(),
                        0,
                    ),
                    int(item.get("id") or 0),
                ),
            )
    else:
        event = max(
            candidates,
            key=lambda item: (
                precedence.get(
                    str(item["details"].get("decision") or "").upper(),
                    0,
                ),
                int(item.get("id") or 0),
            ),
        )
    details = dict(event["details"])
    details["audit_event_id"] = int(event["id"])
    details["recorded_at"] = event.get("created_at")
    return details


def _decision_history_for_item(
    db: Database,
    *,
    analysis_run_id: str,
    source_analysis_run_id: str | None,
    unresolved_key: str,
) -> list[dict[str, Any]]:
    run_ids = {
        str(value).strip()
        for value in (analysis_run_id, source_analysis_run_id)
        if str(value or "").strip()
    }
    history: list[dict[str, Any]] = []
    for run_id in run_ids:
        events = [
            *_decision_events(db, analysis_run_id=run_id),
            *_note_events(db, analysis_run_id=run_id),
        ]
        for event in events:
            if str(event["details"].get("unresolved_key") or "") != str(
                unresolved_key
            ):
                continue
            history.append(
                {
                    **dict(event["details"]),
                    "audit_event_id": int(event["id"]),
                    "recorded_at": event.get("created_at"),
                }
            )
    return sorted(history, key=lambda item: int(item.get("audit_event_id") or 0))


def _load_run_from_event(store: ContentStore, event: Mapping[str, Any]) -> dict[str, Any]:
    details = dict(event.get("details") or {})
    payload = store.read_json(str(details["content_path"]))
    if sha256_text(canonical_json(payload)) != str(details["content_sha256"]):
        raise SpeakerReviewSuggestionError("Stored speaker suggestion run hash mismatch")
    return payload


def _clean_queue_state(db: Database, payload: dict[str, Any]) -> dict[str, Any]:
    analysis_run_id = str(payload["analysis_run_id"])
    for item in payload.get("suggestions") or []:
        unresolved_key = str(item.get("unresolved_key") or "")
        source_analysis_run_id = str(item.get("source_analysis_run_id") or analysis_run_id)
        decision = _latest_decision_for_item(
            db,
            analysis_run_id=analysis_run_id,
            source_analysis_run_id=source_analysis_run_id,
            unresolved_key=unresolved_key,
        )
        history = _decision_history_for_item(
            db,
            analysis_run_id=analysis_run_id,
            source_analysis_run_id=source_analysis_run_id,
            unresolved_key=unresolved_key,
        )
        item.setdefault("source_analysis_run_id", analysis_run_id)
        item["suggestion_id"] = f"{item['source_analysis_run_id']}:{unresolved_key}"
        decision_state = str((decision or {}).get("decision") or "PENDING_REVIEW")
        item["review_state"] = (
            "PENDING_REVIEW"
            if decision_state == "RESTORED_PENDING"
            else decision_state
        )
        item["human_review"] = decision or None
        item["reviewed_at"] = decision.get("recorded_at") if decision else None
        item["review_audit_event_id"] = (
            decision.get("audit_event_id") if decision else None
        )
        item["review_history"] = history
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
        "corrected": 0,
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
        if review_state in APPROVED_STATES:
            counts["approved"] += 1
            if review_state == "CORRECTED":
                counts["corrected"] += 1
        elif review_state == "DEFERRED":
            counts["deferred"] += 1
    counts["needs_human_decision"] = sum(
        1
        for item in suggestions
        if (
            str(item.get("proposed_resolution") or "").upper()
            == "NEEDS_HUMAN_DECISION"
            and str(item.get("review_state") or "PENDING_REVIEW").upper()
            == "PENDING_REVIEW"
        )
        or str(item.get("review_state") or "").upper() == "MARKED_UNCERTAIN"
    )
    counts["pending_review"] = sum(
        1
        for item in suggestions
        if str(item.get("review_state") or "PENDING_REVIEW").upper()
        == "PENDING_REVIEW"
    )
    counts["error"] = sum(
        1
        for item in suggestions
        if str(item.get("review_state") or "").upper() in {"ERROR", "FAILED", "REJECTED"}
        or item.get("error")
        or item.get("error_code")
    )
    counts["queue_views"] = queue_view_counts(suggestions)
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
    current_revision_by_chapter = {
        int(item.get("chapter_number") or 0): int(item.get("text_revision_id") or 0)
        for item in request.get("text_revisions") or []
    }
    proposed_name_keys: dict[str, list[str]] = {}
    for item in suggestions:
        if str(item.get("proposed_resolution") or "") != "NEW_CHARACTER":
            continue
        name = normalize_identity(str(item.get("proposed_character_name") or ""))
        if name:
            proposed_name_keys.setdefault(name, []).append(str(item.get("unresolved_key") or ""))
    augmented: list[dict[str, Any]] = []
    for item in suggestions:
        target = by_key.get(str(item["unresolved_key"])) or (
            dict(item.get("target") or {})
            if isinstance(item.get("target"), Mapping)
            else {}
        )
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
        proposal_warnings = list(proposal.get("warnings") or [])
        name_key = normalize_identity(str(proposal.get("proposed_character_name") or ""))
        if resolution == "NEW_CHARACTER" and name_key and len(proposed_name_keys.get(name_key, [])) > 1:
            proposal_warnings.append(
                "Đề xuất tên nhân vật lặp trong cùng phạm vi; cần gộp hoặc chọn nhân vật có sẵn."
            )
        if duplicate_candidates:
            proposal_warnings = [
                *proposal_warnings,
                "Tên hoặc alias giống nhân vật đã có; cần duyệt thủ công.",
            ]
        if proposal_warnings:
            proposal["warnings"] = list(dict.fromkeys(proposal_warnings))
        source_revision_current = (
            int(target.get("chapter_number") or 0) in current_revision_by_chapter
            and int(
                (proposal.get("text_revision_id") or target.get("text_revision_id") or 0)
            )
            in {
                0,
                current_revision_by_chapter.get(int(target.get("chapter_number") or 0)),
            }
        )
        chapter_id = int(target.get("chapter_id") or 0)
        approved_plan = (
            db.fetch_one(
                """
                SELECT 1
                FROM chapters c
                JOIN casting_plans cp ON cp.chapter_id=c.id
                WHERE c.id=?
                  AND cp.status='approved'
                  AND cp.text_revision_id=c.active_text_revision_id
                LIMIT 1
                """,
                (chapter_id,),
            )
            if chapter_id
            else None
        )
        downstream = (
            db.fetch_one(
                """
                SELECT
                  EXISTS(
                    SELECT 1 FROM job_chapters jc
                    WHERE jc.chapter_id=?
                  ) AS has_job_snapshot,
                  EXISTS(
                    SELECT 1 FROM artifacts a
                    WHERE a.chapter_id=?
                  ) AS has_artifact
                """,
                (chapter_id, chapter_id),
            )
            if chapter_id
            else None
        )
        has_downstream = bool(
            downstream
            and (
                int(downstream["has_job_snapshot"] or 0)
                or int(downstream["has_artifact"] or 0)
            )
        )
        proposal.update(
            {
                "target": target,
                "approved_final_voice_map_available": bool(approved_plan),
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
                "source_revision_current": source_revision_current,
                "downstream_immutable_exists": has_downstream,
                "downstream_stale": has_downstream
                and str(proposal.get("review_state") or "").upper()
                in {"CORRECTED", "REPLACEMENT_DRAFT"},
            }
        )
        proposal["approval_exclusion_reasons"] = batch_exclusion_reasons(proposal)
        proposal["approval_eligible"] = not proposal["approval_exclusion_reasons"]
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
        payload = _latest_compatible_run_for_request(
            db,
            store,
            config,
            request=request,
        )
        if not payload:
            payload = _combined_run_from_existing_events(
                db,
                store,
                config,
                request=request,
            )
        if payload:
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
    connection: Any | None = None,
    resulting_mapping: Mapping[str, Any] | None = None,
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
    if normalized_decision == "REPLACEMENT_DRAFT":
        current = _latest_decision_for_item(
            db,
            analysis_run_id=analysis_run_id,
            source_analysis_run_id=str(
                suggestion.get("source_analysis_run_id") or analysis_run_id
            ),
            unresolved_key=unresolved_key,
        )
        if (
            not current
            or str(current.get("decision") or "").upper() not in APPROVED_STATES
        ):
            raise SpeakerReviewSuggestionError(
                "A replacement decision can only be created from an approved decision"
            )
    details = {
        "schema": QUEUE_SCHEMA,
        "analysis_run_id": analysis_run_id,
        "unresolved_key": unresolved_key,
        "decision": normalized_decision,
        "reviewer_payload": dict(reviewer_payload),
        "source_suggestion": suggestion,
        "resulting_mapping": dict(resulting_mapping or {}),
        "idempotency_key": idempotency_key,
    }
    chapter_id = int((suggestion.get("target") or {}).get("chapter_id") or 0) or None
    audit_event_id: int | None = None
    if connection is None:
        db.audit(DECISION_EVENT, chapter_id=chapter_id, details=details)
        row = db.fetch_one(
            """
            SELECT id,created_at
            FROM audit_events
            WHERE event_code=? AND details_json=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                DECISION_EVENT,
                json.dumps(details, ensure_ascii=False),
            ),
        )
        if row:
            audit_event_id = int(row["id"])
            details["audit_event_id"] = audit_event_id
            details["recorded_at"] = row["created_at"]
    else:
        cursor = connection.execute(
            """
            INSERT INTO audit_events(event_code,job_id,chapter_id,details_json,created_at)
            VALUES(?,?,?,?,?)
            """,
            (
                DECISION_EVENT,
                None,
                chapter_id,
                json.dumps(details, ensure_ascii=False),
                utcnow(),
            ),
        )
        audit_event_id = int(cursor.lastrowid)
        details["audit_event_id"] = audit_event_id
    return {"reused": False, "decision": details}


def record_speaker_suggestion_note(
    db: Database,
    store: ContentStore,
    *,
    analysis_run_id: str,
    unresolved_key: str,
    note: str,
    idempotency_key: str,
) -> dict[str, Any]:
    normalized_note = str(note or "").strip()
    if not normalized_note:
        raise SpeakerReviewSuggestionError("Review note is required")
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
            for event in _note_events(db, analysis_run_id=analysis_run_id)
            if event["details"].get("idempotency_key") == idempotency_key
        ),
        None,
    )
    if existing:
        return {"reused": True, "note": existing["details"]}
    details = {
        "schema": QUEUE_SCHEMA,
        "analysis_run_id": analysis_run_id,
        "unresolved_key": unresolved_key,
        "decision": "NOTE",
        "reviewer_payload": {"note": normalized_note},
        "source_suggestion": suggestion,
        "resulting_mapping": {},
        "idempotency_key": idempotency_key,
    }
    chapter_id = int((suggestion.get("target") or {}).get("chapter_id") or 0) or None
    db.audit(NOTE_EVENT, chapter_id=chapter_id, details=details)
    return {"reused": False, "note": details}


def restore_speaker_suggestion_pending(
    db: Database,
    store: ContentStore,
    *,
    analysis_run_id: str,
    unresolved_key: str,
    reviewer_payload: Mapping[str, Any],
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
    current = _latest_decision_for_item(
        db,
        analysis_run_id=analysis_run_id,
        source_analysis_run_id=str(
            suggestion.get("source_analysis_run_id") or analysis_run_id
        ),
        unresolved_key=unresolved_key,
    )
    if str((current or {}).get("decision") or "").upper() not in APPROVED_STATES:
        raise SpeakerReviewSuggestionError(
            "Only an approved speaker decision can be restored to pending"
        )
    chapter_id = int((suggestion.get("target") or {}).get("chapter_id") or 0)
    downstream = (
        db.fetch_one(
            """
            SELECT
              EXISTS(SELECT 1 FROM job_chapters WHERE chapter_id=?) AS has_job_snapshot,
              EXISTS(SELECT 1 FROM artifacts WHERE chapter_id=?) AS has_artifact
            """,
            (chapter_id, chapter_id),
        )
        if chapter_id
        else None
    )
    if downstream and (
        int(downstream["has_job_snapshot"] or 0)
        or int(downstream["has_artifact"] or 0)
    ):
        raise SpeakerReviewSuggestionError(
            "Downstream production history exists; create a replacement decision instead"
        )
    return record_speaker_suggestion_decision(
        db,
        store,
        analysis_run_id=analysis_run_id,
        unresolved_key=unresolved_key,
        decision="RESTORED_PENDING",
        reviewer_payload=reviewer_payload,
        idempotency_key=idempotency_key,
    )


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
    decision_override: str | None = None,
    require_approved: bool = False,
    connection: Any | None = None,
) -> dict[str, Any]:
    if connection is None:
        with db.transaction() as transaction:
            return accept_speaker_review_suggestion(
                db,
                store,
                config,
                book_id=book_id,
                from_chapter=from_chapter,
                to_chapter=to_chapter,
                analysis_run_id=analysis_run_id,
                unresolved_key=unresolved_key,
                reviewer_payload=reviewer_payload,
                voice_catalog=voice_catalog,
                custom_voice_context=custom_voice_context,
                idempotency_key=idempotency_key,
                decision_override=decision_override,
                require_approved=require_approved,
                connection=transaction,
            )
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
    current_review = _latest_decision_for_item(
        db,
        analysis_run_id=analysis_run_id,
        source_analysis_run_id=str(suggestion.get("source_analysis_run_id") or analysis_run_id),
        unresolved_key=unresolved_key,
    )
    if require_approved:
        current_state = str(
            (current_review or {}).get("decision") or ""
        ).upper()
        replacement_source_state = str(
            ((current_review or {}).get("source_suggestion") or {}).get(
                "review_state"
            )
            or ""
        ).upper()
        if current_state not in APPROVED_STATES and not (
            current_state == "REPLACEMENT_DRAFT"
            and replacement_source_state in APPROVED_STATES
        ):
            raise SpeakerReviewSuggestionError(
                "Only an approved speaker decision can be corrected"
            )
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
    voice_mode = str(reviewer_payload.get("voice_mode") or "").strip().lower()
    voice_change_requested = voice_mode in {
        "book_default",
        "exact",
        "inherit",
        "override",
        "set",
    }
    requested_voice = (
        str(reviewer_payload.get("suggested_voice_id") or "").strip() or None
        if voice_mode not in {"inherit", "book_default"}
        else None
    )
    voice_scope = str(reviewer_payload.get("voice_scope") or "chapter").strip().lower()
    if voice_scope not in {"chapter", "range"}:
        raise SpeakerReviewSuggestionError("Unsupported voice correction scope")
    voice_operation = (
        "set"
        if voice_mode in {"exact", "override", "set"}
        else "clear"
        if voice_mode in {"inherit", "book_default"}
        else "preserve"
    )
    applied: dict[str, Any]
    final_speaker_key: str
    if resolution == "EXISTING_CHARACTER":
        character_id = reviewer_payload.get("existing_character_id") or suggestion.get("existing_character_id")
        if isinstance(character_id, bool) or not isinstance(character_id, int) or int(character_id) <= 0:
            raise SpeakerReviewSuggestionError("existing_character_id is required")
        character_id = int(character_id)
        final_speaker_key = f"character:{character_id}"
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
            connection=connection,
            voice_operation=voice_operation,
            voice_id=requested_voice,
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
            connection=connection,
        )
        character_id = int(created["character"]["id"])
        final_speaker_key = f"character:{character_id}"
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
            connection=connection,
            voice_operation=voice_operation,
            voice_id=requested_voice,
        )
        applied["created_character"] = created
    elif resolution == "NARRATOR":
        final_speaker_key = "narrator"
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
            connection=connection,
            voice_operation=voice_operation,
            voice_id=requested_voice,
        )
    else:
        raise SpeakerReviewSuggestionError("This suggestion requires manual deferral, not approval")
    if voice_change_requested and voice_scope == "range":
        target_chapter = int(
            (suggestion.get("target") or {}).get("chapter_number")
            or suggestion.get("chapter_number")
            or 0
        )
        scoped_results: list[dict[str, Any]] = []
        for range_start, range_end in (
            (from_chapter, target_chapter - 1),
            (target_chapter + 1, to_chapter),
        ):
            if range_start > range_end:
                continue
            scoped_results.append(
                apply_chapter_voice_override(
                    db,
                    store,
                    book_id=book_id,
                    from_chapter=range_start,
                    to_chapter=range_end,
                    speaker_key=final_speaker_key,
                    operation="set" if voice_operation == "set" else "clear",
                    voice_id=requested_voice,
                    voice_catalog=voice_catalog,
                    idempotency_key=(
                        f"{idempotency_key}:voice:{range_start}-{range_end}"
                    ),
                    custom_voice_context=custom_voice_context,
                    connection=connection,
                    skip_missing=True,
                )
            )
        applied["voice_scope_results"] = scoped_results
    editable_fields = (
        "proposed_resolution",
        "existing_character_id",
        "proposed_character_name",
        "proposed_aliases",
        "suggested_voice_id",
    )
    human_edited = any(
        field in reviewer_payload
        and reviewer_payload.get(field) != suggestion.get(field)
        for field in editable_fields
    ) or voice_mode not in {"", "keep", "preserve"}
    review = record_speaker_suggestion_decision(
        db,
        store,
        analysis_run_id=analysis_run_id,
        unresolved_key=unresolved_key,
        decision=decision_override
        or (
            "EDITED_AND_ACCEPTED"
            if human_edited
            else "ACCEPTED"
        ),
        reviewer_payload=reviewer_payload,
        idempotency_key=idempotency_key,
        connection=connection,
        resulting_mapping=applied,
    )
    return {"applied": applied, "review": review}


def _approved_final_voice_map_available(
    db: Database,
    suggestion: Mapping[str, Any],
) -> bool:
    chapter_id = int((suggestion.get("target") or {}).get("chapter_id") or 0)
    if not chapter_id:
        return False
    return bool(
        db.fetch_one(
            """
            SELECT 1
            FROM chapters c
            JOIN casting_plans cp ON cp.chapter_id=c.id
            WHERE c.id=?
              AND cp.status='approved'
              AND cp.text_revision_id=c.active_text_revision_id
            LIMIT 1
            """,
            (chapter_id,),
        )
    )


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
    connection: Any | None = None,
) -> dict[str, Any]:
    payload = _latest_queue_for_run(db, store, analysis_run_id=analysis_run_id)
    keys = [str(item).strip() for item in unresolved_keys if str(item).strip()]
    if not keys:
        raise SpeakerReviewSuggestionError("No suggestions selected for batch approval")
    suggestions = {
        str(item.get("unresolved_key")): item
        for item in payload.get("suggestions") or []
    }
    replayed: list[dict[str, Any]] = []
    for key in keys:
        decision_key = f"{idempotency_key}:{key}"
        existing = next(
            (
                event
                for event in _decision_events(
                    db, analysis_run_id=analysis_run_id
                )
                if event["details"].get("idempotency_key") == decision_key
                and str(event["details"].get("decision") or "").upper()
                in APPROVED_STATES
            ),
            None,
        )
        if existing:
            replayed.append(
                {
                    "applied": None,
                    "review": {
                        "reused": True,
                        "decision": existing["details"],
                    },
                }
            )
    if replayed:
        if len(replayed) != len(keys):
            raise SpeakerReviewSuggestionError(
                "Batch replay is inconsistent; no additional changes were applied"
            )
        return {
            "applied": replayed,
            "submitted_count": len(keys),
            "reused": True,
        }
    for key in keys:
        suggestion = suggestions.get(key)
        if not suggestion:
            raise SpeakerReviewSuggestionError(f"Suggestion not found: {key}")
        reasons = batch_exclusion_reasons(suggestion)
        if reasons:
            raise SpeakerReviewSuggestionError(
                f"Suggestion {key} is not safe for batch approval: {', '.join(reasons)}"
            )
        if not _approved_final_voice_map_available(db, suggestion):
            raise SpeakerReviewSuggestionError(
                "Approved Final Voice Map is missing or stale"
            )
        if suggestion.get("proposed_resolution") not in {
            "EXISTING_CHARACTER",
            "NEW_CHARACTER",
            "NARRATOR",
        }:
            raise SpeakerReviewSuggestionError(
                "Batch approval is limited to resolved safe suggestions"
            )
    applied = []
    def apply_with(transaction: Any) -> None:
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
                    connection=transaction,
                )
            )

    try:
        if connection is None:
            with db.transaction() as transaction:
                apply_with(transaction)
        else:
            apply_with(connection)
    except Exception:
        # The transaction is the only durable batch result. Do not manufacture
        # per-item ERROR decisions after rollback; the command envelope carries
        # the failure and the queue remains retryable.
        raise
    queue = _latest_queue_for_run(db, store, analysis_run_id=analysis_run_id)
    decision_ids = [
        int(
            ((item.get("review") or {}).get("decision") or {}).get(
                "audit_event_id"
            )
        )
        for item in applied
        if ((item.get("review") or {}).get("decision") or {}).get(
            "audit_event_id"
        )
    ]
    return {
        "applied": applied,
        "submitted_count": len(keys),
        "decision_ids": decision_ids,
        "queue_counts": queue_view_counts(queue.get("suggestions") or []),
    }


def approve_speaker_review_batch_items(
    db: Database,
    store: ContentStore,
    config: Settings,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    items: Iterable[Mapping[str, Any]],
    voice_catalog: EffectiveVoiceCatalog,
    custom_voice_context: CustomVoiceContext | None = None,
    idempotency_key: str,
) -> dict[str, Any]:
    """Apply a combined-run batch in one transaction across source runs."""

    normalized: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        run_id = str(item.get("analysis_run_id") or "").strip()
        unresolved_key = str(item.get("unresolved_key") or "").strip()
        identity = (run_id, unresolved_key)
        if not all(identity):
            raise SpeakerReviewSuggestionError(
                "Batch items require analysis_run_id and unresolved_key"
            )
        if identity in seen:
            continue
        seen.add(identity)
        normalized.append(identity)
    if not normalized:
        raise SpeakerReviewSuggestionError("No suggestions selected for batch approval")

    groups: dict[str, list[str]] = {}
    for run_id, unresolved_key in normalized:
        groups.setdefault(run_id, []).append(unresolved_key)
    results: list[dict[str, Any]] = []
    try:
        with db.transaction() as connection:
            for run_id, keys in groups.items():
                results.append(
                    approve_high_confidence_suggestions(
                        db,
                        store,
                        config,
                        book_id=book_id,
                        from_chapter=from_chapter,
                        to_chapter=to_chapter,
                        analysis_run_id=run_id,
                        unresolved_keys=keys,
                        voice_catalog=voice_catalog,
                        custom_voice_context=custom_voice_context,
                        idempotency_key=f"{idempotency_key}:{run_id}",
                        connection=connection,
                    )
                )
    except Exception:
        # Preserve all-or-none semantics across source runs.
        raise
    decision_ids = [
        decision_id
        for result in results
        for decision_id in result.get("decision_ids") or []
    ]
    queue_counts = {
        run_id: queue_view_counts(
            _latest_queue_for_run(
                db,
                store,
                analysis_run_id=run_id,
            ).get("suggestions")
            or []
        )
        for run_id in groups
    }
    return {
        "groups": results,
        "submitted_count": len(normalized),
        "decision_ids": decision_ids,
        "queue_counts": queue_counts,
        "items": [
            {"analysis_run_id": run_id, "unresolved_key": unresolved_key}
            for run_id, unresolved_key in normalized
        ],
    }


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
    "approve_speaker_review_batch_items",
    "build_speaker_review_request",
    "generate_speaker_review_suggestions",
    "get_speaker_review_queue",
    "record_speaker_suggestion_decision",
    "validate_speaker_review_response",
]
