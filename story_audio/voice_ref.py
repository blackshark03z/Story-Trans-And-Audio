# story_audio/voice_ref.py
"""
Logical voice reference parsing and resolution.

Supports two kinds of voice references:
  - Preset:  "duc_tri" (any non-custom string)
  - Custom:  "custom:<positive_integer>"  e.g. "custom:7"

Malformed custom references are rejected explicitly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


CUSTOM_PREFIX = "custom:"
_CUSTOM_PATTERN = re.compile(r"^custom:(\d+)$")


class VoiceRefError(ValueError):
    """Base error for voice reference problems."""


class MalformedVoiceRefError(VoiceRefError):
    """Voice reference string is malformed."""


class CustomVoiceNotFoundError(VoiceRefError):
    """Custom voice does not exist in DB."""


class CustomVoiceInactiveError(VoiceRefError):
    """Custom voice is inactive and cannot be assigned."""


class CustomVoiceNoRevisionError(VoiceRefError):
    """Custom voice has no immutable revision yet."""


class CustomVoiceRevisionDataError(VoiceRefError):
    """Custom voice revision data is invalid."""


class PresetVoiceNotFoundError(VoiceRefError):
    """Preset voice ID is not in the available set."""


def is_custom_ref(voice_ref: str) -> bool:
    """Return True if the string is a custom voice reference (valid or malformed)."""
    return str(voice_ref).startswith(CUSTOM_PREFIX)


def parse_custom_ref(voice_ref: str) -> int:
    """
    Parse a custom voice reference string and return the custom_voice_id.
    
    Accepts: "custom:<positive_integer>"  e.g. "custom:7"
    Rejects with MalformedVoiceRefError:
        - "custom:"  (no ID)
        - "custom:abc"  (non-integer)
        - "custom:-1"  (negative)
        - "custom:0"  (zero)
        - "custom:1:2"  (multiple colons)
    """
    m = _CUSTOM_PATTERN.match(str(voice_ref))
    if not m:
        raise MalformedVoiceRefError(
            f"Invalid custom voice reference: {voice_ref!r}. "
            "Expected format: custom:<positive_integer>"
        )
    value = int(m.group(1))
    if value <= 0:
        raise MalformedVoiceRefError(
            f"Custom voice ID must be a positive integer, got: {value}"
        )
    return value


def custom_ref(custom_voice_id: int) -> str:
    """Return the canonical logical reference string for a custom voice."""
    return f"custom:{custom_voice_id}"


def custom_voice_ref_dict(revision) -> dict[str, Any]:
    """
    Build the structured resolver output for a custom voice reference.
    'revision' is a CustomVoiceRevision dataclass instance.
    """
    return {
        "kind": "custom_reference",
        "logical_voice_ref": custom_ref(revision.custom_voice_id),
        "custom_voice_id": revision.custom_voice_id,
        "custom_voice_revision_id": revision.id,
        "revision_number": revision.revision_number,
        "audio_storage_key": revision.audio_storage_key,
        "audio_sha256": revision.audio_sha256,
        "reference_transcript": revision.reference_transcript,
        "transcript_sha256": revision.transcript_sha256,
        "duration_ms": revision.duration_ms,
        "sample_rate": revision.sample_rate,
        "channels": revision.channels,
        "audio_format": revision.audio_format,
        "provider": "custom",
        "model": "custom_reference",
    }


@dataclass(frozen=True)
class CustomVoiceEntry:
    """An active custom voice with at least one revision, ready for assignment."""
    custom_voice_id: int
    logical_ref: str  # "custom:<id>"
    latest_revision_id: int
    revision_number: int
    audio_storage_key: str
    audio_sha256: str
    reference_transcript: str
    transcript_sha256: str
    duration_ms: int
    sample_rate: int
    channels: int
    audio_format: str


class CustomVoiceContext:
    """
    A prepared catalog of available custom voices for a session.
    Built once and passed to resolver/validation functions.
    Used instead of querying the DB on every utterance.
    """
    
    def __init__(self, entries: list[CustomVoiceEntry]):
        self._by_id: dict[int, CustomVoiceEntry] = {e.custom_voice_id: e for e in entries}
    
    def get(self, custom_voice_id: int) -> CustomVoiceEntry | None:
        return self._by_id.get(custom_voice_id)
    
    def logical_refs(self) -> set[str]:
        """Return the set of logical reference strings for all available custom voices."""
        return {e.logical_ref for e in self._by_id.values()}
    
    def is_available(self, voice_ref: str) -> bool:
        """Return True if this voice_ref is an available custom reference."""
        if not is_custom_ref(voice_ref):
            return False
        try:
            cid = parse_custom_ref(voice_ref)
        except MalformedVoiceRefError:
            return False
        return cid in self._by_id
    
    @classmethod
    def from_repository(cls, repository) -> "CustomVoiceContext":
        """
        Build a CustomVoiceContext from a CustomVoiceRepository.
        Only includes active custom voices that have at least one revision.
        Latest revision is selected by revision_number DESC (deterministic).
        """
        entries = []
        for voice in repository.list_custom_voices(active_only=True):
            latest = repository.get_latest_revision(voice.id)
            if latest is None:
                continue  # Skip voices with no revision
            entries.append(CustomVoiceEntry(
                custom_voice_id=voice.id,
                logical_ref=custom_ref(voice.id),
                latest_revision_id=latest.id,
                revision_number=latest.revision_number,
                audio_storage_key=latest.audio_storage_key,
                audio_sha256=latest.audio_sha256,
                reference_transcript=latest.reference_transcript,
                transcript_sha256=latest.transcript_sha256,
                duration_ms=latest.duration_ms,
                sample_rate=latest.sample_rate,
                channels=latest.channels,
                audio_format=latest.audio_format,
            ))
        return cls(entries)


def resolve_custom_ref(
    voice_ref: str,
    context: CustomVoiceContext,
    repository=None,  # CustomVoiceRepository | None
) -> dict[str, Any]:
    """
    Resolve a custom voice reference to its structured output dict.
    
    Validates:
    1. Parses voice_ref - raises MalformedVoiceRefError if malformed
    2. Looks up in context (available, active, has revision) - raises appropriate errors
    
    Returns custom_voice_ref_dict(revision_dataclass_like).
    """
    custom_voice_id = parse_custom_ref(voice_ref)  # raises MalformedVoiceRefError
    entry = context.get(custom_voice_id)
    if entry is None:
        # Distinguish: does not exist vs inactive vs no revision
        if repository is not None:
            try:
                voice = repository.get_custom_voice(custom_voice_id)
                if not voice.is_active:
                    raise CustomVoiceInactiveError(
                        f"Custom voice {custom_voice_id} is inactive and cannot be assigned."
                    )
                latest = repository.get_latest_revision(custom_voice_id)
                if latest is None:
                    raise CustomVoiceNoRevisionError(
                        f"Custom voice {custom_voice_id} has no revision yet."
                    )
            except Exception:
                raise
        # Raise not found if repository not provided or voice isn't in active catalog
        raise CustomVoiceNotFoundError(
            f"Custom voice {custom_voice_id} is not available (not found, inactive, or has no revision)."
        )
    # Build structured output from entry fields
    class _Rev:
        pass
    rev = _Rev()
    rev.custom_voice_id = entry.custom_voice_id
    rev.id = entry.latest_revision_id
    rev.revision_number = entry.revision_number
    rev.audio_storage_key = entry.audio_storage_key
    rev.audio_sha256 = entry.audio_sha256
    rev.reference_transcript = entry.reference_transcript
    rev.transcript_sha256 = entry.transcript_sha256
    rev.duration_ms = entry.duration_ms
    rev.sample_rate = entry.sample_rate
    rev.channels = entry.channels
    rev.audio_format = entry.audio_format
    return custom_voice_ref_dict(rev)
