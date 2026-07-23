from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Iterable

from .db import Database, utcnow
from .files import sha256_text
from .storage import ContentStore
from .text_encoding import CanonicalTextValidationError, load_validated_text_revision
from .voice_profile import get_book_voice_profile, preset_ref, profile_validation, resolve_voice
from .voice_ref import CustomVoiceContext, is_custom_ref

CASTING_SCHEMA_VERSION = 1
CHUNKER_VERSION = "utterance-v3"
TERMINALS = ".!?…"
OPEN_QUOTES = {'"', "“"}
CLOSE_QUOTES = {'"', "”"}

class CastingError(ValueError):
    pass


def _load_casting_text_revision(
    store: ContentStore,
    revision: Any,
) -> str:
    try:
        return load_validated_text_revision(
            store,
            revision,
            field=f"Text Revision #{int(revision['id'])}",
        )
    except CanonicalTextValidationError as exc:
        raise CastingError(str(exc)) from exc

def _trim(text: str, start: int, end: int) -> tuple[int, int] | None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if start < end else None


ORPHAN_TAIL_MAX_WORDS = 2
ORPHAN_TAIL_MAX_CHARS = 16
LOOKBACK_WINDOW = 96
SENTENCE_PUNCTUATION = ".!?…"
CLAUSE_PUNCTUATION = ",;:"
DANGLING_FINAL_WORDS = {
    "rất",
    "không",
    "đã",
    "sẽ",
    "cũng",
    "vẫn",
    "còn",
    "đang",
    "vừa",
    "mới",
    "chỉ",
}


def _is_orphan_tail(text: str, start: int, end: int) -> bool:
    trimmed = _trim(text, start, end)
    if not trimmed:
        return False
    left, right = trimmed
    snippet = text[left:right]
    words = snippet.split()
    return len(words) <= ORPHAN_TAIL_MAX_WORDS and len(snippet) <= ORPHAN_TAIL_MAX_CHARS


def _final_word(text: str, start: int, end: int) -> str:
    trimmed = _trim(text, start, end)
    if not trimmed:
        return ""
    snippet = text[trimmed[0]:trimmed[1]].rstrip(SENTENCE_PUNCTUATION + CLAUSE_PUNCTUATION + "\"”").strip()
    words = snippet.split()
    return words[-1].casefold() if words else ""


def _candidate_cuts(text: str, left: int, right: int, maximum: int) -> list[tuple[int, str]]:
    limit = min(right, left + maximum)
    candidates: dict[int, str] = {}
    for index in range(left + 1, limit):
        if text[index].isspace():
            look = index - 1
            while look > left and text[look].isspace():
                look -= 1
            while look > left and text[look] in CLOSE_QUOTES:
                look -= 1
            marker = text[look] if left <= look < right else ""
            kind = "space"
            if marker in SENTENCE_PUNCTUATION:
                kind = "sentence"
            elif marker in CLAUSE_PUNCTUATION:
                kind = "clause"
            candidates[index] = kind
    return sorted((cut, kind) for cut, kind in candidates.items() if left < cut < right)


def _select_best_candidate(
    text: str,
    left: int,
    right: int,
    candidates: list[tuple[int, str]],
    *,
    prefer_punctuation: bool,
    maximum: int,
) -> int | None:
    if not candidates:
        return None
    best: tuple[tuple[int, int, int, int], int] | None = None
    for cut, kind in candidates:
        head = _trim(text, left, cut)
        tail = _trim(text, cut, right)
        if not head:
            continue
        if head[1] - head[0] > maximum:
            continue
        tail_orphan = 1 if tail and _is_orphan_tail(text, tail[0], tail[1]) else 0
        head_dangling = 1 if _final_word(text, head[0], head[1]) in DANGLING_FINAL_WORDS else 0
        kind_rank = {"sentence": 0, "clause": 1, "space": 2}[kind]
        if not prefer_punctuation:
            kind_rank = 0 if kind == "space" else 1
        distance_rank = -(cut - left)
        score = (tail_orphan, head_dangling, kind_rank, distance_rank)
        if best is None or score < best[0]:
            best = (score, cut)
    return best[1] if best else None


