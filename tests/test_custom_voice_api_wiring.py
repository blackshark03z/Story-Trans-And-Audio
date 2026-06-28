"""
Test Custom Voice API wiring for voice profiles, character overrides, and casting.

Verifies that custom voices can be saved and used through all normal UI paths.
"""
import unittest
from tests.base import IsolatedTestCase
from story_audio.db import Database
from story_audio.storage import ContentStore
from story_audio.custom_voice import CustomVoiceRepository, AudioValidator
from story_audio.voice_profile import (
    set_book_voice_profile,
    get_book_voice_profile,
    set_character_voice_override,
    resolve_voice,
)
from story_audio.voice_ref import CustomVoiceContext
from story_audio.casting import create_character


class TestCustomVoiceProfileWiring(IsolatedTestCase):
    """Test custom voice integration in Book Voice Profile."""

    def setUp(self):
        super().setUp()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        self.repo = CustomVoiceRepository(self.db, self.store)
        self.validator = AudioValidator()

        # Create test book
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO books(title, author, source_path, source_sha256, created_at, updated_at) VALUES(?, ?, ?, ?, datetime('now'), datetime('now'))",
                ("Test Book", "Test Author", "/fake/test.epub", "0" * 64),
            )
        self.book_id = 1

        # Create a custom voice with revision
        self._create_custom_voice_with_revision()

    def _create_custom_voice_with_revision(self):
        """Helper to create a custom voice with a usable revision."""
        # Create custom voice
        voice = self.repo.create_custom_voice("Test Custom Voice", "Test description")
        self.custom_voice_id = voice.id

        # Create a minimal valid audio file
        audio_data = b"RIFF" + (36).to_bytes(4, "little") + b"WAVE"
        audio_data += b"fmt " + (16).to_bytes(4, "little")
        audio_data += (1).to_bytes(2, "little")  # PCM
        audio_data += (1).to_bytes(2, "little")  # Mono
        audio_data += (22050).to_bytes(4, "little")  # Sample rate
        audio_data += (44100).to_bytes(4, "little")  # Byte rate
        audio_data += (2).to_bytes(2, "little")  # Block align
        audio_data += (16).to_bytes(2, "little")  # Bits per sample
        audio_data += b"data" + (0).to_bytes(4, "little")

        # Create revision
        transcript = "Test transcript for custom voice"
        self.repo.create_revision(
            self.custom_voice_id, audio_data, transcript
        )

    def test_save_custom_narrator(self):
        """Active Custom Voice can be saved as narrator."""
        context = CustomVoiceContext.from_repository(self.repo)
        custom_ref = f"custom:{self.custom_voice_id}"

        result = set_book_voice_profile(
            self.db,
            self.book_id,
            narrator_voice_id=custom_ref,
            male_dialogue_voice_id="preset_male",
            female_dialogue_voice_id="preset_female",
            allowed_voice_ids={"preset_male", "preset_female"},
            custom_voice_context=context,
        )

        self.assertEqual(result["narrator_voice_id"], custom_ref)

    def test_save_custom_male_dialogue(self):
        """Active Custom Voice can be saved as male dialogue."""
        context = CustomVoiceContext.from_repository(self.repo)
        custom_ref = f"custom:{self.custom_voice_id}"

        result = set_book_voice_profile(
            self.db,
            self.book_id,
            narrator_voice_id="preset_narrator",
            male_dialogue_voice_id=custom_ref,
            female_dialogue_voice_id="preset_female",
            allowed_voice_ids={"preset_narrator", "preset_female"},
            custom_voice_context=context,
        )

        self.assertEqual(result["male_dialogue_voice_id"], custom_ref)

    def test_save_custom_female_dialogue(self):
        """Active Custom Voice can be saved as female dialogue."""
        context = CustomVoiceContext.from_repository(self.repo)
        custom_ref = f"custom:{self.custom_voice_id}"

        result = set_book_voice_profile(
            self.db,
            self.book_id,
            narrator_voice_id="preset_narrator",
            male_dialogue_voice_id="preset_male",
            female_dialogue_voice_id=custom_ref,
            allowed_voice_ids={"preset_narrator", "preset_male"},
            custom_voice_context=context,
        )

        self.assertEqual(result["female_dialogue_voice_id"], custom_ref)

    def test_profile_persistence(self):
        """Re-reading the profile returns the saved custom:<id>."""
        context = CustomVoiceContext.from_repository(self.repo)
        custom_ref = f"custom:{self.custom_voice_id}"

        set_book_voice_profile(
            self.db,
            self.book_id,
            narrator_voice_id=custom_ref,
            male_dialogue_voice_id="preset_male",
            female_dialogue_voice_id="preset_female",
            allowed_voice_ids={"preset_male", "preset_female"},
            custom_voice_context=context,
        )

        # Re-read
        profile = get_book_voice_profile(self.db, self.book_id)
        self.assertEqual(profile["narrator_voice_id"], custom_ref)

    def test_inactive_custom_voice_rejected(self):
        """Inactive Custom Voice is rejected."""
        context = CustomVoiceContext.from_repository(self.repo)

        # Deactivate the custom voice
        self.repo.deactivate_custom_voice(self.custom_voice_id)

        # Build new context (should exclude deactivated voice)
        context = CustomVoiceContext.from_repository(self.repo)
        custom_ref = f"custom:{self.custom_voice_id}"

        with self.assertRaises(Exception) as cm:
            set_book_voice_profile(
                self.db,
                self.book_id,
                narrator_voice_id=custom_ref,
                male_dialogue_voice_id="preset_male",
                female_dialogue_voice_id="preset_female",
                allowed_voice_ids={"preset_male", "preset_female"},
                custom_voice_context=context,
            )
        self.assertIn("unavailable", str(cm.exception).lower())

    def test_missing_custom_voice_rejected(self):
        """Missing Custom Voice is rejected."""
        context = CustomVoiceContext.from_repository(self.repo)
        invalid_ref = "custom:99999"

        with self.assertRaises(Exception) as cm:
            set_book_voice_profile(
                self.db,
                self.book_id,
                narrator_voice_id=invalid_ref,
                male_dialogue_voice_id="preset_male",
                female_dialogue_voice_id="preset_female",
                allowed_voice_ids={"preset_male", "preset_female"},
                custom_voice_context=context,
            )
        self.assertIn("unavailable", str(cm.exception).lower())

    def test_preset_only_unchanged(self):
        """Preset-only flows remain unchanged."""
        # Should work without custom_voice_context
        result = set_book_voice_profile(
            self.db,
            self.book_id,
            narrator_voice_id="preset_narrator",
            male_dialogue_voice_id="preset_male",
            female_dialogue_voice_id="preset_female",
            allowed_voice_ids={"preset_narrator", "preset_male", "preset_female"},
            custom_voice_context=None,
        )

        self.assertEqual(result["narrator_voice_id"], "preset_narrator")


