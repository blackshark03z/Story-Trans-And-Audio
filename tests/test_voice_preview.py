from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from pathlib import Path

from story_audio.custom_voice import CustomVoiceRepository
from story_audio.db import Database
from story_audio.storage import ContentStore
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

        # Build fake content based on call type
        if "voice" in kwargs:
            content = f"fake-wav:{kwargs['voice']}:{kwargs['text']}"
        elif "reference_audio_path" in kwargs:
            content = f"fake-custom-wav:{kwargs['reference_audio_path']}:{kwargs['reference_transcript']}:{kwargs['text']}"
        else:
            content = f"fake-wav:{kwargs['text']}"

        output_path.write_bytes(content.encode("utf-8"))
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

    # Preset regression tests
    def test_preset_construction_without_custom_dependencies_still_works(self) -> None:
        config = make_config(self.temp_root)
        fake = FakePreviewTts()
        # Old constructor signature still works
        service = VoicePreviewService(fake, config)
        result = service.create("voice-a")
        self.assertFalse(result["cache_hit"])
        self.assertEqual(result["voice_id"], "voice-a")
        self.assertEqual(len(fake.calls), 1)

    # Dependency validation
    def test_create_custom_fails_when_dependencies_not_configured(self) -> None:
        config = make_config(self.temp_root)
        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config)  # No custom deps
        with self.assertRaisesRegex(RuntimeError, "CustomVoiceRepository and ContentStore"):
            service.create_custom(1)

    def test_production_style_constructor_accepts_injected_dependencies(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)
        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)
        self.assertIsNotNone(service.custom_voice_repo)
        self.assertIsNotNone(service.store)

    # Revision identity
    def test_custom_preview_uses_exact_revision_id(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        # Create custom voice and revision
        voice = repo.create_custom_voice("Test Voice")
        audio_bytes = b"fake-audio-data"
        revision = repo.create_revision(voice.id, audio_bytes, "Test transcript")

        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        result = service.create_custom(revision.id)
        self.assertEqual(result["custom_voice_id"], voice.id)
        self.assertEqual(result["custom_voice_revision_id"], revision.id)
        self.assertFalse(result["cache_hit"])

    def test_different_revision_ids_produce_different_cache_keys(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        rev1 = repo.create_revision(voice.id, b"audio1", "transcript1")
        rev2 = repo.create_revision(voice.id, b"audio2", "transcript2")

        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        result1 = service.create_custom(rev1.id)
        result2 = service.create_custom(rev2.id)

        self.assertNotEqual(result1["cache_key"], result2["cache_key"])

    def test_preset_and_custom_identities_do_not_collide(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"audio", "transcript")

        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        preset_result = service.create("voice-a")
        custom_result = service.create_custom(revision.id)

        self.assertNotEqual(preset_result["cache_key"], custom_result["cache_key"])

    # Cache behavior
    def test_custom_preview_first_call_is_cache_miss(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"audio", "transcript")

        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        result = service.create_custom(revision.id)
        self.assertFalse(result["cache_hit"])
        self.assertEqual(len(fake.calls), 1)

    def test_custom_preview_second_identical_call_is_cache_hit(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"audio", "transcript")

        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        first = service.create_custom(revision.id)
        second = service.create_custom(revision.id)

        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(first["cache_key"], second["cache_key"])
        self.assertEqual(len(fake.calls), 1)

    def test_custom_preview_identity_includes_custom_voice_id(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"audio", "transcript")

        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        result = service.create_custom(revision.id)
        manifest = json.loads(
            (config.preview_cache_dir / f"{result['cache_key']}.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["custom_voice_id"], voice.id)
        self.assertEqual(result["custom_voice_id"], voice.id)

    def test_legacy_custom_preview_manifest_without_voice_id_is_quarantined(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"audio", "transcript")

        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)
        result = service.create_custom(revision.id)
        self.assertFalse(result["cache_hit"])

        old_key = "a" * 64
        current_wav = config.preview_cache_dir / f"{result['cache_key']}.wav"
        legacy_wav = config.preview_cache_dir / f"{old_key}.wav"
        legacy_manifest = config.preview_cache_dir / f"{old_key}.json"
        legacy_wav.write_bytes(current_wav.read_bytes())
        legacy = json.loads(
            (config.preview_cache_dir / f"{result['cache_key']}.json").read_text(encoding="utf-8")
        )
        legacy.pop("custom_voice_id")
        legacy["cache_key"] = old_key
        legacy_manifest.write_text(json.dumps(legacy), encoding="utf-8")

        with self.assertRaises(FileNotFoundError):
            service.audio_path(old_key)

        second = service.create_custom(revision.id)
        self.assertTrue(second["cache_hit"])
        self.assertEqual(len(fake.calls), 1)

    def test_custom_cache_hit_does_not_reread_source_blob(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"audio", "transcript")

        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        # First call reads source
        first = service.create_custom(revision.id)

        # Corrupt the source audio
        audio_path = store.absolute(revision.audio_storage_key)
        audio_path.write_bytes(b"corrupted")

        # Second call should be cache hit and not fail
        second = service.create_custom(revision.id)
        self.assertTrue(second["cache_hit"])

    def test_missing_custom_manifest_is_cache_miss(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"audio", "transcript")

        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        first = service.create_custom(revision.id)

        # Remove manifest
        manifest_path = config.preview_cache_dir / f"{first['cache_key']}.json"
        manifest_path.unlink()

        second = service.create_custom(revision.id)
        self.assertFalse(second["cache_hit"])
        self.assertEqual(len(fake.calls), 2)

    def test_missing_custom_generated_wav_is_cache_miss(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"audio", "transcript")

        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        first = service.create_custom(revision.id)

        # Remove WAV
        wav_path = config.preview_cache_dir / f"{first['cache_key']}.wav"
        wav_path.unlink()

        second = service.create_custom(revision.id)
        self.assertFalse(second["cache_hit"])

    def test_generated_wav_hash_mismatch_is_safe_miss(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"audio", "transcript")

        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        first = service.create_custom(revision.id)

        # Corrupt generated WAV
        wav_path = config.preview_cache_dir / f"{first['cache_key']}.wav"
        wav_path.write_bytes(b"corrupted")

        second = service.create_custom(revision.id)
        self.assertFalse(second["cache_hit"])

    def test_malformed_custom_manifest_is_safe_miss(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"audio", "transcript")

        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        first = service.create_custom(revision.id)

        # Corrupt manifest
        manifest_path = config.preview_cache_dir / f"{first['cache_key']}.json"
        manifest_path.write_text("invalid json", encoding="utf-8")

        second = service.create_custom(revision.id)
        self.assertFalse(second["cache_hit"])

    def test_cleanup_supports_both_preset_and_custom_manifests(self) -> None:
        config = replace(make_config(self.temp_root), preview_cache_retention_days=1)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"audio", "transcript")

        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        preset = service.create("voice-a")
        custom = service.create_custom(revision.id)

        # Age both
        old_time = time.time() - (2 * 86400)
        for cache_key in [preset["cache_key"], custom["cache_key"]]:
            for suffix in (".wav", ".json"):
                os.utime(config.preview_cache_dir / f"{cache_key}{suffix}", (old_time, old_time))

        result = service.cleanup()
        self.assertEqual(result["removed"], 2)
        self.assertEqual(result["remaining"], 0)

    # Source integrity
    def test_missing_revision_raises_custom_voice_revision_not_found_error(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        from story_audio.custom_voice import CustomVoiceRevisionNotFoundError
        with self.assertRaises(CustomVoiceRevisionNotFoundError):
            service.create_custom(999)

    def test_missing_managed_audio_raises_storage_resolution_error(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"audio", "transcript")

        # Remove managed audio
        audio_path = store.absolute(revision.audio_storage_key)
        audio_path.unlink()

        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        from story_audio.synthesis_snapshot import StorageResolutionError
        with self.assertRaisesRegex(StorageResolutionError, "does not exist"):
            service.create_custom(revision.id)

        self.assertEqual(len(fake.calls), 0)

    def test_reference_audio_sha_mismatch_rejected_before_synthesis(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"audio", "transcript")

        # Corrupt managed audio
        audio_path = store.absolute(revision.audio_storage_key)
        audio_path.write_bytes(b"corrupted")

        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        from story_audio.synthesis_snapshot import StorageResolutionError
        with self.assertRaisesRegex(StorageResolutionError, "SHA-256 mismatch"):
            service.create_custom(revision.id)

        self.assertEqual(len(fake.calls), 0)

    def test_empty_transcript_rejected_before_synthesis(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)

        # Manually create invalid revision in DB
        from story_audio.db import utcnow
        from story_audio.files import sha256_bytes

        now = utcnow()
        audio_bytes = b"audio"
        audio_sha = sha256_bytes(audio_bytes)
        audio_key = store.put_audio(audio_bytes, audio_sha)

        with db.transaction() as conn:
            voice_id = conn.execute(
                "INSERT INTO custom_voices(display_name,is_active,created_at,updated_at) VALUES(?,1,?,?)",
                ("Test", now, now)
            ).lastrowid

            # Invalid: empty transcript
            revision_id = conn.execute(
                """INSERT INTO custom_voice_revisions(
                    custom_voice_id,revision_number,audio_storage_key,audio_sha256,
                    reference_transcript,transcript_sha256,duration_ms,sample_rate,
                    channels,audio_format,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (voice_id, 1, audio_key, audio_sha, "", "sha", 1000, 48000, 2, "wav", now)
            ).lastrowid

        repo = CustomVoiceRepository(db, store)
        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        with self.assertRaisesRegex(ValueError, "empty reference_transcript"):
            service.create_custom(revision_id)

        self.assertEqual(len(fake.calls), 0)

    def test_transcript_sha_mismatch_rejected_before_synthesis(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)

        # Manually create invalid revision
        from story_audio.db import utcnow
        from story_audio.files import sha256_bytes, sha256_text

        now = utcnow()
        audio_bytes = b"audio"
        audio_sha = sha256_bytes(audio_bytes)
        audio_key = store.put_audio(audio_bytes, audio_sha)

        # Valid SHA format but wrong hash
        wrong_sha = sha256_text("wrong transcript")

        with db.transaction() as conn:
            voice_id = conn.execute(
                "INSERT INTO custom_voices(display_name,is_active,created_at,updated_at) VALUES(?,1,?,?)",
                ("Test", now, now)
            ).lastrowid

            # Mismatched transcript SHA
            revision_id = conn.execute(
                """INSERT INTO custom_voice_revisions(
                    custom_voice_id,revision_number,audio_storage_key,audio_sha256,
                    reference_transcript,transcript_sha256,duration_ms,sample_rate,
                    channels,audio_format,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (voice_id, 1, audio_key, audio_sha, "transcript", wrong_sha, 1000, 48000, 2, "wav", now)
            ).lastrowid

        repo = CustomVoiceRepository(db, store)
        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        with self.assertRaisesRegex(ValueError, "transcript SHA-256 mismatch"):
            service.create_custom(revision_id)

        self.assertEqual(len(fake.calls), 0)

    def test_invalid_revision_metadata_rejected(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)

        # Manually create revision with invalid metadata
        from story_audio.db import utcnow

        now = utcnow()
        with db.transaction() as conn:
            voice_id = conn.execute(
                "INSERT INTO custom_voices(display_name,is_active,created_at,updated_at) VALUES(?,1,?,?)",
                ("Test", now, now)
            ).lastrowid

            # Invalid: empty audio_storage_key
            revision_id = conn.execute(
                """INSERT INTO custom_voice_revisions(
                    custom_voice_id,revision_number,audio_storage_key,audio_sha256,
                    reference_transcript,transcript_sha256,duration_ms,sample_rate,
                    channels,audio_format,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (voice_id, 1, "", "sha", "transcript", "sha", 1000, 48000, 2, "wav", now)
            ).lastrowid

        repo = CustomVoiceRepository(db, store)
        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        with self.assertRaisesRegex(ValueError, "invalid audio_storage_key"):
            service.create_custom(revision_id)

    # Output and cleanup
    def test_custom_short_duration_accepted(self) -> None:
        """Custom preview accepts valid short audio (2-5 seconds)."""
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"audio", "transcript")

        # 3-second audio should be accepted for custom preview
        fake = FakePreviewTts(duration_ms=3_000)
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        result = service.create_custom(revision.id, preview_text="Short text")

        self.assertFalse(result["cache_hit"])
        self.assertEqual(result["custom_voice_revision_id"], revision.id)
        self.assertEqual(result["duration_ms"], 3_000)
        # Valid cache entry created
        self.assertEqual(len(list(config.preview_cache_dir.glob("*.json"))), 1)

    def test_custom_zero_duration_rejected(self) -> None:
        """Custom preview rejects zero-duration audio."""
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"audio", "transcript")

        fake = FakePreviewTts(duration_ms=0)
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        with self.assertRaisesRegex(ValueError, "greater than zero"):
            service.create_custom(revision.id)

        # No valid cache entry left
        self.assertEqual(len(list(config.preview_cache_dir.glob("*.json"))), 0)

    def test_custom_duration_above_maximum_rejected(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"audio", "transcript")

        fake = FakePreviewTts(duration_ms=21_000)
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        with self.assertRaisesRegex(ValueError, "must not exceed.*20"):
            service.create_custom(revision.id)

        self.assertEqual(len(list(config.preview_cache_dir.glob("*.json"))), 0)

    def test_custom_tts_failure_removes_partial_artifacts(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"audio", "transcript")

        class FailingTts:
            def synthesize(self, **kwargs):
                output_path = kwargs["output_path"]
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"partial")
                raise RuntimeError("Synthesis failed")

        service = VoicePreviewService(FailingTts(), config, custom_voice_repo=repo, store=store)

        with self.assertRaises(RuntimeError):
            service.create_custom(revision.id)

        # No artifacts left
        self.assertEqual(len(list(config.preview_cache_dir.glob("*.wav"))), 0)
        self.assertEqual(len(list(config.preview_cache_dir.glob("*.json"))), 0)

    def test_successful_custom_manifest_and_wav_atomic(self) -> None:
        config = make_config(self.temp_root)
        db = Database(config.db_path)
        db.initialize()
        store = ContentStore(config)
        repo = CustomVoiceRepository(db, store)

        voice = repo.create_custom_voice("Test Voice")
        revision = repo.create_revision(voice.id, b"audio", "transcript")

        fake = FakePreviewTts()
        service = VoicePreviewService(fake, config, custom_voice_repo=repo, store=store)

        result = service.create_custom(revision.id)

        # Both files exist
        wav_path = config.preview_cache_dir / f"{result['cache_key']}.wav"
        manifest_path = config.preview_cache_dir / f"{result['cache_key']}.json"

        self.assertTrue(wav_path.exists())
        self.assertTrue(manifest_path.exists())

        # Manifest has correct audio_sha256
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        from story_audio.files import sha256_file
        self.assertEqual(manifest["audio_sha256"], sha256_file(wav_path))


if __name__ == "__main__":
    import unittest
    unittest.main()
