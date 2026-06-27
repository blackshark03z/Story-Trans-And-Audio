"""
Unit tests for preset synthesis snapshot loading.

Covers Phase 3B3-A: dataclasses, parsing, validation for preset voices.
Custom reference loading belongs to Phase 3B3-B.
"""

import json
import tempfile
import unittest
from pathlib import Path

from story_audio.config import Settings
from story_audio.storage import ContentStore
from story_audio.synthesis_snapshot import (
    LegacySynthesisSnapshotError,
    SegmentSynthesisInput,
    SnapshotIntegrityError,
    SnapshotValidationError,
    SynthesisSettings,
    UnsupportedSynthesisSnapshotError,
    load_segment_synthesis_input,
)


class TestSynthesisSettings(unittest.TestCase):
    def test_from_json_valid(self):
        """Valid settings parse successfully."""
        settings_json = json.dumps({
            "temperature": 0.8,
            "top_k": 25,
            "max_chars": 256,
            "silence_seconds": 0.15,
            "engine_version": "vieneu:v3turbo",
        })
        settings = SynthesisSettings.from_json(settings_json, "vieneu", "v3turbo")
        self.assertEqual(settings.temperature, 0.8)
        self.assertEqual(settings.top_k, 25)
        self.assertEqual(settings.max_chars, 256)
        self.assertEqual(settings.silence_seconds, 0.15)
        self.assertEqual(settings.engine_version, "vieneu:v3turbo")
    
    def test_from_json_invalid_json(self):
        """Invalid JSON raises error."""
        with self.assertRaises(SnapshotValidationError) as ctx:
            SynthesisSettings.from_json("{invalid", "vieneu", "v3turbo")
        self.assertIn("Invalid synthesis_settings_json", str(ctx.exception))
    
    def test_from_json_not_object(self):
        """JSON array raises error."""
        with self.assertRaises(SnapshotValidationError) as ctx:
            SynthesisSettings.from_json("[]", "vieneu", "v3turbo")
        self.assertIn("must be a JSON object", str(ctx.exception))
    
    def test_from_json_missing_key(self):
        """Missing required key raises error."""
        settings_json = json.dumps({"temperature": 0.8, "top_k": 25})
        with self.assertRaises(SnapshotValidationError) as ctx:
            SynthesisSettings.from_json(settings_json, "vieneu", "v3turbo")
        self.assertIn("Missing required settings keys", str(ctx.exception))
        self.assertIn("max_chars", str(ctx.exception))
    
    def test_from_json_string_numeric_rejected(self):
        """String masquerading as number raises error."""
        settings_json = json.dumps({
            "temperature": "0.8",
            "top_k": 25,
            "max_chars": 256,
            "engine_version": "vieneu:v3turbo",
        })
        with self.assertRaises(SnapshotValidationError) as ctx:
            SynthesisSettings.from_json(settings_json, "vieneu", "v3turbo")
        self.assertIn("temperature must be numeric", str(ctx.exception))
    
    def test_from_json_boolean_integer_rejected(self):
        """Boolean as integer raises error."""
        settings_json = json.dumps({
            "temperature": 0.8,
            "top_k": True,
            "max_chars": 256,
            "engine_version": "vieneu:v3turbo",
        })
        with self.assertRaises(SnapshotValidationError) as ctx:
            SynthesisSettings.from_json(settings_json, "vieneu", "v3turbo")
        self.assertIn("top_k must be integer", str(ctx.exception))
    
    def test_from_json_non_finite_float(self):
        """Non-finite float raises error."""
        settings_json = json.dumps({
            "temperature": float('inf'),
            "top_k": 25,
            "max_chars": 256,
            "engine_version": "vieneu:v3turbo",
        })
        with self.assertRaises(SnapshotValidationError) as ctx:
            SynthesisSettings.from_json(settings_json, "vieneu", "v3turbo")
        self.assertIn("temperature must be finite", str(ctx.exception))
    
    def test_from_json_out_of_range_temperature(self):
        """Temperature out of range raises error."""
        settings_json = json.dumps({
            "temperature": 3.0,
            "top_k": 25,
            "max_chars": 256,
            "engine_version": "vieneu:v3turbo",
        })
        with self.assertRaises(SnapshotValidationError) as ctx:
            SynthesisSettings.from_json(settings_json, "vieneu", "v3turbo")
        self.assertIn("temperature out of range", str(ctx.exception))
    
    def test_from_json_provider_conflict(self):
        """Provider conflict raises error."""
        settings_json = json.dumps({
            "temperature": 0.8,
            "top_k": 25,
            "max_chars": 256,
            "engine_version": "azure:v3turbo",
        })
        with self.assertRaises(SnapshotValidationError) as ctx:
            SynthesisSettings.from_json(settings_json, "vieneu", "v3turbo")
        self.assertIn("Provider conflict", str(ctx.exception))
        self.assertIn("azure", str(ctx.exception))
    
    def test_from_json_model_conflict(self):
        """Model conflict raises error."""
        settings_json = json.dumps({
            "temperature": 0.8,
            "top_k": 25,
            "max_chars": 256,
            "engine_version": "vieneu:v4turbo",
        })
        with self.assertRaises(SnapshotValidationError) as ctx:
            SynthesisSettings.from_json(settings_json, "vieneu", "v3turbo")
        self.assertIn("Model conflict", str(ctx.exception))
        self.assertIn("v4turbo", str(ctx.exception))


