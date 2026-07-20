from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Iterable

from fastapi import File, Form, HTTPException, UploadFile

from .custom_voice import (
    CustomVoiceError,
    CustomVoiceNotFoundError,
    CustomVoiceRepository,
    CustomVoiceRevisionNotFoundError,
    DuplicateCustomVoiceNameError,
    InvalidAudioError,
    InvalidTranscriptError,
)
from .db import Database
from .storage import ContentStore

# Size limits
MAX_AUDIO_SIZE_MB = 50
MAX_AUDIO_SIZE_BYTES = MAX_AUDIO_SIZE_MB * 1024 * 1024
MAX_TRANSCRIPT_LENGTH = 10000

def _custom_voice_error_handler(exc: Exception) -> HTTPException:
    """Convert custom voice exceptions to HTTP exceptions."""
    if isinstance(exc, CustomVoiceNotFoundError):
        return HTTPException(404, str(exc))
    if isinstance(exc, CustomVoiceRevisionNotFoundError):
        return HTTPException(404, str(exc))
    if isinstance(exc, DuplicateCustomVoiceNameError):
        return HTTPException(409, str(exc))
    if isinstance(exc, (InvalidTranscriptError, InvalidAudioError)):
        return HTTPException(400, str(exc))
    if isinstance(exc, CustomVoiceError):
        return HTTPException(400, str(exc))
    return HTTPException(500, "Internal server error")

