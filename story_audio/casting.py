from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Iterable

from .db import Database, utcnow
from .files import sha256_text
from .storage import ContentStore
from .voice_profile import get_book_voice_profile, preset_ref, profile_validation, resolve_voice


CASTING_SCHEMA_VERSION = 1
CHUNKER_VERSION = "utterance-v1"
TERMINALS = ".!?…"
OPEN_QUOTES = {'"', "“"}
CLOSE_QUOTES = {'"', "”"}


class CastingError(ValueError):
    pass


def _trim(text: str, start: int, end: int) -> tuple[int, int] | None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if start < end else None


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
            cut = max(
                text.rfind(", ", left, left + maximum),
                text.rfind("; ", left, left + maximum),
                text.rfind(": ", left, left + maximum),
                text.rfind(" ", left, left + maximum),
            )
            cut = cut + 1 if cut > left + maximum // 2 else left + maximum
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


def list_characters(db: Database, book_id: int, include_inactive: bool = False) -> list[dict[str, Any]]:
    suffix = "" if include_inactive else " AND active=1"
    return [
        dict(row)
        for row in db.fetch_all(
            f"SELECT * FROM characters WHERE book_id=?{suffix} ORDER BY display_name,id", (book_id,)
        )
    ]


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
    if gender not in {None, "male", "female", "unknown"}:
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
) -> dict[str, Any]:
    row = db.fetch_one("SELECT * FROM characters WHERE id=? AND active=1", (character_id,))
    if not row:
        raise CastingError("Character not found")
    name = display_name.strip() if display_name is not None else row["display_name"]
    voice = voice_id.strip() if voice_id is not None else row["voice_override_id"]
    resolved_gender = gender if gender is not None else row["gender"]
    if not name or (resolved_gender is not None and resolved_gender not in {"male", "female", "unknown"}):
        raise CastingError("Character name or gender is invalid")
    with db.connect() as connection:
        connection.execute(
            """UPDATE characters SET display_name=?,default_voice_id=?,voice_override_id=?,
               gender=?,updated_at=? WHERE id=?""",
            (name, voice or "", voice or None, resolved_gender, utcnow(), character_id),
        )
    return dict(db.fetch_one("SELECT * FROM characters WHERE id=?", (character_id,)))


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
) -> dict[str, Any]:
    narrator_voice_id = narrator_voice_id.strip()
    revision = _revision(db, chapter_id, text_revision_id)
    chapter = db.fetch_one("SELECT id,book_id FROM chapters WHERE id=?", (chapter_id,))
    profile = get_book_voice_profile(db, int(chapter["book_id"]))
    if profile:
        validation = profile_validation(profile, allowed_voice_ids)
        if not validation["valid"]:
            missing = ", ".join(validation["missing_preset_ids"])
            raise CastingError(f"Book Voice Profile contains unavailable preset(s): {missing}")
        narrator_result = resolve_voice(
            speaker_type="narrator", book_voice_profile=profile
        )
        narrator_voice_id = narrator_result["resolved_voice_id"]
    else:
        narrator_result = None
    if narrator_voice_id not in allowed_voice_ids:
        raise CastingError("Narrator voice is not an available preset")
    text = store.read_text(revision["content_path"])
    utterances = split_utterances(text, maximum=maximum)
    by_id = {utterance["utterance_id"]: utterance for utterance in utterances}
    seen: set[str] = set()
    used_characters: set[int] = set()
    for assignment in assignments:
        utterance_id = str(assignment.get("utterance_id", ""))
        if utterance_id not in by_id or utterance_id in seen:
            raise CastingError("Casting assignment does not match deterministic utterances")
        seen.add(utterance_id)
        role = assignment.get("role", "narrator")
        target = by_id[utterance_id]
        if role == "narrator":
            target["resolved_voice_id"] = narrator_voice_id
            if narrator_result:
                target.update(
                    resolved_voice=narrator_result["voice"],
                    resolution_source=narrator_result["resolution_source"],
                    resolved_gender=narrator_result["gender"],
                    voice_profile_id=narrator_result["profile_id"],
                    voice_profile_version=narrator_result["profile_version"],
                    needs_review=narrator_result["needs_review"],
                )
            continue
        if role != "character" or assignment.get("character_id") is None:
            raise CastingError("Speaker must be narrator or a character")
        character_id = int(assignment["character_id"])
        character = db.fetch_one(
            "SELECT * FROM characters WHERE id=? AND book_id=? AND active=1",
            (character_id, chapter["book_id"]),
        )
        if not character:
            raise CastingError("Character does not belong to this book")
        if profile:
            resolution = resolve_voice(
                speaker_type="dialogue", book_voice_profile=profile, character=character
            )
            resolved_voice_id = resolution["resolved_voice_id"]
        else:
            resolved_voice_id = str(character["voice_override_id"] or "")
            resolution = None
            if not resolved_voice_id:
                raise CastingError(
                    "Create a Book Voice Profile before using book-default character voices"
                )
        if resolved_voice_id not in allowed_voice_ids:
            raise CastingError("Character voice is not an available preset")
        target.update(
            role="character",
            character_id=character_id,
            resolved_voice_id=resolved_voice_id,
        )
        if resolution:
            target.update(
                resolved_voice=resolution["voice"],
                resolution_source=resolution["resolution_source"],
                resolved_gender=resolution["gender"],
                voice_profile_id=resolution["profile_id"],
                voice_profile_version=resolution["profile_version"],
                needs_review=resolution["needs_review"],
            )
        used_characters.add(character_id)
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
    }
    if profile:
        profile_state["narrator_resolution"] = resolve_voice(
            speaker_type="narrator", book_voice_profile=profile
        )
        if allowed_voice_ids is not None:
            profile_state["validation"] = profile_validation(profile, allowed_voice_ids)
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
    db: Database, store: ContentStore, plan_id: int, allowed_voice_ids: set[str] | None = None
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
    if allowed_voice_ids is not None and not voices <= allowed_voice_ids:
        raise CastingError("Casting plan contains an unavailable preset voice")
    return dict(row), plan
