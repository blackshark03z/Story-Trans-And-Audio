from __future__ import annotations

import json
import sqlite3
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .casting import (
    CastingError,
    build_casting_plan_payload,
    get_plan,
    split_utterances,
)
from .character_bible import normalize_identity
from .db import Database, utcnow
from .files import sha256_text
from .storage import ContentStore
from .voice_eligibility import EffectiveVoiceCatalog
from .voice_ref import CustomVoiceContext


UNRESOLVED_DIALOGUE_ROLE = "unresolved_dialogue"
UNRESOLVED_DIALOGUE_STATUS = "UNRESOLVED_DIALOGUE"
UNRESOLVED_DIALOGUE_PREFIX = "unresolved-dialogue"


class CharacterAssignmentError(ValueError):
    """Fail-closed error for durable character/speaker assignment changes."""


@dataclass(frozen=True)
class UnresolvedDialogueReference:
    chapter_id: int
    chapter_number: int
    utterance_id: str
    sequence: int
    text: str
    role: str
    character_id: int | None

    @property
    def speaker_key(self) -> str:
        return unresolved_dialogue_speaker_key(self.chapter_id, self.utterance_id)

    def public_payload(self) -> dict[str, Any]:
        return {
            "chapter_id": self.chapter_id,
            "chapter_number": self.chapter_number,
            "utterance_id": self.utterance_id,
            "sequence": self.sequence,
            "text": self.text,
            "role": self.role,
            "character_id": self.character_id,
        }


@dataclass(frozen=True)
class _PreparedMappingPlan:
    chapter_id: int
    chapter_number: int
    previous_plan_id: int
    previous_plan_sha256: str
    text_revision_id: int
    plan_revision: int
    content_path: str
    plan_sha256: str
    narrator_voice_id: str
    character_ids: tuple[int, ...]
    target_utterance_ids: tuple[str, ...]
    reused: bool


def clean_display_name(value: str, *, maximum: int = 120) -> str:
    cleaned = " ".join(unicodedata.normalize("NFC", str(value or "")).strip().split())
    if not cleaned:
        raise CharacterAssignmentError("Character name is required")
    if len(cleaned) > maximum:
        raise CharacterAssignmentError("Character name is too long")
    return cleaned


def unresolved_dialogue_speaker_key(chapter_id: int, utterance_id: str) -> str:
    return f"{UNRESOLVED_DIALOGUE_PREFIX}:{int(chapter_id)}:{str(utterance_id)}"


def parse_unresolved_dialogue_speaker_key(speaker_key: str) -> tuple[int, str]:
    parts = str(speaker_key or "").split(":", 2)
    if len(parts) != 3 or parts[0] != UNRESOLVED_DIALOGUE_PREFIX:
        raise CharacterAssignmentError("Unsupported unresolved speaker key")
    try:
        chapter_id = int(parts[1])
    except ValueError as exc:
        raise CharacterAssignmentError("Invalid unresolved speaker chapter") from exc
    utterance_id = parts[2].strip()
    if not utterance_id:
        raise CharacterAssignmentError("Invalid unresolved speaker utterance")
    return chapter_id, utterance_id


def is_unresolved_dialogue_text(text: str) -> bool:
    stripped = str(text or "").strip()
    return stripped.startswith("-") or stripped.startswith("–") or stripped.startswith("—")


def unresolved_dialogue_references(
    *,
    chapter: Mapping[str, Any],
    text: str,
    utterances: Iterable[Mapping[str, Any]],
) -> list[UnresolvedDialogueReference]:
    references: list[UnresolvedDialogueReference] = []
    for utterance in utterances:
        role = str(utterance.get("role") or "narrator")
        character_id = utterance.get("character_id")
        if role != "narrator" or character_id is not None:
            continue
        start = int(utterance["start_offset"])
        end = int(utterance["end_offset"])
        line = text[start:end].strip()
        if not is_unresolved_dialogue_text(line):
            continue
        references.append(
            UnresolvedDialogueReference(
                chapter_id=int(chapter["id"]),
                chapter_number=int(chapter["chapter_number"]),
                utterance_id=str(utterance["utterance_id"]),
                sequence=int(utterance["sequence"]),
                text=line,
                role=role,
                character_id=None,
            )
        )
    return references


def unresolved_dialogue_references_from_text(
    *,
    chapter: Mapping[str, Any],
    text: str,
) -> list[UnresolvedDialogueReference]:
    return unresolved_dialogue_references(
        chapter=chapter,
        text=text,
        utterances=split_utterances(text),
    )