def _choose_cut(text: str, left: int, right: int, maximum: int) -> int:
    candidates = _candidate_cuts(text, left, right, maximum)
    limit = min(right, left + maximum)
    lookback_start = max(left + 1, limit - LOOKBACK_WINDOW)
    lookback = [(cut, kind) for cut, kind in candidates if cut >= lookback_start]
    preferred = _select_best_candidate(text, left, right, lookback, prefer_punctuation=True, maximum=maximum)
    if preferred is not None:
        return preferred
    fallback = _select_best_candidate(text, left, right, candidates, prefer_punctuation=False, maximum=maximum)
    return fallback if fallback is not None else left + maximum

def _split_region(text: str, start: int, end: int, maximum: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = start
    index = start
    while index < end:
        boundary = False
        if text[index] in TERMINALS:
            look = index + 1
            while look < end and text[look] in CLOSE_QUOTES:
                look += 1
            boundary = look >= end or text[look].isspace()
            if boundary:
                index = look - 1
        elif text[index] == "\n" and index + 1 < end and text[index + 1] == "\n":
            boundary = True
        if boundary:
            trimmed = _trim(text, cursor, index + 1)
            if trimmed:
                spans.append(trimmed)
            cursor = index + 1
        index += 1
    trimmed = _trim(text, cursor, end)
    if trimmed:
        spans.append(trimmed)

    safe: list[tuple[int, int]] = []
    for left, right in spans:
        while right - left > maximum:
            cut = _choose_cut(text, left, right, maximum)
            piece = _trim(text, left, cut)
            if piece:
                safe.append(piece)
            left = cut
            while left < right and text[left].isspace():
                left += 1
        piece = _trim(text, left, right)
        if piece:
            safe.append(piece)
    return safe

def split_utterances(text: str, maximum: int = 256) -> list[dict[str, Any]]:
    """Split deterministically while preserving offsets into the approved revision."""
    regions: list[tuple[int, int]] = []
    cursor = 0
    index = 0
    while index < len(text):
        if text[index] not in OPEN_QUOTES:
            index += 1
            continue
        closing = "”" if text[index] == "“" else '"'
        close = text.find(closing, index + 1)
        if close < 0:
            index += 1
            continue
        regions.extend(_split_region(text, cursor, index, maximum))
        quote_span = _trim(text, index, close + 1)
        if quote_span and quote_span[1] - quote_span[0] <= maximum:
            regions.append(quote_span)
        else:
            regions.extend(_split_region(text, index, close + 1, maximum))
        cursor = close + 1
        index = cursor
    regions.extend(_split_region(text, cursor, len(text), maximum))
    regions.sort()

    utterances: list[dict[str, Any]] = []
    for sequence, (start, end) in enumerate(regions, start=1):
        text_sha = sha256_text(text[start:end])
        utterance_id = f"u{sequence:04d}-{hashlib.sha256(f'{start}:{end}:{text_sha}'.encode()).hexdigest()[:12]}"
        utterances.append(
            {
                "utterance_id": utterance_id,
                "sequence": sequence,
                "start_offset": start,
                "end_offset": end,
                "text_sha256": text_sha,
                "role": "narrator",
                "character_id": None,
                "resolved_voice_id": "",
            }
        )
    return utterances

def _revision(db: Database, chapter_id: int, text_revision_id: int | None = None):
    if text_revision_id is not None:
        row = db.fetch_one(
            "SELECT * FROM text_revisions WHERE id=? AND chapter_id=? AND status='approved'",
            (text_revision_id, chapter_id),
        )
    else:
        row = db.fetch_one(
            """SELECT tr.* FROM text_revisions tr JOIN chapters c ON c.id=tr.chapter_id
               WHERE tr.chapter_id=? AND tr.status='approved'
               ORDER BY (tr.id=c.active_text_revision_id) DESC,tr.id DESC LIMIT 1""",
            (chapter_id,),
        )
    if not row:
        raise CastingError("Chapter does not have the requested approved TextRevision")
    return row

GENDERS = {"male", "female", "unknown"}
ROLES = {"main", "supporting", "minor", "unknown"}
AGE_GROUPS = {"child", "teen", "young_adult", "adult", "elder", "unknown"}
METADATA_FIELDS = ("role", "age_group", "description", "speech_style", "visual_notes", "notes")

def _clean_optional_text(value: str | None, maximum: int = 4_000) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).strip().split())
    if len(cleaned) > maximum:
        raise CastingError("Character metadata is too long")
    return cleaned

