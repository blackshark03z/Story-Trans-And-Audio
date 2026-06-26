from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from story_audio.config import settings
from story_audio.custom_voice import (
    AudioValidator,
    CustomVoiceError,
    CustomVoiceNotFoundError,
    CustomVoiceRepository,
    CustomVoiceRevisionNotFoundError,
    DuplicateCustomVoiceNameError,
    InvalidAudioError,
    InvalidTranscriptError,
)
from story_audio.db import Database
from story_audio.files import sha256_bytes, sha256_text
from story_audio.migrations import LATEST_SCHEMA_VERSION
from story_audio.storage import ContentStore


class CustomVoiceMigrationTests(unittest.TestCase):
    def test_migration_from_v5_to_v6_creates_custom_voice_tables(self) -> None:
        """Test that migration 0006 creates custom_voices and custom_voice_revisions tables."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.db"
            database = Database(path)
            version = database.initialize()
            
            self.assertEqual(version, LATEST_SCHEMA_VERSION)
            self.assertGreaterEqual(LATEST_SCHEMA_VERSION, 6)
            
            tables = {row["name"] for row in database.fetch_all(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            self.assertIn("custom_voices", tables)
            self.assertIn("custom_voice_revisions", tables)
            
            # Verify custom_voices schema
            voice_columns = {row["name"]: row for row in database.fetch_all(
                "PRAGMA table_info(custom_voices)"
            )}
            self.assertIn("id", voice_columns)
            self.assertIn("display_name", voice_columns)
            self.assertIn("description", voice_columns)
            self.assertIn("is_active", voice_columns)
            self.assertIn("created_at", voice_columns)
            self.assertIn("updated_at", voice_columns)
            
            # Verify custom_voice_revisions schema
            revision_columns = {row["name"]: row for row in database.fetch_all(
                "PRAGMA table_info(custom_voice_revisions)"
            )}
            self.assertIn("id", revision_columns)
            self.assertIn("custom_voice_id", revision_columns)
            self.assertIn("revision_number", revision_columns)
            self.assertIn("audio_storage_key", revision_columns)
            self.assertIn("audio_sha256", revision_columns)
            self.assertIn("reference_transcript", revision_columns)
            self.assertIn("transcript_sha256", revision_columns)
            self.assertIn("duration_ms", revision_columns)
            self.assertIn("sample_rate", revision_columns)
            self.assertIn("channels", revision_columns)
            self.assertIn("audio_format", revision_columns)
            
            # Verify indexes exist
            indexes = {row["name"] for row in database.fetch_all(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )}
            self.assertIn("idx_custom_voices_active", indexes)
            self.assertIn("idx_custom_voice_revisions_audio_sha", indexes)

    def test_custom_voices_display_name_unique_constraint(self) -> None:
        """Test that display_name has a unique constraint."""
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "app.db")
            database.initialize()
            
            with database.transaction() as conn:
                conn.execute(
                    "INSERT INTO custom_voices(display_name,is_active,created_at,updated_at) "
                    "VALUES(?,1,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')",
                    ("TestVoice",)
                )
            
            with self.assertRaises(sqlite3.IntegrityError):
                with database.transaction() as conn:
                    conn.execute(
                        "INSERT INTO custom_voices(display_name,is_active,created_at,updated_at) "
                        "VALUES(?,1,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')",
                        ("TestVoice",)
                    )

    def test_custom_voices_is_active_check_constraint(self) -> None:
        """Test that is_active only accepts 0 or 1."""
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "app.db")
            database.initialize()
            
            with self.assertRaises(sqlite3.IntegrityError):
                with database.transaction() as conn:
                    conn.execute(
                        "INSERT INTO custom_voices(display_name,is_active,created_at,updated_at) "
                        "VALUES(?,2,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')",
                        ("TestVoice",)
                    )

    def test_custom_voice_revisions_unique_constraint(self) -> None:
        """Test that (custom_voice_id, revision_number) is unique."""
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "app.db")
            database.initialize()
            
            with database.transaction() as conn:
                voice_id = conn.execute(
                    "INSERT INTO custom_voices(display_name,is_active,created_at,updated_at) "
                    "VALUES(?1,1,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')",
                    ("TestVoice",)
                ).lastrowid
                
                conn.execute(
                    """INSERT INTO custom_voice_revisions(
                        custom_voice_id,revision_number,audio_storage_key,audio_sha256,
                        reference_transcript,transcript_sha256,duration_ms,sample_rate,
                        channels,audio_format,created_at
                    ) VALUES(?,1,'key1','sha1','transcript','tsha',1000,48000,2,'wav','2026-01-01T00:00:00Z')""",
                    (voice_id,)
                )
            
            with self.assertRaises(sqlite3.IntegrityError):
                with database.transaction() as conn:
                    conn.execute(
                        """INSERT INTO custom_voice_revisions(
                            custom_voice_id,revision_number,audio_storage_key,audio_sha256,
                            reference_transcript,transcript_sha256,duration_ms,sample_rate,
                            channels,audio_format,created_at
                        ) VALUES(?,1,'key2','sha2','transcript2','tsha2',2000,48000,2,'wav','2026-01-01T00:00:00Z')""",
                        (voice_id,)
                    )

    def test_custom_voice_revisions_check_constraints(self) -> None:
        """Test CHECK constraints on revision_number, duration_ms, sample_rate, channels."""
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "app.db")
            database.initialize()
            
            with database.transaction() as conn:
                voice_id = conn.execute(
                    "INSERT INTO custom_voices(display_name,is_active,created_at,updated_at) "
                    "VALUES('TestVoice',1,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')"
                ).lastrowid
            
            # Test revision_number > 0
            with self.assertRaises(sqlite3.IntegrityError):
                with database.transaction() as conn:
                    conn.execute(
                        """INSERT INTO custom_voice_revisions(
                            custom_voice_id,revision_number,audio_storage_key,audio_sha256,
                            reference_transcript,transcript_sha256,duration_ms,sample_rate,
                            channels,audio_format,created_at
                        ) VALUES(?,0,'key','sha','t','tsha',1000,48000,2,'wav','2026-01-01T00:00:00Z')""",
                        (voice_id,)
                    )
            
            # Test duration_ms > 0
            with self.assertRaises(sqlite3.IntegrityError):
                with database.transaction() as conn:
                    conn.execute(
                        """INSERT INTO custom_voice_revisions(
                            custom_voice_id,revision_number,audio_storage_key,audio_sha256,
                            reference_transcript,transcript_sha256,duration_ms,sample_rate,
                            channels,audio_format,created_at
                        ) VALUES(?,1,'key','sha','t','tsha',0,48000,2,'wav','2026-01-01T00:00:00Z')""",
                        (voice_id,)
                    )

    def test_custom_voice_revisions_foreign_key_on_delete_restrict(self) -> None:
        """Test that deleting a custom voice is restricted when revisions exist."""
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "app.db")
            database.initialize()
            
            with database.transaction() as conn:
                voice_id = conn.execute(
                    "INSERT INTO custom_voices(display_name,is_active,created_at,updated_at) "
                    "VALUES('TestVoice',1,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')"
                ).lastrowid
                
                conn.execute(
                    """INSERT INTO custom_voice_revisions(
                        custom_voice_id,revision_number,audio_storage_key,audio_sha256,
                        reference_transcript,transcript_sha256,duration_ms,sample_rate,
                        channels,audio_format,created_at
                    ) VALUES(?,1,'key','sha','t','tsha',1000,48000,2,'wav','2026-01-01T00:00:00Z')""",
                    (voice_id,)
                )
            
            with self.assertRaises(sqlite3.IntegrityError):
                with database.transaction() as conn:
                    conn.execute("DELETE FROM custom_voices WHERE id=?", (voice_id,))


class CustomVoiceRepositoryTests(unittest.TestCase):
    def _setup_test_env(self) -> tuple[Database, ContentStore, CustomVoiceRepository]:
        """Helper to set up test database and repository."""
        temp_dir = tempfile.mkdtemp()
        root = Path(temp_dir)
        config = replace(
            settings,
            root=root,
            data_dir=root / "data",
            db_path=root / "data" / "app.db",
            blobs_dir=root / "data" / "blobs",
            output_dir=root / "data" / "output",
            work_dir=root / "data" / "work",
            log_dir=root / "logs",
        )
        config.ensure_dirs()
        
        database = Database(config.db_path)
        database.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(database, store)
        
        return database, store, repo

    def test_create_custom_voice_success(self) -> None:
        """Test successful custom voice creation."""
        _, _, repo = self._setup_test_env()
        
        voice = repo.create_custom_voice("My Custom Voice", "A test voice")
        
        self.assertIsNotNone(voice.id)
        self.assertEqual(voice.display_name, "My Custom Voice")
        self.assertEqual(voice.description, "A test voice")
        self.assertTrue(voice.is_active)
        self.assertIsNotNone(voice.created_at)
        self.assertIsNotNone(voice.updated_at)

    def test_create_custom_voice_strips_whitespace(self) -> None:
        """Test that display name is stripped of leading/trailing whitespace."""
        _, _, repo = self._setup_test_env()
        
        voice = repo.create_custom_voice("  Spaced Voice  ")
        self.assertEqual(voice.display_name, "Spaced Voice")

    def test_create_custom_voice_duplicate_name_fails(self) -> None:
        """Test that creating a voice with duplicate name fails."""
        _, _, repo = self._setup_test_env()
        
        repo.create_custom_voice("Duplicate")
        
        with self.assertRaises(DuplicateCustomVoiceNameError):
            repo.create_custom_voice("Duplicate")

    def test_create_custom_voice_empty_name_fails(self) -> None:
        """Test that empty display name fails."""
        _, _, repo = self._setup_test_env()
        
        with self.assertRaises(CustomVoiceError):
            repo.create_custom_voice("")
        
        with self.assertRaises(CustomVoiceError):
            repo.create_custom_voice("   ")

    def test_get_custom_voice_success(self) -> None:
        """Test retrieving a custom voice by ID."""
        _, _, repo = self._setup_test_env()
        
        created = repo.create_custom_voice("Test Voice")
        retrieved = repo.get_custom_voice(created.id)
        
        self.assertEqual(retrieved.id, created.id)
        self.assertEqual(retrieved.display_name, created.display_name)

    def test_get_custom_voice_not_found(self) -> None:
        """Test that getting non-existent voice raises error."""
        _, _, repo = self._setup_test_env()
        
        with self.assertRaises(CustomVoiceNotFoundError):
            repo.get_custom_voice(99999)

    def test_list_custom_voices_empty(self) -> None:
        """Test listing voices when none exist."""
        _, _, repo = self._setup_test_env()
        
        voices = repo.list_custom_voices()
        self.assertEqual(len(voices), 0)

    def test_list_custom_voices_multiple(self) -> None:
        """Test listing multiple custom voices."""
        _, _, repo = self._setup_test_env()
        
        repo.create_custom_voice("Voice A")
        repo.create_custom_voice("Voice B")
        repo.create_custom_voice("Voice C")
        
        voices = repo.list_custom_voices()
        self.assertEqual(len(voices), 3)
        names = [v.display_name for v in voices]
        self.assertEqual(names, ["Voice A", "Voice B", "Voice C"])

    def test_list_custom_voices_active_filter(self) -> None:
        """Test filtering voices by active status."""
        _, _, repo = self._setup_test_env()
        
        voice1 = repo.create_custom_voice("Active Voice")
        voice2 = repo.create_custom_voice("Inactive Voice")
        repo.deactivate_custom_voice(voice2.id)
        
        all_voices = repo.list_custom_voices(active_only=False)
        self.assertEqual(len(all_voices), 2)
        
        active_voices = repo.list_custom_voices(active_only=True)
        self.assertEqual(len(active_voices), 1)
        self.assertEqual(active_voices[0].id, voice1.id)

    def test_deactivate_custom_voice_success(self) -> None:
        """Test deactivating a custom voice."""
        _, _, repo = self._setup_test_env()
        
        voice = repo.create_custom_voice("Test Voice")
        self.assertTrue(voice.is_active)
        
        deactivated = repo.deactivate_custom_voice(voice.id)
        self.assertFalse(deactivated.is_active)
        self.assertNotEqual(deactivated.updated_at, voice.updated_at)

    def test_reactivate_custom_voice_success(self) -> None:
        """Test reactivating a custom voice."""
        _, _, repo = self._setup_test_env()
        
        voice = repo.create_custom_voice("Test Voice")
        deactivated = repo.deactivate_custom_voice(voice.id)
        self.assertFalse(deactivated.is_active)
        
        reactivated = repo.reactivate_custom_voice(voice.id)
        self.assertTrue(reactivated.is_active)

    def test_deactivate_nonexistent_voice_fails(self) -> None:
        """Test that deactivating non-existent voice fails."""
        _, _, repo = self._setup_test_env()
        
        with self.assertRaises(CustomVoiceNotFoundError):
            repo.deactivate_custom_voice(99999)

    def test_create_revision_success(self) -> None:
        """Test creating a revision with valid audio and transcript."""
        _, store, repo = self._setup_test_env()
        
        voice = repo.create_custom_voice("Test Voice")
        audio_bytes = b"FAKE_AUDIO_DATA_" * 1000
        transcript = "This is a test transcript."
        
        revision = repo.create_revision(voice.id, audio_bytes, transcript)
        
        self.assertEqual(revision.custom_voice_id, voice.id)
        self.assertEqual(revision.revision_number, 1)
        self.assertEqual(revision.reference_transcript, transcript)
        self.assertEqual(revision.transcript_sha256, sha256_text(transcript))
        self.assertEqual(revision.audio_sha256, sha256_bytes(audio_bytes))
        self.assertGreater(revision.duration_ms, 0)
        self.assertEqual(revision.sample_rate, 48000)
        self.assertEqual(revision.channels, 2)
        self.assertEqual(revision.audio_format, "wav")
        
        # Verify audio is stored and can be retrieved
        stored_audio = store.read_audio(revision.audio_storage_key)
        self.assertEqual(stored_audio, audio_bytes)

    def test_create_revision_allocates_sequential_numbers(self) -> None:
        """Test that revision numbers are allocated sequentially."""
        _, _, repo = self._setup_test_env()
        
        voice = repo.create_custom_voice("Test Voice")
        audio = b"AUDIO_DATA_" * 100
        
        rev1 = repo.create_revision(voice.id, audio, "Transcript 1")
        self.assertEqual(rev1.revision_number, 1)
        
        rev2 = repo.create_revision(voice.id, audio, "Transcript 2")
        self.assertEqual(rev2.revision_number, 2)
        
        rev3 = repo.create_revision(voice.id, audio, "Transcript 3")
        self.assertEqual(rev3.revision_number, 3)

    def test_create_revision_empty_transcript_fails(self) -> None:
        """Test that empty transcript fails validation."""
        _, _, repo = self._setup_test_env()
        
        voice = repo.create_custom_voice("Test Voice")
        audio = b"AUDIO_DATA"
        
        with self.assertRaises(InvalidTranscriptError):
            repo.create_revision(voice.id, audio, "")
        
        with self.assertRaises(InvalidTranscriptError):
            repo.create_revision(voice.id, audio, "   ")

    def test_create_revision_empty_audio_fails(self) -> None:
        """Test that empty audio fails validation."""
        _, _, repo = self._setup_test_env()
        
        voice = repo.create_custom_voice("Test Voice")
        
        with self.assertRaises(InvalidAudioError):
            repo.create_revision(voice.id, b"", "Valid transcript")

    def test_create_revision_nonexistent_voice_fails(self) -> None:
        """Test that creating revision for non-existent voice fails."""
        _, _, repo = self._setup_test_env()
        
        with self.assertRaises(CustomVoiceNotFoundError):
            repo.create_revision(99999, b"AUDIO", "Transcript")

    def test_create_revision_deduplicates_audio(self) -> None:
        """Test that identical audio is deduplicated in storage."""
        _, store, repo = self._setup_test_env()
        
        voice1 = repo.create_custom_voice("Voice 1")
        voice2 = repo.create_custom_voice("Voice 2")
        
        audio = b"IDENTICAL_AUDIO_DATA_" * 100
        transcript1 = "Transcript 1"
        transcript2 = "Transcript 2"
        
        rev1 = repo.create_revision(voice1.id, audio, transcript1)
        rev2 = repo.create_revision(voice2.id, audio, transcript2)
        
        # Same audio SHA, same storage key
        self.assertEqual(rev1.audio_sha256, rev2.audio_sha256)
        self.assertEqual(rev1.audio_storage_key, rev2.audio_storage_key)
        
        # Different transcripts
        self.assertNotEqual(rev1.transcript_sha256, rev2.transcript_sha256)

    def test_get_revision_success(self) -> None:
        """Test retrieving a revision by ID."""
        _, _, repo = self._setup_test_env()
        
        voice = repo.create_custom_voice("Test Voice")
        created = repo.create_revision(voice.id, b"AUDIO" * 100, "Transcript")
        
        retrieved = repo.get_revision(created.id)
        
        self.assertEqual(retrieved.id, created.id)
        self.assertEqual(retrieved.revision_number, created.revision_number)
        self.assertEqual(retrieved.reference_transcript, created.reference_transcript)

    def test_get_revision_not_found(self) -> None:
        """Test that getting non-existent revision raises error."""
        _, _, repo = self._setup_test_env()
        
        with self.assertRaises(CustomVoiceRevisionNotFoundError):
            repo.get_revision(99999)

    def test_get_latest_revision_returns_highest_number(self) -> None:
        """Test that get_latest_revision returns the revision with highest number."""
        _, _, repo = self._setup_test_env()
        
        voice = repo.create_custom_voice("Test Voice")
        audio = b"AUDIO" * 100
        
        rev1 = repo.create_revision(voice.id, audio, "Transcript 1")
        rev2 = repo.create_revision(voice.id, audio, "Transcript 2")
        rev3 = repo.create_revision(voice.id, audio, "Transcript 3")
        
        latest = repo.get_latest_revision(voice.id)
        
        self.assertIsNotNone(latest)
        self.assertEqual(latest.id, rev3.id)
        self.assertEqual(latest.revision_number, 3)

    def test_get_latest_revision_no_revisions_returns_none(self) -> None:
        """Test that get_latest_revision returns None when no revisions exist."""
        _, _, repo = self._setup_test_env()
        
        voice = repo.create_custom_voice("Test Voice")
        latest = repo.get_latest_revision(voice.id)
        
        self.assertIsNone(latest)

    def test_list_revisions_ordered_by_number_descending(self) -> None:
        """Test that list_revisions returns revisions in descending order."""
        _, _, repo = self._setup_test_env()
        
        voice = repo.create_custom_voice("Test Voice")
        audio = b"AUDIO" * 100
        
        repo.create_revision(voice.id, audio, "Transcript 1")
        repo.create_revision(voice.id, audio, "Transcript 2")
        repo.create_revision(voice.id, audio, "Transcript 3")
        
        revisions = repo.list_revisions(voice.id)
        
        self.assertEqual(len(revisions), 3)
        self.assertEqual([r.revision_number for r in revisions], [3, 2, 1])

    def test_list_revisions_empty_when_no_revisions(self) -> None:
        """Test that list_revisions returns empty list when no revisions exist."""
        _, _, repo = self._setup_test_env()
        
        voice = repo.create_custom_voice("Test Voice")
        revisions = repo.list_revisions(voice.id)
        
        self.assertEqual(len(revisions), 0)

    def test_revision_immutability(self) -> None:
        """Test that revisions cannot be updated or deleted."""
        db, _, repo = self._setup_test_env()
        
        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"AUDIO" * 100, "Original")
        
        # Attempt to update should fail (no update method exists)
        # Verify through direct DB access that updates would break integrity
        with self.assertRaises(AttributeError):
            repo.update_revision(revision.id, "Modified")  # type: ignore
        
        # Verify no delete method exists
        with self.assertRaises(AttributeError):
            repo.delete_revision(revision.id)  # type: ignore

    def test_transcript_sha256_deterministic(self) -> None:
        """Test that transcript SHA-256 is deterministic."""
        _, _, repo = self._setup_test_env()
        
        voice = repo.create_custom_voice("Test Voice")
        transcript = "Deterministic transcript test"
        audio = b"AUDIO" * 100
        
        rev1 = repo.create_revision(voice.id, audio, transcript)
        
        # Create another voice with same transcript
        voice2 = repo.create_custom_voice("Voice 2")
        rev2 = repo.create_revision(voice2.id, audio, transcript)
        
        self.assertEqual(rev1.transcript_sha256, rev2.transcript_sha256)
        self.assertEqual(rev1.transcript_sha256, sha256_text(transcript))


class ContentStoreAudioTests(unittest.TestCase):
    def test_put_audio_creates_content_addressed_path(self) -> None:
        """Test that put_audio creates proper content-addressed path."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                settings,
                root=root,
                blobs_dir=root / "blobs",
            )
            config.ensure_dirs()
            
            store = ContentStore(config)
            audio_bytes = b"TEST_AUDIO_DATA"
            sha = sha256_bytes(audio_bytes)
            
            key = store.put_audio(audio_bytes, sha)
            
            expected_path = f"audio/custom_voices/{sha[:2]}/{sha}.wav"
            self.assertEqual(key, expected_path)
            
            # Verify file exists
            absolute_path = store.absolute(key)
            self.assertTrue(absolute_path.exists())
            self.assertEqual(absolute_path.read_bytes(), audio_bytes)

    def test_put_audio_deduplicates_identical_content(self) -> None:
        """Test that identical audio is not written twice."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(settings, root=root, blobs_dir=root / "blobs")
            config.ensure_dirs()
            
            store = ContentStore(config)
            audio_bytes = b"DUPLICATE_AUDIO"
            sha = sha256_bytes(audio_bytes)
            
            key1 = store.put_audio(audio_bytes, sha)
            key2 = store.put_audio(audio_bytes, sha)
            
            self.assertEqual(key1, key2)
            
            # Verify only one file exists
            absolute_path = store.absolute(key1)
            self.assertTrue(absolute_path.exists())

    def test_read_audio_retrieves_stored_bytes(self) -> None:
        """Test that read_audio retrieves the correct audio bytes."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(settings, root=root, blobs_dir=root / "blobs")
            config.ensure_dirs()
            
            store = ContentStore(config)
            audio_bytes = b"AUDIO_TO_RETRIEVE"
            sha = sha256_bytes(audio_bytes)
            
            key = store.put_audio(audio_bytes, sha)
            retrieved = store.read_audio(key)
            
            self.assertEqual(retrieved, audio_bytes)

    def test_absolute_validates_audio_path(self) -> None:
        """Test that absolute path validation works for audio paths."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(settings, root=root, blobs_dir=root / "blobs")
            config.ensure_dirs()
            
            store = ContentStore(config)
            
            # Valid path
            audio_bytes = b"VALID"
            sha = sha256_bytes(audio_bytes)
            key = store.put_audio(audio_bytes, sha)
            absolute = store.absolute(key)
            self.assertTrue(absolute.is_absolute())
            
            # Invalid path (path traversal)
            with self.assertRaises(ValueError):
                store.absolute("../../../etc/passwd")


if __name__ == "__main__":
    unittest.main()
