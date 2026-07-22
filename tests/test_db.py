from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from story_audio.config import canonical_production_db_path
from story_audio.db import Database


class DatabaseGuardTests(unittest.TestCase):
    def test_initialize_blocks_canonical_path_in_test_mode(self) -> None:
        original_testing = os.environ.get("STORY_AUDIO_TESTING")
        original_allow_live = os.environ.get("STORY_AUDIO_ALLOW_LIVE_DB")
        try:
            os.environ["STORY_AUDIO_TESTING"] = "1"
            os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = "1"
            with self.assertRaises(RuntimeError):
                Database(canonical_production_db_path()).initialize()
        finally:
            if original_testing is None:
                os.environ.pop("STORY_AUDIO_TESTING", None)
            else:
                os.environ["STORY_AUDIO_TESTING"] = original_testing
            if original_allow_live is None:
                os.environ.pop("STORY_AUDIO_ALLOW_LIVE_DB", None)
            else:
                os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = original_allow_live

    def test_temporary_path_initializes_normally_in_test_mode(self) -> None:
        original_testing = os.environ.get("STORY_AUDIO_TESTING")
        try:
            os.environ["STORY_AUDIO_TESTING"] = "1"
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "app.db"
                self.assertNotEqual(path.resolve(), canonical_production_db_path().resolve())
                self.assertEqual(Database(path).initialize(), 12)
        finally:
            if original_testing is None:
                os.environ.pop("STORY_AUDIO_TESTING", None)
            else:
                os.environ["STORY_AUDIO_TESTING"] = original_testing


if __name__ == "__main__":
    unittest.main()
