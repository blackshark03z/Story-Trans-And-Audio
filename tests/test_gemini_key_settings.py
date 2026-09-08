from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import story_audio.api as api_module
import story_audio.config as config_module
from story_audio.config import Settings


class GeminiKeySettingsTests(unittest.TestCase):
    def test_append_preserves_existing_keys_deduplicates_and_round_robins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            settings = Settings(root=Path(tmp))
            first = settings.append_gemini_keys(["key-a", "key-b", "key-a"])
            self.assertEqual(first["added_count"], 2)
            self.assertEqual(first["duplicate_count"], 1)
            self.assertEqual(settings.gemini_key_file.read_text(encoding="utf-8").splitlines(), ["key-a", "key-b"])

            second = settings.append_gemini_keys(["key-b", "key-c"])
            self.assertEqual(second["added_count"], 1)
            self.assertEqual(second["duplicate_count"], 1)
            self.assertEqual(settings.gemini_keys(), ["key-a", "key-b", "key-c"])
            self.assertEqual(settings.gemini_key_file.read_text(encoding="utf-8").splitlines(), ["key-a", "key-b", "key-c"])

            config_module._GEMINI_KEY_CURSOR = 0
            self.assertEqual([settings.gemini_key() for _ in range(5)], ["key-a", "key-b", "key-c", "key-a", "key-b"])

    def test_environment_key_is_not_duplicated_into_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"GEMINI_API_KEY": "env-key"}, clear=False):
            settings = Settings(root=Path(tmp))
            result = settings.append_gemini_keys(["env-key", "file-key"])
            self.assertEqual(result["added_count"], 1)
            self.assertEqual(result["duplicate_count"], 1)
            self.assertEqual(settings.gemini_keys(), ["env-key", "file-key"])
            self.assertEqual(settings.gemini_key_file.read_text(encoding="utf-8").splitlines(), ["file-key"])

    def test_tts_probe_loads_provider_and_reports_voice_count(self) -> None:
        class FakeTts:
            status = "not_loaded"
            error = None
            def provider_available(self) -> bool: return True
            def ensure_loaded(self): self.status = "ready"; return object()
            def voices(self): return [{"id": "voice-a"}, {"id": "voice-b"}]
        fake = FakeTts()
        with patch.object(api_module, "tts_service", fake):
            result = api_module.probe_tts_provider()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["voice_count"], 2)
        self.assertTrue(result["provider_available"])

    def test_api_append_response_never_echoes_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            settings = Settings(root=Path(tmp))
            with patch.object(api_module, "settings", settings):
                result = api_module.append_gemini_keys(api_module.GeminiKeysAppendRequest(keys=["secret-one", "secret-two", "secret-one"]))
            self.assertEqual(result["added_count"], 2)
            self.assertEqual(result["duplicate_count"], 1)
            serialized = repr(result)
            self.assertNotIn("secret-one", serialized)
            self.assertNotIn("secret-two", serialized)
            self.assertEqual(result["total_count"], 2)


if __name__ == "__main__":
    unittest.main()
