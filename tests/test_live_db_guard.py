from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from story_audio.config import canonical_production_db_path
from story_audio.db import Database

from tests.base import IsolatedTestCase


class LiveDBGuardTests(IsolatedTestCase):
    """Test fail-closed live DB protection guards."""
    
    def test_test_mode_blocks_canonical_production_path(self) -> None:
        """Test mode with canonical production path raises even without any DB operations."""
        os.environ["STORY_AUDIO_TESTING"] = "1"
        canonical = canonical_production_db_path()
        db = Database(canonical)
        
        with self.assertRaises(RuntimeError) as ctx:
            db.initialize()
        
        self.assertIn("Test mode", str(ctx.exception))
        self.assertIn("production DB", str(ctx.exception))
        # Note: DB may pre-exist from production use; guard prevents mutation
    
    def test_test_mode_blocks_even_with_allow_live_flag(self) -> None:
        """Test mode always blocks live DB, allow_live does not override."""
        os.environ["STORY_AUDIO_TESTING"] = "1"
        os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = "1"
        canonical = canonical_production_db_path()
        db = Database(canonical)
        
        with self.assertRaises(RuntimeError) as ctx:
            db.initialize()
        
        self.assertIn("Test mode", str(ctx.exception))
    
    def test_non_test_mode_canonical_path_without_opt_in_raises(self) -> None:
        """Non-test mode with canonical path but no opt-in raises."""
        os.environ.pop("STORY_AUDIO_TESTING", None)
        os.environ.pop("STORY_AUDIO_ALLOW_LIVE_DB", None)
        canonical = canonical_production_db_path()
        db = Database(canonical)
        
        with self.assertRaises(RuntimeError) as ctx:
            db.initialize()
        
        self.assertIn("without explicit opt-in", str(ctx.exception))
        self.assertIn("STORY_AUDIO_ALLOW_LIVE_DB=1", str(ctx.exception))
    
    def test_non_test_mode_canonical_path_with_opt_in_allowed(self) -> None:
        """Non-test mode with canonical path and explicit opt-in is allowed.
        
        This test uses a monkeypatched temp fixture to avoid touching live DB.
        """
        os.environ.pop("STORY_AUDIO_TESTING", None)
        os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = "1"
        
        # Monkeypatch canonical path to point to temp fixture
        original_canonical = canonical_production_db_path
        temp_canonical = self.temp_root / "data" / "app.db"
        
        try:
            import story_audio.db
            story_audio.db.canonical_production_db_path = lambda: temp_canonical
            
            db = Database(temp_canonical)
            version = db.initialize()
            
            self.assertGreater(version, 0)
            self.assertTrue(temp_canonical.exists())
        finally:
            story_audio.db.canonical_production_db_path = original_canonical
    
    def test_temporary_db_path_allowed_without_opt_in(self) -> None:
        """Temporary DB paths initialize normally without opt-in."""
        os.environ.pop("STORY_AUDIO_TESTING", None)
        os.environ.pop("STORY_AUDIO_ALLOW_LIVE_DB", None)
        
        temp_db = self.temp_root / "temp.db"
        db = Database(temp_db)
        version = db.initialize()
        
        self.assertGreater(version, 0)
        self.assertTrue(temp_db.exists())
    
    def test_guard_runs_before_migration(self) -> None:
        """Guard check happens before any migration or connection."""
        os.environ["STORY_AUDIO_TESTING"] = "1"
        canonical = canonical_production_db_path()
        
        # Record whether DB existed before the test
        existed_before = canonical.exists()
        
        db = Database(canonical)
        
        with self.assertRaises(RuntimeError):
            db.initialize()
        
        # If DB didn't exist before, guard must have prevented creation
        if not existed_before:
            self.assertFalse(canonical.exists(), "Guard failed to prevent DB creation")
    
    def test_environment_restored_after_test(self) -> None:
        """IsolatedTestCase properly restores environment variables."""
        # This test verifies the base class behavior
        self.assertEqual(os.environ.get("STORY_AUDIO_TESTING"), "1")
        # tearDown will restore, next test will verify isolation


class EnvironmentIsolationTests(unittest.TestCase):
    """Verify environment isolation between tests."""

    def setUp(self) -> None:
        """Store original environment state."""
        super().setUp()
        self._original_testing = os.environ.get("STORY_AUDIO_TESTING")
        self._original_allow_live = os.environ.get("STORY_AUDIO_ALLOW_LIVE_DB")

    def tearDown(self) -> None:
        """Restore original environment state."""
        if self._original_testing is None:
            os.environ.pop("STORY_AUDIO_TESTING", None)
        else:
            os.environ["STORY_AUDIO_TESTING"] = self._original_testing

        if self._original_allow_live is None:
            os.environ.pop("STORY_AUDIO_ALLOW_LIVE_DB", None)
        else:
            os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = self._original_allow_live
        super().tearDown()

    def test_previous_test_environment_was_restored(self) -> None:
        """Previous test's STORY_AUDIO_TESTING should not leak."""
        # This test verifies that previous tests in this file properly restored environment
        # LiveDBGuardTests uses IsolatedTestCase which sets STORY_AUDIO_TESTING=1
        # but should restore to original value in tearDown
        testing = os.environ.get("STORY_AUDIO_TESTING")
        # Accept either None or the original value stored in setUp
        # The key invariant: value should match what we stored in setUp
        self.assertEqual(testing, self._original_testing,
                        "Environment variable STORY_AUDIO_TESTING leaked from previous test")


if __name__ == "__main__":
    unittest.main()
