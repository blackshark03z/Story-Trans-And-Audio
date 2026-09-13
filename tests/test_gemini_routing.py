from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import story_audio.config as config_module
from story_audio.config import Settings
from story_audio.gemini_routing import call_gemini_with_fallback


class GeminiRoutingTests(unittest.TestCase):
    def _settings(self, root: Path, keys: list[str]) -> Settings:
        settings = Settings(root=root, gemini_model="gemini-3.8-flash")
        settings.append_gemini_keys(keys)
        config_module._GEMINI_KEY_CURSOR = 0
        return settings

    def test_default_model_chain_is_38_then_37_36_35(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "", "GEMINI_FALLBACK_MODELS": ""},
            clear=False,
        ):
            settings = Settings(root=Path(tmp), gemini_model="gemini-3.8-flash")
            self.assertEqual(
                settings.gemini_models(),
                [
                    "gemini-3.8-flash",
                    "gemini-3.7-flash",
                    "gemini-3.6-flash",
                    "gemini-3.5-flash",
                ],
            )

    def test_custom_model_stays_pinned_without_explicit_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "", "GEMINI_FALLBACK_MODELS": ""},
            clear=False,
        ):
            settings = Settings(root=Path(tmp), gemini_model="fixture-model")
            self.assertEqual(settings.gemini_models(), ["fixture-model"])

    def test_401_advances_to_next_key_without_changing_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "", "GEMINI_FALLBACK_MODELS": ""},
            clear=False,
        ):
            settings = self._settings(Path(tmp), ["bad-key", "good-key"])
            calls: list[tuple[str, str]] = []

            def provider(*, api_key: str, model: str, request_data):
                calls.append((api_key, model))
                if api_key == "bad-key":
                    raise RuntimeError("Gemini HTTP 401: unauthenticated")
                return {"ok": True, "request": request_data}

            result = call_gemini_with_fallback(
                settings,
                provider,
                request_data={"target": 1},
            )
            self.assertEqual(result.model, "gemini-3.8-flash")
            self.assertEqual(result.attempt_count, 2)
            self.assertEqual([model for _key, model in calls], ["gemini-3.8-flash"] * 2)
            self.assertEqual(result.value["ok"], True)

    def test_model_404_descends_to_37(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "", "GEMINI_FALLBACK_MODELS": ""},
            clear=False,
        ):
            settings = self._settings(Path(tmp), ["key-a"])
            models: list[str] = []

            def provider(*, api_key: str, model: str, request_data):
                models.append(model)
                if model == "gemini-3.8-flash":
                    raise RuntimeError("Gemini HTTP 404: model unavailable")
                return {"model": model}

            result = call_gemini_with_fallback(
                settings,
                provider,
                request_data={},
            )
            self.assertEqual(result.model, "gemini-3.7-flash")
            self.assertEqual(models, ["gemini-3.8-flash", "gemini-3.7-flash"])

    def test_all_401_keys_stop_without_wasting_model_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "", "GEMINI_FALLBACK_MODELS": ""},
            clear=False,
        ):
            settings = self._settings(Path(tmp), ["bad-a", "bad-b"])
            models: list[str] = []

            def provider(*, api_key: str, model: str, request_data):
                models.append(model)
                raise RuntimeError("Gemini HTTP 401: unauthenticated")

            with self.assertRaisesRegex(RuntimeError, "401"):
                call_gemini_with_fallback(settings, provider, request_data={})
            self.assertEqual(models, ["gemini-3.8-flash", "gemini-3.8-flash"])

    def test_unknown_provider_failure_remains_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "", "GEMINI_FALLBACK_MODELS": ""},
            clear=False,
        ):
            settings = self._settings(Path(tmp), ["key-a"])

            def provider(*, api_key: str, model: str, request_data):
                raise ValueError("semantic contract failed")

            with self.assertRaisesRegex(ValueError, "semantic contract"):
                call_gemini_with_fallback(settings, provider, request_data={})


if __name__ == "__main__":
    unittest.main()