def _aliases_by_character(db: Database, book_id: int) -> dict[int, list[str]]:
    aliases: dict[int, list[str]] = {}
    for row in db.fetch_all(
        "SELECT character_id,alias FROM character_aliases WHERE book_id=? ORDER BY alias,id",
        (book_id,),
    ):
        aliases.setdefault(int(row["character_id"]), []).append(str(row["alias"]))
    return aliases

def list_characters(db: Database, book_id: int, include_inactive: bool = False) -> list[dict[str, Any]]:
    suffix = "" if include_inactive else " AND active=1"
    characters = [
        dict(row)
        for row in db.fetch_all(
            f"SELECT * FROM characters WHERE book_id=?{suffix} ORDER BY display_name,id", (book_id,)
        )
    ]
    aliases = _aliases_by_character(db, book_id)
    for character in characters:
        character["aliases"] = aliases.get(int(character["id"]), [])
    return characters

def create_character(
    db: Database,
    book_id: int,
    display_name: str,
    voice_id: str | None = None,
    *,
    gender: str | None = None,
) -> dict[str, Any]:
    name = display_name.strip()
    voice_id = voice_id.strip() if voice_id else ""
    if not name:
        raise CastingError("Character name is required")
    if gender not in GENDERS | {None}:
        raise CastingError("Character gender is invalid")
    if not db.fetch_one("SELECT id FROM books WHERE id=?", (book_id,)):
        raise CastingError("Book not found")
    now = utcnow()
    try:
        with db.connect() as connection:
            character_id = int(
                connection.execute(
                    """INSERT INTO characters(
                       book_id,display_name,default_voice_id,voice_override_id,gender,created_at,updated_at
                       ) VALUES(?,?,?,?,?,?,?)""",
                    (book_id, name, voice_id, voice_id or None, gender, now, now),
                ).lastrowid
            )
    except sqlite3.IntegrityError as exc:
        raise CastingError("Character name already exists in this book") from exc
    return dict(db.fetch_one("SELECT * FROM characters WHERE id=?", (character_id,)))

