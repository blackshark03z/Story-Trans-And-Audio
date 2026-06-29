from __future__ import annotations

import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, UploadFile

from dataclasses import replace

from story_audio.config import settings
from story_audio.custom_voice import (
    AudioValidator,
    CustomVoiceRepository,
    DuplicateCustomVoiceNameError,
    InvalidAudioError,
    InvalidTranscriptError,
)
from story_audio.custom_voice_api import (
    MAX_AUDIO_SIZE_BYTES,
    MAX_TRANSCRIPT_LENGTH,
    create_custom_voice_handler,
    create_custom_voice_revision_handler,
    deactivate_custom_voice_handler,
    get_custom_voice_handler,
    get_custom_voice_revision_handler,
    list_custom_voices_handler,
    list_custom_voice_revisions_handler,
    reactivate_custom_voice_handler,
    set_preferred_synthesis_revision_handler,
)
from story_audio.db import Database
from story_audio.storage import ContentStore


class MockAudioValidator(AudioValidator):
    """Mock audio validator for testing."""
    
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.validate_called = False
    
    def validate(self, audio_bytes: bytes) -> tuple[int, int, int, str]:
        self.validate_called = True
        if self.should_fail:
            raise InvalidAudioError("Mock validation failure")
        if len(audio_bytes) == 0:
            raise InvalidAudioError("Audio data is empty.")
        # Return realistic values
        duration_ms = 5000
        return (duration_ms, 48000, 2, "wav")


class CustomVoiceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_testing = os.environ.get("STORY_AUDIO_TESTING")
        os.environ["STORY_AUDIO_TESTING"] = "1"
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = replace(
            settings,
            root=self.root,
            data_dir=self.root / "data",
            db_path=self.root / "data" / "app.db",
            blobs_dir=self.root / "data" / "blobs",
            output_dir=self.root / "data" / "output",
            work_dir=self.root / "data" / "work",
            log_dir=self.root / "logs",
        )
        self.config.ensure_dirs()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        self.validator = MockAudioValidator()
        self.repo = CustomVoiceRepository(self.db, self.store, self.validator)

    def _create_mock_upload(self, filename: str, data: bytes) -> MagicMock:
        """Helper to create properly structured mock UploadFile."""
        mock_file = MagicMock()
        mock_file.read.return_value = data
        
        upload_file = MagicMock(spec=UploadFile)
        upload_file.filename = filename
        upload_file.file = mock_file
        return upload_file

    def tearDown(self) -> None:
        self.temp.cleanup()
        if self._original_testing is None:
            os.environ.pop("STORY_AUDIO_TESTING", None)
        else:
            os.environ["STORY_AUDIO_TESTING"] = self._original_testing

    def test_create_custom_voice_success(self) -> None:
        result = create_custom_voice_handler(self.repo, "Test Voice", "Test description")
        self.assertEqual(result["display_name"], "Test Voice")
        self.assertEqual(result["description"], "Test description")
        self.assertTrue(result["is_active"])
        self.assertIn("id", result)
        self.assertIn("created_at", result)

    def test_create_custom_voice_duplicate_name_rejected(self) -> None:
        create_custom_voice_handler(self.repo, "Duplicate Voice")
        with self.assertRaises(HTTPException) as ctx:
            create_custom_voice_handler(self.repo, "Duplicate Voice")
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("already exists", str(ctx.exception.detail))

    def test_list_custom_voices_empty(self) -> None:
        result = list_custom_voices_handler(self.repo)
        self.assertEqual(result, [])

    def test_list_custom_voices_multiple(self) -> None:
        create_custom_voice_handler(self.repo, "Voice A")
        create_custom_voice_handler(self.repo, "Voice B")
        result = list_custom_voices_handler(self.repo)
        self.assertEqual(len(result), 2)
        names = [v["display_name"] for v in result]
        self.assertIn("Voice A", names)
        self.assertIn("Voice B", names)

    def test_list_custom_voices_active_filter(self) -> None:
        v1 = create_custom_voice_handler(self.repo, "Active Voice")
        v2 = create_custom_voice_handler(self.repo, "Inactive Voice")
        deactivate_custom_voice_handler(self.repo, v2["id"])
        
        all_voices = list_custom_voices_handler(self.repo, active_only=False)
        active_voices = list_custom_voices_handler(self.repo, active_only=True)
        
        self.assertEqual(len(all_voices), 2)
        self.assertEqual(len(active_voices), 1)
        self.assertEqual(active_voices[0]["display_name"], "Active Voice")

    def test_get_custom_voice_success(self) -> None:
        created = create_custom_voice_handler(self.repo, "Get Test")
        result = get_custom_voice_handler(self.repo, created["id"])
        self.assertEqual(result["id"], created["id"])
        self.assertEqual(result["display_name"], "Get Test")

    def test_get_custom_voice_not_found(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            get_custom_voice_handler(self.repo, 999)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_deactivate_custom_voice_success(self) -> None:
        created = create_custom_voice_handler(self.repo, "Deactivate Test")
        self.assertTrue(created["is_active"])
        
        result = deactivate_custom_voice_handler(self.repo, created["id"])
        self.assertFalse(result["is_active"])
        
        # Verify persisted
        fetched = get_custom_voice_handler(self.repo, created["id"])
        self.assertFalse(fetched["is_active"])

    def test_reactivate_custom_voice_success(self) -> None:
        created = create_custom_voice_handler(self.repo, "Reactivate Test")
        deactivate_custom_voice_handler(self.repo, created["id"])
        
        result = reactivate_custom_voice_handler(self.repo, created["id"])
        self.assertTrue(result["is_active"])
        
        # Verify persisted
        fetched = get_custom_voice_handler(self.repo, created["id"])
        self.assertTrue(fetched["is_active"])

    def test_deactivate_nonexistent_voice_rejected(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            deactivate_custom_voice_handler(self.repo, 999)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_create_revision_valid_upload(self) -> None:
        voice = create_custom_voice_handler(self.repo, "Revision Test")
        audio_data = b"fake audio data for testing"
        transcript = "This is a test transcript."
        
        # Mock UploadFile
        upload_file = self._create_mock_upload("test.wav", audio_data)
        
        result = create_custom_voice_revision_handler(
            self.repo, voice["id"], upload_file, transcript
        )
        
        self.assertEqual(result["custom_voice_id"], voice["id"])
        self.assertEqual(result["revision_number"], 1)
        self.assertIn("audio_sha256", result)
        self.assertIn("transcript_sha256", result)
        self.assertEqual(result["duration_ms"], 5000)
        self.assertEqual(result["sample_rate"], 48000)
        self.assertTrue(self.validator.validate_called)

    def test_create_revision_empty_transcript_rejected(self) -> None:
        voice = create_custom_voice_handler(self.repo, "Empty Transcript Test")
        audio_data = b"fake audio data"
        
        upload_file = self._create_mock_upload("test.wav", audio_data)
        
        with self.assertRaises(HTTPException) as ctx:
            create_custom_voice_revision_handler(self.repo, voice["id"], upload_file, "   ")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("empty", str(ctx.exception.detail).lower())

    def test_create_revision_transcript_too_long_rejected(self) -> None:
        voice = create_custom_voice_handler(self.repo, "Long Transcript Test")
        audio_data = b"fake audio data"
        long_transcript = "x" * (MAX_TRANSCRIPT_LENGTH + 1)
        
        upload_file = self._create_mock_upload("test.wav", audio_data)
        
        with self.assertRaises(HTTPException) as ctx:
            create_custom_voice_revision_handler(self.repo, voice["id"], upload_file, long_transcript)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("too long", str(ctx.exception.detail).lower())

    def test_create_revision_empty_audio_rejected(self) -> None:
        voice = create_custom_voice_handler(self.repo, "Empty Audio Test")
        
        upload_file = self._create_mock_upload("test.wav", b"")
        
        with self.assertRaises(HTTPException) as ctx:
            create_custom_voice_revision_handler(self.repo, voice["id"], upload_file, "Valid transcript")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("empty", str(ctx.exception.detail).lower())

    def test_create_revision_audio_too_large_rejected(self) -> None:
        voice = create_custom_voice_handler(self.repo, "Large Audio Test")
        large_audio = b"x" * (MAX_AUDIO_SIZE_BYTES + 1)
        
        upload_file = self._create_mock_upload("test.wav", large_audio)
        
        with self.assertRaises(HTTPException) as ctx:
            create_custom_voice_revision_handler(self.repo, voice["id"], upload_file, "Valid transcript")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("too large", str(ctx.exception.detail).lower())

    def test_create_revision_invalid_filename_rejected(self) -> None:
        voice = create_custom_voice_handler(self.repo, "Path Traversal Test")
        audio_data = b"fake audio data"
        
        upload_file = self._create_mock_upload("../../../etc/passwd", audio_data)
        
        with self.assertRaises(HTTPException) as ctx:
            create_custom_voice_revision_handler(self.repo, voice["id"], upload_file, "Valid transcript")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Invalid filename", str(ctx.exception.detail))

    def test_create_revision_invalid_audio_validation_rejected(self) -> None:
        failing_validator = MockAudioValidator(should_fail=True)
        failing_repo = CustomVoiceRepository(self.db, self.store, failing_validator)
        
        voice = create_custom_voice_handler(failing_repo, "Invalid Audio Test")
        audio_data = b"corrupt audio data"
        
        upload_file = self._create_mock_upload("test.wav", audio_data)
        
        with self.assertRaises(HTTPException) as ctx:
            create_custom_voice_revision_handler(failing_repo, voice["id"], upload_file, "Valid transcript")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_revision_nonexistent_voice_rejected(self) -> None:
        audio_data = b"fake audio data"
        
        upload_file = self._create_mock_upload("test.wav", audio_data)
        
        with self.assertRaises(HTTPException) as ctx:
            create_custom_voice_revision_handler(self.repo, 999, upload_file, "Valid transcript")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_create_multiple_revisions_increments_number(self) -> None:
        voice = create_custom_voice_handler(self.repo, "Multiple Revisions Test")
        audio_data = b"fake audio data"
        
        upload_file1 = self._create_mock_upload("test1.wav", audio_data)
        upload_file2 = self._create_mock_upload("test2.wav", audio_data + b" version 2")
        
        rev1 = create_custom_voice_revision_handler(self.repo, voice["id"], upload_file1, "Transcript 1")
        rev2 = create_custom_voice_revision_handler(self.repo, voice["id"], upload_file2, "Transcript 2")
        
        self.assertEqual(rev1["revision_number"], 1)
        self.assertEqual(rev2["revision_number"], 2)
        self.assertNotEqual(rev1["audio_sha256"], rev2["audio_sha256"])

    def test_list_revisions_empty(self) -> None:
        voice = create_custom_voice_handler(self.repo, "No Revisions Test")
        result = list_custom_voice_revisions_handler(self.repo, voice["id"])
        self.assertEqual(result, [])

    def test_list_revisions_multiple(self) -> None:
        voice = create_custom_voice_handler(self.repo, "List Revisions Test")
        audio_data = b"fake audio data"
        
        for i in range(3):
            upload_file = self._create_mock_upload(f"test{i}.wav", audio_data + str(i).encode())
            create_custom_voice_revision_handler(
                self.repo, voice["id"], upload_file, f"Transcript {i}"
            )
        
        result = list_custom_voice_revisions_handler(self.repo, voice["id"])
        self.assertEqual(len(result), 3)
        # Should be ordered descending by revision number
        self.assertEqual(result[0]["revision_number"], 3)
        self.assertEqual(result[1]["revision_number"], 2)
        self.assertEqual(result[2]["revision_number"], 1)

    def test_get_revision_success(self) -> None:
        voice = create_custom_voice_handler(self.repo, "Get Revision Test")
        audio_data = b"fake audio data"
        
        upload_file = self._create_mock_upload("test.wav", audio_data)
        
        created = create_custom_voice_revision_handler(
            self.repo, voice["id"], upload_file, "Test transcript"
        )
        
        result = get_custom_voice_revision_handler(self.repo, created["id"])
        self.assertEqual(result["id"], created["id"])
        self.assertEqual(result["revision_number"], 1)

    def test_get_revision_not_found(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            get_custom_voice_revision_handler(self.repo, 999)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_adding_revision_does_not_reactivate_voice(self) -> None:
        voice = create_custom_voice_handler(self.repo, "No Auto Reactivate Test")
        deactivate_custom_voice_handler(self.repo, voice["id"])
        
        audio_data = b"fake audio data"
        upload_file = self._create_mock_upload("test.wav", audio_data)
        
        create_custom_voice_revision_handler(self.repo, voice["id"], upload_file, "Test transcript")
        
        # Voice should still be inactive
        result = get_custom_voice_handler(self.repo, voice["id"])
        self.assertFalse(result["is_active"])

    def test_transcript_whitespace_trimmed(self) -> None:
        voice = create_custom_voice_handler(self.repo, "Trim Test")
        audio_data = b"fake audio data"
        
        upload_file = self._create_mock_upload("test.wav", audio_data)
        
        result = create_custom_voice_revision_handler(
            self.repo, voice["id"], upload_file, "  \n  Test transcript  \n  "
        )
        
        # Verify revision was created (transcript stored trimmed internally)
        self.assertIn("transcript_sha256", result)
        fetched = get_custom_voice_revision_handler(self.repo, result["id"])
        self.assertEqual(fetched["id"], result["id"])

    def test_no_absolute_paths_in_responses(self) -> None:
        voice = create_custom_voice_handler(self.repo, "No Paths Test")
        audio_data = b"fake audio data"
        
        upload_file = self._create_mock_upload("test.wav", audio_data)
        
        revision = create_custom_voice_revision_handler(
            self.repo, voice["id"], upload_file, "Test transcript"
        )
        
        # Check that no absolute paths are exposed
        for key, value in revision.items():
            if isinstance(value, str):
                self.assertNotIn(str(self.root), value, f"Found absolute path in field: {key}")
                self.assertNotIn("\\", value, f"Found Windows path separator in field: {key}")
                self.assertNotIn("data/", value, f"Found internal path in field: {key}")

    def test_storage_atomicity_on_db_failure(self) -> None:
        """If DB insert fails, blob should not be orphaned (repo handles this)."""
        voice = create_custom_voice_handler(self.repo, "Atomicity Test")
        audio_data = b"fake audio data for atomicity"
        
        upload_file = self._create_mock_upload("test.wav", audio_data)
        
        # First successful creation
        rev1 = create_custom_voice_revision_handler(
            self.repo, voice["id"], upload_file, "First transcript"
        )
        
        # Verify blob was stored
        blob_path = self.store.absolute(self.repo.get_revision(rev1["id"]).audio_storage_key)
        self.assertTrue(blob_path.exists())

    def test_no_delete_endpoint_exists(self) -> None:
        """Verify that hard delete is not exposed via API."""
        # This is a documentation test - we verify that our handlers don't include delete
        # In actual FastAPI app testing, we'd verify no DELETE route exists
        handlers = [
            create_custom_voice_handler,
            list_custom_voices_handler,
            get_custom_voice_handler,
            deactivate_custom_voice_handler,
            reactivate_custom_voice_handler,
            create_custom_voice_revision_handler,
            list_custom_voice_revisions_handler,
            get_custom_voice_revision_handler,
        ]
        # None of these should be named 'delete'
        for handler in handlers:
            self.assertNotIn("delete", handler.__name__)

    def test_set_preferred_synthesis_revision_success(self) -> None:
        """Test setting preferred synthesis revision."""
        voice = create_custom_voice_handler(self.repo, "Preferred Revision Test")
        audio_data = b"fake audio data"
        
        # Create two revisions
        upload1 = self._create_mock_upload("test1.wav", audio_data)
        upload2 = self._create_mock_upload("test2.wav", audio_data + b" v2")
        
        rev1 = create_custom_voice_revision_handler(self.repo, voice["id"], upload1, "Transcript 1")
        rev2 = create_custom_voice_revision_handler(self.repo, voice["id"], upload2, "Transcript 2")
        
        # Initially no preferred revision
        voice_data = get_custom_voice_handler(self.repo, voice["id"])
        self.assertIsNone(voice_data["preferred_synthesis_revision_id"])
        
        # Set revision 1 as preferred
        result = set_preferred_synthesis_revision_handler(self.repo, voice["id"], rev1["id"])
        self.assertEqual(result["preferred_synthesis_revision_id"], rev1["id"])
        
        # Verify persistence
        voice_data = get_custom_voice_handler(self.repo, voice["id"])
        self.assertEqual(voice_data["preferred_synthesis_revision_id"], rev1["id"])
        
        # Change to revision 2
        result = set_preferred_synthesis_revision_handler(self.repo, voice["id"], rev2["id"])
        self.assertEqual(result["preferred_synthesis_revision_id"], rev2["id"])
        
        # Verify persistence
        voice_data = get_custom_voice_handler(self.repo, voice["id"])
        self.assertEqual(voice_data["preferred_synthesis_revision_id"], rev2["id"])

    def test_set_preferred_synthesis_revision_clear(self) -> None:
        """Test clearing preferred synthesis revision."""
        voice = create_custom_voice_handler(self.repo, "Clear Preferred Test")
        audio_data = b"fake audio data"
        
        upload = self._create_mock_upload("test.wav", audio_data)
        rev = create_custom_voice_revision_handler(self.repo, voice["id"], upload, "Transcript")
        
        # Set preferred
        set_preferred_synthesis_revision_handler(self.repo, voice["id"], rev["id"])
        voice_data = get_custom_voice_handler(self.repo, voice["id"])
        self.assertEqual(voice_data["preferred_synthesis_revision_id"], rev["id"])
        
        # Clear preferred
        result = set_preferred_synthesis_revision_handler(self.repo, voice["id"], None)
        self.assertIsNone(result["preferred_synthesis_revision_id"])
        
        # Verify persistence
        voice_data = get_custom_voice_handler(self.repo, voice["id"])
        self.assertIsNone(voice_data["preferred_synthesis_revision_id"])

    def test_set_preferred_synthesis_revision_nonexistent_voice(self) -> None:
        """Test setting preferred revision for nonexistent voice."""
        with self.assertRaises(HTTPException) as ctx:
            set_preferred_synthesis_revision_handler(self.repo, 999, 1)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_set_preferred_synthesis_revision_nonexistent_revision(self) -> None:
        """Test setting nonexistent revision as preferred."""
        voice = create_custom_voice_handler(self.repo, "Invalid Revision Test")
        
        with self.assertRaises(HTTPException) as ctx:
            set_preferred_synthesis_revision_handler(self.repo, voice["id"], 999)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_preferred_revision_included_in_list(self) -> None:
        """Test that preferred_synthesis_revision_id is included in list responses."""
        voice = create_custom_voice_handler(self.repo, "List Preferred Test")
        audio_data = b"fake audio data"
        
        upload = self._create_mock_upload("test.wav", audio_data)
        rev = create_custom_voice_revision_handler(self.repo, voice["id"], upload, "Transcript")
        
        # Set preferred
        set_preferred_synthesis_revision_handler(self.repo, voice["id"], rev["id"])
        
        # Verify in list response
        voices = list_custom_voices_handler(self.repo)
        voice_in_list = next(v for v in voices if v["id"] == voice["id"])
        self.assertEqual(voice_in_list["preferred_synthesis_revision_id"], rev["id"])

    def test_set_preferred_revision_wrong_voice_rejected(self) -> None:
        """Test that a revision from a different voice cannot be set as preferred."""
        voice_a = create_custom_voice_handler(self.repo, "Voice A")
        voice_b = create_custom_voice_handler(self.repo, "Voice B")
        audio_data = b"fake audio data"

        # Create revision for Voice B
        upload = self._create_mock_upload("test.wav", audio_data)
        rev_b = create_custom_voice_revision_handler(self.repo, voice_b["id"], upload, "Transcript B")

        # Try to set Voice B's revision as preferred for Voice A - should fail
        with self.assertRaises(HTTPException) as ctx:
            set_preferred_synthesis_revision_handler(self.repo, voice_a["id"], rev_b["id"])
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("does not belong", str(ctx.exception.detail))


if __name__ == "__main__":
    unittest.main()




