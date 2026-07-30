"""Book-scoped reusable identities for expendable background speakers."""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from typing import Any, Iterable, Mapping

from .character_bible import normalize_identity
from .db import utcnow
from .voice_eligibility import EffectiveVoiceCatalog


BACKGROUND_GROUPS: dict[str, dict[str, str]] = {
    "MALE": {
        "key": "background-group:male",
        "display_name": "Quần chúng nam",
        "gender": "male",
    },
    "FEMALE": {
        "key": "background-group:female",
        "display_name": "Quần chúng nữ",
        "gender": "female",
    },
    "NEUTRAL_OR_UNKNOWN": {
        "key": "background-group:neutral",
        "display_name": "Quần chúng trung tính",
        "gender": "unknown",
    },
}

_DETERMINERS = re.compile(
    r"^(?:(?:một|tên|gã|kẻ)\s+|người\s+nọ\s+)+",
    flags=re.IGNORECASE,
)
_TRAILING_DETERMINERS = re.compile(r"\s+nọ$", flags=re.IGNORECASE)
_GENERIC_LABELS = {
    "đại hán": "MALE",
    "nam tử": "MALE",
    "nữ tử": "FEMALE",
    "thị vệ": "NEUTRAL_OR_UNKNOWN",
    "đệ tử": "NEUTRAL_OR_UNKNOWN",
    "người qua đường": "NEUTRAL_OR_UNKNOWN",
    "người hầu": "NEUTRAL_OR_UNKNOWN",
    "tiểu nhị": "NEUTRAL_OR_UNKNOWN",
    "khách nhân": "NEUTRAL_OR_UNKNOWN",
    "trưởng quầy": "NEUTRAL_OR_UNKNOWN",
}


class BackgroundSpeakerError(ValueError):
    """Background-speaker contract violation."""


def background_group_spec(gender_hint: str) -> dict[str, str]:
    key = str(gender_hint or "").strip().upper()
    if key not in BACKGROUND_GROUPS:
        raise BackgroundSpeakerError("Background speaker gender group is invalid")
    return dict(BACKGROUND_GROUPS[key])


def normalize_generic_speaker_label(
    value: str | None,
    *,
    bound_identities: Iterable[str] = (),
) -> dict[str, Any]:
    """Return a conservative generic-label signal without making a decision."""

    display = " ".join(
        unicodedata.normalize("NFC", str(value or "")).strip().split()
    )
    normalized = normalize_identity(display)
    generic_core = _DETERMINERS.sub("", display).strip(" .,:;!?-–—")
    generic_core = _TRAILING_DETERMINERS.sub("", generic_core)
    stripped = normalize_identity(generic_core)
    bound = {
        normalize_identity(item)
        for item in bound_identities
        if str(item or "").strip()
    }
    gender_hint = _GENERIC_LABELS.get(stripped)
    return {
        "original": display,
        "normalized": stripped,
        "is_generic_candidate": bool(gender_hint) and normalized not in bound and stripped not in bound,
        "gender_hint": gender_hint,
        "bound_to_existing_character": normalized in bound or stripped in bound,
    }


def find_background_group_character(
    connection: sqlite3.Connection,
    *,
    book_id: int,
    gender_hint: str,
) -> dict[str, Any] | None:
    spec = background_group_spec(gender_hint)
    row = connection.execute(
        """
        SELECT *
        FROM characters
        WHERE book_id=? AND active=1
          AND (
            external_key_normalized=?
            OR canonical_name_normalized=?
            OR lower(display_name)=lower(?)
          )
        ORDER BY
          CASE WHEN external_key_normalized=? THEN 0 ELSE 1 END,
          id
        LIMIT 1
        """,
        (
            int(book_id),
            spec["key"],
            normalize_identity(spec["display_name"]),
            spec["display_name"],
            spec["key"],
        ),
    ).fetchone()
    return dict(row) if row else None


