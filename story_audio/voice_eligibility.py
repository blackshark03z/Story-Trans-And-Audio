from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .voice_ref import MalformedVoiceRefError, is_custom_ref, parse_custom_ref


CATALOG_SCHEMA = "story-audio-effective-voice-catalog/v1"
ISSUE_SCHEMA = "story-audio-voice-eligibility-issue/v1"


class VoiceCatalogUnavailable(RuntimeError):
    """The authoritative synthesis catalog could not be loaded safely."""


class VoiceEligibilityBlocked(ValueError):
    """One or more pinned effective voices cannot be synthesized."""

    def __init__(self, issues: tuple[dict[str, Any], ...]):
        self.issues = issues
        message = issues[0]["message"] if issues else "Voice eligibility is blocked."
        super().__init__(message)


def normalize_voice_id(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Voice ID must be a string.")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        raise ValueError("Voice ID is empty.")
    if len(normalized) > 200:
        raise ValueError("Voice ID is too long.")
    if any(unicodedata.category(char).startswith("C") for char in normalized):
        raise ValueError("Voice ID contains unsupported control characters.")
    if is_custom_ref(normalized):
        try:
            return f"custom:{parse_custom_ref(normalized)}"
        except MalformedVoiceRefError as exc:
            raise ValueError(str(exc)) from exc
    return normalized


@dataclass(frozen=True)
class EffectiveVoiceCatalog:
    items: tuple[dict[str, Any], ...]
    selectable_ids: frozenset[str]
    preset_ids: frozenset[str]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "EffectiveVoiceCatalog":
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise VoiceCatalogUnavailable(
                "Voice catalog returned an invalid shape. Retry after the catalog service is available."
            )
        items: list[dict[str, Any]] = []
        selectable: set[str] = set()
        preset_ids: set[str] = set()
        seen: set[str] = set()
        for raw in raw_items:
            if not isinstance(raw, Mapping):
                raise VoiceCatalogUnavailable(
                    "Voice catalog contains an invalid item. Retry after the catalog is repaired."
                )
            try:
                assignment_key = normalize_voice_id(raw.get("assignment_key"))
            except ValueError as exc:
                raise VoiceCatalogUnavailable(
                    f"Voice catalog contains an invalid identifier: {exc}"
                ) from exc
            if assignment_key in seen:
                raise VoiceCatalogUnavailable(
                    f"Voice catalog contains duplicate identifier '{assignment_key}'."
                )
            seen.add(assignment_key)
            item = dict(raw)
            item["assignment_key"] = assignment_key
            item["selectable"] = bool(
                raw.get("selectable") is True
                and raw.get("active") is not False
                and raw.get("usable") is not False
            )
            items.append(item)
            if item["selectable"]:
                selectable.add(assignment_key)
                if item.get("source_kind") == "preset":
                    preset_ids.add(assignment_key)
        if not selectable:
            raise VoiceCatalogUnavailable(
                "Voice catalog has no selectable synthesis voices. Retry after VieNeu/catalog recovery."
            )
        return cls(tuple(items), frozenset(selectable), frozenset(preset_ids))

    @classmethod
    def from_ids(cls, *voice_ids: str) -> "EffectiveVoiceCatalog":
        items = tuple(
            {
                "assignment_key": normalize_voice_id(voice_id),
                "display_name": normalize_voice_id(voice_id),
                "source_kind": "preset",
                "active": True,
                "usable": True,
                "selectable": True,
            }
            for voice_id in voice_ids
        )
        return cls.from_payload({"items": list(items)})

    def public_payload(self) -> dict[str, Any]:
        return {
            "schema": CATALOG_SCHEMA,
            "items": [dict(item) for item in self.items],
            "selectable_count": len(self.selectable_ids),
        }


class VoiceCatalogAuthority:
    """Loads and validates one authoritative assignment/synthesis catalog."""

    def __init__(self, loader: Callable[[], Mapping[str, Any]]):
        self._loader = loader

    def load(self) -> EffectiveVoiceCatalog:
        try:
            payload = self._loader()
            if not isinstance(payload, Mapping):
                raise VoiceCatalogUnavailable(
                    "Voice catalog service returned an invalid response."
                )
            return EffectiveVoiceCatalog.from_payload(payload)
        except VoiceCatalogUnavailable:
            raise
        except Exception as exc:
            raise VoiceCatalogUnavailable(
                "Voice catalog is unavailable. Retry after VieNeu/catalog recovery; "
                "PREPARE and START_RENDER remain blocked."
            ) from exc


def _speaker_label(role: str, character_id: Any) -> str:
    if role == "narrator":
        return "narrator"
    if role == "character" and character_id not in (None, ""):
        return f"character:{character_id}"
    if role == "unknown":
        return "unknown speaker"
    return role or "unresolved speaker"


def _issue(
    *,
    code: str,
    voice_id: Any,
    chapter_id: int | None,
    chapter_number: int | None,
    role: str,
    character_id: Any = None,
    utterance_id: Any = None,
    sequence: Any = None,
    detail: str,
) -> dict[str, Any]:
    raw_voice_id = voice_id if isinstance(voice_id, str) else ""
    speaker = _speaker_label(role, character_id)
    chapter = (
        f"chapter {chapter_number}"
        if chapter_number is not None
        else f"chapter_id {chapter_id}" if chapter_id is not None else "the pinned chapter"
    )
    return {
        "schema": ISSUE_SCHEMA,
        "code": code,
        "voice_id": raw_voice_id,
        "chapter_id": chapter_id,
        "chapter_number": chapter_number,
        "speaker_role": role or "unknown",
        "speaker": speaker,
        "character_id": int(character_id) if character_id not in (None, "") else None,
        "utterance_id": str(utterance_id) if utterance_id not in (None, "") else None,
        "sequence": int(sequence) if sequence not in (None, "") else None,
        "replacement_required": True,
        "message": (
            f"Voice '{raw_voice_id or '<missing>'}' is not eligible for {speaker} in "
            f"{chapter}: {detail} Replacement is required; no fallback was applied."
        ),
    }


def inspect_voice_ref(
    voice_id: Any,
    catalog: EffectiveVoiceCatalog,
    *,
    chapter_id: int | None,
    chapter_number: int | None,
    role: str,
    character_id: Any = None,
    utterance_id: Any = None,
    sequence: Any = None,
) -> dict[str, Any] | None:
    try:
        normalized = normalize_voice_id(voice_id)
    except ValueError as exc:
        return _issue(
            code="VOICE_ID_MALFORMED",
            voice_id=voice_id,
            chapter_id=chapter_id,
            chapter_number=chapter_number,
            role=role,
            character_id=character_id,
            utterance_id=utterance_id,
            sequence=sequence,
            detail=str(exc),
        )
    if normalized not in catalog.selectable_ids:
        return _issue(
            code="VOICE_UNAVAILABLE",
            voice_id=voice_id,
            chapter_id=chapter_id,
            chapter_number=chapter_number,
            role=role,
            character_id=character_id,
            utterance_id=utterance_id,
            sequence=sequence,
            detail="the identifier is missing or unavailable in the current synthesis catalog.",
        )
    return None


def inspect_casting_plan(
    plan: Mapping[str, Any],
    catalog: EffectiveVoiceCatalog,
    *,
    chapter_id: int | None = None,
    chapter_number: int | None = None,
) -> tuple[dict[str, Any], ...]:
    issues: list[dict[str, Any]] = []
    utterances = plan.get("utterances")
    checked_narrator = False
    if isinstance(utterances, list):
        for utterance in utterances:
            if not isinstance(utterance, Mapping):
                issues.append(
                    _issue(
                        code="VOICE_ASSIGNMENT_MALFORMED",
                        voice_id=None,
                        chapter_id=chapter_id,
                        chapter_number=chapter_number,
                        role="unknown",
                        detail="the Casting Plan contains a malformed utterance assignment.",
                    )
                )
                continue
            role = str(utterance.get("role") or "unknown")
            if role == "narrator":
                checked_narrator = True
            issue = inspect_voice_ref(
                utterance.get("resolved_voice_id"),
                catalog,
                chapter_id=chapter_id,
                chapter_number=chapter_number,
                role=role,
                character_id=utterance.get("character_id"),
                utterance_id=utterance.get("utterance_id"),
                sequence=utterance.get("sequence"),
            )
            if issue:
                issues.append(issue)
    else:
        issues.append(
            _issue(
                code="VOICE_ASSIGNMENT_MALFORMED",
                voice_id=None,
                chapter_id=chapter_id,
                chapter_number=chapter_number,
                role="unknown",
                detail="the Casting Plan utterance list is missing or malformed.",
            )
        )
    if not checked_narrator:
        issue = inspect_voice_ref(
            plan.get("narrator_voice_id"),
            catalog,
            chapter_id=chapter_id,
            chapter_number=chapter_number,
            role="narrator",
        )
        if issue:
            issues.append(issue)
    return tuple(issues)


def require_casting_plan_eligible(
    plan: Mapping[str, Any],
    catalog: EffectiveVoiceCatalog,
    *,
    chapter_id: int | None = None,
    chapter_number: int | None = None,
) -> None:
    issues = inspect_casting_plan(
        plan,
        catalog,
        chapter_id=chapter_id,
        chapter_number=chapter_number,
    )
    if issues:
        raise VoiceEligibilityBlocked(issues)


def require_prepared_job_eligible(
    db,
    *,
    job_id: int,
    catalog: EffectiveVoiceCatalog,
) -> None:
    job = db.fetch_one("SELECT * FROM jobs WHERE id=?", (int(job_id),))
    if not job:
        raise LookupError("Prepared job was not found.")
    chapters = db.fetch_all(
        """SELECT jc.*,c.chapter_number
           FROM job_chapters jc JOIN chapters c ON c.id=jc.chapter_id
           WHERE jc.job_id=? ORDER BY jc.sequence,jc.id""",
        (int(job_id),),
    )
    if not chapters:
        raise VoiceEligibilityBlocked(
            (
                _issue(
                    code="PINNED_VOICE_SNAPSHOT_MISSING",
                    voice_id=None,
                    chapter_id=None,
                    chapter_number=None,
                    role="unknown",
                    detail="the prepared Job has no pinned chapter voice snapshot.",
                ),
            )
        )
    issues: list[dict[str, Any]] = []
    for chapter in chapters:
        raw = chapter["voice_snapshot_json"]
        if raw in (None, ""):
            issue = inspect_voice_ref(
                job["voice_name"],
                catalog,
                chapter_id=int(chapter["chapter_id"]),
                chapter_number=int(chapter["chapter_number"]),
                role="narrator",
            )
            if issue:
                issues.append(issue)
            continue
        try:
            plan = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            plan = None
        if not isinstance(plan, Mapping):
            issues.append(
                _issue(
                    code="PINNED_VOICE_SNAPSHOT_MALFORMED",
                    voice_id=None,
                    chapter_id=int(chapter["chapter_id"]),
                    chapter_number=int(chapter["chapter_number"]),
                    role="unknown",
                    detail="the immutable JobChapter voice snapshot is invalid.",
                )
            )
            continue
        issues.extend(
            inspect_casting_plan(
                plan,
                catalog,
                chapter_id=int(chapter["chapter_id"]),
                chapter_number=int(chapter["chapter_number"]),
            )
        )
    if issues:
        raise VoiceEligibilityBlocked(tuple(issues))


__all__ = [
    "CATALOG_SCHEMA",
    "EffectiveVoiceCatalog",
    "VoiceCatalogAuthority",
    "VoiceCatalogUnavailable",
    "VoiceEligibilityBlocked",
    "inspect_casting_plan",
    "inspect_voice_ref",
    "normalize_voice_id",
    "require_casting_plan_eligible",
    "require_prepared_job_eligible",
]
