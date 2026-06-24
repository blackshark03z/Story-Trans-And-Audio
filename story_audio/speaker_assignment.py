from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .casting import get_plan, list_characters, split_utterances
from .config import Settings
from .db import Database, utcnow
from .files import sha256_text
from .gemini import assign_speakers
from .gemini_cache import GeminiRepairCache, canonical_json
from .storage import ContentStore


DRAFT_SCHEMA = "story-audio-speaker-assignment-draft/v1"
REQUEST_SCHEMA = "story-audio-speaker-assignment-request/v1"
PROMPT_SETTINGS = {"temperature": 0, "response_mime_type": "application/json"}
ALLOWED_MODES = {"unassigned_only", "reanalyze"}
ALLOWED_SPEAKER_TYPES = {"narrator", "character", "unknown"}
MAX_REASON_LENGTH = 300
MAX_ALTERNATIVES = 3


class SpeakerAssignmentError(ValueError):
    pass


def _active_revision(db: Database, chapter_id: int):
    row = db.fetch_one(
        """SELECT tr.*,c.book_id FROM text_revisions tr
           JOIN chapters c ON c.id=tr.chapter_id
           WHERE tr.chapter_id=? AND tr.status='approved'
           ORDER BY (tr.id=c.active_text_revision_id) DESC,tr.id DESC LIMIT 1""",
        (chapter_id,),
    )
    if not row:
        raise SpeakerAssignmentError("Chapter does not have an approved TextRevision")
    return row


def _character_context(db: Database, book_id: int) -> tuple[list[dict[str, Any]], str]:
    fields = (
        "id", "canonical_name", "display_name", "aliases", "gender", "role",
        "age_group", "description", "speech_style", "notes",
    )
    characters: list[dict[str, Any]] = []
    for row in list_characters(db, book_id):
        item = {field: row.get(field) for field in fields}
        item["canonical_name"] = item["canonical_name"] or item["display_name"]
        characters.append(item)
    characters.sort(key=lambda item: int(item["id"]))
    return characters, sha256_text(canonical_json(characters))


def _confirmed_assignments(
    db: Database, store: ContentStore, chapter_id: int, text_revision_id: int
) -> dict[str, dict[str, Any]]:
    row = db.fetch_one(
        """SELECT id FROM casting_plans
           WHERE chapter_id=? AND text_revision_id=? AND status='approved'
           ORDER BY plan_revision DESC LIMIT 1""",
        (chapter_id, text_revision_id),
    )
    if not row:
        return {}
    plan = get_plan(db, store, int(row["id"]))["plan"]
    return {
        str(item["utterance_id"]): {
            "utterance_id": str(item["utterance_id"]),
            "speaker_type": "character" if item.get("role") == "character" else "narrator",
            "character_id": item.get("character_id"),
        }
        for item in plan.get("utterances", [])
    }


def _dialogue_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(text):
        curly = text.find("“", cursor)
        straight = text.find('"', cursor)
        candidates = [value for value in (curly, straight) if value >= 0]
        if not candidates:
            break
        start = min(candidates)
        closing = "”" if text[start] == "“" else '"'
        end = text.find(closing, start + 1)
        if end < 0:
            break
        ranges.append((start, end + 1))
        cursor = end + 1
    return ranges


def _is_dialogue_span(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start < quote_end and end > quote_start for quote_start, quote_end in ranges)


