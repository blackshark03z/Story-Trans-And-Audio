from __future__ import annotations

import unittest
from unittest.mock import patch

import story_audio.api as api_module
from story_audio.custom_voice import CustomVoiceRepository
from story_audio.custom_voice_api import build_voice_catalog_handler
from story_audio.db import Database
from story_audio.storage import ContentStore
from story_audio.voice_ref import CustomVoiceContext
from story_audio.voice_profile import set_book_voice_profile
from tests.base import IsolatedTestCase


def tiny_wav(seed: bytes = b"") -> bytes:
    return (
        b"RIFF" + (36 + len(seed)).to_bytes(4, "little") + b"WAVE"
        + b"fmt " + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (22050).to_bytes(4, "little")
        + (44100).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data" + len(seed).to_bytes(4, "little")
        + seed
    )


class VoiceCatalogContractTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        self.repo = CustomVoiceRepository(self.db, self.store)

    def test_catalog_normalizes_presets_and_selectable_custom_voices(self) -> None:
        voice = self.repo.create_custom_voice("Duc Tri", "clear commander")
        rev1 = self.repo.create_revision(voice.id, tiny_wav(b"a"), "one")
        rev2 = self.repo.create_revision(voice.id, tiny_wav(b"bb"), "two")
        self.repo.set_preferred_synthesis_revision(voice.id, rev1.id)

        catalog = build_voice_catalog_handler(
            self.repo,
            [{"id": "preset-a", "label": "Preset A"}, {"id": "preset-a", "label": "Duplicate"}],
        )
        items = {item["assignment_key"]: item for item in catalog["items"]}

        self.assertEqual(list(items).count("preset-a"), 1)
        self.assertEqual(items["preset-a"]["source_kind"], "preset")
        self.assertTrue(items["preset-a"]["selectable"])
        self.assertEqual(items[f"custom:{voice.id}"]["source_kind"], "custom")
        self.assertTrue(items[f"custom:{voice.id}"]["selectable"])
        self.assertEqual(items[f"custom:{voice.id}"]["effective_synthesis_revision_id"], rev1.id)
        self.assertEqual(items[f"custom:{voice.id}"]["effective_revision_number"], rev1.revision_number)
        self.assertIn("preferred", items[f"custom:{voice.id}"]["provenance_summary"])
        self.assertNotEqual(items[f"custom:{voice.id}"]["effective_synthesis_revision_id"], rev2.id)

    def test_catalog_falls_back_to_latest_when_no_preferred_revision(self) -> None:
        voice = self.repo.create_custom_voice("Latest Voice")
        self.repo.create_revision(voice.id, tiny_wav(b"a"), "one")
        latest = self.repo.create_revision(voice.id, tiny_wav(b"bb"), "two")

        items = {
            item["assignment_key"]: item
            for item in build_voice_catalog_handler(self.repo, [])["items"]
        }

        self.assertEqual(items[f"custom:{voice.id}"]["effective_synthesis_revision_id"], latest.id)
        self.assertEqual(items[f"custom:{voice.id}"]["effective_revision_source"], "latest")

    def test_inactive_and_revisionless_custom_voices_are_not_newly_selectable(self) -> None:
        inactive = self.repo.create_custom_voice("Inactive")
        self.repo.create_revision(inactive.id, tiny_wav(b"a"), "one")
        self.repo.deactivate_custom_voice(inactive.id)
        empty = self.repo.create_custom_voice("No Revision")

        items = {
            item["assignment_key"]: item
            for item in build_voice_catalog_handler(self.repo, [])["items"]
        }

        self.assertFalse(items[f"custom:{inactive.id}"]["selectable"])
        self.assertIn("inactive", items[f"custom:{inactive.id}"]["unavailability_reason"])
        self.assertFalse(items[f"custom:{empty.id}"]["selectable"])
        self.assertIn("no usable", items[f"custom:{empty.id}"]["unavailability_reason"])

    def test_api_endpoint_returns_read_only_catalog(self) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO books(title, author, source_path, source_sha256, created_at, updated_at) "
                "VALUES(?,?,?,?,datetime('now'),datetime('now'))",
                ("Book", "Author", "/fake.epub", "0" * 64),
            )
        voice = self.repo.create_custom_voice("API Voice")
        self.repo.create_revision(voice.id, tiny_wav(b"a"), "one")
        before = dict(self.db.fetch_one("SELECT COUNT(*) AS jobs FROM jobs"))

        with patch.object(api_module, "db", self.db), patch.object(api_module, "custom_voice_repo", self.repo):
            with patch.object(api_module.tts_service, "voices", return_value=[{"id": "preset", "label": "Preset"}]):
                payload = api_module.voice_catalog()

        after = dict(self.db.fetch_one("SELECT COUNT(*) AS jobs FROM jobs"))
        self.assertEqual(before, after)
        keys = {item["assignment_key"] for item in payload["items"]}
        self.assertIn("preset", keys)
        self.assertIn(f"custom:{voice.id}", keys)

    def test_read_profile_validation_accepts_usable_custom_voice(self) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO books(title, author, source_path, source_sha256, created_at, updated_at) "
                "VALUES(?,?,?,?,datetime('now'),datetime('now'))",
                ("Book", "Author", "/fake.epub", "0" * 64),
            )
        voice = self.repo.create_custom_voice("Profile Voice")
        self.repo.create_revision(voice.id, tiny_wav(b"a"), "one")
        custom_ref = f"custom:{voice.id}"
        set_book_voice_profile(
            self.db,
            1,
            narrator_voice_id=custom_ref,
            male_dialogue_voice_id="male",
            female_dialogue_voice_id="female",
            allowed_voice_ids={"male", "female"},
            custom_voice_context=CustomVoiceContext.from_repository(self.repo),
        )

        with patch.object(api_module, "db", self.db), patch.object(api_module, "custom_voice_repo", self.repo):
            with patch.object(api_module, "_preset_voice_ids", return_value={"male", "female"}):
                payload = api_module.read_book_voice_profile(1)

        self.assertTrue(payload["valid"])
        self.assertEqual(payload["missing_preset_ids"], [])
        self.assertEqual(payload["profile"]["narrator_voice_id"], custom_ref)

    def test_add_character_api_accepts_usable_custom_override(self) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO books(title, author, source_path, source_sha256, created_at, updated_at) "
                "VALUES(?,?,?,?,datetime('now'),datetime('now'))",
                ("Book", "Author", "/fake.epub", "0" * 64),
            )
        voice = self.repo.create_custom_voice("Character Voice")
        self.repo.create_revision(voice.id, tiny_wav(b"a"), "one")
        custom_ref = f"custom:{voice.id}"

        with patch.object(api_module, "db", self.db), patch.object(api_module, "custom_voice_repo", self.repo):
            result = api_module.add_character(
                1,
                api_module.CharacterCreateRequest(
                    display_name="Character",
                    voice_override_id=custom_ref,
                    gender="male",
                ),
            )

        self.assertEqual(result["voice_override_id"], custom_ref)
        self.assertEqual(result["default_voice_id"], custom_ref)


if __name__ == "__main__":
    unittest.main()
