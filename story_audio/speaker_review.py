from __future__ import annotations

import threading
from typing import Any

from .casting import (
    CastingError,
    approve_plan,
    create_casting_draft,
    get_plan,
    list_characters,
    split_utterances,
)
from .config import Settings
from .db import Database, utcnow
from .files import sha256_text
from .gemini_cache import canonical_json
from .speaker_assignment import get_speaker_assignment_draft
from .storage import ContentStore
from .voice_profile import get_book_voice_profile


DECISION_SOURCES = {
    "gemini_suggestion", "gemini_alternative", "narrator", "unknown",
    "manual_character", "keep_current",
}
_APPROVAL_LOCK = threading.Lock()


class SpeakerReviewError(ValueError):
    pass


class SpeakerReviewConflict(SpeakerReviewError):
    pass


def _character_fingerprint(db: Database, book_id: int) -> str:
    fields = (
        "id", "canonical_name", "display_name", "aliases", "gender", "role",
        "age_group", "description", "speech_style", "notes",
    )
    values = []
    for row in list_characters(db, book_id):
        item = {field: row.get(field) for field in fields}
        item["canonical_name"] = item["canonical_name"] or item["display_name"]
        values.append(item)
    values.sort(key=lambda item: int(item["id"]))
    return sha256_text(canonical_json(values))


def _current_revision(db: Database, chapter_id: int):
    return db.fetch_one(
        """SELECT tr.* FROM text_revisions tr JOIN chapters c ON c.id=tr.chapter_id
           WHERE tr.chapter_id=? AND tr.status='approved'
           ORDER BY (tr.id=c.active_text_revision_id) DESC,tr.id DESC LIMIT 1""",
        (chapter_id,),
    )


def _current_approved_plan(db: Database, chapter_id: int):
    return db.fetch_one(
        """SELECT * FROM casting_plans WHERE chapter_id=? AND status='approved'
           ORDER BY plan_revision DESC LIMIT 1""",
        (chapter_id,),
    )


def _draft_target_ids(payload: dict[str, Any]) -> list[str]:
    values = [str(item.get("utterance_id", "")) for item in payload.get("assignments", [])]
    values.extend(str(item.get("utterance_id", "")) for item in payload.get("invalid_items", []))
    return list(dict.fromkeys(value for value in values if value))


def _review_links(db: Database, store: ContentStore, chapter_id: int, draft_id: int) -> list[dict[str, Any]]:
    links = []
    for row in db.fetch_all(
        "SELECT id FROM casting_plans WHERE chapter_id=? ORDER BY plan_revision,id",
        (chapter_id,),
    ):
        plan = get_plan(db, store, int(row["id"]))
        metadata = plan["plan"].get("source_metadata") or {}
        review = metadata.get("review") or {}
        if metadata.get("source") == "gemini_speaker_review" and review.get("draft_id") == draft_id:
            links.append({
                "casting_plan_id": int(plan["id"]),
                "plan_revision": int(plan["plan_revision"]),
                "status": plan["status"],
                "approved_count": int(review.get("approved_count") or 0),
                "reviewed_utterance_ids": list(review.get("reviewed_utterance_ids") or []),
            })
    return links