def _chapter_rows(
    db: Database,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
) -> list[dict[str, Any]]:
    if from_chapter > to_chapter:
        raise CharacterAssignmentError("from_chapter must be less than or equal to to_chapter")
    rows = db.fetch_all(
        """
        SELECT id,book_id,chapter_number,title,active_text_revision_id,
               active_audio_artifact_id,audio_status
        FROM chapters
        WHERE book_id=? AND chapter_number BETWEEN ? AND ?
        ORDER BY chapter_number,id
        """,
        (book_id, from_chapter, to_chapter),
    )
    chapters = [dict(row) for row in rows]
    expected = list(range(from_chapter, to_chapter + 1))
    actual = [int(row["chapter_number"]) for row in chapters]
    if actual != expected:
        raise CharacterAssignmentError("Selected range must contain every requested chapter")
    return chapters


def _latest_approved_plan_row(db: Database, chapter_id: int) -> dict[str, Any]:
    row = db.fetch_one(
        """
        SELECT *
        FROM casting_plans
        WHERE chapter_id=? AND status='approved'
        ORDER BY plan_revision DESC,id DESC
        LIMIT 1
        """,
        (chapter_id,),
    )
    if not row:
        raise CharacterAssignmentError("Approved Final Voice Map is missing")
    return dict(row)


def _canonical_plan_sha(payload: Mapping[str, Any]) -> str:
    return sha256_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _assignments_from_plan(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "utterance_id": str(item["utterance_id"]),
            "role": str(item.get("role") or "narrator"),
            "character_id": item.get("character_id"),
        }
        for item in payload.get("utterances") or []
        if isinstance(item, Mapping)
    ]


def _all_plan_voice_ids(payload: Mapping[str, Any]) -> set[str]:
    voices = {
        str(item.get("resolved_voice_id") or "").strip()
        for item in payload.get("utterances") or []
        if isinstance(item, Mapping)
    }
    narrator = str(payload.get("narrator_voice_id") or "").strip()
    if narrator:
        voices.add(narrator)
    return {voice for voice in voices if voice}


def _book_configured_voice_ids(db: Database, book_id: int) -> set[str]:
    voices: set[str] = set()
    profile = db.fetch_one("SELECT * FROM book_voice_profiles WHERE book_id=?", (book_id,))
    if profile:
        for key in (
            "narrator_voice_id",
            "male_dialogue_voice_id",
            "female_dialogue_voice_id",
            "unknown_voice_id",
        ):
            value = str(profile[key] or "").strip()
            if value:
                voices.add(value)
    for row in db.fetch_all(
        "SELECT voice_override_id,default_voice_id FROM characters WHERE book_id=? AND active=1",
        (book_id,),
    ):
        for key in ("voice_override_id", "default_voice_id"):
            value = str(row[key] or "").strip()
            if value:
                voices.add(value)
    return voices


def _character_row(db: Database, *, book_id: int, character_id: int) -> dict[str, Any]:
    row = db.fetch_one(
        "SELECT * FROM characters WHERE id=? AND book_id=? AND active=1",
        (character_id, book_id),
    )
    if not row:
        raise CharacterAssignmentError("Character was not found in this book")
    return dict(row)


def _find_character_by_identity(db: Database, *, book_id: int, name: str) -> dict[str, Any] | None:
    identity = normalize_identity(name)
    row = db.fetch_one(
        """
        SELECT *
        FROM characters
        WHERE book_id=? AND active=1
          AND (
            lower(display_name)=lower(?)
            OR canonical_name_normalized=?
            OR external_key_normalized=?
          )
        ORDER BY id
        LIMIT 1
        """,
        (book_id, name, identity, identity),
    )
    if row:
        return dict(row)
    alias = db.fetch_one(
        """
        SELECT c.*
        FROM character_aliases ca
        JOIN characters c ON c.id=ca.character_id
        WHERE ca.book_id=? AND c.active=1 AND ca.alias_normalized=?
        ORDER BY c.id
        LIMIT 1
        """,
        (book_id, identity),
    )
    return dict(alias) if alias else None


def _aliases_for_character(db: Database, character_id: int) -> list[str]:
    return [
        str(row["alias"])
        for row in db.fetch_all(
            "SELECT alias FROM character_aliases WHERE character_id=? ORDER BY alias,id",
            (character_id,),
        )
    ]


