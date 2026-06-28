"""
Isolated FastAPI TestClient tests for voice preview API.

Tests both preset and custom voice preview request/response/error contracts.
Uses temporary database, storage, and preview cache.
Does not access live DB, load real TTS, or synthesize real audio.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from story_audio.config import Settings
from story_audio.custom_voice import AudioValidator, CustomVoiceRepository
from story_audio.db import Database
from story_audio.files import sha256_bytes, sha256_text
from story_audio.storage import ContentStore
from story_audio.voice_preview import VoicePreviewService


class FakeTts:
    """Fake TTS for isolated testing."""

    def __init__(self):
        self.sample_rate = 24000

    def synthesize(self, **kwargs: Any) -> tuple[int, int]:
        """Generate a minimal valid WAV file and return fixed duration."""
        import numpy as np
        import soundfile as sf

        output_path = kwargs.get("output_path")
        if output_path is None:
            raise ValueError("output_path is required")

        # Generate 15 seconds of silence (within valid 10-20 second range)
        duration_seconds = 15.0
        audio = np.zeros(int(self.sample_rate * duration_seconds), dtype=np.float32)

        # Write WAV file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), audio, self.sample_rate, subtype="PCM_16", format="WAV")

        duration_ms = int(duration_seconds * 1000)
        return (duration_ms, self.sample_rate)


class IsolatedApiPreviewTests(unittest.TestCase):
    """Isolated TestClient tests for voice preview API."""

    def setUp(self) -> None:
        super().setUp()

        # Store original environment
        self._original_testing = os.environ.get("STORY_AUDIO_TESTING")
        self._original_allow_live = os.environ.get("STORY_AUDIO_ALLOW_LIVE_DB")

        # Set test mode
        os.environ["STORY_AUDIO_TESTING"] = "1"

        # Create temporary directory
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_root = Path(self.temp_dir.name)

        # Create isolated config using replace (Settings is frozen dataclass)
        self.config = replace(
            Settings(),
            root=self.temp_root,
            data_dir=self.temp_root / "data",
            db_path=self.temp_root / "data" / "app.db",
            blobs_dir=self.temp_root / "data" / "blobs",
        )
        self.config.preview_cache_dir.mkdir(parents=True, exist_ok=True)

        # Initialize database with migration 0006
        self.db = Database(self.config.db_path)
        self.db.initialize()

        # Create storage
        self.store = ContentStore(self.config)

        # Create custom voice repository
        self.custom_voice_repo = CustomVoiceRepository(self.db, self.store)

        # Create fake TTS
        self.fake_tts = FakeTts()

        # Create preview service with dependencies
        self.preview_service = VoicePreviewService(
            self.fake_tts,
            self.config,
            custom_voice_repo=self.custom_voice_repo,
            store=self.store,
        )

        # Patch the app's initialized services
        import story_audio.api as api_module
        self._original_tts = api_module.tts_service
        self._original_previews = api_module.voice_previews
        self._original_db = api_module.db
        self._original_store = api_module.store
        self._original_custom_repo = api_module.custom_voice_repo

        # Mock tts_service.voices() to return test voices
        mock_tts = MagicMock()
        mock_tts.voices.return_value = [
            {"label": "Test Voice 1", "id": "test_voice_1"},
            {"label": "Test Voice 2", "id": "test_voice_2"},
        ]
        api_module.tts_service = mock_tts
        api_module.voice_previews = self.preview_service
        api_module.db = self.db
        api_module.store = self.store
        api_module.custom_voice_repo = self.custom_voice_repo

        # Create test client
        from story_audio.api import app
        self.client = TestClient(app)

    def tearDown(self) -> None:
        # Restore original services
        import story_audio.api as api_module
        api_module.tts_service = self._original_tts
        api_module.voice_previews = self._original_previews
        api_module.db = self._original_db
        api_module.store = self._original_store
        api_module.custom_voice_repo = self._original_custom_repo

        # Restore original environment
        if self._original_testing is None:
            os.environ.pop("STORY_AUDIO_TESTING", None)
        else:
            os.environ["STORY_AUDIO_TESTING"] = self._original_testing

        if self._original_allow_live is None:
            os.environ.pop("STORY_AUDIO_ALLOW_LIVE_DB", None)
        else:
            os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = self._original_allow_live

        # Clean up temp directory
        self.temp_dir.cleanup()
        super().tearDown()

    # Preset tests

    def test_preset_request_succeeds(self):
        """Legacy preset request with voice_id succeeds."""
        response = self.client.post(
            "/api/voice-previews",
            json={"voice_id": "test_voice_1"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("cache_key", data)
        self.assertIn("duration_ms", data)
        self.assertIn("sample_rate", data)
        self.assertIn("cache_hit", data)
        self.assertIn("preview_text", data)
        self.assertIn("audio_url", data)
        self.assertEqual(data["voice_id"], "test_voice_1")
        self.assertNotIn("custom_voice_revision_id", data)

    def test_preset_audio_retrieval(self):
        """Preset audio file retrieval works."""
        # Create preview
        response = self.client.post(
            "/api/voice-previews",
            json={"voice_id": "test_voice_1"}
        )
        self.assertEqual(response.status_code, 200)
        cache_key = response.json()["cache_key"]

        # Retrieve audio file
        audio_response = self.client.get(f"/api/voice-previews/{cache_key}/file")
        self.assertEqual(audio_response.status_code, 200)
        self.assertEqual(audio_response.headers["content-type"], "audio/wav")

    def test_preset_invalid_voice_id(self):
        """Preset with invalid voice_id returns 400."""
        response = self.client.post(
            "/api/voice-previews",
            json={"voice_id": "nonexistent_voice"}
        )
        self.assertEqual(response.status_code, 400)

    # Custom voice tests

    def test_custom_request_succeeds(self):
        """Custom request with custom_voice_revision_id succeeds."""
        # Create custom voice and revision
        voice = self.custom_voice_repo.create_custom_voice("Test Custom Voice")
        audio_bytes = b"fake wav data" * 1000
        revision = self.custom_voice_repo.create_revision(
            voice.id,
            audio_bytes,
            "Test reference transcript",
        )

        # Request preview
        response = self.client.post(
            "/api/voice-previews",
            json={"custom_voice_revision_id": revision.id}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("cache_key", data)
        self.assertIn("duration_ms", data)
        self.assertIn("sample_rate", data)
        self.assertIn("cache_hit", data)
        self.assertIn("preview_text", data)
        self.assertIn("audio_url", data)
        self.assertEqual(data["custom_voice_revision_id"], revision.id)
        self.assertNotIn("voice_id", data)

    def test_custom_audio_retrieval(self):
        """Custom preview audio file retrieval works."""
        # Create custom voice and revision
        voice = self.custom_voice_repo.create_custom_voice("Test Custom Voice")
        audio_bytes = b"fake wav data" * 1000
        revision = self.custom_voice_repo.create_revision(
            voice.id,
            audio_bytes,
            "Test reference transcript",
        )

        # Create preview
        response = self.client.post(
            "/api/voice-previews",
            json={"custom_voice_revision_id": revision.id}
        )
        self.assertEqual(response.status_code, 200)
        cache_key = response.json()["cache_key"]

        # Retrieve audio file
        audio_response = self.client.get(f"/api/voice-previews/{cache_key}/file")
        self.assertEqual(audio_response.status_code, 200)
        self.assertEqual(audio_response.headers["content-type"], "audio/wav")

    def test_custom_revision_not_found(self):
        """Custom request with nonexistent revision returns 404."""
        response = self.client.post(
            "/api/voice-previews",
            json={"custom_voice_revision_id": 99999}
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())

    def test_custom_storage_resolution_error(self):
        """Custom request with storage error returns 404."""
        # Create custom voice and revision
        voice = self.custom_voice_repo.create_custom_voice("Test Custom Voice")
        audio_bytes = b"fake wav data" * 1000
        revision = self.custom_voice_repo.create_revision(
            voice.id,
            audio_bytes,
            "Test reference transcript",
        )

        # Delete the stored audio to trigger StorageResolutionError
        audio_path = self.store.absolute(revision.audio_storage_key)
        audio_path.unlink()

        response = self.client.post(
            "/api/voice-previews",
            json={"custom_voice_revision_id": revision.id}
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("unavailable", response.json()["detail"].lower())

    # XOR validation tests

    def test_neither_selector_returns_400(self):
        """Request with neither selector returns 400."""
        response = self.client.post(
            "/api/voice-previews",
            json={}
        )
        self.assertEqual(response.status_code, 400)
        detail = response.json()["detail"].lower()
        self.assertIn("must provide", detail)

    def test_both_selectors_returns_400(self):
        """Request with both selectors returns 400."""
        response = self.client.post(
            "/api/voice-previews",
            json={
                "voice_id": "test_voice_1",
                "custom_voice_revision_id": 1
            }
        )
        self.assertEqual(response.status_code, 400)
        detail = response.json()["detail"].lower()
        self.assertIn("cannot provide both", detail)

    # Input validation tests

    def test_zero_revision_id_returns_422(self):
        """Zero revision ID triggers Pydantic validation error."""
        response = self.client.post(
            "/api/voice-previews",
            json={"custom_voice_revision_id": 0}
        )
        self.assertEqual(response.status_code, 422)

    def test_negative_revision_id_returns_422(self):
        """Negative revision ID triggers Pydantic validation error."""
        response = self.client.post(
            "/api/voice-previews",
            json={"custom_voice_revision_id": -1}
        )
        self.assertEqual(response.status_code, 422)

    def test_invalid_revision_id_type_returns_422(self):
        """Invalid revision ID type triggers Pydantic validation error."""
        response = self.client.post(
            "/api/voice-previews",
            json={"custom_voice_revision_id": "not_an_int"}
        )
        self.assertEqual(response.status_code, 422)

    def test_empty_voice_id_returns_422(self):
        """Empty voice_id triggers Pydantic validation error."""
        response = self.client.post(
            "/api/voice-previews",
            json={"voice_id": ""}
        )
        self.assertEqual(response.status_code, 422)

    # Error mapping tests

    def test_metadata_validation_error_returns_400(self):
        """Metadata validation errors return 400 without internal leak."""
        # Create custom voice and revision with corrupted metadata
        voice = self.custom_voice_repo.create_custom_voice("Test Custom Voice")
        audio_bytes = b"fake wav data" * 1000
        revision = self.custom_voice_repo.create_revision(
            voice.id,
            audio_bytes,
            "Test reference transcript",
        )

        # Corrupt the revision metadata in DB
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE custom_voice_revisions SET audio_sha256=? WHERE id=?",
                ("0" * 64, revision.id)
            )

        response = self.client.post(
            "/api/voice-previews",
            json={"custom_voice_revision_id": revision.id}
        )
        self.assertEqual(response.status_code, 404)  # SHA mismatch → StorageResolutionError → 404

    def test_synthesis_failure_returns_503(self):
        """Unexpected synthesis failure returns 503."""
        # Create custom voice and revision
        voice = self.custom_voice_repo.create_custom_voice("Test Custom Voice")
        audio_bytes = b"fake wav data" * 1000
        revision = self.custom_voice_repo.create_revision(
            voice.id,
            audio_bytes,
            "Test reference transcript",
        )

        # Mock TTS to raise exception
        def failing_synthesize(**kwargs):
            raise RuntimeError("Unexpected engine error")

        self.fake_tts.synthesize = failing_synthesize

        response = self.client.post(
            "/api/voice-previews",
            json={"custom_voice_revision_id": revision.id}
        )
        self.assertEqual(response.status_code, 503)
        detail = response.json()["detail"]
        self.assertEqual(detail, "Voice preview generation failed")
        self.assertNotIn("Unexpected engine error", detail)

    def test_corrupt_preview_cache_returns_404(self):
        """Corrupt/missing preview cache returns 404."""
        response = self.client.get("/api/voice-previews/invalid_cache_key/file")
        self.assertEqual(response.status_code, 400)  # Invalid cache key format

        # Valid format but nonexistent
        fake_key = "a" * 64
        response = self.client.get(f"/api/voice-previews/{fake_key}/file")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