def build_speaker_assignment_request(
    db: Database,
    store: ContentStore,
    config: Settings,
    *,
    chapter_id: int,
    mode: str = "unassigned_only",
    utterance_ids: list[str] | None = None,
) -> dict[str, Any]:
    if mode not in ALLOWED_MODES:
        raise SpeakerAssignmentError("Unsupported speaker assignment mode")
    revision = _active_revision(db, chapter_id)
    text = store.read_text(str(revision["content_path"]))
    if sha256_text(text) != revision["content_sha256"]:
        raise SpeakerAssignmentError("TextRevision blob hash mismatch")
    utterances = split_utterances(text, maximum=config.tts_max_chars)
    dialogue_ranges = _dialogue_ranges(text)
    by_id = {str(item["utterance_id"]): item for item in utterances}
    requested = list(dict.fromkeys(utterance_ids or []))
    missing = [item for item in requested if item not in by_id]
    if missing:
        raise SpeakerAssignmentError(f"Unknown utterance_id: {missing[0]}")

    confirmed = _confirmed_assignments(
        db, store, chapter_id, int(revision["id"])
    )
    if requested:
        selected_ids = requested
    else:
        selected_ids = [
            str(item["utterance_id"])
            for item in utterances
            if mode == "reanalyze" or _is_dialogue_span(
                int(item["start_offset"]), int(item["end_offset"]), dialogue_ranges
            )
        ]
    if mode == "unassigned_only":
        selected_ids = [item for item in selected_ids if item not in confirmed]

    characters, bible_fingerprint = _character_context(db, int(revision["book_id"]))
    context_size = config.speaker_assignment_context_size
    index_by_id = {str(item["utterance_id"]): index for index, item in enumerate(utterances)}
    targets: list[dict[str, Any]] = []
    for utterance_id in selected_ids:
        target_index = index_by_id[utterance_id]
        context: list[dict[str, Any]] = []
        for item in utterances[
            max(0, target_index - context_size):target_index + context_size + 1
        ]:
            item_id = str(item["utterance_id"])
            known = confirmed.get(item_id)
            context.append({
                "utterance_id": item_id,
                "text": text[int(item["start_offset"]):int(item["end_offset"])],
                "known_speaker": known,
                "is_target": item_id == utterance_id,
            })
        target = by_id[utterance_id]
        targets.append({
            "utterance_id": utterance_id,
            "utterance_text_sha256": target["text_sha256"],
            "context": context,
        })

    confirmed_list = [confirmed[key] for key in sorted(confirmed)]
    identity = {
        "book_id": int(revision["book_id"]),
        "chapter_id": chapter_id,
        "text_revision_id": int(revision["id"]),
        "text_revision_sha256": str(revision["content_sha256"]),
        "utterance_chunker": "utterance-v1",
        "targets": targets,
        "character_bible_fingerprint": bible_fingerprint,
        "confirmed_assignment_context_sha256": sha256_text(canonical_json(confirmed_list)),
        "prompt_version": config.speaker_assignment_prompt_version,
        "model_id": config.gemini_model,
        "generation_settings": PROMPT_SETTINGS,
        "response_schema": DRAFT_SCHEMA,
        "mode": mode,
    }
    return {
        "schema": REQUEST_SCHEMA,
        "identity": identity,
        "input_fingerprint": sha256_text(canonical_json(identity)),
        "book_id": int(revision["book_id"]),
        "chapter_id": chapter_id,
        "text_revision_id": int(revision["id"]),
        "text_revision_sha256": str(revision["content_sha256"]),
        "character_bible_fingerprint": bible_fingerprint,
        "candidate_characters": characters,
        "confirmed_assignments": confirmed_list,
        "targets": targets,
        "mode": mode,
    }


def _candidate_key(speaker_type: str, character_id: int | None) -> tuple[str, int | None]:
    return speaker_type, character_id


def _validate_candidate(value: Any, allowed_character_ids: set[int]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"speaker_type", "character_id", "confidence"}:
        raise SpeakerAssignmentError("candidate fields are invalid")
    speaker_type = value["speaker_type"]
    character_id = value["character_id"]
    confidence = value["confidence"]
    if speaker_type not in ALLOWED_SPEAKER_TYPES:
        raise SpeakerAssignmentError("speaker_type is invalid")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise SpeakerAssignmentError("confidence is invalid")
    if speaker_type == "character":
        if isinstance(character_id, bool) or not isinstance(character_id, int) or character_id not in allowed_character_ids:
            raise SpeakerAssignmentError("character_id is not an allowed candidate")
    elif character_id is not None:
        raise SpeakerAssignmentError("character_id must be null for narrator/unknown")
    return {
        "speaker_type": speaker_type,
        "character_id": character_id,
        "confidence": float(confidence),
    }