def _clean_alias_pairs(aliases: Iterable[str]) -> list[tuple[str, str]]:
    cleaned: list[tuple[str, str]] = []
    seen: set[str] = set()
    for alias in aliases:
        if not str(alias or "").strip():
            continue
        value = clean_display_name(alias)
        normalized = normalize_identity(value)
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append((value, normalized))
    return cleaned


def _validate_aliases_available(
    db: Database,
    *,
    book_id: int,
    character_id: int,
    alias_pairs: Iterable[tuple[str, str]],
) -> None:
    for _alias, normalized in alias_pairs:
        owner = db.fetch_one(
            """
            SELECT ca.character_id,c.display_name
            FROM character_aliases ca
            JOIN characters c ON c.id=ca.character_id
            WHERE ca.book_id=? AND ca.alias_normalized=? AND c.active=1
            ORDER BY ca.id
            LIMIT 1
            """,
            (book_id, normalized),
        )
        if owner and int(owner["character_id"]) != character_id:
            raise CharacterAssignmentError(
                f"Alias already belongs to {owner['display_name']}"
            )


def _insert_alias_pairs(
    connection: sqlite3.Connection,
    *,
    book_id: int,
    character_id: int,
    alias_pairs: Iterable[tuple[str, str]],
    idempotency_key: str | None,
    now: str,
) -> dict[str, Any]:
    added: list[dict[str, Any]] = []
    reused: list[dict[str, Any]] = []
    source_sha = sha256_text(
        f"assignment-alias\0{book_id}\0{character_id}\0{idempotency_key or ''}"
    )
    for alias, normalized in alias_pairs:
        owner = connection.execute(
            """
            SELECT ca.id,ca.character_id,c.display_name
            FROM character_aliases ca
            JOIN characters c ON c.id=ca.character_id
            WHERE ca.book_id=? AND ca.alias_normalized=? AND c.active=1
            ORDER BY ca.id
            LIMIT 1
            """,
            (book_id, normalized),
        ).fetchone()
        if owner and int(owner["character_id"]) != character_id:
            raise CharacterAssignmentError(
                f"Alias already belongs to {owner['display_name']}"
            )
        if owner:
            reused.append({"alias": alias, "alias_id": int(owner["id"])})
            continue
        alias_id = int(
            connection.execute(
                """INSERT INTO character_aliases(
                    book_id,character_id,alias,alias_normalized,source_sha256,created_at
                ) VALUES(?,?,?,?,?,?)""",
                (book_id, character_id, alias, normalized, source_sha, now),
            ).lastrowid
        )
        added.append({"alias": alias, "alias_id": alias_id})
    return {
        "character_id": character_id,
        "aliases": added + reused,
        "added_count": len(added),
        "reused_count": len(reused),
    }