class TestSegmentSynthesisInput(unittest.TestCase):
    def test_effective_silence_final_segment(self):
        """Final segment returns 0.0 silence."""
        settings = SynthesisSettings(0.8, 25, 256, 0.15, "vieneu:v3turbo")
        synth_input = SegmentSynthesisInput(
            snapshot_version=1,
            voice_source_type="preset",
            voice_provider="vieneu",
            voice_model="v3turbo",
            text="Test",
            text_sha256="abc123",
            settings=settings,
            preset_voice_id="duc_tri",
            custom_voice_revision_id=None,
            reference_audio_path=None,
            reference_audio_sha256=None,
            reference_transcript=None,
            reference_transcript_sha256=None,
            logical_voice_ref="narrator",
            effective_voice_ref="duc_tri",
            voice_resolution_reason="direct",
            casting_plan_id=None,
            segment_index=5,
            is_final_segment=True,
        )
        self.assertEqual(synth_input.effective_silence_seconds(), 0.0)
    
    def test_effective_silence_non_final_segment(self):
        """Non-final segment returns settings silence."""
        settings = SynthesisSettings(0.8, 25, 256, 0.15, "vieneu:v3turbo")
        synth_input = SegmentSynthesisInput(
            snapshot_version=1,
            voice_source_type="preset",
            voice_provider="vieneu",
            voice_model="v3turbo",
            text="Test",
            text_sha256="abc123",
            settings=settings,
            preset_voice_id="duc_tri",
            custom_voice_revision_id=None,
            reference_audio_path=None,
            reference_audio_sha256=None,
            reference_transcript=None,
            reference_transcript_sha256=None,
            logical_voice_ref="narrator",
            effective_voice_ref="duc_tri",
            voice_resolution_reason="direct",
            casting_plan_id=None,
            segment_index=3,
            is_final_segment=False,
        )
        self.assertEqual(synth_input.effective_silence_seconds(), 0.15)