class TestCustomVoiceCharacterOverride(IsolatedTestCase):
    """Test custom voice integration in Character Override."""

    def setUp(self):
        super().setUp()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        self.repo = CustomVoiceRepository(self.db, self.store)
        self.validator = AudioValidator()

        # Create test book
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO books(title, author, source_path, source_sha256, created_at, updated_at) VALUES(?, ?, ?, ?, datetime('now'), datetime('now'))",
                ("Test Book", "Test Author", "/fake/test.epub", "0" * 64),
            )
        self.book_id = 1

        # Create character
        self.character = create_character(
            self.db, self.book_id, "Test Character", "main"
        )
        self.character_id = self.character["id"]

        # Create custom voice with revision
        voice = self.repo.create_custom_voice("Test Custom Voice", "Test description")
        self.custom_voice_id = voice.id

        audio_data = b"RIFF" + (36).to_bytes(4, "little") + b"WAVE"
        audio_data += b"fmt " + (16).to_bytes(4, "little")
        audio_data += (1).to_bytes(2, "little")  # PCM
        audio_data += (1).to_bytes(2, "little")  # Mono
        audio_data += (22050).to_bytes(4, "little")  # Sample rate
        audio_data += (44100).to_bytes(4, "little")  # Byte rate
        audio_data += (2).to_bytes(2, "little")  # Block align
        audio_data += (16).to_bytes(2, "little")  # Bits per sample
        audio_data += b"data" + (0).to_bytes(4, "little")

        self.repo.create_revision(
            self.custom_voice_id, audio_data, "Test transcript"
        )

    def test_character_override_accepts_custom_voice(self):
        """Character override accepts an active Custom Voice."""
        context = CustomVoiceContext.from_repository(self.repo)
        custom_ref = f"custom:{self.custom_voice_id}"

        result = set_character_voice_override(
            self.db,
            self.character_id,
            custom_ref,
            allowed_voice_ids=set(),
            custom_voice_context=context,
        )

        self.assertEqual(result["voice_override_id"], custom_ref)

    def test_character_override_persistence(self):
        """Character override with custom voice persists after save."""
        context = CustomVoiceContext.from_repository(self.repo)
        custom_ref = f"custom:{self.custom_voice_id}"

        set_character_voice_override(
            self.db,
            self.character_id,
            custom_ref,
            allowed_voice_ids=set(),
            custom_voice_context=context,
        )

        # Re-read
        row = self.db.fetch_one(
            "SELECT * FROM characters WHERE id=?", (self.character_id,)
        )
        self.assertEqual(row["voice_override_id"], custom_ref)