def validate_speaker_assignment_response(
    payload: dict[str, Any], *, target_ids: list[str], allowed_character_ids: set[int]
) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {"schema", "assignments"}:
        raise SpeakerAssignmentError("Speaker response top-level fields are invalid")
    if payload["schema"] != DRAFT_SCHEMA or not isinstance(payload["assignments"], list):
        raise SpeakerAssignmentError("Speaker response schema is invalid")
    target_set = set(target_ids)
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(payload["assignments"]):
        utterance_id = str(item.get("utterance_id", "")) if isinstance(item, dict) else ""
        try:
            expected = {"utterance_id", "speaker_type", "character_id", "confidence", "reason", "alternatives"}
            if not isinstance(item, dict) or set(item) != expected:
                raise SpeakerAssignmentError("assignment fields are invalid")
            if utterance_id not in target_set or utterance_id in seen:
                raise SpeakerAssignmentError("utterance_id is unknown or duplicated")
            primary = _validate_candidate(
                {key: item[key] for key in ("speaker_type", "character_id", "confidence")},
                allowed_character_ids,
            )
            reason = item["reason"]
            if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > MAX_REASON_LENGTH:
                raise SpeakerAssignmentError("reason is invalid")
            alternatives = item["alternatives"]
            if not isinstance(alternatives, list) or len(alternatives) > MAX_ALTERNATIVES:
                raise SpeakerAssignmentError("alternatives are invalid")
            parsed_alternatives = [
                _validate_candidate(candidate, allowed_character_ids) for candidate in alternatives
            ]
            keys = [_candidate_key(primary["speaker_type"], primary["character_id"])] + [
                _candidate_key(candidate["speaker_type"], candidate["character_id"])
                for candidate in parsed_alternatives
            ]
            if len(keys) != len(set(keys)):
                raise SpeakerAssignmentError("primary and alternatives must be unique")
            top_alternative = max((item["confidence"] for item in parsed_alternatives), default=0.0)
            confidence = primary["confidence"]
            level = "high" if confidence >= 0.90 and confidence - top_alternative >= 0.20 else (
                "medium" if confidence >= 0.70 else "low"
            )
            valid.append({
                "utterance_id": utterance_id,
                **primary,
                "reason": reason.strip(),
                "alternatives": parsed_alternatives,
                "confidence_level": level,
                "needs_review": True,
                "review_priority": "high" if level == "low" or primary["speaker_type"] == "unknown" else "normal",
            })
            seen.add(utterance_id)
        except SpeakerAssignmentError as exc:
            invalid.append({
                "utterance_id": utterance_id or f"response-item-{index + 1}",
                "error_code": str(exc),
            })
    for utterance_id in target_ids:
        if utterance_id not in seen and not any(item["utterance_id"] == utterance_id for item in invalid):
            invalid.append({"utterance_id": utterance_id, "error_code": "missing_assignment"})
    valid.sort(key=lambda item: target_ids.index(item["utterance_id"]))
    return {"assignments": valid, "invalid_items": invalid}


def _provider_batch_request(request: dict[str, Any], targets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": REQUEST_SCHEMA,
        "target_utterance_ids": [item["utterance_id"] for item in targets],
        "targets": targets,
        "candidate_characters": request["candidate_characters"],
        "confirmed_assignments": request["confirmed_assignments"],
    }


