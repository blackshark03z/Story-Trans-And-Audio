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
    book_id: int | None
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
        *,
        book_id: int | None = None,
    ) -> CustomVoice:
        """Create a new custom voice."""
        if book_id is not None and int(book_id) <= 0:
            raise CustomVoiceError("Book is invalid.")
        if not display_name or not display_name.strip():
            raise CustomVoiceError("Display name cannot be empty.")
        
        now = utcnow()
        try:
            with self.db.transaction() as conn:
                supports_book_scope = self._book_scope_supported(conn)
                if supports_book_scope and book_id is None:
                    raise CustomVoiceError("Book is required when creating a custom voice.")
                if book_id is not None and not supports_book_scope:
                    raise CustomVoiceError("Book-scoped custom voices require schema version 16.")
                if book_id is not None and not conn.execute("SELECT 1 FROM books WHERE id=?", (int(book_id),)).fetchone():
                    raise CustomVoiceError("Book not found.")
                if supports_book_scope:
                    cursor = conn.execute(
                        "INSERT INTO custom_voices(book_id,display_name,description,is_active,created_at,updated_at) "
                        "VALUES(?,?,?,1,?,?)",
                        (int(book_id) if book_id is not None else None, display_name.strip(), description, now, now),
                    )
                else:
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

    def list_custom_voices(self, active_only: bool = False, book_id: int | None = None) -> list[CustomVoice]:
        """List voices, optionally limited to the normal library of one book."""
        where: list[str] = []
        params: list[object] = []
        if active_only:
            where.append("is_active=1")
        if book_id is not None:
            if int(book_id) <= 0:
                raise CustomVoiceError("Book is required for a custom voice library.")
            if not self._book_scope_supported():
                return []
            where.append("book_id=?")
            params.append(int(book_id))
        elif self._book_scope_supported():
            # NULL ownership is reserved for voices created before schema 16.
            # Unscoped callers may inspect legacy history but cannot receive a
            # voice belonging to a different book.
            where.append("book_id IS NULL")
        clause = f" WHERE {' AND '.join(where)}" if where else ""
        rows = self.db.fetch_all(
            f"SELECT * FROM custom_voices{clause} ORDER BY display_name", tuple(params)
        )
        return [self._row_to_voice(row) for row in rows]

    def list_effective_custom_voices(
        self, *, book_id: int | None, active_only: bool = False
    ) -> list[CustomVoice]:
        """Return the synthesis context: legacy voices plus one selected book."""
        if book_id is None:
            return self.list_custom_voices(active_only=active_only)
        if int(book_id) <= 0:
            raise CustomVoiceError("Book is required for an effective custom voice context.")
        if not self._book_scope_supported():
            return self.list_custom_voices(active_only=active_only)
        where = "is_active=1 AND " if active_only else ""
        rows = self.db.fetch_all(
            f"SELECT * FROM custom_voices WHERE {where}(book_id IS NULL OR book_id=?) "
            "ORDER BY display_name",
            (int(book_id),),
        )
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

    def create_custom_voice_with_revision(
        self,
        book_id: int,
        display_name: str,
        audio_bytes: bytes,
        reference_transcript: str,
        description: str | None = None,
    ) -> tuple[CustomVoice, CustomVoiceRevision]:
        """Create a book-owned voice and its first immutable revision together."""
        voice = self.create_custom_voice(display_name, description, book_id=book_id)
        try:
            return voice, self.create_revision(voice.id, audio_bytes, reference_transcript)
        except Exception:
            # This cleanup is only for the just-created, unreferenced logical
            # voice. Historical/referenced voices are never deleted here.
            with self.db.transaction() as conn:
                conn.execute("DELETE FROM custom_voices WHERE id=?", (voice.id,))
            raise

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

    def _book_scope_supported(self, connection: sqlite3.Connection | None = None) -> bool:
        rows = (connection.execute("PRAGMA table_info(custom_voices)").fetchall()
                if connection is not None else self.db.fetch_all("PRAGMA table_info(custom_voices)"))
        return any(row["name"] == "book_id" for row in rows)

    @staticmethod
    def _row_to_voice(row: sqlite3.Row) -> CustomVoice:
        row_keys = set(row.keys())
        return CustomVoice(
            id=int(row["id"]),
            book_id=int(row["book_id"]) if "book_id" in row_keys and row["book_id"] is not None else None,
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
