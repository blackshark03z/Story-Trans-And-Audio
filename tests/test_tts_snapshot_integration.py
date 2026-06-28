"""
Unit tests for TtsService snapshot-aware synthesis.

Covers Phase 3B3-C: snapshot integration with mocked VieNeu engine.
No real model loading, no real synthesis, no network access.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from story_audio.config import Settings
from story_audio.storage import ContentStore
from story_audio.synthesis_snapshot import SegmentSynthesisInput, SynthesisSettings
from story_audio.tts import TtsService


class MockVieneu:
    """Mock VieNeu engine for testing without real synthesis."""

    def __init__(self, mode="v3turbo"):
        self.mode = mode
        self.sample_rate = 24000
        self.last_call_args = None
        self.last_call_kwargs = None

    def infer(self, text, **kwargs):
        """Mock infer that returns valid audio without real synthesis."""
        self.last_call_args = (text,)
        self.last_call_kwargs = kwargs
        # Return synthetic audio (1 second of valid float32 data)
        return np.random.uniform(-0.5, 0.5, self.sample_rate).astype(np.float32)

    def list_preset_voices(self):
        return [("Male Voice", "duc_tri"), ("Female Voice", "my_anh")]


class TestTtsSnapshotIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config = Settings(root=Path(self.temp_dir.name))
        self.store = ContentStore(self.config)
        self.service = TtsService()
        self.mock_engine = MockVieneu()

        # Patch vieneu.Vieneu to use mock (imported inside ensure_loaded)
        self.vieneu_patcher = patch('vieneu.Vieneu', return_value=self.mock_engine)
        self.vieneu_patcher.start()

    def tearDown(self):
        self.vieneu_patcher.stop()
        self.temp_dir.cleanup()

    def _make_preset_input(self, is_final=False):
        """Create a valid preset SegmentSynthesisInput."""
        settings = SynthesisSettings(0.8, 25, 256, 0.15, "vieneu:v3turbo")
        return SegmentSynthesisInput(
            snapshot_version=1,
            voice_source_type="preset",
            voice_provider="vieneu",
            voice_model="v3turbo",
            text="Test synthesis text.",
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
            segment_index=1,
            is_final_segment=is_final,
        )

    def _make_custom_input(self, is_final=False):
        """Create a valid custom reference SegmentSynthesisInput."""
        # Create reference audio fixture
        ref_audio_bytes = b"RIFF\x00\x00\x00\x00WAVE"
        from story_audio.files import sha256_bytes, sha256_text
        ref_audio_sha = sha256_bytes(ref_audio_bytes)
        ref_storage_key = self.store.put_audio(ref_audio_bytes, ref_audio_sha)
        ref_audio_path = self.store.absolute(ref_storage_key)

        ref_transcript = "Đây là câu mẫu."
        ref_transcript_sha = sha256_text(ref_transcript)

        settings = SynthesisSettings(0.8, 25, 256, 0.15, "vieneu:v3turbo")
        return SegmentSynthesisInput(
            snapshot_version=1,
            voice_source_type="custom_reference",
            voice_provider="vieneu",
            voice_model="v3turbo",
            text="Custom voice synthesis.",
            text_sha256="def456",
            settings=settings,
            preset_voice_id=None,
            custom_voice_revision_id=42,
            reference_audio_path=ref_audio_path,
            reference_audio_sha256=ref_audio_sha,
            reference_transcript=ref_transcript,
            reference_transcript_sha256=ref_transcript_sha,
            logical_voice_ref="custom:7",
            effective_voice_ref="custom:42",
            voice_resolution_reason="character_override",
            casting_plan_id=5,
            segment_index=2,
            is_final_segment=is_final,
        )

    def test_preset_snapshot_calls_infer_with_voice(self):
        """Preset snapshot calls infer with voice parameter."""
        synth_input = self._make_preset_input()
        output = Path(self.temp_dir.name) / "output.wav"

        self.service.synthesize(synth_input=synth_input, output_path=output)

        # Verify infer was called with correct arguments
        self.assertEqual(self.mock_engine.last_call_args[0], "Test synthesis text.")
        self.assertEqual(self.mock_engine.last_call_kwargs["voice"], "duc_tri")
        self.assertEqual(self.mock_engine.last_call_kwargs["temperature"], 0.8)
        self.assertEqual(self.mock_engine.last_call_kwargs["top_k"], 25)
        self.assertEqual(self.mock_engine.last_call_kwargs["max_chars"], 256)
        self.assertNotIn("ref_audio", self.mock_engine.last_call_kwargs)
        self.assertNotIn("ref_text", self.mock_engine.last_call_kwargs)
        self.assertTrue(output.exists())

    def test_custom_snapshot_calls_infer_with_ref_audio(self):
        """Custom snapshot calls infer with ref_audio and ref_text."""
        synth_input = self._make_custom_input()
        output = Path(self.temp_dir.name) / "output.wav"

        self.service.synthesize(synth_input=synth_input, output_path=output)

        # Verify infer was called with custom reference arguments
        self.assertEqual(self.mock_engine.last_call_args[0], "Custom voice synthesis.")
        self.assertIn("ref_audio", self.mock_engine.last_call_kwargs)
        self.assertEqual(
            self.mock_engine.last_call_kwargs["ref_text"],
            "Đây là câu mẫu."
        )
        self.assertEqual(self.mock_engine.last_call_kwargs["temperature"], 0.8)
        self.assertNotIn("voice", self.mock_engine.last_call_kwargs)
        self.assertTrue(output.exists())

    def test_final_segment_appends_zero_silence(self):
        """Final segment appends zero silence."""
        synth_input = self._make_preset_input(is_final=True)
        output = Path(self.temp_dir.name) / "output.wav"

        duration_ms, sample_rate = self.service.synthesize(
            synth_input=synth_input, output_path=output
        )

        # Mock returns 1 second, final segment adds no silence
        self.assertEqual(sample_rate, 24000)
        self.assertAlmostEqual(duration_ms, 1000, delta=50)

    def test_non_final_segment_appends_settings_silence(self):
        """Non-final segment appends settings silence (0.15s)."""
        synth_input = self._make_preset_input(is_final=False)
        output = Path(self.temp_dir.name) / "output.wav"

        duration_ms, sample_rate = self.service.synthesize(
            synth_input=synth_input, output_path=output
        )

        # Mock returns 1 second, non-final adds 0.15s silence
        self.assertEqual(sample_rate, 24000)
        self.assertAlmostEqual(duration_ms, 1150, delta=50)

    def test_provider_mismatch_rejected(self):
        """Unsupported provider rejected."""
        synth_input = self._make_preset_input()
        # Hack the provider
        synth_input = SegmentSynthesisInput(
            snapshot_version=synth_input.snapshot_version,
            voice_source_type=synth_input.voice_source_type,
            voice_provider="azure",
            voice_model=synth_input.voice_model,
            text=synth_input.text,
            text_sha256=synth_input.text_sha256,
            settings=synth_input.settings,
            preset_voice_id=synth_input.preset_voice_id,
            custom_voice_revision_id=synth_input.custom_voice_revision_id,
            reference_audio_path=synth_input.reference_audio_path,
            reference_audio_sha256=synth_input.reference_audio_sha256,
            reference_transcript=synth_input.reference_transcript,
            reference_transcript_sha256=synth_input.reference_transcript_sha256,
            logical_voice_ref=synth_input.logical_voice_ref,
            effective_voice_ref=synth_input.effective_voice_ref,
            voice_resolution_reason=synth_input.voice_resolution_reason,
            casting_plan_id=synth_input.casting_plan_id,
            segment_index=synth_input.segment_index,
            is_final_segment=synth_input.is_final_segment,
        )
        output = Path(self.temp_dir.name) / "output.wav"

        with self.assertRaises(ValueError) as ctx:
            self.service.synthesize(synth_input=synth_input, output_path=output)
        self.assertIn("Unsupported provider", str(ctx.exception))

    def test_model_mismatch_rejected(self):
        """Unsupported model rejected."""
        synth_input = self._make_preset_input()
        # Hack the model
        synth_input = SegmentSynthesisInput(
            snapshot_version=synth_input.snapshot_version,
            voice_source_type=synth_input.voice_source_type,
            voice_provider=synth_input.voice_provider,
            voice_model="v4turbo",
            text=synth_input.text,
            text_sha256=synth_input.text_sha256,
            settings=synth_input.settings,
            preset_voice_id=synth_input.preset_voice_id,
            custom_voice_revision_id=synth_input.custom_voice_revision_id,
            reference_audio_path=synth_input.reference_audio_path,
            reference_audio_sha256=synth_input.reference_audio_sha256,
            reference_transcript=synth_input.reference_transcript,
            reference_transcript_sha256=synth_input.reference_transcript_sha256,
            logical_voice_ref=synth_input.logical_voice_ref,
            effective_voice_ref=synth_input.effective_voice_ref,
            voice_resolution_reason=synth_input.voice_resolution_reason,
            casting_plan_id=synth_input.casting_plan_id,
            segment_index=synth_input.segment_index,
            is_final_segment=synth_input.is_final_segment,
        )
        output = Path(self.temp_dir.name) / "output.wav"

        with self.assertRaises(ValueError) as ctx:
            self.service.synthesize(synth_input=synth_input, output_path=output)
        self.assertIn("Unsupported model", str(ctx.exception))

    def test_inconsistent_preset_dataclass_rejected(self):
        """Preset with missing preset_voice_id rejected."""
        synth_input = self._make_preset_input()
        # Break consistency
        synth_input = SegmentSynthesisInput(
            snapshot_version=synth_input.snapshot_version,
            voice_source_type="preset",
            voice_provider=synth_input.voice_provider,
            voice_model=synth_input.voice_model,
            text=synth_input.text,
            text_sha256=synth_input.text_sha256,
            settings=synth_input.settings,
            preset_voice_id=None,  # Missing
            custom_voice_revision_id=synth_input.custom_voice_revision_id,
            reference_audio_path=synth_input.reference_audio_path,
            reference_audio_sha256=synth_input.reference_audio_sha256,
            reference_transcript=synth_input.reference_transcript,
            reference_transcript_sha256=synth_input.reference_transcript_sha256,
            logical_voice_ref=synth_input.logical_voice_ref,
            effective_voice_ref=synth_input.effective_voice_ref,
            voice_resolution_reason=synth_input.voice_resolution_reason,
            casting_plan_id=synth_input.casting_plan_id,
            segment_index=synth_input.segment_index,
            is_final_segment=synth_input.is_final_segment,
        )
        output = Path(self.temp_dir.name) / "output.wav"

        with self.assertRaises(ValueError) as ctx:
            self.service.synthesize(synth_input=synth_input, output_path=output)
        self.assertIn("missing preset_voice_id", str(ctx.exception))

    def test_empty_audio_rejected(self):
        """Empty audio output rejected."""
        self.mock_engine.infer = lambda *a, **kw: np.array([], dtype=np.float32)
        synth_input = self._make_preset_input()
        output = Path(self.temp_dir.name) / "output.wav"

        with self.assertRaises(ValueError) as ctx:
            self.service.synthesize(synth_input=synth_input, output_path=output)
        self.assertIn("rỗng hoặc không hợp lệ", str(ctx.exception))

    def test_nan_audio_rejected(self):
        """Audio with NaN rejected."""
        self.mock_engine.infer = lambda *a, **kw: np.array([1.0, np.nan, 2.0], dtype=np.float32)
        synth_input = self._make_preset_input()
        output = Path(self.temp_dir.name) / "output.wav"

        with self.assertRaises(ValueError) as ctx:
            self.service.synthesize(synth_input=synth_input, output_path=output)
        self.assertIn("rỗng hoặc không hợp lệ", str(ctx.exception))

    def test_infinity_audio_rejected(self):
        """Audio with infinity rejected."""
        self.mock_engine.infer = lambda *a, **kw: np.array([1.0, np.inf, 2.0], dtype=np.float32)
        synth_input = self._make_preset_input()
        output = Path(self.temp_dir.name) / "output.wav"

        with self.assertRaises(ValueError) as ctx:
            self.service.synthesize(synth_input=synth_input, output_path=output)
        self.assertIn("rỗng hoặc không hợp lệ", str(ctx.exception))

    def test_partial_removed_on_failure(self):
        """Partial file removed on synthesis failure."""
        self.mock_engine.infer = lambda *a, **kw: np.array([], dtype=np.float32)
        synth_input = self._make_preset_input()
        output = Path(self.temp_dir.name) / "output.wav"
        partial = output.with_suffix(output.suffix + ".partial")

        with self.assertRaises(ValueError):
            self.service.synthesize(synth_input=synth_input, output_path=output)

        self.assertFalse(partial.exists())

    def test_existing_wav_retained_on_failure(self):
        """Existing final WAV retained when synthesis fails."""
        synth_input = self._make_preset_input()
        output = Path(self.temp_dir.name) / "output.wav"

        # Create existing valid WAV
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"existing WAV content")

        # Make synthesis fail
        self.mock_engine.infer = lambda *a, **kw: np.array([], dtype=np.float32)

        with self.assertRaises(ValueError):
            self.service.synthesize(synth_input=synth_input, output_path=output)

        # Existing WAV should still exist
        self.assertTrue(output.exists())
        self.assertEqual(output.read_bytes(), b"existing WAV content")

    def test_successful_synthesis_replaces_final_wav(self):
        """Successful synthesis atomically replaces final WAV."""
        synth_input = self._make_preset_input()
        output = Path(self.temp_dir.name) / "output.wav"

        # Create old WAV
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"old content")

        self.service.synthesize(synth_input=synth_input, output_path=output)

        # New WAV should exist and be different
        self.assertTrue(output.exists())
        self.assertNotEqual(output.read_bytes(), b"old content")

    def test_mixed_arguments_rejected(self):
        """Cannot mix snapshot and legacy arguments."""
        synth_input = self._make_preset_input()
        output = Path(self.temp_dir.name) / "output.wav"

        with self.assertRaises(ValueError) as ctx:
            self.service.synthesize(
                synth_input=synth_input,
                text="legacy text",
                output_path=output,
            )
        self.assertIn("Cannot mix synth_input with legacy", str(ctx.exception))

    def test_no_arguments_rejected(self):
        """Must provide either snapshot or legacy arguments."""
        output = Path(self.temp_dir.name) / "output.wav"

        with self.assertRaises(ValueError) as ctx:
            self.service.synthesize(output_path=output)
        self.assertIn("Must provide either synth_input or complete legacy", str(ctx.exception))

    def test_incomplete_legacy_arguments_rejected(self):
        """Incomplete legacy arguments rejected."""
        output = Path(self.temp_dir.name) / "output.wav"

        with self.assertRaises(ValueError) as ctx:
            self.service.synthesize(
                text="test",
                voice="duc_tri",
                output_path=output,
            )
        self.assertIn("Incomplete preset legacy parameters", str(ctx.exception))

    def test_legacy_api_still_works(self):
        """Legacy API preserved for backward compatibility."""
        output = Path(self.temp_dir.name) / "output.wav"

        duration_ms, sample_rate = self.service.synthesize(
            text="Legacy synthesis.",
            voice="duc_tri",
            temperature=0.8,
            top_k=25,
            max_chars=256,
            silence_seconds=0.2,
            output_path=output,
        )

        self.assertTrue(output.exists())
        self.assertEqual(sample_rate, 24000)
        # Mock returns 1s, legacy adds 0.2s
        self.assertAlmostEqual(duration_ms, 1200, delta=50)

    # Phase 4B1: Custom reference preview validation
    def test_custom_reference_preview_calls_infer_with_ref_params(self):
        """Custom reference preview calls infer with ref_audio and ref_text."""
        # Create reference audio fixture
        ref_audio_bytes = b"RIFF\x00\x00\x00\x00WAVE"
        from story_audio.files import sha256_bytes
        ref_audio_sha = sha256_bytes(ref_audio_bytes)
        ref_storage_key = self.store.put_audio(ref_audio_bytes, ref_audio_sha)
        ref_audio_path = self.store.absolute(ref_storage_key)

        output = Path(self.temp_dir.name) / "output.wav"

        duration_ms, sample_rate = self.service.synthesize(
            text="Custom reference preview.",
            reference_audio_path=ref_audio_path,
            reference_transcript="Câu mẫu tham chiếu.",
            temperature=0.8,
            top_k=25,
            max_chars=256,
            silence_seconds=0.0,
            output_path=output,
        )

        # Verify custom reference path was used
        self.assertTrue(output.exists())
        self.assertEqual(self.mock_engine.last_call_args[0], "Custom reference preview.")
        self.assertIn("ref_audio", self.mock_engine.last_call_kwargs)
        self.assertEqual(str(ref_audio_path), self.mock_engine.last_call_kwargs["ref_audio"])
        self.assertEqual("Câu mẫu tham chiếu.", self.mock_engine.last_call_kwargs["ref_text"])
        self.assertNotIn("voice", self.mock_engine.last_call_kwargs)

    def test_preset_voice_plus_reference_rejected(self):
        """Cannot mix preset voice with reference parameters."""
        output = Path(self.temp_dir.name) / "output.wav"
        ref_path = Path(self.temp_dir.name) / "ref.wav"
        ref_path.write_bytes(b"audio")

        with self.assertRaisesRegex(ValueError, "Cannot mix preset voice with custom reference"):
            self.service.synthesize(
                text="test",
                voice="duc_tri",
                reference_audio_path=ref_path,
                reference_transcript="transcript",
                temperature=0.8,
                top_k=25,
                max_chars=256,
                silence_seconds=0.0,
                output_path=output,
            )

    def test_incomplete_reference_pair_rejected(self):
        """Both reference_audio_path and reference_transcript required."""
        output = Path(self.temp_dir.name) / "output.wav"
        ref_path = Path(self.temp_dir.name) / "ref.wav"
        ref_path.write_bytes(b"audio")

        with self.assertRaisesRegex(ValueError, "requires both reference_audio_path and reference_transcript"):
            self.service.synthesize(
                text="test",
                reference_audio_path=ref_path,
                temperature=0.8,
                top_k=25,
                max_chars=256,
                silence_seconds=0.0,
                output_path=output,
            )

    def test_reference_transcript_without_audio_rejected(self):
        """reference_transcript alone rejected."""
        output = Path(self.temp_dir.name) / "output.wav"

        with self.assertRaisesRegex(ValueError, "requires both reference_audio_path and reference_transcript"):
            self.service.synthesize(
                text="test",
                reference_transcript="transcript",
                temperature=0.8,
                top_k=25,
                max_chars=256,
                silence_seconds=0.0,
                output_path=output,
            )

    def test_snapshot_plus_reference_rejected(self):
        """Cannot mix snapshot with reference parameters."""
        synth_input = self._make_preset_input()
        output = Path(self.temp_dir.name) / "output.wav"
        ref_path = Path(self.temp_dir.name) / "ref.wav"
        ref_path.write_bytes(b"audio")

        with self.assertRaisesRegex(ValueError, "Cannot mix synth_input with legacy"):
            self.service.synthesize(
                synth_input=synth_input,
                reference_audio_path=ref_path,
                reference_transcript="transcript",
                output_path=output,
            )

    def test_incomplete_custom_reference_legacy_params_rejected(self):
        """Custom reference requires complete parameter set."""
        output = Path(self.temp_dir.name) / "output.wav"
        ref_path = Path(self.temp_dir.name) / "ref.wav"
        ref_path.write_bytes(b"audio")

        with self.assertRaisesRegex(ValueError, "Incomplete custom reference legacy parameters"):
            self.service.synthesize(
                text="test",
                reference_audio_path=ref_path,
                reference_transcript="transcript",
                temperature=0.8,
                # Missing top_k, max_chars, silence_seconds
                output_path=output,
            )


if __name__ == "__main__":
    unittest.main()