class TestCustomVoiceResolution(IsolatedTestCase):
    """Test custom voice resolution returns correct metadata."""

    def setUp(self):
        super().setUp()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        self.repo = CustomVoiceRepository(self.db, self.store)
        self.validator = AudioValidator()

        # Create test book
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO books(title, author, source_path, source_sha256, created_at, updated_at) VALUES(?, ?, ?, ?, datetime('now'), datetime('now'))",
                ("Test Book", "Test Author", "/fake/test.epub", "0" * 64),
            )
        self.book_id = 1

        # Create custom voice with revision
        voice = self.repo.create_custom_voice("Test Custom Voice", "Test description")
        self.custom_voice_id = voice.id

        audio_data = b"RIFF" + (36).to_bytes(4, "little") + b"WAVE"
        audio_data += b"fmt " + (16).to_bytes(4, "little")
        audio_data += (1).to_bytes(2, "little")
        audio_data += (1).to_bytes(2, "little")
        audio_data += (22050).to_bytes(4, "little")
        audio_data += (44100).to_bytes(4, "little")
        audio_data += (2).to_bytes(2, "little")
        audio_data += (16).to_bytes(2, "little")
        audio_data += b"data" + (0).to_bytes(4, "little")

        self.repo.create_revision(
            self.custom_voice_id, audio_data, "Test transcript"
        )

        # Create profile with custom narrator
        context = CustomVoiceContext.from_repository(self.repo)
        self.custom_ref = f"custom:{self.custom_voice_id}"

        set_book_voice_profile(
            self.db,
            self.book_id,
            narrator_voice_id=self.custom_ref,
            male_dialogue_voice_id="preset_male",
            female_dialogue_voice_id="preset_female",
            allowed_voice_ids={"preset_male", "preset_female"},
            custom_voice_context=context,
        )

    def test_effective_resolution_returns_custom_id(self):
        """Effective resolution returns correct logical Custom Voice ID."""
        context = CustomVoiceContext.from_repository(self.repo)
        profile = get_book_voice_profile(self.db, self.book_id)

        result = resolve_voice(
            speaker_type="narrator",
            book_voice_profile=profile,
            custom_voice_context=context,
        )

        self.assertEqual(result["resolved_voice_id"], self.custom_ref)
        self.assertIsInstance(result["voice"], dict)  # voice_ref dict
        self.assertEqual(result["resolution_source"], "narrator")


if __name__ == "__main__":
    unittest.main()
