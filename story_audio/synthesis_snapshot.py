"""
Synthesis snapshot loading and validation.

Provides immutable synthesis input from segment snapshots.
Single source of truth for deterministic synthesis and retry.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .files import sha256_text
from .storage import ContentStore


# Exception hierarchy

class SynthesisSnapshotError(RuntimeError):
    """Base error for synthesis snapshot problems."""


class LegacySynthesisSnapshotError(SynthesisSnapshotError):
    """
    Segment has no synthesis snapshot (voice_snapshot_version IS NULL).
    
    Legacy segments with verified WAVs may remain untouched.
    Synthesis, resynthesis, or retry requires a new job.
    """


class UnsupportedSynthesisSnapshotError(SynthesisSnapshotError):
    """Snapshot version is not supported by current code."""


class SnapshotIntegrityError(SynthesisSnapshotError):
    """Snapshot data failed integrity verification (SHA-256 mismatch)."""


class SnapshotValidationError(SynthesisSnapshotError):
    """Snapshot is incomplete or contains invalid data."""


class StorageResolutionError(SynthesisSnapshotError):
    """Failed to resolve or load reference audio from managed storage."""


# Immutable dataclasses

@dataclass(frozen=True)
class SynthesisSettings:
    """
    Parsed and validated synthesis settings from snapshot.
    Contains only TTS-relevant parameters.
    """
    temperature: float
    top_k: int
    max_chars: int
    silence_seconds: float
    engine_version: str
    
    @classmethod
    def from_json(cls, settings_json: str, voice_provider: str, voice_model: str) -> "SynthesisSettings":
        """
        Parse and validate synthesis_settings_json.
        
        Args:
            settings_json: JSON string from synthesis_settings_json column
            voice_provider: Dedicated voice_provider column value
            voice_model: Dedicated voice_model column value
        
        Returns:
            SynthesisSettings with validated fields
        
        Raises:
            SnapshotValidationError: If JSON invalid, required keys missing, unknown keys present, or values invalid
        """
        # Parse JSON
        try:
            settings = json.loads(settings_json)
        except json.JSONDecodeError as exc:
            raise SnapshotValidationError(f"Invalid synthesis_settings_json: {exc}") from exc
        
        if not isinstance(settings, dict):
            raise SnapshotValidationError("synthesis_settings_json must be a JSON object")
        
        # Required keys for snapshot version 1
        required = {"temperature", "top_k", "max_chars", "engine_version"}
        missing = required - settings.keys()
        if missing:
            raise SnapshotValidationError(f"Missing required settings keys: {missing}")
        
        # Unknown keys policy for version 1: allow but ignore (forward compatibility)
        # Only validate known keys
        
        # Extract and validate types
        temperature_raw = settings["temperature"]
        top_k_raw = settings["top_k"]
        max_chars_raw = settings["max_chars"]
        silence_seconds_raw = settings.get("silence_seconds", 0.0)
        engine_version_raw = settings["engine_version"]
        
        # Type validation - reject strings masquerading as numbers
        if not isinstance(temperature_raw, (int, float)) or isinstance(temperature_raw, bool):
            raise SnapshotValidationError(f"temperature must be numeric, got {type(temperature_raw).__name__}")
        if not isinstance(top_k_raw, int) or isinstance(top_k_raw, bool):
            raise SnapshotValidationError(f"top_k must be integer, got {type(top_k_raw).__name__}")
        if not isinstance(max_chars_raw, int) or isinstance(max_chars_raw, bool):
            raise SnapshotValidationError(f"max_chars must be integer, got {type(max_chars_raw).__name__}")
        if not isinstance(silence_seconds_raw, (int, float)) or isinstance(silence_seconds_raw, bool):
            raise SnapshotValidationError(f"silence_seconds must be numeric, got {type(silence_seconds_raw).__name__}")
        if not isinstance(engine_version_raw, str):
            raise SnapshotValidationError(f"engine_version must be string, got {type(engine_version_raw).__name__}")
        
        # Convert to Python types
        temperature = float(temperature_raw)
        top_k = int(top_k_raw)
        max_chars = int(max_chars_raw)
        silence_seconds = float(silence_seconds_raw)
        engine_version = str(engine_version_raw)
        
        # Validate finite values
        if not math.isfinite(temperature):
            raise SnapshotValidationError(f"temperature must be finite, got {temperature}")
        if not math.isfinite(silence_seconds):
            raise SnapshotValidationError(f"silence_seconds must be finite, got {silence_seconds}")
        
        # Validate ranges (match existing config constraints)
        if not (0.0 <= temperature <= 2.0):
            raise SnapshotValidationError(f"temperature out of range [0.0, 2.0]: {temperature}")
        if not (1 <= top_k <= 1000):
            raise SnapshotValidationError(f"top_k out of range [1, 1000]: {top_k}")
        if not (1 <= max_chars <= 1000):
            raise SnapshotValidationError(f"max_chars out of range [1, 1000]: {max_chars}")
        if not (0.0 <= silence_seconds <= 10.0):
            raise SnapshotValidationError(f"silence_seconds out of range [0.0, 10.0]: {silence_seconds}")
        
        # Validate engine_version format
        if not engine_version or ":" not in engine_version:
            raise SnapshotValidationError(f"engine_version must be 'provider:model' format, got: {engine_version}")
        
        # Parse provider:model
        parts = engine_version.split(":", 1)
        settings_provider, settings_model = parts[0], parts[1]
        
        # Validate agreement with dedicated columns
        if settings_provider != voice_provider:
            raise SnapshotValidationError(
                f"Provider conflict: synthesis_settings_json has '{settings_provider}', "
                f"voice_provider column has '{voice_provider}'"
            )
        if settings_model != voice_model:
            raise SnapshotValidationError(
                f"Model conflict: synthesis_settings_json has '{settings_model}', "
                f"voice_model column has '{voice_model}'"
            )
        
        return cls(
            temperature=temperature,
            top_k=top_k,
            max_chars=max_chars,
            silence_seconds=silence_seconds,
            engine_version=engine_version,
        )


@dataclass(frozen=True)
class SegmentSynthesisInput:
    """
    Complete immutable synthesis input loaded from segment snapshot.
    All fields validated and ready for TTS engine.
    Single source of truth for deterministic synthesis.
    """
    # Snapshot metadata
    snapshot_version: int
    
    # Voice routing
    voice_source_type: Literal["preset", "custom_reference"]
    voice_provider: str
    voice_model: str
    
    # Text content
    text: str
    text_sha256: str
    
    # Synthesis parameters
    settings: SynthesisSettings
    
    # Preset voice (populated if voice_source_type == "preset")
    preset_voice_id: str | None
    
    # Custom voice (all populated if voice_source_type == "custom_reference")
    custom_voice_revision_id: int | None
    reference_audio_path: Path | None
    reference_audio_sha256: str | None
    reference_transcript: str | None
    reference_transcript_sha256: str | None
    
    # Provenance (informational)
    logical_voice_ref: str
    effective_voice_ref: str
    voice_resolution_reason: str
    casting_plan_id: int | None
    
    # Segment position
    segment_index: int
    is_final_segment: bool
    
    def effective_silence_seconds(self) -> float:
        """
        Calculate effective silence based on segment position.
        Final segment overrides to 0.0 per pipeline rule.
        """
        if self.is_final_segment:
            return 0.0
        return self.settings.silence_seconds


# Snapshot loader

def load_segment_synthesis_input(
    segment: dict[str, Any],
    store: ContentStore,
    *,
    is_final_segment: bool,
) -> SegmentSynthesisInput:
    """
    Load immutable synthesis input from segment snapshot.
    
    Single source of truth for deterministic synthesis.
    Used by both normal processing and retry.
    
    Args:
        segment: Segment row dict from DB (all columns)
        store: ContentStore for loading text and reference audio
        is_final_segment: Whether this is the final segment in the chapter
    
    Returns:
        SegmentSynthesisInput with validated fields
    
    Raises:
        LegacySynthesisSnapshotError: If snapshot_version is NULL
        UnsupportedSynthesisSnapshotError: If snapshot_version != 1
        SnapshotValidationError: If snapshot incomplete or invalid
        SnapshotIntegrityError: If SHA-256 verification fails
        StorageResolutionError: If reference audio cannot be loaded
    
    No database queries performed.
    """
    # Phase 1: Snapshot version check
    snapshot_version = segment.get("voice_snapshot_version")
    if snapshot_version is None:
        segment_id = segment.get("id", "unknown")
        raise LegacySynthesisSnapshotError(
            f"Segment {segment_id} has no synthesis snapshot (voice_snapshot_version IS NULL); "
            f"create new job to synthesize with current configuration"
        )
    
    if snapshot_version != 1:
        raise UnsupportedSynthesisSnapshotError(f"Snapshot version {snapshot_version} not supported")
    
    # Phase 2: Common field presence
    required_fields = [
        "voice_source_type",
        "voice_provider",
        "voice_model",
        "logical_voice_ref",
        "effective_voice_ref",
        "synthesis_settings_json",
        "text_path",
        "text_sha256",
        "segment_index",
        "voice_resolution_reason",
    ]
    for field in required_fields:
        if segment.get(field) is None:
            raise SnapshotValidationError(f"Missing required field: {field}")
    
    voice_source_type = segment["voice_source_type"]
    
    # Validate source type
    if voice_source_type not in ("preset", "custom_reference"):
        raise SnapshotValidationError(f"Invalid voice_source_type: {voice_source_type}")
    
    # Phase 3: Provider/model validation
    voice_provider = segment["voice_provider"]
    voice_model = segment["voice_model"]
    
    if voice_provider != "vieneu":
        raise SnapshotValidationError(f"Unsupported provider: {voice_provider}")
    if voice_model != "v3turbo":
        raise SnapshotValidationError(f"Unsupported model: {voice_model}")
    
    # Phase 4: Settings parsing
    settings = SynthesisSettings.from_json(
        segment["synthesis_settings_json"],
        voice_provider,
        voice_model,
    )
    
    # Phase 5: Text loading and verification
    text = store.read_text(segment["text_path"])
    text_sha_computed = sha256_text(text)
    if text_sha_computed != segment["text_sha256"]:
        raise SnapshotIntegrityError(
            f"Text SHA-256 mismatch: expected {segment['text_sha256']}, got {text_sha_computed}"
        )
    
    # Phase 6: Voice source branching
    if voice_source_type == "custom_reference":
        # Custom reference branch (Phase 3B3-B)
        # Validate required custom fields
        custom_voice_revision_id = segment.get("custom_voice_revision_id")
        reference_audio_storage_key = segment.get("reference_audio_storage_key")
        reference_audio_sha256 = segment.get("reference_audio_sha256")
        reference_transcript = segment.get("reference_transcript")
        reference_transcript_sha256 = segment.get("reference_transcript_sha256")
        
        # Validate revision ID
        if custom_voice_revision_id is None:
            raise SnapshotValidationError("Custom reference missing custom_voice_revision_id")
        if not isinstance(custom_voice_revision_id, int) or isinstance(custom_voice_revision_id, bool):
            raise SnapshotValidationError(f"custom_voice_revision_id must be integer, got {type(custom_voice_revision_id).__name__}")
        if custom_voice_revision_id <= 0:
            raise SnapshotValidationError(f"custom_voice_revision_id must be positive, got {custom_voice_revision_id}")
        
        # Validate storage key
        if not reference_audio_storage_key or not isinstance(reference_audio_storage_key, str):
            raise SnapshotValidationError("Custom reference missing or invalid reference_audio_storage_key")
        if reference_audio_storage_key.strip() == "":
            raise SnapshotValidationError("Custom reference reference_audio_storage_key is empty")
        
        # Validate audio SHA-256
        if not reference_audio_sha256 or not isinstance(reference_audio_sha256, str):
            raise SnapshotValidationError("Custom reference missing or invalid reference_audio_sha256")
        if len(reference_audio_sha256) != 64 or not all(c in "0123456789abcdef" for c in reference_audio_sha256):
            raise SnapshotValidationError(f"Invalid reference_audio_sha256 format: {reference_audio_sha256}")
        
        # Validate transcript
        if reference_transcript is None or not isinstance(reference_transcript, str):
            raise SnapshotValidationError("Custom reference missing or invalid reference_transcript")
        if reference_transcript.strip() == "":
            raise SnapshotValidationError("Custom reference reference_transcript is empty")
        
        # Validate transcript SHA-256
        if not reference_transcript_sha256 or not isinstance(reference_transcript_sha256, str):
            raise SnapshotValidationError("Custom reference missing or invalid reference_transcript_sha256")
        if len(reference_transcript_sha256) != 64 or not all(c in "0123456789abcdef" for c in reference_transcript_sha256):
            raise SnapshotValidationError(f"Invalid reference_transcript_sha256 format: {reference_transcript_sha256}")
        
        # Validate effective_voice_ref matches custom:<revision_id> format
        effective_voice_ref = segment["effective_voice_ref"]
        expected_ref = f"custom:{custom_voice_revision_id}"
        if effective_voice_ref != expected_ref:
            raise SnapshotValidationError(
                f"Custom reference effective_voice_ref mismatch: "
                f"expected '{expected_ref}', got '{effective_voice_ref}'"
            )
        
        # Managed storage resolution with safety checks
        # Check for absolute path
        if Path(reference_audio_storage_key).is_absolute():
            raise StorageResolutionError("Absolute storage keys are not allowed")
        
        # Check for parent traversal
        if ".." in Path(reference_audio_storage_key).parts:
            raise StorageResolutionError("Parent traversal in storage key is not allowed")
        
        # Resolve through ContentStore
        try:
            reference_audio_path = store.absolute(reference_audio_storage_key)
        except ValueError as exc:
            raise StorageResolutionError(f"Invalid storage key: {exc}") from exc
        
        # Verify it's a regular file
        if not reference_audio_path.exists():
            raise StorageResolutionError(f"Reference audio does not exist: {reference_audio_storage_key}")
        if not reference_audio_path.is_file():
            raise StorageResolutionError(f"Reference audio is not a regular file: {reference_audio_storage_key}")
        
        # Audio integrity check
        from .files import sha256_file
        audio_sha_computed = sha256_file(reference_audio_path)
        if audio_sha_computed != reference_audio_sha256:
            raise SnapshotIntegrityError(
                f"Reference audio SHA-256 mismatch: expected {reference_audio_sha256}, got {audio_sha_computed}"
            )
        
        # Transcript integrity check
        transcript_sha_computed = sha256_text(reference_transcript)
        if transcript_sha_computed != reference_transcript_sha256:
            raise SnapshotIntegrityError(
                f"Reference transcript SHA-256 mismatch: expected {reference_transcript_sha256}, got {transcript_sha_computed}"
            )
        
        # Return immutable custom reference input
        return SegmentSynthesisInput(
            snapshot_version=snapshot_version,
            voice_source_type="custom_reference",
            voice_provider=voice_provider,
            voice_model=voice_model,
            text=text,
            text_sha256=segment["text_sha256"],
            settings=settings,
            preset_voice_id=None,
            custom_voice_revision_id=custom_voice_revision_id,
            reference_audio_path=reference_audio_path,
            reference_audio_sha256=reference_audio_sha256,
            reference_transcript=reference_transcript,
            reference_transcript_sha256=reference_transcript_sha256,
            logical_voice_ref=segment["logical_voice_ref"],
            effective_voice_ref=effective_voice_ref,
            voice_resolution_reason=segment["voice_resolution_reason"],
            casting_plan_id=segment.get("casting_plan_id"),
            segment_index=segment["segment_index"],
            is_final_segment=is_final_segment,
        )
    
    # Phase 7: Preset branch
    effective_voice_ref = segment["effective_voice_ref"]
    if not effective_voice_ref or not effective_voice_ref.strip():
        raise SnapshotValidationError("Preset voice effective_voice_ref is empty")
    
    # Validate custom fields are NULL for preset
    custom_fields = [
        "custom_voice_revision_id",
        "reference_audio_sha256",
        "reference_audio_storage_key",
        "reference_transcript",
        "reference_transcript_sha256",
    ]
    for field in custom_fields:
        if segment.get(field) is not None:
            raise SnapshotValidationError(f"Preset voice has custom field '{field}' populated")
    
    # Return immutable input
    return SegmentSynthesisInput(
        snapshot_version=snapshot_version,
        voice_source_type="preset",
        voice_provider=voice_provider,
        voice_model=voice_model,
        text=text,
        text_sha256=segment["text_sha256"],
        settings=settings,
        preset_voice_id=effective_voice_ref,
        custom_voice_revision_id=None,
        reference_audio_path=None,
        reference_audio_sha256=None,
        reference_transcript=None,
        reference_transcript_sha256=None,
        logical_voice_ref=segment["logical_voice_ref"],
        effective_voice_ref=effective_voice_ref,
        voice_resolution_reason=segment["voice_resolution_reason"],
        casting_plan_id=segment.get("casting_plan_id"),
        segment_index=segment["segment_index"],
        is_final_segment=is_final_segment,
    )
