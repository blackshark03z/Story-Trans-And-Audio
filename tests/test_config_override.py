"""
Tests for STORY_AUDIO_DATA_DIR environment variable override.

Ensures the configuration respects the environment variable for isolated testing
while preserving default behavior when unset.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path


class TestConfigOverride(unittest.TestCase):
    """Tests for data directory override behavior."""
    
    def setUp(self):
        """Save original environment and clear config cache."""
        self.original_env = os.environ.get("STORY_AUDIO_DATA_DIR")
        self.original_testing = os.environ.get("STORY_AUDIO_TESTING")
        
        # Remove config module to force reimport
        if "story_audio.config" in sys.modules:
            del sys.modules["story_audio.config"]
    
    def tearDown(self):
        """Restore original environment."""
        if self.original_env is None:
            os.environ.pop("STORY_AUDIO_DATA_DIR", None)
        else:
            os.environ["STORY_AUDIO_DATA_DIR"] = self.original_env
        
        if self.original_testing is None:
            os.environ.pop("STORY_AUDIO_TESTING", None)
        else:
            os.environ["STORY_AUDIO_TESTING"] = self.original_testing
        
        # Clear config cache
        if "story_audio.config" in sys.modules:
            del sys.modules["story_audio.config"]
    
    def test_default_behavior_when_unset(self):
        """When STORY_AUDIO_DATA_DIR is unset, use default repository data directory."""
        os.environ.pop("STORY_AUDIO_DATA_DIR", None)
        
        from story_audio.config import settings, ROOT
        
        self.assertEqual(settings.data_dir, ROOT / "data")
        self.assertEqual(settings.db_path, ROOT / "data" / "app.db")
        self.assertEqual(settings.blobs_dir, ROOT / "data" / "blobs")
        self.assertEqual(settings.output_dir, ROOT / "data" / "output")
        self.assertEqual(settings.work_dir, ROOT / "data" / "work")
    
    def test_override_points_to_custom_directory(self):
        """When STORY_AUDIO_DATA_DIR is set, resolve all mutable paths under it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["STORY_AUDIO_DATA_DIR"] = tmpdir
            
            from story_audio.config import settings
            
            tmp_path = Path(tmpdir).resolve()
            self.assertEqual(settings.data_dir, tmp_path)
            self.assertEqual(settings.db_path, tmp_path / "app.db")
            self.assertEqual(settings.blobs_dir, tmp_path / "blobs")
            self.assertEqual(settings.output_dir, tmp_path / "output")
            self.assertEqual(settings.work_dir, tmp_path / "work")
    
    def test_override_resolves_to_absolute_path(self):
        """Relative paths in STORY_AUDIO_DATA_DIR are resolved to absolute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a subdirectory to use as relative path within same drive
            test_dir = Path(tmpdir) / "isolated_data"
            test_dir.mkdir()
            
            # Change to temp dir and use relative path
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                os.environ["STORY_AUDIO_DATA_DIR"] = "isolated_data"
                
                from story_audio.config import settings
                
                # Should be resolved to absolute
                self.assertTrue(settings.data_dir.is_absolute())
                self.assertEqual(settings.data_dir, test_dir.resolve())
            finally:
                os.chdir(original_cwd)
    
    def test_empty_override_raises_error(self):
        """Empty STORY_AUDIO_DATA_DIR value raises ValueError."""
        os.environ["STORY_AUDIO_DATA_DIR"] = ""
        
        with self.assertRaises(ValueError) as cm:
            import story_audio.config
        
        self.assertIn("cannot be empty", str(cm.exception))
    
    def test_whitespace_only_override_raises_error(self):
        """Whitespace-only STORY_AUDIO_DATA_DIR value raises ValueError."""
        os.environ["STORY_AUDIO_DATA_DIR"] = "   "
        
        with self.assertRaises(ValueError) as cm:
            import story_audio.config
        
        self.assertIn("cannot be empty", str(cm.exception))
    
    def test_static_paths_remain_in_source_tree(self):
        """UI and source paths remain in application root when data is overridden."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["STORY_AUDIO_DATA_DIR"] = tmpdir
            
            from story_audio.config import settings, ROOT
            
            # Static paths stay in source tree
            self.assertEqual(settings.root, ROOT)
            self.assertEqual(settings.log_dir, ROOT / "logs")


if __name__ == "__main__":
    unittest.main()