class TestLoadSegmentSynthesisInput(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config = Settings(root=Path(self.temp_dir.name))
        self.store = ContentStore(self.config)
    
    def tearDown(self):
        self.temp_dir.cleanup()
    
    def _make_preset_segment(self, overrides=None):
        """Create a valid preset segment dict."""
        text_path, text_sha = self.store.put_text("Test segment text.")
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
            "voice_source_type": "preset",
            "voice_provider": "vieneu",
            "voice_model": "v3turbo",
            "logical_voice_ref": "narrator",
            "effective_voice_ref": "duc_tri",
            "synthesis_settings_json": settings_json,
            "text_path": text_path,
            "text_sha256": text_sha,
            "segment_index": 1,
            "voice_resolution_reason": "direct_assignment",
            "casting_plan_id": None,
            "custom_voice_revision_id": None,
            "reference_audio_sha256": None,
            "reference_audio_storage_key": None,
            "reference_transcript": None,
            "reference_transcript_sha256": None,
        }
        if overrides:
            segment.update(overrides)
        return segment
    
    def test_load_preset_success(self):
        """Valid preset snapshot loads successfully."""
        segment = self._make_preset_segment()
        synth_input = load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        
        self.assertEqual(synth_input.snapshot_version, 1)
        self.assertEqual(synth_input.voice_source_type, "preset")
        self.assertEqual(synth_input.voice_provider, "vieneu")
        self.assertEqual(synth_input.voice_model, "v3turbo")
        self.assertEqual(synth_input.text, "Test segment text.")
        self.assertEqual(synth_input.preset_voice_id, "duc_tri")
        self.assertIsNone(synth_input.custom_voice_revision_id)
        self.assertEqual(synth_input.settings.temperature, 0.8)
        self.assertFalse(synth_input.is_final_segment)
    
    def test_snapshot_version_null(self):
        """NULL snapshot version raises LegacySynthesisSnapshotError."""
        segment = self._make_preset_segment({"voice_snapshot_version": None})
        with self.assertRaises(LegacySynthesisSnapshotError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("no synthesis snapshot", str(ctx.exception))
        self.assertIn("create new job", str(ctx.exception))
    
    def test_snapshot_version_unsupported(self):
        """Unsupported snapshot version raises error."""
        segment = self._make_preset_segment({"voice_snapshot_version": 2})
        with self.assertRaises(UnsupportedSynthesisSnapshotError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("version 2 not supported", str(ctx.exception))
    
    def test_missing_required_field(self):
        """Missing required field raises error."""
        segment = self._make_preset_segment({"voice_provider": None})
        with self.assertRaises(SnapshotValidationError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("Missing required field", str(ctx.exception))
    
    def test_invalid_provider(self):
        """Invalid provider raises error."""
        segment = self._make_preset_segment({"voice_provider": "azure"})
        with self.assertRaises(SnapshotValidationError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("Unsupported provider", str(ctx.exception))
    
    def test_invalid_model(self):
        """Invalid model raises error."""
        segment = self._make_preset_segment({"voice_model": "v4turbo"})
        with self.assertRaises(SnapshotValidationError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("Unsupported model", str(ctx.exception))
    
    def test_text_sha256_mismatch(self):
        """Text SHA mismatch raises IntegrityError."""
        segment = self._make_preset_segment({"text_sha256": "wrong_hash"})
        with self.assertRaises(SnapshotIntegrityError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("Text SHA-256 mismatch", str(ctx.exception))
    
    def test_custom_reference_deferred(self):
        """Custom reference now implemented in Phase 3B3-B."""
        # This test is obsolete - custom reference is now implemented
        # Update to verify custom reference requires all custom fields
        segment = self._make_preset_segment({
            "voice_source_type": "custom_reference",
            "custom_voice_revision_id": None,
        })
        with self.assertRaises(SnapshotValidationError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("missing custom_voice_revision_id", str(ctx.exception).lower())
    
    def test_invalid_voice_source_type(self):
        """Invalid voice_source_type raises error."""
        segment = self._make_preset_segment({"voice_source_type": "unknown"})
        with self.assertRaises(SnapshotValidationError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("Invalid voice_source_type", str(ctx.exception))
    
    def test_preset_with_custom_fields_populated(self):
        """Preset with custom fields raises error."""
        segment = self._make_preset_segment({"custom_voice_revision_id": 5})
        with self.assertRaises(SnapshotValidationError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("Preset voice has custom field", str(ctx.exception))
    
    def test_empty_preset_identifier(self):
        """Empty preset identifier raises error."""
        segment = self._make_preset_segment({"effective_voice_ref": ""})
        with self.assertRaises(SnapshotValidationError) as ctx:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertIn("effective_voice_ref is empty", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