def update_character(
    db: Database,
    character_id: int,
    *,
    display_name: str | None = None,
    voice_id: str | None = None,
    gender: str | None = None,
    role: str | None = None,
    age_group: str | None = None,
    description: str | None = None,
    speech_style: str | None = None,
    visual_notes: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    row = db.fetch_one("SELECT * FROM characters WHERE id=? AND active=1", (character_id,))
    if not row:
        raise CastingError("Character not found")
    name = display_name.strip() if display_name is not None else row["display_name"]
    voice = voice_id.strip() if voice_id is not None else row["voice_override_id"]
    resolved_gender = gender if gender is not None else row["gender"]
    if not name or (resolved_gender is not None and resolved_gender not in GENDERS):
        raise CastingError("Character name or gender is invalid")
    updates: dict[str, Any] = {
        "display_name": name,
        "default_voice_id": voice or "",
        "voice_override_id": voice or None,
        "gender": resolved_gender,
    }
    if role is not None:
        if role not in ROLES:
            raise CastingError("Character role is invalid")
        updates["role"] = role
    if age_group is not None:
        if age_group not in AGE_GROUPS | {""}:
            raise CastingError("Character age group is invalid")
        updates["age_group"] = age_group or None
    for field, value in (
        ("description", description),
        ("speech_style", speech_style),
        ("visual_notes", visual_notes),
        ("notes", notes),
    ):
        if value is not None:
            updates[field] = _clean_optional_text(value)
    updates["updated_at"] = utcnow()
    assignments = ",".join(f"{field}=?" for field in updates)
    with db.connect() as connection:
        connection.execute(
            f"UPDATE characters SET {assignments} WHERE id=?",
            (*updates.values(), character_id),
        )
    result = dict(db.fetch_one("SELECT * FROM characters WHERE id=?", (character_id,)))
    result["aliases"] = _aliases_by_character(db, int(result["book_id"])).get(character_id, [])
    return result

def deactivate_character(db: Database, character_id: int) -> None:
    row = db.fetch_one("SELECT id FROM characters WHERE id=? AND active=1", (character_id,))
    if not row:
        raise CastingError("Character not found")
    referenced = db.fetch_one(
        "SELECT 1 FROM casting_plan_characters WHERE character_id=? LIMIT 1", (character_id,)
    )
    if referenced:
        raise CastingError("Character is referenced by a casting plan and cannot be deleted")
    with db.connect() as connection:
        connection.execute(
            "UPDATE characters SET active=0,updated_at=? WHERE id=?", (utcnow(), character_id)
        )

def _is_allowed_voice(voice_ref: str, allowed_voice_ids: set[str], custom_voice_context: CustomVoiceContext | None) -> bool:
    """Check if a voice reference is allowed (preset or custom)."""
    if voice_ref in allowed_voice_ids:
        return True
    if custom_voice_context is not None and custom_voice_context.is_available(voice_ref):
        return True
    return False

def _apply_assignment_to_utterance(
    utterance: dict[str, Any],
    role: str,
    character_id: int | None,
    chapter: dict[str, Any],
    db: Database,
    profile: dict[str, Any] | None,
    narrator_voice_id: str,
    narrator_result: dict[str, Any] | None,
    allowed_voice_ids: set[str],
    custom_voice_context: CustomVoiceContext | None,
    used_characters: set[int],
) -> None:
    """Apply a role/character assignment to a single utterance.

    Mutates the utterance dict in place.
    """
    # Clear previous resolution metadata
    for field in (
        "resolved_voice", "resolution_source", "resolved_gender",
        "voice_profile_id", "voice_profile_version", "needs_review",
    ):
        utterance.pop(field, None)

    if role == "narrator":
        utterance.update(
            role="narrator", character_id=None, resolved_voice_id=narrator_voice_id
        )
        if narrator_result:
            utterance.update(
                resolved_voice=narrator_result["voice"],
                resolution_source=narrator_result["resolution_source"],
                resolved_gender=narrator_result["gender"],
                voice_profile_id=narrator_result["profile_id"],
                voice_profile_version=narrator_result["profile_version"],
                needs_review=narrator_result["needs_review"],
            )
        return

    if role == "unknown":
        if profile:
            resolution = resolve_voice(
                speaker_type="dialogue", book_voice_profile=profile, custom_voice_context=custom_voice_context
            )
            resolved_voice_id = resolution["resolved_voice_id"]
        else:
            resolution = None
            resolved_voice_id = narrator_voice_id
        if not _is_allowed_voice(resolved_voice_id, allowed_voice_ids, custom_voice_context):
            raise CastingError("Unknown fallback is not available")
        utterance.update(
            role="unknown",
            character_id=None,
            resolved_voice_id=resolved_voice_id,
        )
        if resolution:
            utterance.update(
                resolved_voice=resolution["voice"],
                resolution_source=resolution["resolution_source"],
                resolved_gender=resolution["gender"],
                voice_profile_id=resolution["profile_id"],
                voice_profile_version=resolution["profile_version"],
                needs_review=True,
            )
        return

    # role == "character"
    character = db.fetch_one(
        "SELECT * FROM characters WHERE id=? AND book_id=? AND active=1",
        (character_id, chapter["book_id"]),
    )
    if not character:
        raise CastingError("Character does not belong to this book")
    if profile:
        resolution = resolve_voice(
            speaker_type="dialogue", book_voice_profile=profile, character=character,
            custom_voice_context=custom_voice_context
        )
        resolved_voice_id = resolution["resolved_voice_id"]
    else:
        resolved_voice_id = str(character["voice_override_id"] or "")
        resolution = None
        if not resolved_voice_id:
            raise CastingError(
                "Create a Book Voice Profile before using book-default character voices"
            )
    if not _is_allowed_voice(resolved_voice_id, allowed_voice_ids, custom_voice_context):
        raise CastingError("Character voice is not available")
    utterance.update(
        role="character",
        character_id=character_id,
        resolved_voice_id=resolved_voice_id,
    )
    if resolution:
        utterance.update(
            resolved_voice=resolution["voice"],
            resolution_source=resolution["resolution_source"],
            resolved_gender=resolution["gender"],
            voice_profile_id=resolution["profile_id"],
            voice_profile_version=resolution["profile_version"],
            needs_review=resolution["needs_review"],
        )
    used_characters.add(character_id)

def _validate_and_categorize_assignments(
    assignments: list[dict[str, Any]], text: str, book_id: int, db: Database
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate and categorize assignments into offset-based and utterance-id-based.

    Returns:
        (offset_assignments, utterance_assignments)

    Raises:
        CastingError: if validation fails
    """
    offset_assignments: list[dict[str, Any]] = []
    utterance_assignments: list[dict[str, Any]] = []

    for idx, assignment in enumerate(assignments):
        has_utterance_id = assignment.get("utterance_id") is not None
        has_offsets = assignment.get("start_offset") is not None and assignment.get("end_offset") is not None

        # XOR validation: exactly one mode
        if has_utterance_id and has_offsets:
            raise CastingError(
                f"Assignment {idx}: cannot specify both utterance_id and offsets"
            )
        if not has_utterance_id and not has_offsets:
            raise CastingError(
                f"Assignment {idx}: must specify either utterance_id or start_offset/end_offset"
            )

        role = assignment.get("role", "narrator")
        character_id = assignment.get("character_id")

        # Role validation
        if role not in {"narrator", "character", "unknown"}:
            raise CastingError(f"Assignment {idx}: role must be narrator, character, or unknown")

        # Character ID validation
        if role == "narrator" and character_id is not None:
            raise CastingError(f"Assignment {idx}: narrator cannot have character_id")
        if role == "unknown" and character_id is not None:
            raise CastingError(f"Assignment {idx}: unknown speaker cannot have character_id")
        if role == "character":
            if character_id is None:
                raise CastingError(f"Assignment {idx}: character role requires character_id")
            # Verify character exists, is active, and belongs to book
            character = db.fetch_one(
                "SELECT id FROM characters WHERE id=? AND book_id=? AND active=1",
                (character_id, book_id),
            )
            if not character:
                raise CastingError(
                    f"Assignment {idx}: character {character_id} does not exist, is inactive, or belongs to another book"
                )

        if has_offsets:
            start = assignment["start_offset"]
            end = assignment["end_offset"]

            # Offset validation
            if not isinstance(start, int) or not isinstance(end, int):
                raise CastingError(f"Assignment {idx}: offsets must be integers")
            if start < 0 or end < 0:
                raise CastingError(f"Assignment {idx}: offsets cannot be negative")
            if start >= end:
                raise CastingError(f"Assignment {idx}: start_offset must be less than end_offset")
            if start >= len(text) or end > len(text):
                raise CastingError(
                    f"Assignment {idx}: offsets [{start}, {end}) are out of text bounds [0, {len(text)})"
                )

            offset_assignments.append(assignment)
        else:
            utterance_assignments.append(assignment)

    # Check for overlaps in offset assignments
    if offset_assignments:
        # Sort by start_offset
        sorted_offsets = sorted(offset_assignments, key=lambda a: a["start_offset"])
        for i in range(len(sorted_offsets) - 1):
            curr = sorted_offsets[i]
            next_a = sorted_offsets[i + 1]
            if curr["end_offset"] > next_a["start_offset"]:
                raise CastingError(
                    f"Overlapping offset assignments: [{curr['start_offset']}, {curr['end_offset']}) "
                    f"and [{next_a['start_offset']}, {next_a['end_offset']})"
                )

    return offset_assignments, utterance_assignments

def create_casting_draft(
    db: Database,
    store: ContentStore,
    *,
    chapter_id: int,
    text_revision_id: int,
    narrator_voice_id: str,
    assignments: Iterable[dict[str, Any]],
    allowed_voice_ids: set[str],
    maximum: int = 256,
    source_metadata: dict[str, Any] | None = None,
    base_utterances: Iterable[dict[str, Any]] | None = None,
    custom_voice_context: CustomVoiceContext | None = None,
) -> dict[str, Any]:
    narrator_voice_id = narrator_voice_id.strip()
    revision = _revision(db, chapter_id, text_revision_id)
    chapter = db.fetch_one("SELECT id,book_id FROM chapters WHERE id=?", (chapter_id,))
    profile = get_book_voice_profile(db, int(chapter["book_id"]))
    if profile:
        validation = profile_validation(profile, allowed_voice_ids, custom_voice_context)
        if not validation["valid"]:
            missing = ", ".join(validation["missing_preset_ids"])
            raise CastingError(f"Book Voice Profile contains unavailable voice(s): {missing}")
        narrator_result = resolve_voice(
            speaker_type="narrator", book_voice_profile=profile, custom_voice_context=custom_voice_context
        )
        narrator_voice_id = narrator_result["resolved_voice_id"]
    else:
        narrator_result = None
    if not _is_allowed_voice(narrator_voice_id, allowed_voice_ids, custom_voice_context):
        raise CastingError("Narrator voice is not available")
    text = _load_casting_text_revision(store, revision)

    # Validate and categorize assignments
    assignments_list = list(assignments)
    offset_assignments, utterance_assignments = _validate_and_categorize_assignments(
        assignments_list, text, int(chapter["book_id"]), db
    )

    utterances = split_utterances(text, maximum=maximum)
    if base_utterances is not None:
        base_by_id = {
            str(item.get("utterance_id", "")): dict(item) for item in base_utterances
        }
        if set(base_by_id) != {str(item["utterance_id"]) for item in utterances}:
            raise CastingError("Base casting plan utterances do not match TextRevision")
        preserved: list[dict[str, Any]] = []
        for generated in utterances:
            base = base_by_id[str(generated["utterance_id"])]
            if any(base.get(field) != generated[field] for field in (
                "sequence", "start_offset", "end_offset", "text_sha256"
            )):
                raise CastingError("Base casting plan offsets do not match TextRevision")
            base.pop("text", None)
            preserved.append(base)
        utterances = preserved
    by_id = {utterance["utterance_id"]: utterance for utterance in utterances}
    seen: set[str] = set()
    used_characters: set[int] = {
        int(item["character_id"])
        for item in utterances
        if item.get("role") == "character" and item.get("character_id") is not None
    }

    # Process offset-based assignments first
    for assignment in offset_assignments:
        role = assignment.get("role", "narrator")
        character_id = assignment.get("character_id")
        start = assignment["start_offset"]
        end = assignment["end_offset"]

        # Find all utterances that are fully or partially contained in this span
        # An utterance matches if its range overlaps with the assignment span
        matched_utterances = [
            u for u in utterances
            if u["start_offset"] < end and u["end_offset"] > start and u["utterance_id"] not in seen
        ]

        if not matched_utterances:
            raise CastingError(
                f"Offset assignment [{start}, {end}) does not match any unassigned utterances"
            )

        # Apply assignment to all matched utterances
        for utterance in matched_utterances:
            utterance_id = utterance["utterance_id"]
            seen.add(utterance_id)

            # Apply the assignment
            _apply_assignment_to_utterance(
                utterance, role, character_id, chapter, db, profile,
                narrator_voice_id, narrator_result, allowed_voice_ids,
                custom_voice_context, used_characters
            )

    # Process utterance-ID-based assignments (existing flow)
    for assignment in utterance_assignments:
        utterance_id = str(assignment.get("utterance_id", ""))
        if utterance_id not in by_id or utterance_id in seen:
            raise CastingError("Casting assignment does not match deterministic utterances")
        seen.add(utterance_id)
        role = assignment.get("role", "narrator")
        character_id = assignment.get("character_id")
        target = by_id[utterance_id]

        _apply_assignment_to_utterance(
            target, role, character_id, chapter, db, profile,
            narrator_voice_id, narrator_result, allowed_voice_ids,
            custom_voice_context, used_characters
        )
    for utterance in utterances:
        if not utterance["resolved_voice_id"]:
            utterance["resolved_voice_id"] = narrator_voice_id
            if narrator_result:
                utterance.update(
                    resolved_voice=narrator_result["voice"],
                    resolution_source=narrator_result["resolution_source"],
                    resolved_gender=narrator_result["gender"],
                    voice_profile_id=narrator_result["profile_id"],
                    voice_profile_version=narrator_result["profile_version"],
                    needs_review=narrator_result["needs_review"],
                )

    payload = {
        "schema_version": CASTING_SCHEMA_VERSION,
        "chunker_version": CHUNKER_VERSION,
        "chapter_id": chapter_id,
        "text_revision_id": text_revision_id,
        "narrator_voice_id": narrator_voice_id,
        "book_voice_profile": (
            {
                "id": int(profile["id"]),
                "config_version": int(profile["config_version"]),
                "narrator_voice_id": profile["narrator_voice_id"],
                "male_dialogue_voice_id": profile["male_dialogue_voice_id"],
                "female_dialogue_voice_id": profile["female_dialogue_voice_id"],
                "unknown_fallback": profile["unknown_fallback"],
                "unknown_voice_id": profile["unknown_voice_id"],
            }
            if profile
            else None
        ),
        "utterances": utterances,
    }
    if source_metadata is not None:
        payload["source_metadata"] = source_metadata
    content_path, plan_sha = store.put_json(payload, namespace="casting")
    now = utcnow()
    with db.transaction() as connection:
        next_revision = int(
            connection.execute(
                "SELECT COALESCE(MAX(plan_revision),0)+1 FROM casting_plans WHERE chapter_id=?",
                (chapter_id,),
            ).fetchone()[0]
        )
        plan_id = int(
            connection.execute(
                """INSERT INTO casting_plans(
                    chapter_id,text_revision_id,plan_revision,status,content_path,plan_sha256,
                    narrator_voice_id,created_at
                ) VALUES(?,?,?,'draft',?,?,?,?)""",
                (chapter_id, text_revision_id, next_revision, content_path, plan_sha, narrator_voice_id, now),
            ).lastrowid
        )
        for character_id in sorted(used_characters):
            connection.execute(
                "INSERT INTO casting_plan_characters(casting_plan_id,character_id) VALUES(?,?)",
                (plan_id, character_id),
            )
    return get_plan(db, store, plan_id, include_text=True)

def get_plan(db: Database, store: ContentStore, plan_id: int, include_text: bool = False) -> dict[str, Any]:
    row = db.fetch_one("SELECT * FROM casting_plans WHERE id=?", (plan_id,))
    if not row:
        raise CastingError("Casting plan not found")
    plan = store.read_json(row["content_path"])
    if sha256_text(json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))) != row["plan_sha256"]:
        raise CastingError("Casting plan hash mismatch")
    result = dict(row)
    result["plan"] = plan
    if include_text:
        revision = _revision(db, int(row["chapter_id"]), int(row["text_revision_id"]))
        text = store.read_text(revision["content_path"])
        for utterance in result["plan"]["utterances"]:
            utterance["text"] = text[utterance["start_offset"] : utterance["end_offset"]]
    return result

def casting_context(
    db: Database,
    store: ContentStore,
    chapter_id: int,
    allowed_voice_ids: set[str] | None = None,
    custom_voice_context: CustomVoiceContext | None = None,
) -> dict[str, Any]:
    chapter = db.fetch_one("SELECT * FROM chapters WHERE id=?", (chapter_id,))
    if not chapter:
        raise CastingError("Chapter not found")
    revision = _revision(db, chapter_id)
    latest = db.fetch_one(
        "SELECT id FROM casting_plans WHERE chapter_id=? ORDER BY plan_revision DESC LIMIT 1",
        (chapter_id,),
    )
    if latest:
        plan = get_plan(db, store, int(latest["id"]), include_text=True)
    else:
        text = store.read_text(revision["content_path"])
        utterances = split_utterances(text)
        for utterance in utterances:
            utterance["text"] = text[utterance["start_offset"] : utterance["end_offset"]]
        plan = {
            "id": None,
            "chapter_id": chapter_id,
            "text_revision_id": int(revision["id"]),
            "plan_revision": 0,
            "status": "new",
            "narrator_voice_id": "",
            "plan": {"utterances": utterances},
        }
    profile = get_book_voice_profile(db, int(chapter["book_id"]))
    characters = list_characters(db, int(chapter["book_id"]))
    for character in characters:
        if profile:
            character["effective_resolution"] = resolve_voice(
                speaker_type="dialogue",
                book_voice_profile=profile,
                character=character,
                custom_voice_context=custom_voice_context,
            )
        elif character.get("voice_override_id"):
            legacy_voice = str(character["voice_override_id"])
            character["effective_resolution"] = {
                "voice": preset_ref(legacy_voice),
                "resolved_voice_id": legacy_voice,
                "resolution_source": "character_override",
                "character_id": int(character["id"]),
                "gender": character.get("gender") or "unknown",
                "profile_id": None,
                "profile_version": None,
                "needs_review": False,
            }
        else:
            character["effective_resolution"] = None
    profile_state: dict[str, Any] = {
        "configured": bool(profile),
        "profile": profile,
        "validation": None,
        "narrator_resolution": None,
        "unknown_resolution": None,
    }
    if profile:
        profile_state["narrator_resolution"] = resolve_voice(
            speaker_type="narrator", book_voice_profile=profile, custom_voice_context=custom_voice_context
        )
        profile_state["unknown_resolution"] = resolve_voice(
            speaker_type="dialogue", book_voice_profile=profile, custom_voice_context=custom_voice_context
        )
        if allowed_voice_ids is not None:
            profile_state["validation"] = profile_validation(profile, allowed_voice_ids, custom_voice_context)
    return {
        "chapter": {"id": chapter_id, "book_id": chapter["book_id"], "title": chapter["title"]},
        "characters": characters,
        "voice_profile": profile_state,
        "casting": plan,
    }

def approve_plan(db: Database, store: ContentStore, plan_id: int) -> dict[str, Any]:
    row = db.fetch_one("SELECT * FROM casting_plans WHERE id=?", (plan_id,))
    if not row:
        raise CastingError("Casting plan not found")
    if row["status"] == "approved":
        return get_plan(db, store, plan_id, include_text=True)
    if row["status"] != "draft":
        raise CastingError("Only a draft casting plan can be approved")
    get_plan(db, store, plan_id)
    revision = _revision(db, int(row["chapter_id"]), int(row["text_revision_id"]))
    _load_casting_text_revision(store, revision)
    now = utcnow()
    with db.transaction() as connection:
        connection.execute(
            "UPDATE casting_plans SET status='archived',archived_at=? WHERE chapter_id=? AND status='approved'",
            (now, row["chapter_id"]),
        )
        connection.execute(
            "UPDATE casting_plans SET status='approved',approved_at=? WHERE id=? AND status='draft'",
            (now, plan_id),
        )
    return get_plan(db, store, plan_id, include_text=True)

def validate_approved_plan(
    db: Database,
    store: ContentStore,
    plan_id: int,
    allowed_voice_ids: set[str] | None = None,
    custom_voice_context: CustomVoiceContext | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    row = db.fetch_one(
        """SELECT cp.*,c.book_id FROM casting_plans cp
           JOIN chapters c ON c.id=cp.chapter_id WHERE cp.id=?""",
        (plan_id,),
    )
    if not row or row["status"] != "approved":
        raise CastingError("Casting plan must be approved")
    result = get_plan(db, store, plan_id)
    plan = result["plan"]
    revision = _revision(db, int(row["chapter_id"]), int(row["text_revision_id"]))
    _load_casting_text_revision(store, revision)
    voices = {plan["narrator_voice_id"]}
    for utterance in plan["utterances"]:
        voices.add(utterance["resolved_voice_id"])
        if utterance["role"] == "character":
            character = db.fetch_one(
                "SELECT id FROM characters WHERE id=? AND book_id=?",
                (utterance["character_id"], row["book_id"]),
            )
            if not character:
                raise CastingError("Casting plan references a character from another book")

    # Validate all voices (preset and custom)
    if allowed_voice_ids is not None:
        from .voice_ref import is_custom_ref, parse_custom_ref
        for voice_id in voices:
            if is_custom_ref(voice_id):
                # Validate custom voice
                try:
                    custom_id = parse_custom_ref(voice_id)
                    if custom_voice_context is None or custom_voice_context.get(custom_id) is None:
                        raise CastingError(f"Casting plan contains unavailable custom voice: {voice_id}")
                except Exception as e:
                    raise CastingError(f"Casting plan contains invalid custom voice: {e}") from e
            elif voice_id not in allowed_voice_ids:
                raise CastingError("Casting plan contains an unavailable voice")
    return dict(row), plan