def create_assignment_character(
    db: Database,
    *,
    book_id: int,
    display_name: str,
    aliases: Iterable[str] = (),
    gender: str | None = None,
    role: str = "unknown",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    name = clean_display_name(display_name)
    if gender not in {"male", "female", "unknown", None}:
        raise CharacterAssignmentError("Character gender is invalid")
    if role not in {"main", "supporting", "minor", "unknown"}:
        raise CharacterAssignmentError("Character role is invalid")
    if not db.fetch_one("SELECT id FROM books WHERE id=?", (book_id,)):
        raise CharacterAssignmentError("Book not found")
    existing = _find_character_by_identity(db, book_id=book_id, name=name)
    alias_pairs = _clean_alias_pairs(aliases)
    if existing:
        added = add_character_aliases(
            db,
            book_id=book_id,
            character_id=int(existing["id"]),
            aliases=[alias for alias, _normalized in alias_pairs],
            idempotency_key=idempotency_key,
        )
        existing["aliases"] = _aliases_for_character(db, int(existing["id"]))
        return {"character": existing, "created": False, "reused": True, "aliases": added["aliases"]}

    identity = normalize_identity(name)
    now = utcnow()
    try:
        # Validate before opening the write transaction so duplicate aliases fail
        # without leaving a newly created character behind.
        _validate_aliases_available(
            db,
            book_id=book_id,
            character_id=-1,
            alias_pairs=alias_pairs,
        )
        with db.transaction() as connection:
            character_id = int(
                connection.execute(
                    """INSERT INTO characters(
                        book_id,display_name,default_voice_id,active,created_at,updated_at,
                        gender,voice_override_id,external_key,external_key_normalized,
                        canonical_name,canonical_name_normalized,role,notes
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        book_id,
                        name,
                        "",
                        1,
                        now,
                        now,
                        gender or "unknown",
                        None,
                        f"assignment:{identity}",
                        f"assignment:{identity}",
                        name,
                        identity,
                        role,
                        f"Created from Assignment command {idempotency_key or ''}".strip(),
                    ),
                ).lastrowid
            )
            alias_result = _insert_alias_pairs(
                connection,
                book_id=book_id,
                character_id=character_id,
                alias_pairs=alias_pairs,
                idempotency_key=idempotency_key,
                now=now,
            )
    except sqlite3.IntegrityError as exc:
        raise CharacterAssignmentError("Character name already exists in this book") from exc

    character = _character_row(db, book_id=book_id, character_id=character_id)
    character["aliases"] = _aliases_for_character(db, character_id)
    return {
        "character": character,
        "created": True,
        "reused": False,
        "aliases": alias_result["aliases"],
    }


def add_character_aliases(
    db: Database,
    *,
    book_id: int,
    character_id: int,
    aliases: Iterable[str],
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    _character_row(db, book_id=book_id, character_id=character_id)
    cleaned = _clean_alias_pairs(aliases)
    if not cleaned:
        return {"character_id": character_id, "aliases": [], "added_count": 0, "reused_count": 0}
    now = utcnow()
    with db.transaction() as connection:
        return _insert_alias_pairs(
            connection,
            book_id=book_id,
            character_id=character_id,
            alias_pairs=cleaned,
            idempotency_key=idempotency_key,
            now=now,
        )


def _target_utterance_ids(
    *,
    speaker_key: str,
    chapter: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    if speaker_key.startswith(f"{UNRESOLVED_DIALOGUE_PREFIX}:"):
        target_chapter_id, utterance_id = parse_unresolved_dialogue_speaker_key(speaker_key)
        if target_chapter_id != int(chapter["id"]):
            return ()
        return (utterance_id,)
    if speaker_key == "unknown":
        return tuple(
            str(item["utterance_id"])
            for item in payload.get("utterances") or []
            if isinstance(item, Mapping) and str(item.get("role") or "") == "unknown"
        )
    if speaker_key.startswith("character:"):
        try:
            source_character_id = int(speaker_key.split(":", 1)[1])
        except ValueError as exc:
            raise CharacterAssignmentError("Invalid character speaker key") from exc
        return tuple(
            str(item["utterance_id"])
            for item in payload.get("utterances") or []
            if isinstance(item, Mapping)
            and str(item.get("role") or "") == "character"
            and int(item.get("character_id") or 0) == source_character_id
        )
    raise CharacterAssignmentError("Unsupported speaker key")


def _prepare_mapping_plan(
    db: Database,
    store: ContentStore,
    *,
    chapter: Mapping[str, Any],
    speaker_key: str,
    target_role: str,
    character_id: int | None,
    voice_catalog: EffectiveVoiceCatalog,
    source_metadata: Mapping[str, Any],
    custom_voice_context: CustomVoiceContext | None,
) -> _PreparedMappingPlan | None:
    plan_row = _latest_approved_plan_row(db, int(chapter["id"]))
    if int(plan_row["text_revision_id"]) != int(chapter.get("active_text_revision_id") or 0):
        raise CharacterAssignmentError(
            f"Final Voice Map is stale for Chapter {int(chapter['chapter_number'])}"
        )
    current = get_plan(db, store, int(plan_row["id"]))
    current_payload = current["plan"]
    target_ids = _target_utterance_ids(
        speaker_key=speaker_key,
        chapter=chapter,
        payload=current_payload,
    )
    if not target_ids:
        return None
    existing_ids = {
        str(item["utterance_id"])
        for item in current_payload.get("utterances") or []
        if isinstance(item, Mapping)
    }
    missing = sorted(set(target_ids) - existing_ids)
    if missing:
        raise CharacterAssignmentError("Speaker mapping target no longer exists")
    assignments = _assignments_from_plan(current_payload)
    target_set = set(target_ids)
    for assignment in assignments:
        if assignment["utterance_id"] not in target_set:
            continue
        assignment["role"] = target_role
        assignment["character_id"] = character_id if target_role == "character" else None
    build_allowed_voice_ids = (
        set(voice_catalog.selectable_ids)
        | _all_plan_voice_ids(current_payload)
        | _book_configured_voice_ids(db, int(chapter["book_id"]))
    )
    built = build_casting_plan_payload(
        db,
        store,
        chapter_id=int(chapter["id"]),
        text_revision_id=int(plan_row["text_revision_id"]),
        narrator_voice_id=str(current_payload.get("narrator_voice_id") or ""),
        assignments=assignments,
        allowed_voice_ids=build_allowed_voice_ids,
        source_metadata=dict(source_metadata),
        base_utterances=current_payload.get("utterances") or [],
        custom_voice_context=custom_voice_context,
    )
    plan_sha = _canonical_plan_sha(built.payload)
    content_path, stored_sha = store.put_json(built.payload, namespace="casting")
    if stored_sha != plan_sha:
        raise CharacterAssignmentError("Generated Casting Plan hash mismatch")
    return _PreparedMappingPlan(
        chapter_id=int(chapter["id"]),
        chapter_number=int(chapter["chapter_number"]),
        previous_plan_id=int(plan_row["id"]),
        previous_plan_sha256=str(plan_row["plan_sha256"]),
        text_revision_id=int(plan_row["text_revision_id"]),
        plan_revision=int(plan_row["plan_revision"]),
        content_path=content_path,
        plan_sha256=plan_sha,
        narrator_voice_id=built.narrator_voice_id,
        character_ids=tuple(sorted(built.used_characters)),
        target_utterance_ids=target_ids,
        reused=plan_sha == str(plan_row["plan_sha256"]),
    )


def apply_speaker_character_mapping(
    db: Database,
    store: ContentStore,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    speaker_key: str,
    character_id: int,
    aliases: Iterable[str],
    voice_catalog: EffectiveVoiceCatalog,
    idempotency_key: str,
    custom_voice_context: CustomVoiceContext | None = None,
) -> dict[str, Any]:
    normalized_speaker = str(speaker_key or "").strip()
    _character_row(db, book_id=book_id, character_id=character_id)
    alias_pairs = _clean_alias_pairs(aliases)
    _validate_aliases_available(
        db,
        book_id=book_id,
        character_id=character_id,
        alias_pairs=alias_pairs,
    )
    chapters = _chapter_rows(
        db,
        book_id=book_id,
        from_chapter=from_chapter,
        to_chapter=to_chapter,
    )
    source_metadata = {
        "source": "speaker_character_mapping",
        "operation": "map",
        "speaker_key": normalized_speaker,
        "character_id": character_id,
        "aliases": [alias for alias, _normalized in alias_pairs],
        "scope": {
            "book_id": book_id,
            "from_chapter": from_chapter,
            "to_chapter": to_chapter,
            "chapter_count": len(chapters),
        },
        "idempotency_key": idempotency_key,
    }
    prepared = [
        item
        for item in (
            _prepare_mapping_plan(
                db,
                store,
                chapter=chapter,
                speaker_key=normalized_speaker,
                target_role="character",
                character_id=character_id,
                voice_catalog=voice_catalog,
                source_metadata=source_metadata,
                custom_voice_context=custom_voice_context,
            )
            for chapter in chapters
        )
        if item is not None
    ]
    if not prepared:
        raise CharacterAssignmentError("Speaker does not appear in the selected scope")
    return _commit_mapping_plans(
        db,
        prepared,
        "map",
        normalized_speaker,
        character_id,
        alias_pairs,
        book_id=book_id,
        idempotency_key=idempotency_key,
    )


def clear_speaker_character_mapping(
    db: Database,
    store: ContentStore,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    speaker_key: str,
    voice_catalog: EffectiveVoiceCatalog,
    idempotency_key: str,
    custom_voice_context: CustomVoiceContext | None = None,
) -> dict[str, Any]:
    normalized_speaker = str(speaker_key or "").strip()
    chapters = _chapter_rows(
        db,
        book_id=book_id,
        from_chapter=from_chapter,
        to_chapter=to_chapter,
    )
    source_metadata = {
        "source": "speaker_character_mapping",
        "operation": "clear",
        "speaker_key": normalized_speaker,
        "scope": {
            "book_id": book_id,
            "from_chapter": from_chapter,
            "to_chapter": to_chapter,
            "chapter_count": len(chapters),
        },
        "idempotency_key": idempotency_key,
    }
    prepared = [
        item
        for item in (
            _prepare_mapping_plan(
                db,
                store,
                chapter=chapter,
                speaker_key=normalized_speaker,
                target_role="narrator",
                character_id=None,
                voice_catalog=voice_catalog,
                source_metadata=source_metadata,
                custom_voice_context=custom_voice_context,
            )
            for chapter in chapters
        )
        if item is not None
    ]
    if not prepared:
        raise CharacterAssignmentError("Speaker does not appear in the selected scope")
    return _commit_mapping_plans(
        db,
        prepared,
        "clear",
        normalized_speaker,
        None,
        (),
        book_id=book_id,
        idempotency_key=idempotency_key,
    )


def _commit_mapping_plans(
    db: Database,
    prepared: list[_PreparedMappingPlan],
    operation: str,
    speaker_key: str,
    character_id: int | None,
    alias_pairs: Iterable[tuple[str, str]],
    *,
    book_id: int,
    idempotency_key: str,
) -> dict[str, Any]:
    applied: list[dict[str, Any]] = []
    now = utcnow()
    alias_result: dict[str, Any] = {
        "character_id": character_id,
        "aliases": [],
        "added_count": 0,
        "reused_count": 0,
    }
    with db.transaction() as connection:
        if character_id is not None:
            alias_result = _insert_alias_pairs(
                connection,
                book_id=book_id,
                character_id=character_id,
                alias_pairs=alias_pairs,
                idempotency_key=idempotency_key,
                now=now,
            )
        for item in prepared:
            latest = connection.execute(
                """
                SELECT id,status,plan_revision,plan_sha256
                FROM casting_plans
                WHERE chapter_id=?
                ORDER BY plan_revision DESC,id DESC
                LIMIT 1
                """,
                (item.chapter_id,),
            ).fetchone()
            if (
                not latest
                or int(latest["id"]) != item.previous_plan_id
                or str(latest["status"]) != "approved"
                or str(latest["plan_sha256"]) != item.previous_plan_sha256
            ):
                raise CharacterAssignmentError(
                    f"Chapter {item.chapter_number} voice map changed while saving"
                )
            if item.reused:
                applied.append(
                    {
                        "chapter_id": item.chapter_id,
                        "chapter_number": item.chapter_number,
                        "casting_plan_id": item.previous_plan_id,
                        "plan_revision": item.plan_revision,
                        "utterance_ids": list(item.target_utterance_ids),
                        "reused": True,
                    }
                )
                continue
            next_revision = int(latest["plan_revision"]) + 1
            connection.execute(
                "UPDATE casting_plans SET status='archived',archived_at=? WHERE id=? AND status='approved'",
                (now, item.previous_plan_id),
            )
            plan_id = int(
                connection.execute(
                    """INSERT INTO casting_plans(
                        chapter_id,text_revision_id,plan_revision,status,content_path,
                        plan_sha256,narrator_voice_id,created_at,approved_at
                    ) VALUES(?,?,?,'approved',?,?,?,?,?)""",
                    (
                        item.chapter_id,
                        item.text_revision_id,
                        next_revision,
                        item.content_path,
                        item.plan_sha256,
                        item.narrator_voice_id,
                        now,
                        now,
                    ),
                ).lastrowid
            )
            for mapped_character_id in item.character_ids:
                connection.execute(
                    "INSERT INTO casting_plan_characters(casting_plan_id,character_id) VALUES(?,?)",
                    (plan_id, mapped_character_id),
                )
            applied.append(
                {
                    "chapter_id": item.chapter_id,
                    "chapter_number": item.chapter_number,
                    "casting_plan_id": plan_id,
                    "plan_revision": next_revision,
                    "utterance_ids": list(item.target_utterance_ids),
                    "reused": False,
                }
            )
    return {
        "operation": operation,
        "speaker_key": speaker_key,
        "character_id": character_id,
        "alias_result": dict(alias_result or {}),
        "applied": applied,
        "chapter_count": len(prepared),
        "utterance_count": sum(len(item.target_utterance_ids) for item in prepared),
        "reused_count": sum(1 for item in applied if item.get("reused")),
    }


__all__ = [
    "CharacterAssignmentError",
    "UNRESOLVED_DIALOGUE_PREFIX",
    "UNRESOLVED_DIALOGUE_ROLE",
    "UNRESOLVED_DIALOGUE_STATUS",
    "UnresolvedDialogueReference",
    "add_character_aliases",
    "apply_speaker_character_mapping",
    "clear_speaker_character_mapping",
    "create_assignment_character",
    "is_unresolved_dialogue_text",
    "parse_unresolved_dialogue_speaker_key",
    "unresolved_dialogue_references",
    "unresolved_dialogue_references_from_text",
    "unresolved_dialogue_speaker_key",
]
