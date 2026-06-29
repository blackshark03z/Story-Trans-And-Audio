from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .db import Database, utcnow
from .files import sha256_bytes, sha256_text
from .storage import ContentStore


class CustomVoiceError(RuntimeError):
    """Base error for custom voice operations."""


class CustomVoiceNotFoundError(CustomVoiceError):
    """Raised when a custom voice does not exist."""


class CustomVoiceRevisionNotFoundError(CustomVoiceError):
    """Raised when a custom voice revision does not exist."""


class DuplicateCustomVoiceNameError(CustomVoiceError):
    """Raised when attempting to create a custom voice with a duplicate name."""


class InvalidTranscriptError(CustomVoiceError):
    """Raised when a transcript is invalid."""


class InvalidAudioError(CustomVoiceError):
    """Raised when audio validation fails."""


@dataclass(frozen=True)
class CustomVoice:
    id: int
    display_name: str
    description: str | None
    is_active: bool
    preferred_synthesis_revision_id: int | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class CustomVoiceRevision:
    id: int
    custom_voice_id: int
    revision_number: int
    audio_storage_key: str
    audio_sha256: str
    reference_transcript: str
    transcript_sha256: str
    duration_ms: int
    sample_rate: int
    channels: int
    audio_format: str
    created_at: str


class AudioValidator:
    """Simple audio validation interface. Can be extended with FFprobe in production."""

    def validate(self, audio_bytes: bytes) -> tuple[int, int, int, str]:
        """
        Validate audio and return (duration_ms, sample_rate, channels, format).
        Raises InvalidAudioError if validation fails.
        """
        if len(audio_bytes) == 0:
            raise InvalidAudioError("Audio data is empty.")
        # Stub implementation for tests - production would use FFprobe
        # Return plausible defaults for WAV
        duration_ms = max(1000, len(audio_bytes) // 96)  # Approximate for 48kHz stereo
        return (duration_ms, 48000, 2, "wav")


class CustomVoiceRepository:
    def __init__(self, db: Database, store: ContentStore, audio_validator: AudioValidator | None = None):
        self.db = db
        self.store = store
        self.audio_validator = audio_validator or AudioValidator()

    def create_custom_voice(
        self,
        display_name: str,
        description: str | None = None,
    ) -> CustomVoice:
        """Create a new custom voice."""
        if not display_name or not display_name.strip():
            raise CustomVoiceError("Display name cannot be empty.")
        
        now = utcnow()
        try:
            with self.db.transaction() as conn:
                cursor = conn.execute(
                    "INSERT INTO custom_voices(display_name,description,is_active,created_at,updated_at) "
                    "VALUES(?,?,1,?,?)",
                    (display_name.strip(), description, now, now),
                )
                voice_id = cursor.lastrowid
                return self._row_to_voice(
                    conn.execute("SELECT * FROM custom_voices WHERE id=?", (voice_id,)).fetchone()
                )
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                raise DuplicateCustomVoiceNameError(f"Custom voice '{display_name}' already exists.")
            raise

    def get_custom_voice(self, voice_id: int) -> CustomVoice:
        """Get a custom voice by ID."""
        row = self.db.fetch_one("SELECT * FROM custom_voices WHERE id=?", (voice_id,))
        if not row:
            raise CustomVoiceNotFoundError(f"Custom voice {voice_id} not found.")
        return self._row_to_voice(row)

    def list_custom_voices(self, active_only: bool = False) -> list[CustomVoice]:
        """List all custom voices, optionally filtering to active only."""
        if active_only:
            rows = self.db.fetch_all(
                "SELECT * FROM custom_voices WHERE is_active=1 ORDER BY display_name"
            )
        else:
            rows = self.db.fetch_all("SELECT * FROM custom_voices ORDER BY display_name")
        return [self._row_to_voice(row) for row in rows]

    def deactivate_custom_voice(self, voice_id: int) -> CustomVoice:
        """Deactivate a custom voice."""
        return self._set_active_status(voice_id, False)

    def reactivate_custom_voice(self, voice_id: int) -> CustomVoice:
        """Reactivate a custom voice."""
        return self._set_active_status(voice_id, True)

    def set_preferred_synthesis_revision(
        self, voice_id: int, revision_id: int | None
    ) -> CustomVoice:
        """
        Set or clear the preferred synthesis revision for a custom voice.
        
        Args:
            voice_id: Logical custom voice ID
            revision_id: Revision ID to prefer, or None to clear preference
            
        Raises:
            CustomVoiceNotFoundError: Voice doesn't exist
            CustomVoiceRevisionNotFoundError: Revision doesn't exist or doesn't belong to this voice
        """
        # Verify voice exists
        voice = self.get_custom_voice(voice_id)
        
        # If setting a preference, verify revision exists and belongs to this voice
        if revision_id is not None:
            revision = self.get_revision(revision_id)
            if revision.custom_voice_id != voice_id:
                raise CustomVoiceRevisionNotFoundError(
                    f"Revision {revision_id} does not belong to custom voice {voice_id}."
                )
        
        # Update preference
        now = utcnow()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE custom_voices SET preferred_synthesis_revision_id=?, updated_at=? WHERE id=?",
                (revision_id, now, voice_id),
            )
            return self._row_to_voice(
                conn.execute("SELECT * FROM custom_voices WHERE id=?", (voice_id,)).fetchone()
            )

    def _set_active_status(self, voice_id: int, is_active: bool) -> CustomVoice:
        """Update active status of a custom voice."""
        now = utcnow()
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "UPDATE custom_voices SET is_active=?, updated_at=? WHERE id=?",
                (1 if is_active else 0, now, voice_id),
            )
            if cursor.rowcount == 0:
                raise CustomVoiceNotFoundError(f"Custom voice {voice_id} not found.")
            return self._row_to_voice(
                conn.execute("SELECT * FROM custom_voices WHERE id=?", (voice_id,)).fetchone()
            )

    def create_revision(
        self,
        custom_voice_id: int,
        audio_bytes: bytes,
        reference_transcript: str,
    ) -> CustomVoiceRevision:
        """
        Create an immutable revision for a custom voice.
        Validates audio and transcript, stores audio in content-addressed storage.
        """
        # Validate transcript
        if not reference_transcript or not reference_transcript.strip():
            raise InvalidTranscriptError("Transcript cannot be empty.")
        transcript = reference_transcript.strip()
        transcript_sha = sha256_text(transcript)

        # Validate audio
        try:
            duration_ms, sample_rate, channels, audio_format = self.audio_validator.validate(audio_bytes)
        except InvalidAudioError:
            raise
        except Exception as e:
            raise InvalidAudioError(f"Audio validation failed: {e}")

        # Store audio in content-addressed storage
        audio_sha = sha256_bytes(audio_bytes)
        audio_key = self.store.put_audio(audio_bytes, audio_sha)

        # Allocate revision number and insert
        now = utcnow()
        with self.db.transaction() as conn:
            # Verify custom voice exists
            voice_row = conn.execute(
                "SELECT id FROM custom_voices WHERE id=?", (custom_voice_id,)
            ).fetchone()
            if not voice_row:
                raise CustomVoiceNotFoundError(f"Custom voice {custom_voice_id} not found.")

            # Allocate next revision number
            current_max = conn.execute(
                "SELECT COALESCE(MAX(revision_number), 0) AS max_rev FROM custom_voice_revisions "
                "WHERE custom_voice_id=?",
                (custom_voice_id,),
            ).fetchone()["max_rev"]
            next_revision = current_max + 1

            # Insert revision
            cursor = conn.execute(
                """INSERT INTO custom_voice_revisions(
                    custom_voice_id,revision_number,audio_storage_key,audio_sha256,
                    reference_transcript,transcript_sha256,duration_ms,sample_rate,
                    channels,audio_format,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    custom_voice_id,
                    next_revision,
                    audio_key,
                    audio_sha,
                    transcript,
                    transcript_sha,
                    duration_ms,
                    sample_rate,
                    channels,
                    audio_format,
                    now,
                ),
            )
            revision_id = cursor.lastrowid
            return self._row_to_revision(
                conn.execute("SELECT * FROM custom_voice_revisions WHERE id=?", (revision_id,)).fetchone()
            )

    def get_revision(self, revision_id: int) -> CustomVoiceRevision:
        """Get a revision by ID."""
        row = self.db.fetch_one("SELECT * FROM custom_voice_revisions WHERE id=?", (revision_id,))
        if not row:
            raise CustomVoiceRevisionNotFoundError(f"Revision {revision_id} not found.")
        return self._row_to_revision(row)

    def get_latest_revision(self, custom_voice_id: int) -> CustomVoiceRevision | None:
        """Get the latest revision for a custom voice, or None if no revisions exist."""
        row = self.db.fetch_one(
            "SELECT * FROM custom_voice_revisions WHERE custom_voice_id=? "
            "ORDER BY revision_number DESC LIMIT 1",
            (custom_voice_id,),
        )
        return self._row_to_revision(row) if row else None

    def list_revisions(self, custom_voice_id: int) -> list[CustomVoiceRevision]:
        """List all revisions for a custom voice, ordered by revision number descending."""
        rows = self.db.fetch_all(
            "SELECT * FROM custom_voice_revisions WHERE custom_voice_id=? "
            "ORDER BY revision_number DESC",
            (custom_voice_id,),
        )
        return [self._row_to_revision(row) for row in rows]

    @staticmethod
    def _row_to_voice(row: sqlite3.Row) -> CustomVoice:
        return CustomVoice(
            id=int(row["id"]),
            display_name=str(row["display_name"]),
            description=row["description"],
            is_active=bool(row["is_active"]),
            preferred_synthesis_revision_id=row["preferred_synthesis_revision_id"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _row_to_revision(row: sqlite3.Row) -> CustomVoiceRevision:
        return CustomVoiceRevision(
            id=int(row["id"]),
            custom_voice_id=int(row["custom_voice_id"]),
            revision_number=int(row["revision_number"]),
            audio_storage_key=str(row["audio_storage_key"]),
            audio_sha256=str(row["audio_sha256"]),
            reference_transcript=str(row["reference_transcript"]),
            transcript_sha256=str(row["transcript_sha256"]),
            duration_ms=int(row["duration_ms"]),
            sample_rate=int(row["sample_rate"]),
            channels=int(row["channels"]),
            audio_format=str(row["audio_format"]),
            created_at=str(row["created_at"]),
        )


__all__ = [
    "AudioValidator",
    "CustomVoice",
    "CustomVoiceError",
    "CustomVoiceNotFoundError",
    "CustomVoiceRepository",
    "CustomVoiceRevision",
    "CustomVoiceRevisionNotFoundError",
    "DuplicateCustomVoiceNameError",
    "InvalidAudioError",
    "InvalidTranscriptError",
]
