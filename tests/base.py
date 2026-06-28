from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from story_audio.config import Settings


class IsolatedTestCase(unittest.TestCase):
    """Base test case with isolated temporary filesystem and test mode enforcement.
    
    Automatically:
    - Creates a temporary root directory for each test
    - Provides a Settings instance pointing to the temp directory
    - Sets STORY_AUDIO_TESTING=1 to prevent live DB access
    - Cleans up the temp directory and restores environment after each test
    """
    
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_root = Path(self.temp_dir.name)
        
        # Store original environment
        self._original_testing = os.environ.get("STORY_AUDIO_TESTING")
        self._original_allow_live = os.environ.get("STORY_AUDIO_ALLOW_LIVE_DB")
        
        # Set test mode
        os.environ["STORY_AUDIO_TESTING"] = "1"
        
        # Create isolated config pointing to temp directory
        self.config = replace(
            Settings(),
            root=self.temp_root,
            data_dir=self.temp_root / "data",
            db_path=self.temp_root / "data" / "app.db",
            blobs_dir=self.temp_root / "data" / "blobs",
            output_dir=self.temp_root / "data" / "output",
            work_dir=self.temp_root / "data" / "work",
            log_dir=self.temp_root / "logs",
        )
    
    def tearDown(self) -> None:
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
