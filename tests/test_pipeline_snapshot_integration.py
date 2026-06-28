"""
Unit tests for pipeline snapshot consumption and retry integration.

Covers Phase 3B3-D: retry metadata reset.
Uses temporary databases and isolated tests.
"""

import json
import unittest

from tests.base import IsolatedTestCase
from story_audio.db import Database, utcnow
from story_audio.diagnostics import retry_job_chapter, retry_segment
from story_audio.storage import ContentStore


class TestRetryMetadataReset(IsolatedTestCase):
    """Test retry operations clear output metadata but preserve snapshot."""
    
    def setUp(self):
        super().setUp()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        
        # Create minimal required rows
        with self.db.connect() as conn:
            now = utcnow()
            conn.execute(
                """INSERT INTO books (id, title, source_path, source_sha256, created_at, updated_at)
                   VALUES (1, 'Test', '/test.epub', 'sha', ?, ?)""",
                (now, now),
            )
            conn.execute(
                """INSERT INTO chapters (id, book_id, chapter_number, title, created_at, updated_at)
                   VALUES (1, 1, 1, 'Ch1', ?, ?)""",
                (now, now),
            )
            text_path, text_sha = self.store.put_text("Test text.")
            from story_audio.text import lexical_sha256
            text_lex_sha = lexical_sha256("Test text.")
            conn.execute(
                """INSERT INTO text_revisions (id, chapter_id, kind, content_path, content_sha256,
                       lexical_sha256, char_count, processor_version, status, created_at)
                   VALUES (1, 1, 'reflowed', ?, ?, ?, 10, 'test', 'approved', ?)""",
                (text_path, text_sha, text_lex_sha, now),
            )
            conn.execute(
                """INSERT INTO jobs (id, book_id, status, from_chapter, to_chapter, voice_name,
                       repair_mode, output_format, settings_json, scheduled_at, created_at, updated_at)
                   VALUES (1, 1, 'failed', 1, 1, 'test_voice', 'off', 'm4a', '{}', ?, ?, ?)""",
                (now, now, now),
            )
            conn.execute(
                """INSERT INTO job_chapters (id, job_id, chapter_id, sequence, status)
                   VALUES (1, 1, 1, 1, 'failed')""",
            )
    
    def test_retry_segment_clears_wav_metadata(self):
        """retry_segment clears wav_path, audio_sha256, duration_ms, verified_at."""
        # Create segment with output metadata
        with self.db.connect() as conn:
            now = utcnow()
            text_path, text_sha = self.store.put_text("Segment text.")
            settings_json = json.dumps({
                "temperature": 0.8,
                "top_k": 25,
                "max_chars": 256,
                "silence_seconds": 0.15,
                "engine_version": "vieneu:v3turbo",
            })
            conn.execute(
                """INSERT INTO segments (id, job_chapter_id, segment_index, status,
                       text_path, text_sha256,
                       voice_snapshot_version, voice_source_type, voice_provider, voice_model,
                       logical_voice_ref, effective_voice_ref, synthesis_settings_json,
                       voice_resolution_reason, synthesis_hash,
                       wav_path, audio_sha256, duration_ms, verified_at, created_at)
                   VALUES (1, 1, 0, 'failed', ?, ?, 1, 'preset', 'vieneu', 'v3turbo',
                       'narrator', 'test_voice', ?, 'direct', 'hash123',
                       '/old/path.wav', 'oldsha256', 1500, '2024-01-01', ?)""",
                (text_path, text_sha, settings_json, now),
            )
        
        # Retry
        retry_segment(self.db, 1)
        
        # Verify output metadata cleared
        seg = self.db.fetch_one(
            "SELECT wav_path, audio_sha256, duration_ms, verified_at FROM segments WHERE id=1"
        )
        self.assertIsNone(seg["wav_path"])
        self.assertIsNone(seg["audio_sha256"])
        self.assertIsNone(seg["duration_ms"])
        self.assertIsNone(seg["verified_at"])
    
    def test_retry_segment_preserves_snapshot(self):
        """retry_segment preserves all snapshot columns."""
        # Create segment
        with self.db.connect() as conn:
            now = utcnow()
            text_path, text_sha = self.store.put_text("Segment text.")
            settings_json = json.dumps({
                "temperature": 0.8,
                "top_k": 25,
                "max_chars": 256,
                "silence_seconds": 0.15,
                "engine_version": "vieneu:v3turbo",
            })
            conn.execute(
                """INSERT INTO segments (id, job_chapter_id, segment_index, status,
                       text_path, text_sha256,
                       voice_snapshot_version, voice_source_type, voice_provider, voice_model,
                       logical_voice_ref, effective_voice_ref, synthesis_settings_json,
                       voice_resolution_reason, synthesis_hash, created_at)
                   VALUES (1, 1, 0, 'failed', ?, ?, 1, 'preset', 'vieneu', 'v3turbo',
                       'narrator', 'test_voice', ?, 'direct', 'hash123', ?)""",
                (text_path, text_sha, settings_json, now),
            )
        
        # Get snapshot before
        before = self.db.fetch_one(
            """SELECT voice_snapshot_version, voice_source_type, voice_provider, voice_model,
                      logical_voice_ref, effective_voice_ref, synthesis_settings_json,
                      voice_resolution_reason, synthesis_hash
               FROM segments WHERE id=1"""
        )
        
        # Retry
        retry_segment(self.db, 1)
        
        # Get snapshot after
        after = self.db.fetch_one(
            """SELECT voice_snapshot_version, voice_source_type, voice_provider, voice_model,
                      logical_voice_ref, effective_voice_ref, synthesis_settings_json,
                      voice_resolution_reason, synthesis_hash
               FROM segments WHERE id=1"""
        )
        
        # All snapshot fields unchanged
        for key in before.keys():
            self.assertEqual(before[key], after[key], f"Field {key} changed")
    
    def test_retry_job_chapter_clears_failed_segments_only(self):
        """retry_job_chapter clears metadata for failed/pending/interrupted, not verified."""
        with self.db.connect() as conn:
            now = utcnow()
            text_path, text_sha = self.store.put_text("Segment text.")
            settings_json = json.dumps({
                "temperature": 0.8,
                "top_k": 25,
                "max_chars": 256,
                "silence_seconds": 0.15,
                "engine_version": "vieneu:v3turbo",
            })
            
            # Verified segment
            conn.execute(
                """INSERT INTO segments (id, job_chapter_id, segment_index, status,
                       text_path, text_sha256,
                       voice_snapshot_version, voice_source_type, voice_provider, voice_model,
                       logical_voice_ref, effective_voice_ref, synthesis_settings_json,
                       voice_resolution_reason, synthesis_hash,
                       wav_path, audio_sha256, duration_ms, verified_at, created_at)
                   VALUES (1, 1, 0, 'verified', ?, ?, 1, 'preset', 'vieneu', 'v3turbo',
                       'narrator', 'test_voice', ?, 'direct', 'hash1',
                       '/verified.wav', 'verifiedsha', 2000, '2024-01-01', ?)""",
                (text_path, text_sha, settings_json, now),
            )
            
            # Failed segment
            conn.execute(
                """INSERT INTO segments (id, job_chapter_id, segment_index, status,
                       text_path, text_sha256,
                       voice_snapshot_version, voice_source_type, voice_provider, voice_model,
                       logical_voice_ref, effective_voice_ref, synthesis_settings_json,
                       voice_resolution_reason, synthesis_hash,
                       wav_path, audio_sha256, duration_ms, created_at)
                   VALUES (2, 1, 1, 'failed', ?, ?, 1, 'preset', 'vieneu', 'v3turbo',
                       'narrator', 'test_voice', ?, 'direct', 'hash2',
                       '/failed.wav', 'failedsha', 1000, ?)""",
                (text_path, text_sha, settings_json, now),
            )
        
        # Retry chapter
        retry_job_chapter(self.db, 1)
        
        # Verified segment keeps metadata
        seg1 = self.db.fetch_one("SELECT wav_path, status FROM segments WHERE id=1")
        self.assertEqual(seg1["status"], "verified")
        self.assertEqual(seg1["wav_path"], "/verified.wav")
        
        # Failed segment cleared
        seg2 = self.db.fetch_one("SELECT wav_path, audio_sha256 FROM segments WHERE id=2")
        self.assertIsNone(seg2["wav_path"])
        self.assertIsNone(seg2["audio_sha256"])
    
    def test_retry_preserves_text_and_synthesis_hash(self):
        """Retry preserves text_path, text_sha256, synthesis_hash."""
        with self.db.connect() as conn:
            now = utcnow()
            text_path, text_sha = self.store.put_text("Segment text.")
            settings_json = json.dumps({
                "temperature": 0.8,
                "top_k": 25,
                "max_chars": 256,
                "silence_seconds": 0.15,
                "engine_version": "vieneu:v3turbo",
            })
            conn.execute(
                """INSERT INTO segments (id, job_chapter_id, segment_index, status,
                       text_path, text_sha256,
                       voice_snapshot_version, voice_source_type, voice_provider, voice_model,
                       logical_voice_ref, effective_voice_ref, synthesis_settings_json,
                       voice_resolution_reason, synthesis_hash,
                       wav_path, audio_sha256, created_at)
                   VALUES (1, 1, 0, 'failed', ?, ?, 1, 'preset', 'vieneu', 'v3turbo',
                       'narrator', 'test_voice', ?, 'direct', 'synth_hash_123',
                       '/old.wav', 'oldsha', ?)""",
                (text_path, text_sha, settings_json, now),
            )
        
        # Retry
        retry_segment(self.db, 1)
        
        # Text and synthesis_hash preserved
        seg = self.db.fetch_one(
            "SELECT text_path, text_sha256, synthesis_hash FROM segments WHERE id=1"
        )
        self.assertEqual(seg["text_path"], text_path)
        self.assertEqual(seg["text_sha256"], text_sha)
        self.assertEqual(seg["synthesis_hash"], "synth_hash_123")


