from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from pathlib import Path

from story_audio.voice_preview import PREVIEW_TEXT, VoicePreviewService
from tests.base import IsolatedTestCase
from tests.test_recovery import make_config

class FakePreviewTts:
    def __init__(self, duration_ms: int = 15_000):
        self.calls: list[dict] = []
        self.duration_ms = duration_ms

    def synthesize(self, **kwargs):
        self.calls.append(kwargs)
        output_path = kwargs["output_path"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(f"fake-wav:{kwargs['voice']}:{kwargs['text']}".encode("utf-8"))
        return self.duration_ms, 48_000

class VoicePreviewTests(IsolatedTestCase):
    def test_preview_is_cached_by_complete_identity_without_database(self) -> None:
        config = make_config(self.temp_root)
        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config)

        first = service.create("voice-a")
        second = service.create("voice-a")

        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(first["cache_key"], second["cache_key"])
        self.assertEqual(len(fake.calls), 1)
        self.assertFalse(config.db_path.exists())
        manifest = json.loads(
            (config.preview_cache_dir / f"{first['cache_key']}.json").read_text(encoding="utf-8")
        )
        for key in ("voice_id", "preview_text_sha256", "settings_hash", "engine_version"):
            self.assertTrue(manifest[key])
        self.assertEqual(first["duration_ms"], 15_000)
        self.assertLessEqual(len(PREVIEW_TEXT), config.tts_max_chars)

    def test_different_voice_or_settings_produce_different_cache_keys(self) -> None:
        config = make_config(self.temp_root)
        fake = FakePreviewTts()
        first = VoicePreviewService(fake, config).create("voice-a")
        second = VoicePreviewService(fake, config).create("voice-b")
        changed = replace(config, tts_temperature=config.tts_temperature + 0.1)
        third = VoicePreviewService(fake, changed).create("voice-a")
        self.assertEqual(len({first["cache_key"], second["cache_key"], third["cache_key"]}), 3)

    def test_corrupted_cache_is_not_reused(self) -> None:
        config = make_config(self.temp_root)
        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config)
        first = service.create("voice-a")
        wav = config.preview_cache_dir / f"{first['cache_key']}.wav"
        wav.write_bytes(b"corrupted")
        result = service.create("voice-a")
        self.assertFalse(result["cache_hit"])
        self.assertEqual(len(fake.calls), 2)

    def test_cleanup_removes_only_expired_preview_entries(self) -> None:
        config = replace(make_config(self.temp_root), preview_cache_retention_days=1)
        service = VoicePreviewService(FakePreviewTts(), config)
        old = service.create("old-voice")
        current = service.create("current-voice")
        old_time = time.time() - (2 * 86400)
        for suffix in (".wav", ".json"):
            os.utime(config.preview_cache_dir / f"{old['cache_key']}{suffix}", (old_time, old_time))
        result = service.cleanup()
        self.assertEqual(result["removed"], 1)
        self.assertFalse((config.preview_cache_dir / f"{old['cache_key']}.wav").exists())
        self.assertTrue((config.preview_cache_dir / f"{current['cache_key']}.wav").exists())

    def test_preview_outside_duration_contract_is_rejected(self) -> None:
        config = make_config(self.temp_root)
        service = VoicePreviewService(FakePreviewTts(duration_ms=9_000), config)
        with self.assertRaisesRegex(ValueError, "10–20 seconds"):
            service.create("voice-a")
        self.assertEqual(list(config.preview_cache_dir.glob("*.wav")), [])

if __name__ == "__main__":
    import unittest
    unittest.main()