def generate_speaker_assignment_draft(
    db: Database,
    store: ContentStore,
    config: Settings,
    *,
    chapter_id: int,
    mode: str = "unassigned_only",
    utterance_ids: list[str] | None = None,
    force_refresh: bool = False,
    provider: Callable[..., dict[str, Any]] = assign_speakers,
) -> dict[str, Any]:
    request = build_speaker_assignment_request(
        db, store, config, chapter_id=chapter_id, mode=mode, utterance_ids=utterance_ids
    )
    cache = GeminiRepairCache(store, config)
    allowed_ids = {int(item["id"]) for item in request["candidate_characters"]}
    assignments: list[dict[str, Any]] = []
    invalid_items: list[dict[str, str]] = []
    cache_hits = cache_misses = 0
    targets = request["targets"]
    for offset in range(0, len(targets), config.speaker_assignment_batch_size):
        batch = targets[offset:offset + config.speaker_assignment_batch_size]
        batch_request = _provider_batch_request(request, batch)
        batch_fingerprint = sha256_text(canonical_json({
            "request_input_fingerprint": request["input_fingerprint"],
            "batch": batch_request,
        }))
        identity = cache.json_identity(
            task_kind="speaker_assignment",
            input_fingerprint=batch_fingerprint,
            model=config.gemini_model,
            prompt_version=config.speaker_assignment_prompt_version,
            response_schema=DRAFT_SCHEMA,
            settings=PROMPT_SETTINGS,
        )
        lookup = cache.lookup_json(identity) if not force_refresh else None
        if lookup and lookup.status == "hit":
            response = lookup.payload or {}
            try:
                validated = validate_speaker_assignment_response(
                    response,
                    target_ids=[item["utterance_id"] for item in batch],
                    allowed_character_ids=allowed_ids,
                )
                cache_hits += 1
            except SpeakerAssignmentError:
                lookup = None
        if not lookup or lookup.status != "hit":
            api_key = config.gemini_key()
            if not api_key:
                raise SpeakerAssignmentError("Gemini API key is not configured")
            response = provider(api_key=api_key, model=config.gemini_model, request_data=batch_request)
            validated = validate_speaker_assignment_response(
                response,
                target_ids=[item["utterance_id"] for item in batch],
                allowed_character_ids=allowed_ids,
            )
            cache.store_json(identity, response)
            cache_misses += 1
        assignments.extend(validated["assignments"])
        invalid_items.extend(validated["invalid_items"])

    status = "partially_invalid" if invalid_items else "generated"
    payload = {
        "schema": DRAFT_SCHEMA,
        "status": status,
        "input_fingerprint": request["input_fingerprint"],
        "book_id": request["book_id"],
        "chapter_id": request["chapter_id"],
        "text_revision_id": request["text_revision_id"],
        "text_revision_sha256": request["text_revision_sha256"],
        "character_bible_fingerprint": request["character_bible_fingerprint"],
        "confirmed_assignment_context_sha256": request["identity"]["confirmed_assignment_context_sha256"],
        "model_id": config.gemini_model,
        "prompt_version": config.speaker_assignment_prompt_version,
        "mode": mode,
        "assignments": assignments,
        "invalid_items": invalid_items,
        "summary": {
            "target_count": len(targets),
            "valid_count": len(assignments),
            "invalid_count": len(invalid_items),
        },
    }
    content_path, content_sha = store.put_json(payload, namespace="speaker_assignment")
    existing = db.fetch_one(
        "SELECT id FROM speaker_assignment_drafts WHERE input_fingerprint=? AND content_sha256=?",
        (request["input_fingerprint"], content_sha),
    )
    if existing:
        result = get_speaker_assignment_draft(db, store, int(existing["id"]), reused=True)
        result["cache"] = {"hit_count": cache_hits, "miss_count": cache_misses}
        return result
    now = utcnow()
    with db.transaction() as connection:
        draft_id = int(connection.execute(
            """INSERT INTO speaker_assignment_drafts(
               book_id,chapter_id,text_revision_id,input_fingerprint,character_bible_fingerprint,
               model_id,prompt_version,response_schema,mode,status,content_path,content_sha256,
               target_count,valid_count,invalid_count,cache_hit_count,cache_miss_count,created_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                request["book_id"], chapter_id, request["text_revision_id"],
                request["input_fingerprint"], request["character_bible_fingerprint"],
                config.gemini_model, config.speaker_assignment_prompt_version, DRAFT_SCHEMA,
                mode, status, content_path, content_sha, len(targets), len(assignments),
                len(invalid_items), cache_hits, cache_misses, now,
            ),
        ).lastrowid)
        for character_id in sorted(allowed_ids):
            connection.execute(
                "INSERT INTO speaker_assignment_draft_characters(draft_id,character_id) VALUES(?,?)",
                (draft_id, character_id),
            )
    result = get_speaker_assignment_draft(db, store, draft_id, reused=False)
    result["cache"] = {"hit_count": cache_hits, "miss_count": cache_misses}
    return result


def get_speaker_assignment_draft(
    db: Database, store: ContentStore, draft_id: int, *, reused: bool | None = None
) -> dict[str, Any]:
    row = db.fetch_one("SELECT * FROM speaker_assignment_drafts WHERE id=?", (draft_id,))
    if not row:
        raise SpeakerAssignmentError("Speaker assignment draft not found")
    payload = store.read_json(str(row["content_path"]))
    if sha256_text(canonical_json(payload)) != row["content_sha256"]:
        raise SpeakerAssignmentError("Speaker assignment draft hash mismatch")
    result = dict(row)
    result.pop("content_path", None)
    result["draft"] = payload
    if reused is not None:
        result["reused"] = reused
    return result
