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
    """Verify IsolatedTestCase environment isolation mechanism.

    These tests directly verify that IsolatedTestCase properly restores
    environment variables to their exact prior state, including:
    - absent (None)
    - set to "1"
    - set to empty string ""

    We test the isolation mechanism directly rather than relying on
    unittest execution order.
    """

    def test_isolated_test_case_restores_absent_variables(self) -> None:
        """IsolatedTestCase restores variables that were absent before setUp."""
        # Ensure variables are absent
        os.environ.pop("STORY_AUDIO_TESTING", None)
        os.environ.pop("STORY_AUDIO_ALLOW_LIVE_DB", None)

        # Create and run lifecycle
        test = IsolatedTestCase()
        test.setUp()

        # Verify setUp set STORY_AUDIO_TESTING=1
        self.assertEqual(os.environ.get("STORY_AUDIO_TESTING"), "1")

        # Run tearDown
        test.tearDown()

        # Verify variables are absent again
        self.assertIsNone(os.environ.get("STORY_AUDIO_TESTING"),
                         "STORY_AUDIO_TESTING should be absent after tearDown")
        self.assertIsNone(os.environ.get("STORY_AUDIO_ALLOW_LIVE_DB"),
                         "STORY_AUDIO_ALLOW_LIVE_DB should be absent after tearDown")

    def test_isolated_test_case_restores_set_variables(self) -> None:
        """IsolatedTestCase restores variables that were set to '1' before setUp."""
        # Set variables to specific values
        os.environ["STORY_AUDIO_TESTING"] = "1"
        os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = "1"

        # Create and run lifecycle
        test = IsolatedTestCase()
        test.setUp()

        # Verify setUp still has STORY_AUDIO_TESTING=1 (same value)
        self.assertEqual(os.environ.get("STORY_AUDIO_TESTING"), "1")

        # Modify during test to simulate test body
        os.environ["STORY_AUDIO_TESTING"] = "modified"
        os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = "modified"

        # Run tearDown
        test.tearDown()

        # Verify variables restored to original "1"
        self.assertEqual(os.environ.get("STORY_AUDIO_TESTING"), "1",
                        "STORY_AUDIO_TESTING should be restored to '1'")
        self.assertEqual(os.environ.get("STORY_AUDIO_ALLOW_LIVE_DB"), "1",
                        "STORY_AUDIO_ALLOW_LIVE_DB should be restored to '1'")

    def test_isolated_test_case_restores_empty_string_variables(self) -> None:
        """IsolatedTestCase restores variables that were empty string before setUp."""
        # Set variables to empty string (edge case for truthiness)
        os.environ["STORY_AUDIO_TESTING"] = ""
        os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = ""

        # Create and run lifecycle
        test = IsolatedTestCase()
        test.setUp()

        # Verify setUp set STORY_AUDIO_TESTING=1 (overrides empty string)
        self.assertEqual(os.environ.get("STORY_AUDIO_TESTING"), "1")

        # Run tearDown
        test.tearDown()

        # Verify variables restored to empty string (not absent)
        self.assertEqual(os.environ.get("STORY_AUDIO_TESTING"), "",
                        "STORY_AUDIO_TESTING should be restored to empty string")
        self.assertEqual(os.environ.get("STORY_AUDIO_ALLOW_LIVE_DB"), "",
                        "STORY_AUDIO_ALLOW_LIVE_DB should be restored to empty string")

    def tearDown(self) -> None:
        """Clean up environment after each test."""
        # Ensure we don't leak our test setup to other tests
        os.environ.pop("STORY_AUDIO_TESTING", None)
        os.environ.pop("STORY_AUDIO_ALLOW_LIVE_DB", None)
        super().tearDown()


if __name__ == "__main__":
    unittest.main()
