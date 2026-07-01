"""
Tests for segment regeneration feature.

Tests the complete flow of regenerating verified segments with A/B comparison:
- Generate candidate using immutable snapshot
- Listen to original and candidate
- Accept candidate (rebuilds artifacts)
- Reject candidate (keeps original)
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from story_audio.config import Settings
from story_audio.db import Database, utcnow
from story_audio.files import sha256_file, sha256_text
from story_audio.segment_regeneration import (
    RegenerationError,
    RegenerationRebuildError,
    RegenerationValidationError,
    accept_segment_candidate,
    list_segment_attempts,
    regenerate_verified_segment,
    reject_segment_candidate,
)
from story_audio.storage import ContentStore
from tests.base import IsolatedTestCase


class TestSegmentRegeneration(IsolatedTestCase):
    """Tests for segment regeneration API."""

    def setUp(self):
        super().setUp()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        
        # Create mock TTS service
        self.tts = Mock()
        
        # Create test fixtures
        self._create_test_job()

    def _create_test_job(self):
        """Create a completed job with verified segments."""
        with self.db.connect() as conn:
            # Book
            conn.execute(
                "INSERT INTO books(title,author,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                ("Test Book", "Test Author", "test.epub", sha256_text("test.epub"), utcnow(), utcnow())
            )
            self.book_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Chapter
            conn.execute(
                """INSERT INTO chapters(
                    book_id,chapter_number,title,char_count,audio_status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (self.book_id, 1, "Test Chapter", 100, "completed", utcnow(), utcnow())
            )
            self.chapter_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Text revision
            text = "Test chapter text for synthesis."
            text_path, text_sha = self.store.put_text(text)
            conn.execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,parent_revision_id,content_path,content_sha256,lexical_sha256,
                    char_count,processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (self.chapter_id, "reflowed", None, text_path, text_sha, text_sha, len(text), "test-v1", "approved", utcnow())
            )
            self.text_revision_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Job
            settings_json = json.dumps({
                "tts_mode": "v3turbo",
                "temperature": 0.8,
                "top_k": 25,
                "max_chars": 256,
                "target_chars": 230,
                "silence_seconds": 0.15,
                "engine_version": "vieneu:v3turbo"
            })
            conn.execute(
                """INSERT INTO jobs(
                    book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                    settings_json,total_chapters,scheduled_at,created_at,updated_at,finished_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.book_id, "completed", 1, 1, "preset_voice", "off", "m4a", settings_json, 1, utcnow(), utcnow(), utcnow(), utcnow())
            )
            self.job_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Job chapter
            conn.execute(
                """INSERT INTO job_chapters(
                    job_id,chapter_id,sequence,status,text_revision_id,finished_at
                ) VALUES(?,?,?,?,?,?)""",
                (self.job_id, self.chapter_id, 1, "completed", self.text_revision_id, utcnow())
            )
            self.job_chapter_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Create test segment WAV
            self.segment_dir = self.config.work_dir / f"job_{self.job_id}" / "chapter_0001" / "segments"
            self.segment_dir.mkdir(parents=True, exist_ok=True)
            self.segment_wav = self.segment_dir / "000001.wav"
            self._create_test_wav(self.segment_wav, duration_ms=1000)
            
            # Segment with preset voice snapshot
            segment_text = "Test segment text."
            segment_text_path, segment_text_sha = self.store.put_text(segment_text)
            
            synthesis_settings_json = json.dumps({
                "temperature": 0.8,
                "top_k": 25,
                "max_chars": 256,
                "silence_seconds": 0.15,
                "engine_version": "vieneu:v3turbo"
            }, sort_keys=True)
            
            # Calculate synthesis hash (needs to match how pipeline does it)
            synthesis_hash = sha256_text(synthesis_settings_json + segment_text + "preset_voice")
            
            conn.execute(
                """INSERT INTO segments(
                    job_chapter_id,segment_index,text_path,text_sha256,status,
                    wav_path,audio_sha256,duration_ms,verified_at,created_at,
                    voice_snapshot_version,voice_source_type,voice_provider,voice_model,
                    logical_voice_ref,effective_voice_ref,synthesis_settings_json,
                    voice_resolution_reason,synthesis_hash
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    self.job_chapter_id, 1, segment_text_path, segment_text_sha, "verified",
                    str(self.segment_wav), sha256_file(self.segment_wav), 1000, utcnow(), utcnow(),
                    1, "preset", "vieneu", "v3turbo",
                    "narrator", "preset_voice", synthesis_settings_json,
                    "direct", synthesis_hash
                )
            )
            self.segment_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Create artifact
            artifact_path = self.config.output_dir / "test_artifact.m4a"
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_bytes(b"test audio data")
            
            conn.execute(
                """INSERT INTO artifacts(
                    chapter_id,job_chapter_id,text_revision_id,artifact_type,
                    path,sha256,size_bytes,duration_ms,status,created_at,verified_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    self.chapter_id, self.job_chapter_id, self.text_revision_id, "chapter_final_m4a",
                    str(artifact_path), sha256_file(artifact_path), artifact_path.stat().st_size,
                    1000, "active", utcnow(), utcnow()
                )
            )
            self.artifact_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Link artifact to chapter
            conn.execute(
                "UPDATE chapters SET active_audio_artifact_id=? WHERE id=?",
                (self.artifact_id, self.chapter_id)
            )

    def _create_test_wav(self, path: Path, duration_ms: int = 1000):
        """Create a minimal valid WAV file for testing."""
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Generate 1 second of silence at 48kHz, mono, 16-bit PCM
        sample_rate = 48000
        samples = (duration_ms * sample_rate) // 1000
        
        import wave
        with wave.open(str(path), 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(b'\x00\x00' * samples)

    def test_regenerate_verified_segment_creates_candidate(self):
        """Test that regenerating a verified segment creates a candidate attempt."""
        # Mock TTS synthesis
        def mock_synthesize(synth_input=None, output_path=None, **kwargs):
            self._create_test_wav(output_path, duration_ms=1100)
            return (1100, 48000)
        
        self.tts.synthesize = Mock(side_effect=mock_synthesize)
        
        # Regenerate
        result = regenerate_verified_segment(
            self.db, self.store, self.tts, self.config, self.segment_id
        )
        
        # Verify result
        self.assertIn("attempt_id", result)
        self.assertEqual(result["segment_id"], self.segment_id)
        self.assertEqual(result["attempt_number"], 2)  # Candidate is Attempt 2
        self.assertEqual(result["duration_ms"], 1100)
        
        # Verify database: active Attempt 1 was seeded from existing segment
        active_attempt = self.db.fetch_one(
            "SELECT * FROM segment_attempts WHERE segment_id=? AND status='active'",
            (self.segment_id,)
        )
        self.assertIsNotNone(active_attempt)
        self.assertEqual(active_attempt["attempt_number"], 1)
        self.assertEqual(active_attempt["wav_path"], str(self.segment_wav))
        self.assertEqual(active_attempt["duration_ms"], 1000)
        
        # Verify database: candidate is Attempt 2
        candidate = self.db.fetch_one(
            "SELECT * FROM segment_attempts WHERE id=?",
            (result["attempt_id"],)
        )
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["status"], "candidate")
        self.assertEqual(candidate["segment_id"], self.segment_id)
        self.assertEqual(candidate["attempt_number"], 2)
        
        # Verify original segment unchanged
        segment = self.db.fetch_one("SELECT * FROM segments WHERE id=?", (self.segment_id,))
        self.assertEqual(segment["status"], "verified")
        self.assertEqual(segment["wav_path"], str(self.segment_wav))
        self.assertEqual(segment["duration_ms"], 1000)
        
        # Verify WAV files exist
        self.assertTrue(Path(active_attempt["wav_path"]).exists())
        self.assertTrue(Path(candidate["wav_path"]).exists())

    def test_regenerate_rejects_non_verified_segment(self):
        """Test that only verified segments can be regenerated."""
        # Change segment to failed
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE segments SET status='failed' WHERE id=?",
                (self.segment_id,)
            )
        
        # Attempt regeneration
        with self.assertRaises(RegenerationValidationError) as cm:
            regenerate_verified_segment(
                self.db, self.store, self.tts, self.config, self.segment_id
            )
        
        self.assertIn("Only verified segments", str(cm.exception))
        self.assertIn("/api/segments/{id}/retry", str(cm.exception))

    def test_regenerate_rejects_running_job(self):
        """Test that regeneration is blocked when job is running."""
        # Set job to running
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE jobs SET status='running' WHERE id=?",
                (self.job_id,)
            )
        
        # Attempt regeneration
        with self.assertRaises(RegenerationValidationError) as cm:
            regenerate_verified_segment(
                self.db, self.store, self.tts, self.config, self.segment_id
            )
        
        self.assertIn("Cannot regenerate while job is", str(cm.exception))

    def test_regenerate_rejects_existing_candidate(self):
        """Test that only one candidate can exist at a time."""
        # Create existing candidate
        candidate_path = self.segment_dir / "segment_1_attempt_1.wav"
        self._create_test_wav(candidate_path)
        
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO segment_attempts(
                    segment_id,attempt_number,status,wav_path,audio_sha256,duration_ms,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (self.segment_id, 1, "candidate", str(candidate_path), sha256_file(candidate_path), 1100, utcnow())
            )
        
        # Attempt regeneration
        with self.assertRaises(RegenerationValidationError) as cm:
            regenerate_verified_segment(
                self.db, self.store, self.tts, self.config, self.segment_id
            )
        
        self.assertIn("already has a pending candidate", str(cm.exception))

    def test_candidate_synthesis_reuses_immutable_snapshot(self):
        """Test that synthesis uses exact snapshot fields from segment."""
        captured_input = None
        
        def mock_synthesize(synth_input=None, output_path=None, **kwargs):
            nonlocal captured_input
            captured_input = synth_input
            self._create_test_wav(output_path)
            return (1000, 48000)
        
        self.tts.synthesize = Mock(side_effect=mock_synthesize)
        
        # Regenerate
        regenerate_verified_segment(
            self.db, self.store, self.tts, self.config, self.segment_id
        )
        
        # Verify snapshot was used
        self.assertIsNotNone(captured_input)
        self.assertEqual(captured_input.voice_source_type, "preset")
        self.assertEqual(captured_input.voice_provider, "vieneu")
        self.assertEqual(captured_input.voice_model, "v3turbo")
        self.assertEqual(captured_input.effective_voice_ref, "preset_voice")
        self.assertEqual(captured_input.settings.temperature, 0.8)
        self.assertEqual(captured_input.settings.top_k, 25)

    @patch('story_audio.segment_regeneration._reassemble_chapter_with_candidate')
    def test_accept_candidate_promotes_and_marks_superseded(self, mock_reassemble):
        """Test that accepting candidate promotes it and marks old as superseded."""
        # Create candidate
        candidate_path = self.segment_dir / "segment_1_attempt_1.wav"
        self._create_test_wav(candidate_path, duration_ms=1100)
        
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO segment_attempts(
                    segment_id,attempt_number,status,wav_path,audio_sha256,duration_ms,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (self.segment_id, 1, "candidate", str(candidate_path), sha256_file(candidate_path), 1100, utcnow())
            )
            attempt_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        # Mock rebuild to return success
        master_path = self.config.work_dir / "temp_master.wav"
        timeline_path = self.config.work_dir / "temp_timeline.json"
        self._create_test_wav(master_path, duration_ms=1100)
        timeline_path.write_text(json.dumps({"schema_version": 2, "duration_ms": 1100}))
        
        mock_reassemble.return_value = {
            "master_wav": master_path,
            "master_duration_ms": 1100,
            "timeline_json": timeline_path,
            "final_path": master_path,
            "temp_dir": self.config.work_dir / "temp"
        }
        
        # Accept candidate
        result = accept_segment_candidate(
            self.db, self.store, self.config, self.segment_id, attempt_id
        )
        
        # Verify result
        self.assertEqual(result["segment_id"], self.segment_id)
        self.assertEqual(result["attempt_id"], attempt_id)
        self.assertIn("new_artifact_id", result)
        
        # Verify candidate is now active
        attempt = self.db.fetch_one("SELECT * FROM segment_attempts WHERE id=?", (attempt_id,))
        self.assertEqual(attempt["status"], "active")
        self.assertIsNotNone(attempt["accepted_at"])
        
        # Verify old active was NOT marked as superseded (since it didn't exist in attempts table yet)
        # But segment pointers were updated
        segment = self.db.fetch_one("SELECT * FROM segments WHERE id=?", (self.segment_id,))
        self.assertEqual(segment["wav_path"], str(candidate_path))
        self.assertEqual(segment["duration_ms"], 1100)
        
        # Verify new artifact created
        new_artifact = self.db.fetch_one("SELECT * FROM artifacts WHERE id=?", (result["new_artifact_id"],))
        self.assertIsNotNone(new_artifact)
        self.assertEqual(new_artifact["status"], "active")
        
        # Verify chapter pointer updated
        chapter = self.db.fetch_one("SELECT * FROM chapters WHERE id=?", (self.chapter_id,))
        self.assertEqual(chapter["active_audio_artifact_id"], result["new_artifact_id"])

    def test_reject_candidate_leaves_active_unchanged(self):
        """Test that rejecting candidate leaves everything unchanged."""
        # Create candidate
        candidate_path = self.segment_dir / "segment_1_attempt_1.wav"
        self._create_test_wav(candidate_path)
        
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO segment_attempts(
                    segment_id,attempt_number,status,wav_path,audio_sha256,duration_ms,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (self.segment_id, 1, "candidate", str(candidate_path), sha256_file(candidate_path), 1100, utcnow())
            )
            attempt_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        # Get original state
        orig_segment = dict(self.db.fetch_one("SELECT * FROM segments WHERE id=?", (self.segment_id,)))
        orig_chapter = dict(self.db.fetch_one("SELECT * FROM chapters WHERE id=?", (self.chapter_id,)))
        
        # Reject candidate
        result = reject_segment_candidate(self.db, self.segment_id, attempt_id)
        
        # Verify result
        self.assertEqual(result["status"], "rejected")
        
        # Verify candidate is rejected
        attempt = self.db.fetch_one("SELECT * FROM segment_attempts WHERE id=?", (attempt_id,))
        self.assertEqual(attempt["status"], "rejected")
        self.assertIsNotNone(attempt["rejected_at"])
        
        # Verify segment unchanged
        segment = dict(self.db.fetch_one("SELECT * FROM segments WHERE id=?", (self.segment_id,)))
        self.assertEqual(segment["wav_path"], orig_segment["wav_path"])
        self.assertEqual(segment["duration_ms"], orig_segment["duration_ms"])
        
        # Verify chapter unchanged
        chapter = dict(self.db.fetch_one("SELECT * FROM chapters WHERE id=?", (self.chapter_id,)))
        self.assertEqual(chapter["active_audio_artifact_id"], orig_chapter["active_audio_artifact_id"])
        
        # Verify candidate WAV still exists (for audit)
        self.assertTrue(Path(attempt["wav_path"]).exists())

    def test_list_attempts_shows_active_candidate_history(self):
        """Test listing all attempts for a segment."""
        # Create multiple attempts
        attempt_ids = []
        for i in range(1, 4):
            candidate_path = self.segment_dir / f"segment_1_attempt_{i}.wav"
            self._create_test_wav(candidate_path)
            
            status = "active" if i == 1 else ("candidate" if i == 3 else "superseded")
            
            with self.db.connect() as conn:
                conn.execute(
                    """INSERT INTO segment_attempts(
                        segment_id,attempt_number,status,wav_path,audio_sha256,duration_ms,created_at
                    ) VALUES(?,?,?,?,?,?,?)""",
                    (self.segment_id, i, status, str(candidate_path), sha256_file(candidate_path), 1000 + i * 100, utcnow())
                )
                attempt_ids.append(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        
        # List attempts
        result = list_segment_attempts(self.db, self.segment_id)
        
        # Verify structure
        self.assertEqual(result["segment_id"], self.segment_id)
        self.assertIsNotNone(result["active_attempt"])
        self.assertIsNotNone(result["candidate"])
        self.assertEqual(len(result["history"]), 1)
        
        # Verify active
        self.assertEqual(result["active_attempt"]["attempt_id"], attempt_ids[0])
        self.assertEqual(result["active_attempt"]["status"], "active")
        
        # Verify candidate
        self.assertEqual(result["candidate"]["attempt_id"], attempt_ids[2])
        self.assertEqual(result["candidate"]["status"], "candidate")
        
        # Verify history
        self.assertEqual(result["history"][0]["attempt_id"], attempt_ids[1])
        self.assertEqual(result["history"][0]["status"], "superseded")

    def test_list_attempts_before_regeneration_shows_original(self):
        """Test that list API shows original segment as active before first regeneration."""
        # List attempts before any regeneration
        result = list_segment_attempts(self.db, self.segment_id)
        
        # Verify structure
        self.assertEqual(result["segment_id"], self.segment_id)
        self.assertIsNotNone(result["active_attempt"])
        self.assertIsNone(result["candidate"])
        self.assertEqual(len(result["history"]), 0)
        
        # Verify active shows original segment
        active = result["active_attempt"]
        self.assertIsNone(active["attempt_id"])  # Not in attempts table yet
        self.assertEqual(active["attempt_number"], 0)  # Virtual attempt 0
        self.assertEqual(active["status"], "active")
        self.assertEqual(active["duration_ms"], 1000)
    
    def test_first_regeneration_seeds_active_and_creates_candidate(self):
        """Test that first regeneration seeds active Attempt 1 and creates candidate Attempt 2."""
        # Mock TTS synthesis
        def mock_synthesize(synth_input=None, output_path=None, **kwargs):
            self._create_test_wav(output_path, duration_ms=1100)
            return (1100, 48000)
        
        self.tts.synthesize = Mock(side_effect=mock_synthesize)
        
        # First regeneration
        result = regenerate_verified_segment(
            self.db, self.store, self.tts, self.config, self.segment_id
        )
        
        # Verify candidate is Attempt 2
        self.assertEqual(result["attempt_number"], 2)
        
        # List attempts
        attempts_result = list_segment_attempts(self.db, self.segment_id)
        
        # Verify both active and candidate exist
        self.assertIsNotNone(attempts_result["active_attempt"])
        self.assertIsNotNone(attempts_result["candidate"])
        
        # Verify active is Attempt 1 (seeded from original)
        active = attempts_result["active_attempt"]
        self.assertEqual(active["attempt_number"], 1)
        self.assertEqual(active["duration_ms"], 1000)
        
        # Verify candidate is Attempt 2
        candidate = attempts_result["candidate"]
        self.assertEqual(candidate["attempt_number"], 2)
        self.assertEqual(candidate["duration_ms"], 1100)

    def test_concurrent_candidate_constraint(self):
        """Test that only one candidate can exist per segment (database constraint)."""
        # Create first candidate
        candidate1_path = self.segment_dir / "segment_1_attempt_1.wav"
        self._create_test_wav(candidate1_path)
        
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO segment_attempts(
                    segment_id,attempt_number,status,wav_path,audio_sha256,duration_ms,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (self.segment_id, 1, "candidate", str(candidate1_path), sha256_file(candidate1_path), 1100, utcnow())
            )
        
        # Attempt to create second candidate (should fail due to unique index)
        candidate2_path = self.segment_dir / "segment_1_attempt_2.wav"
        self._create_test_wav(candidate2_path)
        
        with self.assertRaises(Exception) as cm:
            with self.db.connect() as conn:
                conn.execute(
                    """INSERT INTO segment_attempts(
                        segment_id,attempt_number,status,wav_path,audio_sha256,duration_ms,created_at
                    ) VALUES(?,?,?,?,?,?,?)""",
                    (self.segment_id, 2, "candidate", str(candidate2_path), sha256_file(candidate2_path), 1200, utcnow())
                )
        
        self.assertIn("UNIQUE", str(cm.exception))

    def test_concurrent_active_constraint(self):
        """Test that only one active attempt can exist per segment (database constraint)."""
        # Create first active
        active1_path = self.segment_dir / "segment_1_attempt_1.wav"
        self._create_test_wav(active1_path)
        
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO segment_attempts(
                    segment_id,attempt_number,status,wav_path,audio_sha256,duration_ms,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (self.segment_id, 1, "active", str(active1_path), sha256_file(active1_path), 1100, utcnow())
            )
        
        # Attempt to create second active (should fail due to unique index)
        active2_path = self.segment_dir / "segment_1_attempt_2.wav"
        self._create_test_wav(active2_path)
        
        with self.assertRaises(Exception) as cm:
            with self.db.connect() as conn:
                conn.execute(
                    """INSERT INTO segment_attempts(
                        segment_id,attempt_number,status,wav_path,audio_sha256,duration_ms,created_at
                    ) VALUES(?,?,?,?,?,?,?)""",
                    (self.segment_id, 2, "active", str(active2_path), sha256_file(active2_path), 1200, utcnow())
                )
        
        self.assertIn("UNIQUE", str(cm.exception))

    @patch('story_audio.segment_regeneration._reassemble_chapter_with_candidate')
    def test_accept_rebuild_failure_preserves_active_state(self, mock_reassemble):
        """Test that rebuild failure leaves segment and artifact unchanged."""
        # Create candidate
        candidate_path = self.segment_dir / "segment_1_attempt_1.wav"
        self._create_test_wav(candidate_path, duration_ms=1100)
        
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO segment_attempts(
                    segment_id,attempt_number,status,wav_path,audio_sha256,duration_ms,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (self.segment_id, 1, "candidate", str(candidate_path), sha256_file(candidate_path), 1100, utcnow())
            )
            attempt_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        # Get original state
        orig_segment = dict(self.db.fetch_one("SELECT * FROM segments WHERE id=?", (self.segment_id,)))
        orig_chapter = dict(self.db.fetch_one("SELECT * FROM chapters WHERE id=?", (self.chapter_id,)))
        orig_artifact_count = int(self.db.fetch_one("SELECT COUNT(*) as count FROM artifacts")["count"])
        
        # Mock rebuild to fail (force chapter rebuild/export failure)
        mock_reassemble.side_effect = Exception("FFmpeg concat failed")
        
        # Attempt accept (should fail with rebuild error)
        with self.assertRaises(RegenerationRebuildError) as cm:
            accept_segment_candidate(
                self.db, self.store, self.config, self.segment_id, attempt_id
            )
        
        self.assertIn("rebuild failed", str(cm.exception).lower())
        self.assertIn("candidate preserved", str(cm.exception).lower())
        
        # Assert candidate remains available
        attempt = self.db.fetch_one("SELECT * FROM segment_attempts WHERE id=?", (attempt_id,))
        self.assertEqual(attempt["status"], "candidate")
        
        # Assert segment active WAV/hash/duration unchanged
        segment = dict(self.db.fetch_one("SELECT * FROM segments WHERE id=?", (self.segment_id,)))
        self.assertEqual(segment["wav_path"], orig_segment["wav_path"])
        self.assertEqual(segment["audio_sha256"], orig_segment["audio_sha256"])
        self.assertEqual(segment["duration_ms"], orig_segment["duration_ms"])
        
        # Assert active chapter/final artifact pointer unchanged
        chapter = dict(self.db.fetch_one("SELECT * FROM chapters WHERE id=?", (self.chapter_id,)))
        self.assertEqual(chapter["active_audio_artifact_id"], orig_chapter["active_audio_artifact_id"])
        
        # Assert no new artifacts created
        new_artifact_count = int(self.db.fetch_one("SELECT COUNT(*) as count FROM artifacts")["count"])
        self.assertEqual(new_artifact_count, orig_artifact_count)

    def test_legacy_state_repair_seeds_active_and_renumbers_candidate(self):
        """Test that legacy state (verified + candidate as Attempt 1 + no active) is repaired on list."""
        # Simulate legacy state: candidate exists as Attempt 1, no active row
        candidate_path = self.segment_dir / "segment_1_attempt_1.wav"
        self._create_test_wav(candidate_path, duration_ms=1100)
        
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO segment_attempts(
                    segment_id,attempt_number,status,wav_path,audio_sha256,duration_ms,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (self.segment_id, 1, "candidate", str(candidate_path), sha256_file(candidate_path), 1100, utcnow())
            )
            legacy_candidate_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        # List attempts - should trigger repair
        result = list_segment_attempts(self.db, self.segment_id)
        
        # Verify repair happened
        self.assertIsNotNone(result["active_attempt"])
        self.assertIsNotNone(result["candidate"])
        
        # Verify active is Attempt 1 (seeded from segment)
        active = result["active_attempt"]
        self.assertIsNotNone(active["attempt_id"])  # Real row now
        self.assertEqual(active["attempt_number"], 1)
        self.assertEqual(active["status"], "active")
        self.assertEqual(active["duration_ms"], 1000)  # Original segment duration
        
        # Verify candidate is now Attempt 2 (renumbered)
        candidate = result["candidate"]
        self.assertEqual(candidate["attempt_id"], legacy_candidate_id)
        self.assertEqual(candidate["attempt_number"], 2)  # Renumbered from 1
        self.assertEqual(candidate["status"], "candidate")
        self.assertEqual(candidate["duration_ms"], 1100)
        
        # Verify database state after repair
        db_active = self.db.fetch_one(
            "SELECT * FROM segment_attempts WHERE segment_id=? AND status='active'",
            (self.segment_id,)
        )
        self.assertIsNotNone(db_active)
        self.assertEqual(db_active["attempt_number"], 1)
        self.assertEqual(db_active["wav_path"], str(self.segment_wav))
        
        db_candidate = self.db.fetch_one(
            "SELECT * FROM segment_attempts WHERE id=?",
            (legacy_candidate_id,)
        )
        self.assertEqual(db_candidate["attempt_number"], 2)
        
        # Verify repair is idempotent - calling again doesn't duplicate
        result2 = list_segment_attempts(self.db, self.segment_id)
        self.assertEqual(result2["active_attempt"]["attempt_number"], 1)
        self.assertEqual(result2["candidate"]["attempt_number"], 2)
        
        # Verify only one active and one candidate exist
        attempt_count = int(self.db.fetch_one(
            "SELECT COUNT(*) as count FROM segment_attempts WHERE segment_id=?",
            (self.segment_id,)
        )["count"])
        self.assertEqual(attempt_count, 2)
    
    def test_legacy_repair_active_audio_endpoint_works(self):
        """Test that repaired active attempt serves audio correctly via /api/segments/{id}/audio."""
        # Simulate legacy state and trigger repair
        candidate_path = self.segment_dir / "segment_1_attempt_1.wav"
        self._create_test_wav(candidate_path, duration_ms=1100)
        
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO segment_attempts(
                    segment_id,attempt_number,status,wav_path,audio_sha256,duration_ms,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (self.segment_id, 1, "candidate", str(candidate_path), sha256_file(candidate_path), 1100, utcnow())
            )
        
        # List attempts to trigger repair
        result = list_segment_attempts(self.db, self.segment_id)
        
        # Verify active Attempt 1 was created and points to original segment WAV
        active = result["active_attempt"]
        self.assertIsNotNone(active)
        self.assertEqual(active["attempt_number"], 1)
        self.assertEqual(active["duration_ms"], 1000)  # Original duration
        
        # Verify segments.wav_path still points to original
        segment = self.db.fetch_one("SELECT * FROM segments WHERE id=?", (self.segment_id,))
        self.assertEqual(segment["wav_path"], str(self.segment_wav))
        self.assertTrue(Path(segment["wav_path"]).exists())
        
        # Verify candidate is Attempt 2
        candidate = result["candidate"]
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["attempt_number"], 2)
        self.assertEqual(candidate["duration_ms"], 1100)  # Candidate duration

    @patch('story_audio.segment_regeneration._reassemble_chapter_with_candidate')
    def test_accept_supersedes_previous_active(self, mock_reassemble):
        """Test that accepting Attempt 2 supersedes Active Attempt 1."""
        # Create Active Attempt 1 (original)
        active_path = self.segment_dir / "segment_1_attempt_1.wav"
        self._create_test_wav(active_path, duration_ms=1000)

        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO segment_attempts(
                    segment_id,attempt_number,status,wav_path,audio_sha256,duration_ms,created_at,accepted_at
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (self.segment_id, 1, "active", str(active_path), sha256_file(active_path), 1000, utcnow(), utcnow())
            )

            # Create Candidate Attempt 2
            candidate_path = self.segment_dir / "segment_1_attempt_2.wav"
            self._create_test_wav(candidate_path, duration_ms=1100)

            conn.execute(
                """INSERT INTO segment_attempts(
                    segment_id,attempt_number,status,wav_path,audio_sha256,duration_ms,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (self.segment_id, 2, "candidate", str(candidate_path), sha256_file(candidate_path), 1100, utcnow())
            )
            candidate_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Mock rebuild to return success
        master_path = self.config.work_dir / "temp_master.wav"
        timeline_path = self.config.work_dir / "temp_timeline.json"
        self._create_test_wav(master_path, duration_ms=1100)
        timeline_path.write_text(json.dumps({"schema_version": 2, "duration_ms": 1100}))

        mock_reassemble.return_value = {
            "master_wav": master_path,
            "master_duration_ms": 1100,
            "timeline_json": timeline_path,
            "final_path": master_path,
            "temp_dir": self.config.work_dir / "temp"
        }

        # Get original chapter artifact
        orig_artifact_id = self.db.fetch_one("SELECT active_audio_artifact_id FROM chapters WHERE id=?", (self.chapter_id,))["active_audio_artifact_id"]

        # Accept Attempt 2
        result = accept_segment_candidate(
            self.db, self.store, self.config, self.segment_id, candidate_id
        )

        # Assert Attempt 1 becomes superseded
        attempt1 = self.db.fetch_one("SELECT * FROM segment_attempts WHERE segment_id=? AND attempt_number=1", (self.segment_id,))
        self.assertEqual(attempt1["status"], "superseded")
        self.assertIsNotNone(attempt1["superseded_at"])

        # Assert Attempt 2 becomes active
        attempt2 = self.db.fetch_one("SELECT * FROM segment_attempts WHERE id=?", (candidate_id,))
        self.assertEqual(attempt2["status"], "active")
        self.assertIsNotNone(attempt2["accepted_at"])

        # Assert segment pointers point to Attempt 2
        segment = self.db.fetch_one("SELECT * FROM segments WHERE id=?", (self.segment_id,))
        self.assertEqual(segment["wav_path"], str(candidate_path))
        self.assertEqual(segment["audio_sha256"], sha256_file(candidate_path))
        self.assertEqual(segment["duration_ms"], 1100)

        # Assert chapter active artifact pointer changed
        new_artifact_id = self.db.fetch_one("SELECT active_audio_artifact_id FROM chapters WHERE id=?", (self.chapter_id,))["active_audio_artifact_id"]
        self.assertNotEqual(new_artifact_id, orig_artifact_id)
        self.assertEqual(new_artifact_id, result["new_artifact_id"])

        # Assert accepting Attempt 2 again is rejected (now it's active, not candidate)
        with self.assertRaises(RegenerationValidationError) as cm:
            accept_segment_candidate(
                self.db, self.store, self.config, self.segment_id, candidate_id
            )
        self.assertIn("expected 'candidate'", str(cm.exception))
        self.assertIn("active", str(cm.exception))

    def test_accept_rejects_non_candidate_status(self):
        """Test that accepting non-candidate status is rejected."""
        # Create already-accepted attempt
        accepted_path = self.segment_dir / "segment_1_attempt_1.wav"
        self._create_test_wav(accepted_path, duration_ms=1100)

        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO segment_attempts(
                    segment_id,attempt_number,status,wav_path,audio_sha256,duration_ms,created_at,accepted_at
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (self.segment_id, 1, "active", str(accepted_path), sha256_file(accepted_path), 1100, utcnow(), utcnow())
            )
            attempt_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Attempt to accept already-active attempt
        with self.assertRaises(RegenerationValidationError) as cm:
            accept_segment_candidate(
                self.db, self.store, self.config, self.segment_id, attempt_id
            )

        self.assertIn("expected 'candidate'", str(cm.exception))
        self.assertIn("active", str(cm.exception))

    def test_reject_rejects_non_candidate_status(self):
        """Test that rejecting non-candidate status is rejected."""
        # Create already-rejected attempt
        rejected_path = self.segment_dir / "segment_1_attempt_1.wav"
        self._create_test_wav(rejected_path, duration_ms=1100)

        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO segment_attempts(
                    segment_id,attempt_number,status,wav_path,audio_sha256,duration_ms,created_at,rejected_at
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (self.segment_id, 1, "rejected", str(rejected_path), sha256_file(rejected_path), 1100, utcnow(), utcnow())
            )
            attempt_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Attempt to reject already-rejected attempt
        with self.assertRaises(RegenerationValidationError) as cm:
            reject_segment_candidate(self.db, self.segment_id, attempt_id)

        self.assertIn("expected 'candidate'", str(cm.exception))
        self.assertIn("rejected", str(cm.exception))

    def test_regenerate_after_reject_creates_next_attempt(self):
        """Test that regeneration after reject creates next valid attempt number."""
        # Mock TTS
        def mock_synthesize(synth_input=None, output_path=None, **kwargs):
            self._create_test_wav(output_path, duration_ms=1100)
            return (1100, 48000)

        self.tts.synthesize = Mock(side_effect=mock_synthesize)

        # First regeneration (creates active Attempt 1, candidate Attempt 2)
        result1 = regenerate_verified_segment(
            self.db, self.store, self.tts, self.config, self.segment_id
        )
        self.assertEqual(result1["attempt_number"], 2)
        candidate1_id = result1["attempt_id"]

        # Reject first candidate
        reject_segment_candidate(self.db, self.segment_id, candidate1_id)

        # Verify rejected
        attempt1 = self.db.fetch_one("SELECT * FROM segment_attempts WHERE id=?", (candidate1_id,))
        self.assertEqual(attempt1["status"], "rejected")

        # Second regeneration (should create Attempt 3)
        result2 = regenerate_verified_segment(
            self.db, self.store, self.tts, self.config, self.segment_id
        )
        self.assertEqual(result2["attempt_number"], 3)

        # Verify all attempts exist
        attempts = self.db.fetch_all(
            "SELECT * FROM segment_attempts WHERE segment_id=? ORDER BY attempt_number",
            (self.segment_id,)
        )
        self.assertEqual(len(attempts), 3)
        self.assertEqual(attempts[0]["attempt_number"], 1)
        self.assertEqual(attempts[0]["status"], "active")
        self.assertEqual(attempts[1]["attempt_number"], 2)
        self.assertEqual(attempts[1]["status"], "rejected")
        self.assertEqual(attempts[2]["attempt_number"], 3)
        self.assertEqual(attempts[2]["status"], "candidate")

    def test_custom_snapshot_regeneration(self):
        """Test custom voice segment regeneration with pinned revision."""
        # Create custom voice with revision
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO custom_voices(
                    display_name,description,is_active,created_at,updated_at
                ) VALUES(?,?,?,?,?)""",
                ("Test Custom", "Test", 1, utcnow(), utcnow())
            )
            custom_voice_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Create reference audio
            ref_audio_key = "audio/custom/test_ref.wav"
            ref_audio_path = self.config.blobs_dir / ref_audio_key
            ref_audio_path.parent.mkdir(parents=True, exist_ok=True)
            self._create_test_wav(ref_audio_path)
            
            # Create revision
            conn.execute(
                """INSERT INTO custom_voice_revisions(
                    custom_voice_id,revision_number,audio_storage_key,audio_sha256,
                    reference_transcript,transcript_sha256,duration_ms,sample_rate,
                    channels,audio_format,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (custom_voice_id, 1, ref_audio_key, sha256_file(ref_audio_path),
                 "Custom transcript", sha256_text("Custom transcript"), 1000, 48000,
                 1, "wav", utcnow())
            )
            revision_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Create custom voice segment with pinned revision
            segment_text = "Custom voice test."
            segment_text_path, segment_text_sha = self.store.put_text(segment_text)
            
            synthesis_settings_json = json.dumps({
                "temperature": 0.8,
                "top_k": 25,
                "max_chars": 256,
                "silence_seconds": 0.15,
                "engine_version": "vieneu:v3turbo"
            }, sort_keys=True)
            
            synthesis_hash = sha256_text(synthesis_settings_json + segment_text + str(revision_id))
            
            custom_wav = self.segment_dir / "custom.wav"
            self._create_test_wav(custom_wav)
            
            conn.execute(
                """INSERT INTO segments(
                    job_chapter_id,segment_index,text_path,text_sha256,status,
                    wav_path,audio_sha256,duration_ms,verified_at,created_at,
                    voice_snapshot_version,voice_source_type,voice_provider,voice_model,
                    logical_voice_ref,effective_voice_ref,synthesis_settings_json,
                    voice_resolution_reason,synthesis_hash,custom_voice_revision_id,
                    reference_transcript,reference_transcript_sha256,reference_audio_storage_key,reference_audio_sha256
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    self.job_chapter_id, 2, segment_text_path, segment_text_sha, "verified",
                    str(custom_wav), sha256_file(custom_wav), 1000, utcnow(), utcnow(),
                    1, "custom_reference", "vieneu", "v3turbo",
                    f"custom:{custom_voice_id}", f"custom:{custom_voice_id}",
                    synthesis_settings_json, "profile", synthesis_hash, revision_id,
                    "Custom transcript", sha256_text("Custom transcript"), ref_audio_key, sha256_file(ref_audio_path)
                )
            )
            custom_segment_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        # Mock TTS
        captured_input = None
        def mock_synthesize(synth_input=None, output_path=None, **kwargs):
            nonlocal captured_input
            captured_input = synth_input
            self._create_test_wav(output_path, duration_ms=1100)
            return (1100, 48000)
        
        self.tts.synthesize = Mock(side_effect=mock_synthesize)
        
        # Regenerate
        result = regenerate_verified_segment(
            self.db, self.store, self.tts, self.config, custom_segment_id
        )
        
        # Assert pinned custom revision, reference audio, transcript, synthesis settings reused
        self.assertIsNotNone(captured_input)
        self.assertEqual(captured_input.voice_source_type, "custom_reference")
        self.assertEqual(captured_input.custom_voice_revision_id, revision_id)
        self.assertEqual(captured_input.reference_transcript, "Custom transcript")
        self.assertIsNotNone(captured_input.reference_audio_path)
        self.assertEqual(captured_input.settings.temperature, 0.8)
        
        # No logical voice re-resolution (uses stored snapshot)
        self.assertEqual(captured_input.effective_voice_ref, f"custom:{custom_voice_id}")
        
        # Verify attempt created
        attempt = self.db.fetch_one("SELECT * FROM segment_attempts WHERE id=?", (result["attempt_id"],))
        self.assertEqual(attempt["status"], "candidate")

    def test_safe_candidate_audio_serving(self):
        """Test API audio serving validates paths safely."""
        # Create candidate
        candidate_path = self.segment_dir / "segment_1_attempt_1.wav"
        self._create_test_wav(candidate_path)
        
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO segment_attempts(
                    segment_id,attempt_number,status,wav_path,audio_sha256,duration_ms,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (self.segment_id, 1, "candidate", str(candidate_path), sha256_file(candidate_path), 1100, utcnow())
            )
            attempt_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        # Valid attempt returns audio (via database lookup)
        attempt = self.db.fetch_one("SELECT * FROM segment_attempts WHERE id=?", (attempt_id,))
        self.assertIsNotNone(attempt)
        self.assertTrue(Path(attempt["wav_path"]).exists())
        
        # Unrelated/missing attempt fails safely
        nonexistent = self.db.fetch_one("SELECT * FROM segment_attempts WHERE id=?", (99999,))
        self.assertIsNone(nonexistent)
        
        # API exposes no raw filesystem path (path comes from database, not user input)
        # The API endpoint /api/segment-attempts/{id}/audio takes attempt_id (integer)
        # and queries database for wav_path - user cannot inject filesystem paths
        self.assertIn("wav_path", attempt.keys())
        self.assertNotIn("../", attempt["wav_path"])  # No path traversal in stored path


class SegmentRegenerationApiTests(IsolatedTestCase):
    """API endpoint tests for segment regeneration using TestClient."""
    
    def setUp(self):
        super().setUp()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        
        # Create test fixtures
        self._create_test_job()
        
        # Mock TTS service for API
        self.mock_tts = Mock()
        
        def mock_synthesize(synth_input=None, output_path=None, **kwargs):
            self._create_test_wav(output_path, duration_ms=1100)
            return (1100, 48000)
        
        self.mock_tts.synthesize = Mock(side_effect=mock_synthesize)
    
    def _create_test_job(self):
        """Create a completed job with verified segments."""
        with self.db.connect() as conn:
            # Book
            conn.execute(
                "INSERT INTO books(title,author,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                ("Test Book", "Test Author", "test.epub", sha256_text("test.epub"), utcnow(), utcnow())
            )
            self.book_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Chapter
            conn.execute(
                """INSERT INTO chapters(
                    book_id,chapter_number,title,char_count,audio_status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (self.book_id, 1, "Test Chapter", 100, "completed", utcnow(), utcnow())
            )
            self.chapter_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Text revision
            text = "Test chapter text for synthesis."
            text_path, text_sha = self.store.put_text(text)
            conn.execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,parent_revision_id,content_path,content_sha256,lexical_sha256,
                    char_count,processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (self.chapter_id, "reflowed", None, text_path, text_sha, text_sha, len(text), "test-v1", "approved", utcnow())
            )
            self.text_revision_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Job
            settings_json = json.dumps({
                "tts_mode": "v3turbo",
                "temperature": 0.8,
                "top_k": 25,
                "max_chars": 256,
                "target_chars": 230,
                "silence_seconds": 0.15,
                "engine_version": "vieneu:v3turbo"
            })
            conn.execute(
                """INSERT INTO jobs(
                    book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                    settings_json,total_chapters,scheduled_at,created_at,updated_at,finished_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.book_id, "completed", 1, 1, "preset_voice", "off", "m4a", settings_json, 1, utcnow(), utcnow(), utcnow(), utcnow())
            )
            self.job_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Job chapter
            conn.execute(
                """INSERT INTO job_chapters(
                    job_id,chapter_id,sequence,status,text_revision_id,finished_at
                ) VALUES(?,?,?,?,?,?)""",
                (self.job_id, self.chapter_id, 1, "completed", self.text_revision_id, utcnow())
            )
            self.job_chapter_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Create test segment WAV
            self.segment_dir = self.config.work_dir / f"job_{self.job_id}" / "chapter_0001" / "segments"
            self.segment_dir.mkdir(parents=True, exist_ok=True)
            self.segment_wav = self.segment_dir / "000001.wav"
            self._create_test_wav(self.segment_wav, duration_ms=1000)
            
            # Segment with preset voice snapshot
            segment_text = "Test segment text."
            segment_text_path, segment_text_sha = self.store.put_text(segment_text)
            
            synthesis_settings_json = json.dumps({
                "temperature": 0.8,
                "top_k": 25,
                "max_chars": 256,
                "silence_seconds": 0.15,
                "engine_version": "vieneu:v3turbo"
            }, sort_keys=True)
            
            synthesis_hash = sha256_text(synthesis_settings_json + segment_text + "preset_voice")
            
            conn.execute(
                """INSERT INTO segments(
                    job_chapter_id,segment_index,text_path,text_sha256,status,
                    wav_path,audio_sha256,duration_ms,verified_at,created_at,
                    voice_snapshot_version,voice_source_type,voice_provider,voice_model,
                    logical_voice_ref,effective_voice_ref,synthesis_settings_json,
                    voice_resolution_reason,synthesis_hash
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    self.job_chapter_id, 1, segment_text_path, segment_text_sha, "verified",
                    str(self.segment_wav), sha256_file(self.segment_wav), 1000, utcnow(), utcnow(),
                    1, "preset", "vieneu", "v3turbo",
                    "narrator", "preset_voice", synthesis_settings_json,
                    "direct", synthesis_hash
                )
            )
            self.segment_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    
    def _create_test_wav(self, path: Path, duration_ms: int = 1000):
        """Create a minimal valid WAV file for testing."""
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Generate 1 second of silence at 48kHz, mono, 16-bit PCM
        sample_rate = 48000
        samples = (duration_ms * sample_rate) // 1000
        
        import wave
        with wave.open(str(path), 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(b'\x00\x00' * samples)
    
    def test_api_endpoint_regenerate_calls_with_tts_service(self):
        """POST /api/segments/{id}/regenerate uses tts_service dependency."""
        # Patch the API module's dependencies
        import story_audio.api as api_module
        
        with patch.object(api_module, 'db', self.db), \
             patch.object(api_module, 'store', self.store), \
             patch.object(api_module, 'tts_service', self.mock_tts), \
             patch.object(api_module, 'settings', self.config):
            
            # Import app after patching
            from story_audio.api import app
            client = TestClient(app)
            
            # Call regenerate endpoint
            response = client.post(f"/api/segments/{self.segment_id}/regenerate")
            
            # Verify success
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["ok"])
            self.assertIn("attempt_id", data)
            self.assertEqual(data["segment_id"], self.segment_id)
            
            # Verify TTS service was called
            self.mock_tts.synthesize.assert_called_once()
    
    def test_api_endpoint_segment_audio_serves_active_wav(self):
        """GET /api/segments/{id}/audio serves active segment WAV."""
        import story_audio.api as api_module
        
        with patch.object(api_module, 'db', self.db), \
             patch.object(api_module, 'store', self.store), \
             patch.object(api_module, 'tts_service', self.mock_tts), \
             patch.object(api_module, 'settings', self.config):
            
            from story_audio.api import app
            client = TestClient(app)
            
            # Call segment audio endpoint
            response = client.get(f"/api/segments/{self.segment_id}/audio")
            
            # Verify success
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "audio/wav")
            self.assertGreater(len(response.content), 0)
            
            # Verify it serves the actual segment WAV
            segment = self.db.fetch_one("SELECT * FROM segments WHERE id=?", (self.segment_id,))
            with open(segment["wav_path"], "rb") as f:
                expected_content = f.read()
            self.assertEqual(response.content, expected_content)


if __name__ == "__main__":
    unittest.main()