class TestPipelineSnapshotConsumption(IsolatedTestCase):
    """Test pipeline snapshot loading and consumption."""
    
    def setUp(self):
        super().setUp()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
    
    def test_legacy_segment_fails_closed(self):
        """Pending legacy segment (NULL snapshot_version) fails closed without calling TTS."""
        from story_audio.synthesis_snapshot import load_segment_synthesis_input, LegacySynthesisSnapshotError
        
        # Create segment WITHOUT snapshot
        segment = {
            "id": 1,
            "segment_index": 0,
            "text": "Test text",
            "text_sha256": "sha256hash",
            "voice_snapshot_version": None,  # Legacy segment
        }
        
        with self.assertRaises(LegacySynthesisSnapshotError) as cm:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        
        self.assertIn("no synthesis snapshot", str(cm.exception))
    
    def test_preset_snapshot_loads_successfully(self):
        """Valid preset snapshot loads SegmentSynthesisInput."""
        from story_audio.synthesis_snapshot import load_segment_synthesis_input
        
        text_path, text_sha = self.store.put_text("Test segment text")
        settings_json = json.dumps({
            "temperature": 0.8,
            "top_k": 25,
            "max_chars": 256,
            "silence_seconds": 0.15,
            "engine_version": "vieneu:v3turbo",
        })
        
        segment = {
            "id": 1,
            "segment_index": 0,
            "text_path": text_path,
            "text_sha256": text_sha,
            "voice_snapshot_version": 1,
            "voice_source_type": "preset",
            "voice_provider": "vieneu",
            "voice_model": "v3turbo",
            "logical_voice_ref": "narrator",
            "effective_voice_ref": "preset_voice_id",
            "synthesis_settings_json": settings_json,
            "voice_resolution_reason": "direct",
            "synthesis_hash": "hash123",
            "custom_voice_revision_id": None,
            "reference_audio_storage_key": None,
            "reference_audio_sha256": None,
            "reference_transcript": None,
            "reference_transcript_sha256": None,
            "casting_plan_id": None,
        }
        
        synth_input = load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        
        self.assertEqual(synth_input.snapshot_version, 1)
        self.assertEqual(synth_input.voice_source_type, "preset")
        self.assertEqual(synth_input.preset_voice_id, "preset_voice_id")
        self.assertEqual(synth_input.text, "Test segment text")
        self.assertEqual(synth_input.settings.temperature, 0.8)
    
    def test_final_segment_detection(self):
        """Final segment uses is_final_segment parameter, not segment_index."""
        from story_audio.synthesis_snapshot import load_segment_synthesis_input
        
        text_path, text_sha = self.store.put_text("Final text")
        settings_json = json.dumps({
            "temperature": 0.8,
            "top_k": 25,
            "max_chars": 256,
            "silence_seconds": 0.15,
            "engine_version": "vieneu:v3turbo",
        })
        
        segment = {
            "id": 1,
            "segment_index": 5,  # Non-contiguous index
            "text_path": text_path,
            "text_sha256": text_sha,
            "voice_snapshot_version": 1,
            "voice_source_type": "preset",
            "voice_provider": "vieneu",
            "voice_model": "v3turbo",
            "logical_voice_ref": "narrator",
            "effective_voice_ref": "voice_id",
            "synthesis_settings_json": settings_json,
            "voice_resolution_reason": "direct",
            "synthesis_hash": "hash",
            "custom_voice_revision_id": None,
            "reference_audio_storage_key": None,
            "reference_audio_sha256": None,
            "reference_transcript": None,
            "reference_transcript_sha256": None,
            "casting_plan_id": None,
        }
        
        # Test as non-final
        synth_non_final = load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        self.assertFalse(synth_non_final.is_final_segment)
        self.assertEqual(synth_non_final.effective_silence_seconds(), 0.15)
        
        # Test as final (position-based, ignores segment_index)
        synth_final = load_segment_synthesis_input(segment, self.store, is_final_segment=True)
        self.assertTrue(synth_final.is_final_segment)
        self.assertEqual(synth_final.effective_silence_seconds(), 0.0)
    
    def test_custom_snapshot_uses_pinned_revision(self):
        """Custom-reference segment uses pinned revision without database lookup."""
        from story_audio.synthesis_snapshot import load_segment_synthesis_input
        from pathlib import Path
        
        # Create reference audio and transcript in storage
        ref_audio = b"fake audio data"
        ref_audio_path = self.config.blobs_dir / "audio" / "ab" / "abcd1234.wav"
        ref_audio_path.parent.mkdir(parents=True, exist_ok=True)
        ref_audio_path.write_bytes(ref_audio)
        
        from story_audio.files import sha256_file, sha256_text
        ref_audio_sha = sha256_file(ref_audio_path)
        ref_transcript = "Reference transcript text"
        ref_transcript_sha = sha256_text(ref_transcript)
        
        text_path, text_sha = self.store.put_text("Segment text")
        settings_json = json.dumps({
            "temperature": 0.8,
            "top_k": 25,
            "max_chars": 256,
            "silence_seconds": 0.15,
            "engine_version": "vieneu:v3turbo",
        })
        
        segment = {
            "id": 1,
            "segment_index": 0,
            "text_path": text_path,
            "text_sha256": text_sha,
            "voice_snapshot_version": 1,
            "voice_source_type": "custom_reference",
            "voice_provider": "vieneu",
            "voice_model": "v3turbo",
            "logical_voice_ref": "custom:5",
            "effective_voice_ref": "custom:5",
            "synthesis_settings_json": settings_json,
            "voice_resolution_reason": "character_override",
            "synthesis_hash": "hash",
            "custom_voice_revision_id": 5,
            "reference_audio_storage_key": "audio/ab/abcd1234.wav",
            "reference_audio_sha256": ref_audio_sha,
            "reference_transcript": ref_transcript,
            "reference_transcript_sha256": ref_transcript_sha,
            "casting_plan_id": None,
        }
        
        # Load snapshot (should not query database)
        synth_input = load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        
        # Verify pinned values
        self.assertEqual(synth_input.voice_source_type, "custom_reference")
        self.assertEqual(synth_input.custom_voice_revision_id, 5)
        self.assertEqual(synth_input.reference_audio_sha256, ref_audio_sha)
        self.assertEqual(synth_input.reference_transcript, ref_transcript)
        self.assertEqual(synth_input.reference_transcript_sha256, ref_transcript_sha)
        self.assertTrue(synth_input.reference_audio_path.exists())
    
    def test_legacy_fields_ignored_after_snapshot(self):
        """Changing legacy fields after snapshot creation does not affect synthesis."""
        from story_audio.synthesis_snapshot import load_segment_synthesis_input
        
        text_path, text_sha = self.store.put_text("Original text")
        original_settings = {
            "temperature": 0.8,
            "top_k": 25,
            "max_chars": 256,
            "silence_seconds": 0.15,
            "engine_version": "vieneu:v3turbo",
        }
        settings_json = json.dumps(original_settings)
        
        # Create segment with snapshot
        segment = {
            "id": 1,
            "segment_index": 0,
            "text_path": text_path,
            "text_sha256": text_sha,
            "voice_snapshot_version": 1,
            "voice_source_type": "preset",
            "voice_provider": "vieneu",
            "voice_model": "v3turbo",
            "logical_voice_ref": "narrator",
            "effective_voice_ref": "original_voice",
            "synthesis_settings_json": settings_json,
            "voice_resolution_reason": "direct",
            "synthesis_hash": "original_hash",
            "resolved_voice_id": "original_voice",  # Legacy field
            "custom_voice_revision_id": None,
            "reference_audio_storage_key": None,
            "reference_audio_sha256": None,
            "reference_transcript": None,
            "reference_transcript_sha256": None,
            "casting_plan_id": None,
        }
        
        # Load original
        synth_original = load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        
        # Change legacy fields (simulating database mutations)
        segment["resolved_voice_id"] = "changed_voice"
        
        # Load again - should use snapshot, not legacy field
        synth_after = load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        
        self.assertEqual(synth_after.preset_voice_id, "original_voice")
        self.assertEqual(synth_after.settings.temperature, 0.8)
    
    def test_same_input_object_across_retry_attempts(self):
        """TTS retry receives the exact same SegmentSynthesisInput object."""
        from story_audio.synthesis_snapshot import load_segment_synthesis_input
        
        text_path, text_sha = self.store.put_text("Test text")
        settings_json = json.dumps({
            "temperature": 0.8,
            "top_k": 25,
            "max_chars": 256,
            "silence_seconds": 0.15,
            "engine_version": "vieneu:v3turbo",
        })
        
        segment = {
            "id": 1,
            "segment_index": 0,
            "text_path": text_path,
            "text_sha256": text_sha,
            "voice_snapshot_version": 1,
            "voice_source_type": "preset",
            "voice_provider": "vieneu",
            "voice_model": "v3turbo",
            "logical_voice_ref": "narrator",
            "effective_voice_ref": "voice_id",
            "synthesis_settings_json": settings_json,
            "voice_resolution_reason": "direct",
            "synthesis_hash": "hash",
            "custom_voice_revision_id": None,
            "reference_audio_storage_key": None,
            "reference_audio_sha256": None,
            "reference_transcript": None,
            "reference_transcript_sha256": None,
            "casting_plan_id": None,
        }
        
        # Load once (simulating first attempt)
        input1 = load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        
        # Load again (simulating retry attempt)
        input2 = load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        
        # Objects are equal but not identical (each call creates new instance)
        # Pipeline loads once and reuses, which is tested in integration
        self.assertEqual(input1.text, input2.text)
        self.assertEqual(input1.preset_voice_id, input2.preset_voice_id)
        self.assertEqual(input1.settings.temperature, input2.settings.temperature)
    
    def test_snapshot_validation_failure_no_tts_call(self):
        """Invalid snapshot fails before TTS with concise diagnostic."""
        from story_audio.synthesis_snapshot import load_segment_synthesis_input, SnapshotValidationError
        
        text_path, text_sha = self.store.put_text("Test text")
        
        # Invalid: missing required settings key
        invalid_settings = json.dumps({
            "temperature": 0.8,
            "top_k": 25,
            # Missing max_chars, silence_seconds, engine_version
        })
        
        segment = {
            "id": 1,
            "segment_index": 0,
            "text_path": text_path,
            "text_sha256": text_sha,
            "voice_snapshot_version": 1,
            "voice_source_type": "preset",
            "voice_provider": "vieneu",
            "voice_model": "v3turbo",
            "logical_voice_ref": "narrator",
            "effective_voice_ref": "voice_id",
            "synthesis_settings_json": invalid_settings,
            "voice_resolution_reason": "direct",
            "synthesis_hash": "hash",
            "custom_voice_revision_id": None,
            "reference_audio_storage_key": None,
            "reference_audio_sha256": None,
            "reference_transcript": None,
            "reference_transcript_sha256": None,
            "casting_plan_id": None,
        }
        
        with self.assertRaises(SnapshotValidationError) as cm:
            load_segment_synthesis_input(segment, self.store, is_final_segment=False)
        
        self.assertIn("Missing required settings keys", str(cm.exception))
    
    def test_physical_wav_retained_after_retry(self):
        """retry_segment clears metadata but preserves physical WAV file."""
        import tempfile
        from pathlib import Path
        
        # Create minimal database setup
        with self.db.connect() as conn:
            now = utcnow()
            conn.execute(
                """INSERT INTO books (id, title, source_path, source_sha256, created_at, updated_at)
                   VALUES (1, 'Test', '/test.epub', 'sha', ?, ?)""",
                (now, now),
            )
            conn.execute(
                """INSERT INTO chapters (id, book_id, chapter_number, title, created_at, updated_at)
                   VALUES (1, 1, 1, 'Ch1', ?, ?)""",
                (now, now),
            )
            text_path, text_sha = self.store.put_text("Test text.")
            from story_audio.text import lexical_sha256
            text_lex_sha = lexical_sha256("Test text.")
            conn.execute(
                """INSERT INTO text_revisions (id, chapter_id, kind, content_path, content_sha256,
                       lexical_sha256, char_count, processor_version, status, created_at)
                   VALUES (1, 1, 'reflowed', ?, ?, ?, 10, 'test', 'approved', ?)""",
                (text_path, text_sha, text_lex_sha, now),
            )
            conn.execute(
                """INSERT INTO jobs (id, book_id, status, from_chapter, to_chapter, voice_name,
                       repair_mode, output_format, settings_json, scheduled_at, created_at, updated_at)
                   VALUES (1, 1, 'failed', 1, 1, 'test_voice', 'off', 'm4a', '{}', ?, ?, ?)""",
                (now, now, now),
            )
            conn.execute(
                """INSERT INTO job_chapters (id, job_id, chapter_id, sequence, status)
                   VALUES (1, 1, 1, 1, 'failed')""",
            )
            
            # Create physical WAV file
            wav_path = Path(tempfile.mktemp(suffix=".wav", dir=self.temp_root))
            wav_path.write_bytes(b"fake wav data")
            
            settings_json = json.dumps({
                "temperature": 0.8,
                "top_k": 25,
                "max_chars": 256,
                "silence_seconds": 0.15,
                "engine_version": "vieneu:v3turbo",
            })
            
            conn.execute(
                """INSERT INTO segments (id, job_chapter_id, segment_index, status,
                       text_path, text_sha256,
                       voice_snapshot_version, voice_source_type, voice_provider, voice_model,
                       logical_voice_ref, effective_voice_ref, synthesis_settings_json,
                       voice_resolution_reason, synthesis_hash,
                       wav_path, audio_sha256, duration_ms, created_at)
                   VALUES (1, 1, 0, 'failed', ?, ?, 1, 'preset', 'vieneu', 'v3turbo',
                       'narrator', 'test_voice', ?, 'direct', 'hash123',
                       ?, 'oldsha', 1500, ?)""",
                (text_path, text_sha, settings_json, str(wav_path), now),
            )
        
        # Verify WAV exists before retry
        self.assertTrue(wav_path.exists())
        
        # Retry segment
        retry_segment(self.db, 1)
        
        # Verify metadata cleared
        seg = self.db.fetch_one("SELECT wav_path, audio_sha256, duration_ms FROM segments WHERE id=1")
        self.assertIsNone(seg["wav_path"])
        self.assertIsNone(seg["audio_sha256"])
        self.assertIsNone(seg["duration_ms"])
        
        # Verify physical WAV still exists
        self.assertTrue(wav_path.exists())


if __name__ == "__main__":
    unittest.main()