def get_speaker_review_draft(
    db: Database, store: ContentStore, config: Settings, *, chapter_id: int, draft_id: int
) -> dict[str, Any]:
    result = get_speaker_assignment_draft(db, store, draft_id)
    if int(result["chapter_id"]) != chapter_id:
        raise SpeakerReviewError("Speaker assignment draft not found for this chapter")
    payload = result["draft"]
    revision = db.fetch_one(
        "SELECT * FROM text_revisions WHERE id=? AND chapter_id=?",
        (result["text_revision_id"], chapter_id),
    )
    if not revision:
        raise SpeakerReviewError("Draft TextRevision is missing")
    text = store.read_text(str(revision["content_path"]))
    if sha256_text(text) != revision["content_sha256"]:
        raise SpeakerReviewError("Draft TextRevision blob hash mismatch")
    utterances = split_utterances(text, maximum=config.tts_max_chars)
    by_id = {str(item["utterance_id"]): item for item in utterances}
    index_by_id = {str(item["utterance_id"]): index for index, item in enumerate(utterances)}
    suggestions = {str(item["utterance_id"]): item for item in payload.get("assignments", [])}
    invalid = {str(item["utterance_id"]): item for item in payload.get("invalid_items", [])}
    target_ids = [item for item in _draft_target_ids(payload) if item in by_id]

    base_row = _current_approved_plan(db, chapter_id)
    base_plan = get_plan(db, store, int(base_row["id"])) if base_row else None
    confirmed = {}
    if base_plan and int(base_plan["text_revision_id"]) == int(revision["id"]):
        confirmed = {
            str(item["utterance_id"]): {
                "speaker_type": "character" if item.get("role") == "character" else item.get("role", "narrator"),
                "character_id": item.get("character_id"),
            }
            for item in base_plan["plan"].get("utterances", [])
        }

    rows = []
    for utterance_id in target_ids:
        index = index_by_id[utterance_id]
        item = by_id[utterance_id]
        context = []
        for context_item in utterances[
            max(0, index - config.speaker_assignment_context_size):
            index + config.speaker_assignment_context_size + 1
        ]:
            context_id = str(context_item["utterance_id"])
            context.append({
                "utterance_id": context_id,
                "text": text[int(context_item["start_offset"]):int(context_item["end_offset"])],
                "is_target": context_id == utterance_id,
                "confirmed_assignment": confirmed.get(context_id),
            })
        rows.append({
            "utterance_id": utterance_id,
            "sequence": int(item["sequence"]),
            "text": text[int(item["start_offset"]):int(item["end_offset"])],
            "context": context,
            "current_assignment": confirmed.get(utterance_id),
            "suggestion": suggestions.get(utterance_id),
            "invalid_item": invalid.get(utterance_id),
        })

    current = _current_revision(db, chapter_id)
    current_bible = _character_fingerprint(db, int(result["book_id"]))
    stale_reasons = []
    if not current or int(current["id"]) != int(result["text_revision_id"]):
        stale_reasons.append("TextRevision changed after this draft was generated.")
    elif str(current["content_sha256"]) != str(payload.get("text_revision_sha256")):
        stale_reasons.append("TextRevision hash no longer matches this draft.")
    if current_bible != str(result["character_bible_fingerprint"]):
        stale_reasons.append(
            "Character Bible changed after this draft was generated. Generate a new draft before approval."
        )
    confirmed_list = []
    if base_plan and int(base_plan["text_revision_id"]) == int(revision["id"]):
        confirmed_list = [
            {
                "utterance_id": str(item["utterance_id"]),
                "speaker_type": "character" if item.get("role") == "character" else item.get("role", "narrator"),
                "character_id": item.get("character_id"),
            }
            for item in base_plan["plan"].get("utterances", [])
        ]
        confirmed_list.sort(key=lambda item: item["utterance_id"])
    expected_confirmed_hash = payload.get("confirmed_assignment_context_sha256")
    current_confirmed_hash = sha256_text(canonical_json(confirmed_list))
    base_source = (base_plan["plan"].get("source_metadata") or {}) if base_plan else {}
    base_review = base_source.get("review") or {}
    if (
        expected_confirmed_hash
        and expected_confirmed_hash != current_confirmed_hash
        and not (
            base_source.get("source") == "gemini_speaker_review"
            and base_review.get("draft_id") == draft_id
        )
    ):
        stale_reasons.append("Base Casting Plan changed after this draft was generated.")
    links = _review_links(db, store, chapter_id, draft_id)
    reviewed_ids = sorted({
        utterance_id for link in links for utterance_id in link["reviewed_utterance_ids"]
    })
    reviewed_set = set(reviewed_ids)
    for row in rows:
        row["reviewed"] = row["utterance_id"] in reviewed_set
    return {
        **result,
        "stale": bool(stale_reasons),
        "stale_reasons": stale_reasons,
        "current_character_bible_fingerprint": current_bible,
        "base_casting_plan_id": int(base_row["id"]) if base_row else None,
        "base_casting_plan_revision": int(base_row["plan_revision"]) if base_row else None,
        "characters": list_characters(db, int(result["book_id"])),
        "review_rows": rows,
        "review_links": links,
        "reviewed_utterance_ids": reviewed_ids,
        "remaining_unreviewed_count": max(0, len(target_ids) - len(set(reviewed_ids))),
    }


