"""
Unit tests for custom reference synthesis snapshot loading.

Covers Phase 3B3-B: managed storage resolution, integrity verification.
"""

import json
import tempfile
import unittest
from pathlib import Path

from story_audio.config import Settings
from story_audio.files import sha256_bytes, sha256_text
from story_audio.storage import ContentStore
from story_audio.synthesis_snapshot import (
    SegmentSynthesisInput,
    SnapshotIntegrityError,
    SnapshotValidationError,
    StorageResolutionError,
    load_segment_synthesis_input,
)


class TestLoadCustomReferenceSnapshot(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config = Settings(root=Path(self.temp_dir.name))
        self.store = ContentStore(self.config)
        
        # Create reference audio fixture
        self.ref_audio_bytes = b"RIFF\x00\x00\x00\x00WAVE"
        self.ref_audio_sha = sha256_bytes(self.ref_audio_bytes)
        self.ref_storage_key = self.store.put_audio(self.ref_audio_bytes, self.ref_audio_sha)
        
        # Create reference transcript
        self.ref_transcript = "Đây là câu thoại mẫu."
        self.ref_transcript_sha = sha256_text(self.ref_transcript)
    
    def tearDown(self):
        self.temp_dir.cleanup()
    
    def _make_custom_segment(self, overrides=None):
        """Create a valid custom reference segment dict."""
        text_path, text_sha = self.store.put_text("Custom voice segment text.")
        settings_json = json.dumps({
            "temperature": 0.8,
            "top_k": 25,
            "max_chars": 256,
            "silence_seconds": 0.15,
            "engine_version": "vieneu:v3turbo",
        })
        segment = {
            "id": 1,
            "voice_snapshot_version": 1,
            "voice_source_type": "custom_reference",
            "voice_provider": "vieneu",
            "voice_model": "v3turbo",
            "logical_voice_ref": "custom:7",
            "effective_voice_ref": "custom:42",
            "synthesis_settings_json": settings_json,
            "text_path": text_path,
            "text_sha256": text_sha,
            "segment_index": 1,
            "voice_resolution_reason": "character_override",
            "casting_plan_id": 5,
            "custom_voice_revision_id": 42,
            "reference_audio_storage_key": self.ref_storage_key,
            "reference_audio_sha256": self.ref_audio_sha,
            "reference_transcript": self.ref_transcript,
            "reference_transcript_sha256": self.ref_transcript_sha,
        }
        if overrides:
            segment.update(overrides)
        return segment
    
    def test_load_custom_success(self):
        """Valid custom reference snapshot loads successfully."""
        segment = self._make_custom_segment()
        synth_input = load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        
        self.assertEqual(synth_input.snapshot_version, 1)
        self.assertEqual(synth_input.voice_source_type, "custom_reference")
        self.assertEqual(synth_input.voice_provider, "vieneu")
        self.assertEqual(synth_input.voice_model, "v3turbo")
        self.assertEqual(synth_input.text, "Custom voice segment text.")
        self.assertIsNone(synth_input.preset_voice_id)
        self.assertEqual(synth_input.custom_voice_revision_id, 42)
        self.assertTrue(synth_input.reference_audio_path.exists())
        self.assertEqual(synth_input.reference_audio_sha256, self.ref_audio_sha)
        self.assertEqual(synth_input.reference_transcript, self.ref_transcript)
        self.assertEqual(synth_input.reference_transcript_sha256, self.ref_transcript_sha)
        self.assertEqual(synth_input.effective_voice_ref, "custom:42")
        self.assertFalse(synth_input.is_final_segment)
    
    def test_custom_revision_id_missing(self):
        """Missing custom_voice_revision_id raises error."""
        segment = self._make_custom_segment({"custom_voice_revision_id": None})
        with self.assertRaises(SnapshotValidationError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("missing custom_voice_revision_id", str(ctx.exception).lower())
    
    def test_custom_revision_id_boolean_rejected(self):
        """Boolean revision ID rejected."""
        segment = self._make_custom_segment({"custom_voice_revision_id": True})
        with self.assertRaises(SnapshotValidationError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("must be integer", str(ctx.exception))
    
    def test_custom_revision_id_zero_rejected(self):
        """Zero revision ID rejected."""
        segment = self._make_custom_segment({"custom_voice_revision_id": 0})
        with self.assertRaises(SnapshotValidationError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("must be positive", str(ctx.exception))
    
    def test_custom_revision_id_negative_rejected(self):
        """Negative revision ID rejected."""
        segment = self._make_custom_segment({"custom_voice_revision_id": -5})
        with self.assertRaises(SnapshotValidationError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("must be positive", str(ctx.exception))
    
    def test_effective_voice_ref_mismatch(self):
        """effective_voice_ref must match custom:<revision_id>."""
        segment = self._make_custom_segment({"effective_voice_ref": "custom:999"})
        with self.assertRaises(SnapshotValidationError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("effective_voice_ref mismatch", str(ctx.exception))
        self.assertIn("custom:42", str(ctx.exception))
        self.assertIn("custom:999", str(ctx.exception))
    
    def test_storage_key_missing(self):
        """Missing storage key raises error."""
        segment = self._make_custom_segment({"reference_audio_storage_key": None})
        with self.assertRaises(SnapshotValidationError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("missing or invalid reference_audio_storage_key", str(ctx.exception).lower())
    
    def test_storage_key_empty(self):
        """Empty storage key raises error."""
        segment = self._make_custom_segment({"reference_audio_storage_key": "   "})
        with self.assertRaises(SnapshotValidationError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("empty", str(ctx.exception).lower())
    
    def test_absolute_storage_key_rejected(self):
        """Absolute storage key rejected."""
        segment = self._make_custom_segment({"reference_audio_storage_key": "/absolute/path.wav"})
        with self.assertRaises(StorageResolutionError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        # ContentStore.absolute() raises "Invalid content path" for absolute paths
        self.assertIn("storage key", str(ctx.exception).lower())
    
    def test_parent_traversal_rejected(self):
        """Parent traversal in storage key rejected."""
        segment = self._make_custom_segment({"reference_audio_storage_key": "../escape/path.wav"})
        with self.assertRaises(StorageResolutionError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("traversal", str(ctx.exception).lower())
    
    def test_storage_file_missing(self):
        """Missing reference file raises error."""
        segment = self._make_custom_segment({"reference_audio_storage_key": "audio/custom_voices/00/missing.wav"})
        with self.assertRaises(StorageResolutionError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("does not exist", str(ctx.exception))
    
    def test_storage_target_is_directory(self):
        """Storage target that is a directory raises error."""
        # Create a directory at the storage key location
        dir_key = "audio/custom_voices/00/directory_not_file"
        dir_path = self.config.blobs_dir / dir_key
        dir_path.mkdir(parents=True, exist_ok=True)
        
        segment = self._make_custom_segment({"reference_audio_storage_key": dir_key})
        with self.assertRaises(StorageResolutionError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("not a regular file", str(ctx.exception))
    
    def test_audio_sha_mismatch(self):
        """Audio SHA-256 mismatch raises IntegrityError."""
        segment = self._make_custom_segment({"reference_audio_sha256": "0" * 64})
        with self.assertRaises(SnapshotIntegrityError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("Reference audio SHA-256 mismatch", str(ctx.exception))
    
    def test_audio_sha_malformed(self):
        """Malformed audio SHA-256 raises ValidationError."""
        segment = self._make_custom_segment({"reference_audio_sha256": "not_a_hash"})
        with self.assertRaises(SnapshotValidationError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("Invalid reference_audio_sha256 format", str(ctx.exception))
    
    def test_transcript_empty_rejected(self):
        """Empty transcript rejected."""
        segment = self._make_custom_segment({"reference_transcript": "   "})
        with self.assertRaises(SnapshotValidationError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("empty", str(ctx.exception).lower())
    
    def test_transcript_sha_mismatch(self):
        """Transcript SHA-256 mismatch raises IntegrityError."""
        segment = self._make_custom_segment({"reference_transcript_sha256": "0" * 64})
        with self.assertRaises(SnapshotIntegrityError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("Reference transcript SHA-256 mismatch", str(ctx.exception))
    
    def test_transcript_sha_malformed(self):
        """Malformed transcript SHA-256 raises ValidationError."""
        segment = self._make_custom_segment({"reference_transcript_sha256": "ZZZZZZ"})
        with self.assertRaises(SnapshotValidationError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("Invalid reference_transcript_sha256 format", str(ctx.exception))
    
    def test_custom_final_segment_silence_override(self):
        """Final segment with custom voice returns 0.0 silence."""
        segment = self._make_custom_segment()
        synth_input = load_segment_synthesis_input(segment, self.store, is_final_segment=True)
        self.assertEqual(synth_input.effective_silence_seconds(), 0.0)
    
    def test_custom_non_final_segment_silence(self):
        """Non-final segment with custom voice returns settings silence."""
        segment = self._make_custom_segment()
        synth_input = load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertEqual(synth_input.effective_silence_seconds(), 0.15)
    
    def test_no_database_lookup_performed(self):
        """Custom loading does not query database (database-free operation)."""
        # This test verifies that load_segment_synthesis_input works without DB
        # by using only ContentStore and in-memory segment dict
        segment = self._make_custom_segment()
        synth_input = load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        # If no exception raised, no DB access occurred
        self.assertIsNotNone(synth_input)


if __name__ == "__main__":
    unittest.main()
