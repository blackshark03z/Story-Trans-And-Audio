from __future__ import annotations

from typing import Any, Mapping

from .db import Database, utcnow
from .voice_ref import (
    CustomVoiceContext,
    is_custom_ref,
    resolve_custom_ref,
)

FALLBACK_POLICIES = {"narrator", "male_dialogue", "female_dialogue", "explicit_voice"}
GENDERS = {"male", "female", "unknown"}

class VoiceProfileError(ValueError):
    pass

def preset_ref(preset_id: str) -> dict[str, str]:
    return {"kind": "preset", "provider": "vieneu", "preset_id": preset_id}

def get_book_voice_profile(db: Database, book_id: int) -> dict[str, Any] | None:
    row = db.fetch_one("SELECT * FROM book_voice_profiles WHERE book_id=?", (book_id,))
    return dict(row) if row else None

def _is_allowed_voice(
    voice_id: str,
    allowed_voice_ids: set[str],
    custom_voice_context: CustomVoiceContext | None,
) -> bool:
    """Check if a voice ID is allowed (preset or custom)."""
    if voice_id in allowed_voice_ids:
        return True
    if custom_voice_context is not None and custom_voice_context.is_available(voice_id):
        return True
    return False

def set_book_voice_profile(
    db: Database,
    book_id: int,
    *,
    narrator_voice_id: str,
    male_dialogue_voice_id: str,
    female_dialogue_voice_id: str,
    unknown_fallback: str = "narrator",
    unknown_voice_id: str | None = None,
    allowed_voice_ids: set[str],
    custom_voice_context: CustomVoiceContext | None = None,
) -> dict[str, Any]:
    if not db.fetch_one("SELECT id FROM books WHERE id=?", (book_id,)):
        raise VoiceProfileError("Book not found")
    voices = [narrator_voice_id, male_dialogue_voice_id, female_dialogue_voice_id]
    voices = [str(value).strip() for value in voices]
    policy = str(unknown_fallback).strip()
    explicit = str(unknown_voice_id).strip() if unknown_voice_id else None
    if policy not in FALLBACK_POLICIES:
        raise VoiceProfileError("Unknown fallback policy is invalid")
    if any(not voice or not _is_allowed_voice(voice, allowed_voice_ids, custom_voice_context) for voice in voices):
        raise VoiceProfileError("Voice profile contains an unavailable voice")
    if policy == "explicit_voice" and (not explicit or not _is_allowed_voice(explicit, allowed_voice_ids, custom_voice_context)):
        raise VoiceProfileError("Explicit unknown fallback must be an available voice")
    if explicit and not _is_allowed_voice(explicit, allowed_voice_ids, custom_voice_context):
        raise VoiceProfileError("Unknown fallback voice is not available")
    now = utcnow()
    with db.connect() as connection:
        existing = connection.execute(
            "SELECT id,config_version FROM book_voice_profiles WHERE book_id=?", (book_id,)
        ).fetchone()
        if existing:
            connection.execute(
                """UPDATE book_voice_profiles SET narrator_voice_id=?,male_dialogue_voice_id=?,
                   female_dialogue_voice_id=?,unknown_fallback=?,unknown_voice_id=?,
                   config_version=config_version+1,updated_at=? WHERE book_id=?""",
                (*voices, policy, explicit, now, book_id),
            )
        else:
            connection.execute(
                """INSERT INTO book_voice_profiles(
                   book_id,narrator_voice_id,male_dialogue_voice_id,female_dialogue_voice_id,
                   unknown_fallback,unknown_voice_id,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                (book_id, *voices, policy, explicit, now, now),
            )
    return get_book_voice_profile(db, book_id) or {}

def profile_validation(
    profile: Mapping[str, Any],
    allowed_voice_ids: set[str],
    custom_voice_context: CustomVoiceContext | None = None,
) -> dict[str, Any]:
    ids = {
        str(profile["narrator_voice_id"]),
        str(profile["male_dialogue_voice_id"]),
        str(profile["female_dialogue_voice_id"]),
    }
    if profile.get("unknown_fallback") == "explicit_voice" and profile.get("unknown_voice_id"):
        ids.add(str(profile["unknown_voice_id"]))
    missing = sorted([
        vid for vid in ids
        if not _is_allowed_voice(vid, allowed_voice_ids, custom_voice_context)
    ])
    return {"valid": not missing, "missing_preset_ids": missing}

def set_character_voice_override(
    db: Database,
    character_id: int,
    voice_id: str | None,
    *,
    allowed_voice_ids: set[str],
    custom_voice_context: CustomVoiceContext | None = None,
) -> dict[str, Any]:
    row = db.fetch_one("SELECT * FROM characters WHERE id=? AND active=1", (character_id,))
    if not row:
        raise VoiceProfileError("Character not found")
    value = str(voice_id).strip() if voice_id else None
    if value and not _is_allowed_voice(value, allowed_voice_ids, custom_voice_context):
        raise VoiceProfileError("Character override is not an available voice")
    with db.connect() as connection:
        connection.execute(
            "UPDATE characters SET voice_override_id=?,updated_at=? WHERE id=?",
            (value, utcnow(), character_id),
        )
    return dict(db.fetch_one("SELECT * FROM characters WHERE id=?", (character_id,)))

def set_character_gender(db: Database, character_id: int, gender: str | None) -> dict[str, Any]:
    value = str(gender).strip().lower() if gender else None
    if value not in GENDERS | {None}:
        raise VoiceProfileError("Character gender is invalid")
    with db.connect() as connection:
        changed = connection.execute(
            "UPDATE characters SET gender=?,updated_at=? WHERE id=? AND active=1",
            (value, utcnow(), character_id),
        ).rowcount
    if not changed:
        raise VoiceProfileError("Character not found")
    return dict(db.fetch_one("SELECT * FROM characters WHERE id=?", (character_id,)))

def resolve_voice(
    *,
    speaker_type: str,
    book_voice_profile: Mapping[str, Any],
    character: Mapping[str, Any] | None = None,
    inferred_gender: str | None = None,
    optional_override: str | None = None,
    custom_voice_context: CustomVoiceContext | None = None,
) -> dict[str, Any]:
    if speaker_type not in {"narrator", "dialogue", "character"}:
        raise VoiceProfileError("Speaker type is invalid")
    character_data = dict(character) if character is not None else None
    profile_data = dict(book_voice_profile)
    override = optional_override
    if override is None and character_data is not None:
        override = character_data.get("voice_override_id")
    character_id = int(character_data["id"]) if character_data and character_data.get("id") is not None else None
    confirmed_gender = character_data.get("gender") if character_data else None
    gender = confirmed_gender if confirmed_gender in GENDERS else inferred_gender
    gender = gender if gender in GENDERS else "unknown"
    needs_review = False
    if override:
        voice_id, source = str(override), "character_override"
    elif speaker_type == "narrator":
        voice_id, source = str(profile_data["narrator_voice_id"]), "narrator"
    elif gender == "male":
        voice_id, source = str(profile_data["male_dialogue_voice_id"]), "book_male"
    elif gender == "female":
        voice_id, source = str(profile_data["female_dialogue_voice_id"]), "book_female"
    else:
        policy = str(profile_data.get("unknown_fallback") or "narrator")
        key = {
            "narrator": "narrator_voice_id",
            "male_dialogue": "male_dialogue_voice_id",
            "female_dialogue": "female_dialogue_voice_id",
            "explicit_voice": "unknown_voice_id",
        }[policy]
        voice_id, source, needs_review = str(profile_data[key]), "unknown_fallback", True
    
    # Resolve voice reference (preset or custom)
    if is_custom_ref(voice_id) and custom_voice_context is not None:
        voice_ref = resolve_custom_ref(voice_id, custom_voice_context)
    else:
        voice_ref = preset_ref(voice_id)
    
    return {
        "voice": voice_ref,
        "resolved_voice_id": voice_id,
        "resolution_source": source,
        "character_id": character_id,
        "gender": gender,
        "profile_id": int(profile_data["id"]) if profile_data.get("id") is not None else None,
        "profile_version": int(profile_data.get("config_version") or 1),
        "needs_review": needs_review,
    }
