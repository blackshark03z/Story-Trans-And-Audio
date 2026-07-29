from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .casting import (
    CastingError,
    build_casting_plan_payload,
    get_plan,
    speaker_key_for,
)
from .db import Database, utcnow
from .files import sha256_text
from .storage import ContentStore
from .voice_eligibility import EffectiveVoiceCatalog
from .voice_ref import CustomVoiceContext


class ChapterVoiceOverrideError(ValueError):
    """Fail-closed error for chapter-scoped future voice changes."""


@dataclass(frozen=True)
class _PreparedPlan:
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
    reused: bool


def _canonical_plan_sha(payload: Mapping[str, Any]) -> str:
    return sha256_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _chapters_for_range(
    db: Database,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
) -> list[dict[str, Any]]:
    if from_chapter > to_chapter:
        raise ChapterVoiceOverrideError("from_chapter must be less than or equal to to_chapter")
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
        raise ChapterVoiceOverrideError("Selected range must contain every requested chapter")
    return chapters


def _latest_plan_row(db: Database, chapter_id: int) -> dict[str, Any]:
    row = db.fetch_one(
        """
        SELECT *
        FROM casting_plans
        WHERE chapter_id=?
        ORDER BY plan_revision DESC,id DESC
        LIMIT 1
        """,
        (chapter_id,),
    )
    if not row:
        raise ChapterVoiceOverrideError("Final Voice Map is missing for the selected chapter")
    result = dict(row)
    status = str(result.get("status") or "").lower()
    if status != "approved":
        raise ChapterVoiceOverrideError(
            "Final Voice Map must be approved before applying a chapter voice override"
        )
    return result


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


