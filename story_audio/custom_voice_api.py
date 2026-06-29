from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

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