def list_speaker_review_drafts(
    db: Database, store: ContentStore, config: Settings, *, chapter_id: int
) -> dict[str, Any]:
    if not db.fetch_one("SELECT id FROM chapters WHERE id=?", (chapter_id,)):
        raise SpeakerReviewError("Chapter not found")
    items = []
    for row in db.fetch_all(
        "SELECT id FROM speaker_assignment_drafts WHERE chapter_id=? ORDER BY created_at DESC,id DESC",
        (chapter_id,),
    ):
        draft_id = int(row["id"])
        try:
            detail = get_speaker_review_draft(
                db, store, config, chapter_id=chapter_id, draft_id=draft_id
            )
            levels = {"high": 0, "medium": 0, "low": 0}
            for assignment in detail["draft"].get("assignments", []):
                level = assignment.get("confidence_level")
                if level in levels:
                    levels[level] += 1
            items.append({
                "id": draft_id,
                "created_at": detail["created_at"],
                "model_id": detail["model_id"],
                "prompt_version": detail["prompt_version"],
                "status": detail["status"],
                "text_revision_id": detail["text_revision_id"],
                "target_count": detail["target_count"],
                "valid_count": detail["valid_count"],
                "invalid_count": detail["invalid_count"],
                "confidence_counts": levels,
                "input_fingerprint": detail["input_fingerprint"],
                "stale": detail["stale"],
                "stale_reasons": detail["stale_reasons"],
                "remaining_unreviewed_count": detail["remaining_unreviewed_count"],
            })
        except (OSError, UnicodeError, ValueError):
            items.append({
                "id": draft_id,
                "status": "invalid",
                "stale": True,
                "load_error": "Draft payload is missing, corrupt, or invalid.",
            })
    return {"chapter_id": chapter_id, "items": items}


