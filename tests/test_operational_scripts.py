from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from story_audio.db import Database, canonical_production_db_path
from tests.base import IsolatedTestCase


class TestOperationalScripts(IsolatedTestCase):
    """Test operational scripts respect live DB guard with --allow-live-db flag."""

    def test_import_character_bible_flag_sets_env_var(self):
        """import_character_bible --allow-live-db sets STORY_AUDIO_ALLOW_LIVE_DB=1."""
        bible_content = json.dumps({
            "$schema": "https://example.com/story-audio-character-bible/v1",
            "records": [
                {"canonical_name": "Test Character", "aliases": ["TC"]}
            ]
        }, ensure_ascii=False)
        bible_file = self.temp_root / "test_bible.json"
        bible_file.write_text(bible_content, encoding="utf-8")
        
        db = Database(self.config.db_path)
        db.initialize()
        with db.transaction() as conn:
            book_id = conn.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,datetime('now'),datetime('now'))",
                ("Test Book", "test://path", "abc123", 1)
            ).lastrowid
        
        original_allow = os.environ.pop("STORY_AUDIO_ALLOW_LIVE_DB", None)
        try:
            # Temporarily disable test mode for this check
            original_testing = os.environ.pop("STORY_AUDIO_TESTING", None)
            try:
                with patch("story_audio.tts.tts_service") as mock_tts:
                    mock_tts.voices.return_value = []
                    with patch("sys.argv", ["import_character_bible.py", "--book-id", str(book_id), "--file", str(bible_file), "--dry-run", "--allow-live-db"]):
                        # Verify flag sets the env var
                        self.assertIsNone(os.environ.get("STORY_AUDIO_ALLOW_LIVE_DB"))
                        from scripts.import_character_bible import main as import_main
                        import_main()
                        self.assertEqual(os.environ.get("STORY_AUDIO_ALLOW_LIVE_DB"), "1")
            finally:
                if original_testing:
                    os.environ["STORY_AUDIO_TESTING"] = original_testing
        finally:
            if original_allow is not None:
                os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = original_allow
            else:
                os.environ.pop("STORY_AUDIO_ALLOW_LIVE_DB", None)

    def test_speaker_assignment_draft_flag_sets_env_var(self):
        """speaker_assignment_draft --allow-live-db sets STORY_AUDIO_ALLOW_LIVE_DB=1."""
        db = Database(self.config.db_path)
        db.initialize()
        with db.transaction() as conn:
            book_id = conn.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,datetime('now'),datetime('now'))",
                ("Test Book", "test://path", "abc123", 1)
            ).lastrowid
            chapter_id = conn.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at) VALUES(?,?,?,?,datetime('now'),datetime('now'))",
                (book_id, 1, "Chapter 1", 100)
            ).lastrowid
            conn.execute(
                "INSERT INTO text_revisions(chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,processor_version,status,created_at) VALUES(?,?,?,?,?,?,?,?,datetime('now'))",
                (chapter_id, "reflowed", "blobs/text/ab/abc123.txt", "abc123", "lex123", 100, "v1", "approved")
            )
        
        original_allow = os.environ.pop("STORY_AUDIO_ALLOW_LIVE_DB", None)
        original_testing = os.environ.pop("STORY_AUDIO_TESTING", None)
        try:
            with patch("story_audio.config.settings") as mock_settings:
                mock_settings.db_path = self.config.db_path
                mock_settings.ensure_dirs = MagicMock()
                with patch("story_audio.speaker_assignment.generate_speaker_assignment_draft") as mock_gen:
                    mock_gen.return_value = {"status": "success"}
                    with patch("sys.argv", ["speaker_assignment_draft.py", "--chapter-id", str(chapter_id), "--allow-live-db"]):
                        self.assertIsNone(os.environ.get("STORY_AUDIO_ALLOW_LIVE_DB"))
                        from scripts.speaker_assignment_draft import main as speaker_main
                        speaker_main()
                        self.assertEqual(os.environ.get("STORY_AUDIO_ALLOW_LIVE_DB"), "1")
        finally:
            if original_allow is not None:
                os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = original_allow
            else:
                os.environ.pop("STORY_AUDIO_ALLOW_LIVE_DB", None)
            if original_testing:
                os.environ["STORY_AUDIO_TESTING"] = original_testing

    def test_smoke_multivoice_flag_sets_env_var(self):
        """smoke_multivoice --allow-live-db sets STORY_AUDIO_ALLOW_LIVE_DB=1."""
        db = Database(self.config.db_path)
        db.initialize()
        
        original_allow = os.environ.pop("STORY_AUDIO_ALLOW_LIVE_DB", None)
        original_testing = os.environ.pop("STORY_AUDIO_TESTING", None)
        try:
            with patch("story_audio.config.settings") as mock_settings:
                mock_settings.db_path = self.config.db_path
                mock_settings.data_dir = self.config.data_dir
                mock_settings.work_dir = self.config.work_dir
                mock_settings.tts_max_chars = 256
                mock_settings.ensure_dirs = MagicMock()
                with patch("story_audio.tts.tts_service") as mock_tts:
                    mock_tts.voices.return_value = [
                        {"id": f"voice{i}", "name": f"Voice {i}"} for i in range(4)
                    ]
                    with patch("sys.argv", ["smoke_multivoice.py", "--allow-live-db", "--skip-retry"]):
                        self.assertIsNone(os.environ.get("STORY_AUDIO_ALLOW_LIVE_DB"))
                        from scripts.smoke_multivoice import main as smoke_main
                        try:
                            smoke_main()
                        except Exception:
                            pass  # May fail for other reasons, we just check env var
                        self.assertEqual(os.environ.get("STORY_AUDIO_ALLOW_LIVE_DB"), "1")
        finally:
            if original_allow is not None:
                os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = original_allow
            else:
                os.environ.pop("STORY_AUDIO_ALLOW_LIVE_DB", None)
            if original_testing:
                os.environ["STORY_AUDIO_TESTING"] = original_testing

    def test_db_guard_blocks_without_flag(self):
        """Database.initialize() blocks canonical path without STORY_AUDIO_ALLOW_LIVE_DB."""
        # Temporarily disable test mode
        original_testing = os.environ.pop("STORY_AUDIO_TESTING", None)
        original_allow = os.environ.pop("STORY_AUDIO_ALLOW_LIVE_DB", None)
        try:
            with patch("story_audio.db.canonical_production_db_path") as mock_canonical:
                mock_canonical.return_value = self.config.db_path
                db = Database(self.config.db_path)
                with self.assertRaises(RuntimeError) as cm:
                    db.initialize()
                self.assertIn("without explicit opt-in", str(cm.exception))
                self.assertIn("--allow-live-db", str(cm.exception))
        finally:
            if original_testing:
                os.environ["STORY_AUDIO_TESTING"] = original_testing
            if original_allow:
                os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = original_allow

    def test_db_guard_allows_with_flag(self):
        """Database.initialize() allows canonical path with STORY_AUDIO_ALLOW_LIVE_DB=1."""
        original_testing = os.environ.pop("STORY_AUDIO_TESTING", None)
        original_allow = os.environ.get("STORY_AUDIO_ALLOW_LIVE_DB")
        try:
            os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = "1"
            with patch("story_audio.db.canonical_production_db_path") as mock_canonical:
                mock_canonical.return_value = self.config.db_path
                db = Database(self.config.db_path)
                db.initialize()  # Should not raise
                self.assertGreater(db.schema_version(), 0)
        finally:
            if original_testing:
                os.environ["STORY_AUDIO_TESTING"] = original_testing
            if original_allow:
                os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = original_allow
            else:
                os.environ.pop("STORY_AUDIO_ALLOW_LIVE_DB", None)

    def test_test_mode_always_blocks(self):
        """STORY_AUDIO_TESTING=1 blocks even with STORY_AUDIO_ALLOW_LIVE_DB=1."""
        os.environ["STORY_AUDIO_TESTING"] = "1"
        os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = "1"
        try:
            with patch("story_audio.db.canonical_production_db_path") as mock_canonical:
                mock_canonical.return_value = self.config.db_path
                db = Database(self.config.db_path)
                with self.assertRaises(RuntimeError) as cm:
                    db.initialize()
                self.assertIn("Test mode", str(cm.exception))
        finally:
            os.environ.pop("STORY_AUDIO_ALLOW_LIVE_DB", None)

    def test_read_only_script_does_not_require_flag(self):
        """Read-only scripts like doctor.py should not require --allow-live-db."""
        db = Database(self.config.db_path)
        db.initialize()
        
        # doctor.py only reads, doesn't call initialize() on a new DB
        # Patch settings to use test config so doctor reads from the initialized test DB
        with patch("story_audio.config.settings", self.config):
            with patch("story_audio.integrity.Database") as mock_db_class:
                # Make Database class return the already-initialized test DB
                mock_db_class.return_value = db
                
                with patch("sys.argv", ["doctor.py"]):
                    # Import doctor after patching to pick up test config
                    import importlib
                    if 'scripts.doctor' in sys.modules:
                        importlib.reload(sys.modules['scripts.doctor'])
                    from scripts.doctor import main as doctor_main
                    
                    try:
                        result = doctor_main()
                        self.assertIsInstance(result, int)
                    except RuntimeError as e:
                        # Should NOT be the live DB guard error
                        self.assertNotIn("without explicit opt-in", str(e))


if __name__ == "__main__":
    unittest.main()