def _speaker_voices(payload: Mapping[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for item in payload.get("utterances") or []:
        if not isinstance(item, Mapping):
            continue
        key = speaker_key_for(
            str(item.get("role") or "narrator"),
            int(item["character_id"]) if item.get("character_id") not in (None, "") else None,
        )
        voice_id = str(item.get("resolved_voice_id") or "").strip()
        if voice_id:
            result.setdefault(key, set()).add(voice_id)
    return result


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


def _speaker_present(payload: Mapping[str, Any], speaker_key: str) -> bool:
    return speaker_key in _speaker_voices(payload)


def _existing_plan_overrides(
    current_payload: Mapping[str, Any],
    default_payload: Mapping[str, Any],
) -> dict[str, str]:
    current = _speaker_voices(current_payload)
    defaults = _speaker_voices(default_payload)
    overrides: dict[str, str] = {}
    for key, voices in current.items():
        default_voices = defaults.get(key) or set()
        if len(voices) == 1 and len(default_voices) == 1 and voices != default_voices:
            overrides[key] = next(iter(voices))
    return overrides


def _prepare_plan(
    db: Database,
    store: ContentStore,
    *,
    chapter: Mapping[str, Any],
    speaker_key: str,
    operation: str,
    voice_id: str | None,
    allowed_voice_ids: set[str],
    source_metadata: Mapping[str, Any],
    custom_voice_context: CustomVoiceContext | None,
) -> _PreparedPlan:
    plan_row = _latest_plan_row(db, int(chapter["id"]))
    if int(plan_row["text_revision_id"]) != int(chapter["active_text_revision_id"] or 0):
        raise ChapterVoiceOverrideError(
            f"Final Voice Map is stale for Chapter {int(chapter['chapter_number'])}"
        )
    current = get_plan(db, store, int(plan_row["id"]))
    current_payload = current["plan"]
    build_allowed_voice_ids = (
        set(allowed_voice_ids)
        | _all_plan_voice_ids(current_payload)
        | _book_configured_voice_ids(db, int(chapter["book_id"]))
    )
    if not _speaker_present(current_payload, speaker_key):
        raise ChapterVoiceOverrideError(
            f"Speaker {speaker_key} does not appear in Chapter {int(chapter['chapter_number'])}"
        )
    assignments = _assignments_from_plan(current_payload)
    default_build = build_casting_plan_payload(
        db,
        store,
        chapter_id=int(chapter["id"]),
        text_revision_id=int(plan_row["text_revision_id"]),
        narrator_voice_id=str(current_payload.get("narrator_voice_id") or ""),
        assignments=assignments,
        allowed_voice_ids=build_allowed_voice_ids,
        base_utterances=current_payload.get("utterances") or [],
        custom_voice_context=custom_voice_context,
    )
    overrides = _existing_plan_overrides(current_payload, default_build.payload)
    if operation == "set":
        if not voice_id:
            raise ChapterVoiceOverrideError("voice_id is required when setting an override")
        if voice_id not in allowed_voice_ids and not (
            custom_voice_context and custom_voice_context.is_available(voice_id)
        ):
            raise ChapterVoiceOverrideError("Selected voice is not available")
        overrides[speaker_key] = voice_id
    elif operation == "clear":
        overrides.pop(speaker_key, None)
    else:
        raise ChapterVoiceOverrideError("Unsupported voice override operation")
    built = build_casting_plan_payload(
        db,
        store,
        chapter_id=int(chapter["id"]),
        text_revision_id=int(plan_row["text_revision_id"]),
        narrator_voice_id=str(current_payload.get("narrator_voice_id") or ""),
        assignments=assignments,
        allowed_voice_ids=build_allowed_voice_ids | ({voice_id} if voice_id else set()),
        source_metadata=dict(source_metadata),
        base_utterances=current_payload.get("utterances") or [],
        custom_voice_context=custom_voice_context,
        speaker_voice_overrides=overrides,
    )
    plan_sha = _canonical_plan_sha(built.payload)
    content_path, stored_sha = store.put_json(built.payload, namespace="casting")
    if stored_sha != plan_sha:
        raise ChapterVoiceOverrideError("Generated Casting Plan hash mismatch")
    return _PreparedPlan(
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
        reused=plan_sha == str(plan_row["plan_sha256"]),
    )


def apply_chapter_voice_override(
    db: Database,
    store: ContentStore,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    speaker_key: str,
    operation: str,
    voice_id: str | None,
    voice_catalog: EffectiveVoiceCatalog,
    idempotency_key: str,
    custom_voice_context: CustomVoiceContext | None = None,
) -> dict[str, Any]:
    normalized_speaker = str(speaker_key or "").strip()
    if normalized_speaker not in {"narrator", "unknown"} and not normalized_speaker.startswith("character:"):
        raise ChapterVoiceOverrideError("Unsupported speaker key")
    chapters = _chapters_for_range(
        db,
        book_id=book_id,
        from_chapter=from_chapter,
        to_chapter=to_chapter,
    )
    source_metadata = {
        "source": "chapter_voice_override",
        "operation": operation,
        "speaker_key": normalized_speaker,
        "voice_id": voice_id,
        "scope": {
            "book_id": book_id,
            "from_chapter": from_chapter,
            "to_chapter": to_chapter,
            "chapter_count": len(chapters),
        },
        "idempotency_key": idempotency_key,
    }
    allowed_voice_ids = set(voice_catalog.selectable_ids)
    prepared = [
        _prepare_plan(
            db,
            store,
            chapter=chapter,
            speaker_key=normalized_speaker,
            operation=operation,
            voice_id=voice_id,
            allowed_voice_ids=allowed_voice_ids,
            source_metadata=source_metadata,
            custom_voice_context=custom_voice_context,
        )
        for chapter in chapters
    ]
    applied: list[dict[str, Any]] = []
    now = utcnow()
    with db.transaction() as connection:
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
                raise ChapterVoiceOverrideError(
                    f"Chapter {item.chapter_number} voice map changed while saving"
                )
            if item.reused:
                applied.append(
                    {
                        "chapter_id": item.chapter_id,
                        "chapter_number": item.chapter_number,
                        "casting_plan_id": item.previous_plan_id,
                        "plan_revision": item.plan_revision,
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
            for character_id in item.character_ids:
                connection.execute(
                    "INSERT INTO casting_plan_characters(casting_plan_id,character_id) VALUES(?,?)",
                    (plan_id, character_id),
                )
            applied.append(
                {
                    "chapter_id": item.chapter_id,
                    "chapter_number": item.chapter_number,
                    "casting_plan_id": plan_id,
                    "plan_revision": next_revision,
                    "reused": False,
                }
            )
    return {
        "operation": operation,
        "speaker_key": normalized_speaker,
        "voice_id": voice_id,
        "applied": applied,
        "chapter_count": len(chapters),
        "reused_count": sum(1 for item in applied if item.get("reused")),
    }


__all__ = [
    "ChapterVoiceOverrideError",
    "apply_chapter_voice_override",
]