def _decision_fingerprint(decisions: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    normalized = sorted(
        ({
            "utterance_id": str(item.get("utterance_id", "")),
            "speaker_type": str(item.get("speaker_type", "")),
            "character_id": item.get("character_id"),
            "decision_source": str(item.get("decision_source", "")),
        } for item in decisions),
        key=lambda item: item["utterance_id"],
    )
    return sha256_text(canonical_json(normalized)), normalized


def _approval_response(plan: dict[str, Any], review: dict[str, Any], *, reused: bool) -> dict[str, Any]:
    return {
        "casting_plan_id": int(plan["id"]),
        "casting_plan_revision": int(plan["plan_revision"]),
        "base_casting_plan_revision_id": review.get("base_casting_plan_id"),
        "approved_item_count": int(review["approved_count"]),
        "unchanged_item_count": int(review["unchanged_count"]),
        "decision_fingerprint": review["decision_fingerprint"],
        "idempotent_reused": reused,
        "remaining_unreviewed_count": int(review["remaining_unreviewed_count"]),
    }


def approve_speaker_review(
    db: Database,
    store: ContentStore,
    config: Settings,
    *,
    chapter_id: int,
    draft_id: int,
    base_casting_plan_revision_id: int | None,
    expected_draft_fingerprint: str,
    expected_text_revision_id: int,
    decisions: list[dict[str, Any]],
    idempotency_key: str,
    allowed_voice_ids: set[str],
    custom_voice_context: CustomVoiceContext | None = None,
) -> dict[str, Any]:
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise SpeakerReviewError("A valid idempotency_key is required")
    if not decisions:
        raise SpeakerReviewError("At least one reviewed decision is required")
    decision_fingerprint, normalized = _decision_fingerprint(decisions)
    if len({item["utterance_id"] for item in normalized}) != len(normalized):
        raise SpeakerReviewError("Duplicate utterance decision")

    with _APPROVAL_LOCK:
        for row in db.fetch_all(
            "SELECT id FROM casting_plans WHERE chapter_id=? ORDER BY plan_revision,id",
            (chapter_id,),
        ):
            plan = get_plan(db, store, int(row["id"]))
            metadata = plan["plan"].get("source_metadata") or {}
            review = metadata.get("review") or {}
            if metadata.get("source") != "gemini_speaker_review":
                continue
            same_key = review.get("idempotency_key") == idempotency_key
            same_identity = (
                review.get("draft_id") == draft_id
                and review.get("base_casting_plan_id") == base_casting_plan_revision_id
                and review.get("decision_fingerprint") == decision_fingerprint
            )
            if same_key and not same_identity:
                raise SpeakerReviewConflict("Idempotency key was already used for different decisions")
            if same_identity:
                return _approval_response(plan, review, reused=True)

        detail = get_speaker_review_draft(
            db, store, config, chapter_id=chapter_id, draft_id=draft_id
        )
        if detail["stale"]:
            raise SpeakerReviewConflict(" ".join(detail["stale_reasons"]))
        if expected_draft_fingerprint != detail["input_fingerprint"]:
            raise SpeakerReviewConflict("Draft fingerprint changed")
        if expected_text_revision_id != int(detail["text_revision_id"]):
            raise SpeakerReviewConflict("TextRevision changed")

        current_base = _current_approved_plan(db, chapter_id)
        if base_casting_plan_revision_id is None:
            if current_base:
                raise SpeakerReviewConflict("A newer approved Casting Plan must be used as the base")
            base_plan = None
        else:
            if not current_base or int(current_base["id"]) != base_casting_plan_revision_id:
                raise SpeakerReviewConflict("Base Casting Plan is no longer current")
            base_plan = get_plan(db, store, base_casting_plan_revision_id)
            if int(base_plan["text_revision_id"]) != expected_text_revision_id:
                raise SpeakerReviewConflict("Base Casting Plan pins a different TextRevision")

        rows = {item["utterance_id"]: item for item in detail["review_rows"]}
        target_ids = set(rows)
        characters = {int(item["id"]): item for item in detail["characters"] if item.get("active", 1)}
        base_assignments = {}
        if base_plan:
            base_assignments = {
                str(item["utterance_id"]): {
                    "speaker_type": "character" if item.get("role") == "character" else item.get("role", "narrator"),
                    "character_id": item.get("character_id"),
                }
                for item in base_plan["plan"]["utterances"]
            }

        casting_decisions = []
        for decision in normalized:
            utterance_id = decision["utterance_id"]
            if utterance_id not in target_ids:
                raise SpeakerReviewError("Decision does not belong to this draft/chapter")
            source = decision["decision_source"]
            speaker_type = decision["speaker_type"]
            character_id = decision["character_id"]
            if source not in DECISION_SOURCES:
                raise SpeakerReviewError("Decision source is invalid")
            if speaker_type not in {"narrator", "unknown", "character"}:
                raise SpeakerReviewError("Decision speaker_type is invalid")
            if speaker_type == "character":
                if isinstance(character_id, bool) or not isinstance(character_id, int) or character_id not in characters:
                    raise SpeakerReviewError("Decision character does not belong to this book")
            elif character_id is not None:
                raise SpeakerReviewError("Narrator/unknown decision cannot reference a character")
            suggestion = rows[utterance_id].get("suggestion")
            candidate = {"speaker_type": speaker_type, "character_id": character_id}
            if source == "gemini_suggestion":
                if not suggestion or candidate != {
                    "speaker_type": suggestion.get("speaker_type"),
                    "character_id": suggestion.get("character_id"),
                }:
                    raise SpeakerReviewError("Selected Gemini suggestion is invalid")
            elif source == "gemini_alternative":
                alternatives = suggestion.get("alternatives", []) if suggestion else []
                if not any(candidate == {
                    "speaker_type": item.get("speaker_type"), "character_id": item.get("character_id")
                } for item in alternatives):
                    raise SpeakerReviewError("Selected Gemini alternative is invalid")
            elif source == "keep_current":
                if candidate != base_assignments.get(utterance_id):
                    raise SpeakerReviewError("Current assignment is unavailable or changed")
            elif source == "manual_character" and speaker_type != "character":
                raise SpeakerReviewError("Manual character decision requires character speaker_type")
            elif source == "narrator" and speaker_type != "narrator":
                raise SpeakerReviewError("Narrator decision is invalid")
            elif source == "unknown" and speaker_type != "unknown":
                raise SpeakerReviewError("Unknown decision is invalid")
            casting_decisions.append({
                "utterance_id": utterance_id,
                "role": speaker_type,
                "character_id": character_id,
            })

        if not base_plan:
            decided = {item["utterance_id"] for item in casting_decisions}
            casting_decisions.extend({
                "utterance_id": utterance_id, "role": "unknown", "character_id": None
            } for utterance_id in sorted(target_ids - decided))

        previously_reviewed = set()
        if base_plan:
            base_metadata = base_plan["plan"].get("source_metadata") or {}
            base_review = base_metadata.get("review") or {}
            if base_review.get("draft_id") == draft_id:
                previously_reviewed.update(base_review.get("reviewed_utterance_ids") or [])
        reviewed_ids = sorted(previously_reviewed | {item["utterance_id"] for item in normalized})
        remaining = max(0, len(target_ids) - len(set(reviewed_ids)))
        review_metadata = {
            "draft_id": draft_id,
            "draft_fingerprint": detail["input_fingerprint"],
            "base_casting_plan_id": base_casting_plan_revision_id,
            "decision_fingerprint": decision_fingerprint,
            "idempotency_key": idempotency_key,
            "approved_count": len(normalized),
            "unchanged_count": len(split_utterances(
                store.read_text(str(db.fetch_one("SELECT content_path FROM text_revisions WHERE id=?", (expected_text_revision_id,))["content_path"])),
                maximum=config.tts_max_chars,
            )) - len(normalized),
            "reviewed_utterance_ids": reviewed_ids,
            "remaining_unreviewed_count": remaining,
            "reviewed_by": "local_user",
            "created_at": utcnow(),
        }
        profile = get_book_voice_profile(db, int(detail["book_id"]))
        narrator_voice_id = (
            str(base_plan["plan"]["narrator_voice_id"])
            if base_plan else str(profile["narrator_voice_id"] if profile else "")
        )
        if not narrator_voice_id:
            raise SpeakerReviewError("Create a Book Voice Profile before approving speaker review")
        created = create_casting_draft(
            db,
            store,
            chapter_id=chapter_id,
            text_revision_id=expected_text_revision_id,
            narrator_voice_id=narrator_voice_id,
            assignments=casting_decisions,
            allowed_voice_ids=allowed_voice_ids,
            maximum=config.tts_max_chars,
            source_metadata={"source": "gemini_speaker_review", "review": review_metadata},
            base_utterances=base_plan["plan"]["utterances"] if base_plan else None,
            custom_voice_context=custom_voice_context,
        )
        approved = approve_plan(db, store, int(created["id"]))
        return _approval_response(approved, review_metadata, reused=False)