def create_custom_voice_handler(
    repo: CustomVoiceRepository,
    display_name: str,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a new custom voice."""
    try:
        voice = repo.create_custom_voice(display_name, description)
        return {
            "id": voice.id,
            "display_name": voice.display_name,
            "description": voice.description,
            "is_active": voice.is_active,
            "preferred_synthesis_revision_id": voice.preferred_synthesis_revision_id,
            "created_at": voice.created_at,
            "updated_at": voice.updated_at,
        }
    except CustomVoiceError as exc:
        raise _custom_voice_error_handler(exc) from exc

def list_custom_voices_handler(
    repo: CustomVoiceRepository,
    active_only: bool = False,
) -> list[dict[str, Any]]:
    """List all custom voices."""
    voices = repo.list_custom_voices(active_only=active_only)
    return [
        {
            "id": v.id,
            "display_name": v.display_name,
            "description": v.description,
            "is_active": v.is_active,
            "preferred_synthesis_revision_id": v.preferred_synthesis_revision_id,
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }
        for v in voices
    ]

def get_custom_voice_handler(
    repo: CustomVoiceRepository,
    voice_id: int,
) -> dict[str, Any]:
    """Get a single custom voice by ID."""
    try:
        voice = repo.get_custom_voice(voice_id)
        return {
            "id": voice.id,
            "display_name": voice.display_name,
            "description": voice.description,
            "is_active": voice.is_active,
            "preferred_synthesis_revision_id": voice.preferred_synthesis_revision_id,
            "created_at": voice.created_at,
            "updated_at": voice.updated_at,
        }
    except CustomVoiceError as exc:
        raise _custom_voice_error_handler(exc) from exc

def deactivate_custom_voice_handler(
    repo: CustomVoiceRepository,
    voice_id: int,
) -> dict[str, Any]:
    """Deactivate a custom voice."""
    try:
        voice = repo.deactivate_custom_voice(voice_id)
        return {
            "id": voice.id,
            "display_name": voice.display_name,
            "description": voice.description,
            "is_active": voice.is_active,
            "preferred_synthesis_revision_id": voice.preferred_synthesis_revision_id,
            "created_at": voice.created_at,
            "updated_at": voice.updated_at,
        }
    except CustomVoiceError as exc:
        raise _custom_voice_error_handler(exc) from exc

def reactivate_custom_voice_handler(
    repo: CustomVoiceRepository,
    voice_id: int,
) -> dict[str, Any]:
    """Reactivate a custom voice."""
    try:
        voice = repo.reactivate_custom_voice(voice_id)
        return {
            "id": voice.id,
            "display_name": voice.display_name,
            "description": voice.description,
            "is_active": voice.is_active,
            "preferred_synthesis_revision_id": voice.preferred_synthesis_revision_id,
            "created_at": voice.created_at,
            "updated_at": voice.updated_at,
        }
    except CustomVoiceError as exc:
        raise _custom_voice_error_handler(exc) from exc

def set_preferred_synthesis_revision_handler(
    repo: CustomVoiceRepository,
    voice_id: int,
    revision_id: int | None,
) -> dict[str, Any]:
    """Set or clear the preferred synthesis revision for a custom voice."""
    try:
        voice = repo.set_preferred_synthesis_revision(voice_id, revision_id)
        return {
            "id": voice.id,
            "display_name": voice.display_name,
            "description": voice.description,
            "is_active": voice.is_active,
            "preferred_synthesis_revision_id": voice.preferred_synthesis_revision_id,
            "created_at": voice.created_at,
            "updated_at": voice.updated_at,
        }
    except CustomVoiceError as exc:
        raise _custom_voice_error_handler(exc) from exc

def create_custom_voice_revision_handler(
    repo: CustomVoiceRepository,
    voice_id: int,
    audio_file: UploadFile,
    transcript: str,
) -> dict[str, Any]:
    """
    Create a new revision for a custom voice by uploading audio and transcript.
    Handles validation, storage, and cleanup atomically.
    """
    temp_path: Path | None = None
    
    try:
        # Validate transcript early
        if not transcript or not transcript.strip():
            raise HTTPException(400, "Transcript cannot be empty.")
        
        clean_transcript = transcript.strip()
        if len(clean_transcript) > MAX_TRANSCRIPT_LENGTH:
            raise HTTPException(
                400, 
                f"Transcript too long ({len(clean_transcript)} chars, max {MAX_TRANSCRIPT_LENGTH})."
            )
        
        # Read audio file
        audio_bytes = audio_file.file.read()
        
        # Validate audio size
        if len(audio_bytes) == 0:
            raise HTTPException(400, "Audio file is empty.")
        
        if len(audio_bytes) > MAX_AUDIO_SIZE_BYTES:
            raise HTTPException(
                400,
                f"Audio file too large ({len(audio_bytes)} bytes, max {MAX_AUDIO_SIZE_BYTES})."
            )
        
        # Validate filename for path traversal
        if audio_file.filename:
            filename = Path(audio_file.filename).name
            if filename != audio_file.filename or ".." in audio_file.filename:
                raise HTTPException(400, "Invalid filename.")
        
        # Create revision (handles validation, storage, and DB atomically)
        revision = repo.create_revision(voice_id, audio_bytes, clean_transcript)
        
        return {
            "id": revision.id,
            "custom_voice_id": revision.custom_voice_id,
            "revision_number": revision.revision_number,
            "audio_sha256": revision.audio_sha256,
            "transcript_sha256": revision.transcript_sha256,
            "duration_ms": revision.duration_ms,
            "sample_rate": revision.sample_rate,
            "channels": revision.channels,
            "audio_format": revision.audio_format,
            "created_at": revision.created_at,
        }
    
    except (CustomVoiceError, InvalidAudioError, InvalidTranscriptError) as exc:
        raise _custom_voice_error_handler(exc) from exc
    
    finally:
        # Cleanup temp file if created
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)

def list_custom_voice_revisions_handler(
    repo: CustomVoiceRepository,
    voice_id: int,
) -> list[dict[str, Any]]:
    """List all revisions for a custom voice."""
    try:
        revisions = repo.list_revisions(voice_id)
        return [
            {
                "id": r.id,
                "custom_voice_id": r.custom_voice_id,
                "revision_number": r.revision_number,
                "audio_sha256": r.audio_sha256,
                "transcript_sha256": r.transcript_sha256,
                "duration_ms": r.duration_ms,
                "sample_rate": r.sample_rate,
                "channels": r.channels,
                "audio_format": r.audio_format,
                "created_at": r.created_at,
            }
            for r in revisions
        ]
    except CustomVoiceError as exc:
        raise _custom_voice_error_handler(exc) from exc

def get_custom_voice_revision_handler(
    repo: CustomVoiceRepository,
    revision_id: int,
) -> dict[str, Any]:
    """Get a single custom voice revision by ID."""
    try:
        revision = repo.get_revision(revision_id)
        return {
            "id": revision.id,
            "custom_voice_id": revision.custom_voice_id,
            "revision_number": revision.revision_number,
            "audio_sha256": revision.audio_sha256,
            "transcript_sha256": revision.transcript_sha256,
            "duration_ms": revision.duration_ms,
            "sample_rate": revision.sample_rate,
            "channels": revision.channels,
            "audio_format": revision.audio_format,
            "created_at": revision.created_at,
        }
    except CustomVoiceError as exc:
        raise _custom_voice_error_handler(exc) from exc


def _revision_payload(revision) -> dict[str, Any] | None:
    if revision is None:
        return None
    return {
        "id": revision.id,
        "custom_voice_id": revision.custom_voice_id,
        "revision_number": revision.revision_number,
        "audio_sha256": revision.audio_sha256,
        "transcript_sha256": revision.transcript_sha256,
        "duration_ms": revision.duration_ms,
        "sample_rate": revision.sample_rate,
        "channels": revision.channels,
        "audio_format": revision.audio_format,
        "created_at": revision.created_at,
    }


def _effective_custom_revision(repo: CustomVoiceRepository, voice) -> tuple[Any | None, str]:
    """
    Match CustomVoiceContext revision selection without changing synthesis semantics.

    Priority:
    1. preferred synthesis revision, if it exists and belongs to the logical voice;
    2. latest revision fallback.
    """
    if voice.preferred_synthesis_revision_id is not None:
        try:
            revision = repo.get_revision(voice.preferred_synthesis_revision_id)
            if revision.custom_voice_id == voice.id:
                return revision, "preferred"
        except CustomVoiceError:
            pass
    return repo.get_latest_revision(voice.id), "latest"


def build_voice_catalog_handler(
    repo: CustomVoiceRepository,
    preset_voices: Iterable[dict[str, Any]],
    *,
    include_unavailable_custom: bool = True,
) -> dict[str, Any]:
    """Return a read-only catalog for assignment selectors."""
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for preset in preset_voices:
        key = str(preset.get("id") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        label = str(preset.get("label") or key)
        items.append(
            {
                "assignment_key": key,
                "display_name": label,
                "primary_label": label,
                "secondary_label": "Preset voice",
                "source_kind": "preset",
                "active": True,
                "usable": True,
                "selectable": True,
                "custom_voice_id": None,
                "preferred_synthesis_revision_id": None,
                "effective_synthesis_revision_id": None,
                "effective_revision_number": None,
                "effective_revision_source": None,
                "reference_duration_ms": None,
                "reference_audio_url": None,
                "provenance_summary": "Preset VieNeu voice",
                "unavailability_reason": None,
                "legacy": False,
            }
        )

    for voice in repo.list_custom_voices(active_only=not include_unavailable_custom):
        key = f"custom:{voice.id}"
        if key in seen:
            continue
        revision, revision_source = _effective_custom_revision(repo, voice)
        usable = bool(voice.is_active and revision is not None)
        reason = None
        if not voice.is_active:
            reason = "Custom voice is inactive."
        elif revision is None:
            reason = "Custom voice has no usable synthesis revision."
        rev_payload = _revision_payload(revision)
        revision_number = rev_payload["revision_number"] if rev_payload else None
        secondary = (
            f"Custom voice · Revision {revision_number}"
            if usable
            else f"Custom voice · {reason}"
        )
        duration = rev_payload["duration_ms"] if rev_payload else None
        provenance = secondary
        if usable:
            provenance = (
                f"Logical custom voice #{voice.id}; effective synthesis revision "
                f"#{rev_payload['id']} (revision {revision_number}, {revision_source}; "
                f"{duration} ms reference)."
            )
        items.append(
            {
                "assignment_key": key,
                "display_name": voice.display_name,
                "primary_label": voice.display_name,
                "secondary_label": secondary,
                "source_kind": "custom",
                "active": bool(voice.is_active),
                "usable": usable,
                "selectable": usable,
                "custom_voice_id": voice.id,
                "preferred_synthesis_revision_id": voice.preferred_synthesis_revision_id,
                "effective_synthesis_revision_id": rev_payload["id"] if rev_payload else None,
                "effective_revision_number": revision_number,
                "effective_revision_source": revision_source if rev_payload else None,
                "reference_duration_ms": duration,
                "reference_audio_url": f"/api/custom-voice-revisions/{rev_payload['id']}/audio" if rev_payload else None,
                "provenance_summary": provenance,
                "unavailability_reason": reason,
                "legacy": False,
            }
        )
        seen.add(key)

    return {"items": items}