def ensure_background_group_character(
    connection: sqlite3.Connection,
    *,
    book_id: int,
    gender_hint: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Create or reuse one reserved group identity inside the caller transaction."""

    spec = background_group_spec(gender_hint)
    now = utcnow()
    existing = find_background_group_character(
        connection,
        book_id=book_id,
        gender_hint=gender_hint,
    )
    if existing:
        external_key = str(existing.get("external_key_normalized") or "")
        if external_key and external_key != spec["key"]:
            raise BackgroundSpeakerError(
                "Reserved background group name conflicts with an existing Character"
            )
        connection.execute(
            """
            UPDATE characters
            SET external_key=?,
                external_key_normalized=?,
                canonical_name=?,
                canonical_name_normalized=?,
                gender=?,
                role='minor',
                updated_at=?
            WHERE id=?
            """,
            (
                spec["key"],
                spec["key"],
                spec["display_name"],
                normalize_identity(spec["display_name"]),
                spec["gender"],
                now,
                int(existing["id"]),
            ),
        )
        row = connection.execute(
            "SELECT * FROM characters WHERE id=?",
            (int(existing["id"]),),
        ).fetchone()
        return {
            "character": dict(row),
            "created": False,
            "reused": True,
            "group": spec,
        }

    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO characters(
            book_id,display_name,default_voice_id,active,created_at,updated_at,
            gender,voice_override_id,external_key,external_key_normalized,
            canonical_name,canonical_name_normalized,role,notes
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            int(book_id),
            spec["display_name"],
            "",
            1,
            now,
            now,
            spec["gender"],
            None,
            spec["key"],
            spec["key"],
            spec["display_name"],
            normalize_identity(spec["display_name"]),
            "minor",
            f"Reserved reusable background group; command {idempotency_key}",
        ),
    )
    row = connection.execute(
        """
        SELECT *
        FROM characters
        WHERE book_id=? AND active=1 AND external_key_normalized=?
        """,
        (int(book_id), spec["key"]),
    ).fetchone()
    if not row:
        raise BackgroundSpeakerError("Background group could not be created safely")
    return {
        "character": dict(row),
        "created": cursor.rowcount == 1,
        "reused": cursor.rowcount != 1,
        "group": spec,
    }


def resolve_background_group_voice(
    *,
    gender_hint: str,
    book_profile: Mapping[str, Any] | None,
    catalog: EffectiveVoiceCatalog,
    group_character: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """Resolve a safe group voice without cross-gender fallback."""

    spec = background_group_spec(gender_hint)
    character_voice = str(
        (group_character or {}).get("voice_override_id")
        or (group_character or {}).get("default_voice_id")
        or ""
    ).strip()
    source = "Giọng đã lưu cho nhóm"
    voice_id = character_voice
    profile = dict(book_profile or {})
    if not voice_id and gender_hint == "MALE":
        voice_id = str(profile.get("male_dialogue_voice_id") or "").strip()
        source = "Mặc định nam của sách"
    elif not voice_id and gender_hint == "FEMALE":
        voice_id = str(profile.get("female_dialogue_voice_id") or "").strip()
        source = "Mặc định nữ của sách"
    elif not voice_id and gender_hint == "NEUTRAL_OR_UNKNOWN":
        policy = str(profile.get("unknown_fallback") or "narrator")
        if policy == "explicit_voice":
            voice_id = str(profile.get("unknown_voice_id") or "").strip()
            source = "Fallback trung tính của sách"
        elif policy == "narrator":
            voice_id = str(profile.get("narrator_voice_id") or "").strip()
            source = "Giọng chung của sách"
        else:
            return None, "Chưa có giọng trung tính tương thích"
    if not voice_id:
        return None, "Chưa có giọng tương thích"
    item = next(
        (
            dict(candidate)
            for candidate in catalog.items
            if str(candidate.get("assignment_key") or "") == voice_id
        ),
        {},
    )
    return (
        {
            "id": voice_id,
            "display_name": str(item.get("display_name") or voice_id),
            "available": voice_id in catalog.selectable_ids,
            "source_kind": item.get("source_kind"),
            "preview_url": item.get("preview_url") or item.get("preview_asset_url"),
            "gender_group": spec["gender"],
        },
        source,
    )


__all__ = [
    "BACKGROUND_GROUPS",
    "BackgroundSpeakerError",
    "background_group_spec",
    "ensure_background_group_character",
    "find_background_group_character",
    "normalize_generic_speaker_label",
    "resolve_background_group_voice",
]
