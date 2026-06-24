from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import story_audio.api as api_module
from story_audio.casting import CastingError, casting_context, create_casting_draft, split_utterances
from story_audio.voice_profile import set_book_voice_profile, set_character_gender, set_character_voice_override
from tests.test_casting import TEXT, VOICES, seed_casting


ALL_VOICES = VOICES | {"male", "female"}


class VoiceProfileApiUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        (
            self.config,
            self.db,
            self.store,
            self.book,
            self.chapter,
            self.revision,
            self.character,
            _other,
            _plan,
        ) = seed_casting(Path(self.temp.name))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create_profile(self):
        return set_book_voice_profile(
            self.db,
            self.book,
            narrator_voice_id="narrator",
            male_dialogue_voice_id="male",
            female_dialogue_voice_id="female",
            unknown_fallback="narrator",
            allowed_voice_ids=ALL_VOICES,
        )

    def test_profile_api_has_explicit_empty_state_then_create_and_update(self) -> None:
        with patch.object(api_module, "db", self.db), patch.object(
            api_module, "_preset_voice_ids", return_value=ALL_VOICES
        ):
            empty = api_module.read_book_voice_profile(self.book)
            self.assertEqual(empty["configured"], False)
            request = api_module.BookVoiceProfileRequest(
                narrator_voice_id="narrator",
                male_dialogue_voice_id="male",
                female_dialogue_voice_id="female",
            )
            created = api_module.write_book_voice_profile(self.book, request)
            updated = api_module.write_book_voice_profile(
                self.book, request.model_copy(update={"male_dialogue_voice_id": "voice-a"})
            )
            self.assertEqual(created["config_version"], 1)
            self.assertEqual(updated["config_version"], 2)

    def test_resolve_preview_is_read_only_and_returns_public_voice_alias(self) -> None:
        self.create_profile()
        set_character_gender(self.db, self.character["id"], "male")
        set_character_voice_override(
            self.db, self.character["id"], None, allowed_voice_ids=ALL_VOICES
        )
        before = dict(self.db.fetch_one(
            "SELECT COUNT(*) AS jobs, (SELECT COUNT(*) FROM casting_plans) AS plans FROM jobs"
        ))
        with patch.object(api_module, "db", self.db):
            result = api_module.resolve_voice_preview(
                self.book,
                api_module.VoiceResolveRequest(
                    speaker_type="dialogue", character_id=self.character["id"]
                ),
            )
        after = dict(self.db.fetch_one(
            "SELECT COUNT(*) AS jobs, (SELECT COUNT(*) FROM casting_plans) AS plans FROM jobs"
        ))
        self.assertEqual(before, after)
        self.assertEqual(result["resolved_voice"]["preset_id"], "male")
        self.assertEqual(result["resolution_source"], "book_male")
        with patch.object(api_module, "db", self.db), patch.object(
            api_module, "_preset_voice_ids", return_value=ALL_VOICES
        ):
            custom = api_module.resolve_voice_preview(
                self.book,
                api_module.VoiceResolveRequest(
                    speaker_type="dialogue",
                    character_id=self.character["id"],
                    gender="female",
                    voice_override_id="voice-b",
                ),
            )
            book_default = api_module.resolve_voice_preview(
                self.book,
                api_module.VoiceResolveRequest(
                    speaker_type="dialogue",
                    character_id=self.character["id"],
                    gender="female",
                    use_character_override=False,
                ),
            )
        self.assertEqual(custom["resolution_source"], "character_override")
        self.assertEqual(custom["resolved_voice_id"], "voice-b")
        self.assertEqual(book_default["resolution_source"], "book_female")
        self.assertEqual(book_default["resolved_voice_id"], "female")

    def test_casting_context_exposes_effective_voice_and_review_metadata(self) -> None:
        self.create_profile()
        set_character_voice_override(
            self.db, self.character["id"], None, allowed_voice_ids=ALL_VOICES
        )
        context = casting_context(self.db, self.store, self.chapter, ALL_VOICES)
        self.assertTrue(context["voice_profile"]["configured"])
        self.assertTrue(context["voice_profile"]["validation"]["valid"])
        self.assertEqual(
            context["voice_profile"]["unknown_resolution"]["resolution_source"],
            "unknown_fallback",
        )
        effective = next(
            item["effective_resolution"]
            for item in context["characters"]
            if item["id"] == self.character["id"]
        )
        self.assertEqual(effective["resolution_source"], "unknown_fallback")
        self.assertTrue(effective["needs_review"])

    def test_missing_profile_blocks_book_default_character_safely(self) -> None:
        set_character_voice_override(
            self.db, self.character["id"], None, allowed_voice_ids=ALL_VOICES
        )
        utterance = split_utterances(TEXT)[0]
        with self.assertRaisesRegex(CastingError, "Create a Book Voice Profile"):
            create_casting_draft(
                self.db,
                self.store,
                chapter_id=self.chapter,
                text_revision_id=self.revision,
                narrator_voice_id="narrator",
                assignments=[{
                    "utterance_id": utterance["utterance_id"],
                    "role": "character",
                    "character_id": self.character["id"],
                }],
                allowed_voice_ids=ALL_VOICES,
            )

    def test_ui_contract_contains_profile_override_preview_and_safe_rendering(self) -> None:
        root = Path(__file__).resolve().parents[1]
        html = (root / "ui" / "index.html").read_text(encoding="utf-8")
        script = (root / "ui" / "app.js").read_text(encoding="utf-8")
        for element_id in (
            "voiceProfileEmpty",
            "profileNarratorVoice",
            "profileMaleVoice",
            "profileFemaleVoice",
            "profileUnknownFallback",
            "profileExplicitVoice",
            "saveVoiceProfile",
            "newCharacterAssignment",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("Use book default", html)
        self.assertIn("Use custom voice", html)
        self.assertIn("data-profile-preview", html)
        self.assertIn("esc(resolutionText", script)
        self.assertIn("esc(c.display_name)", script)
        self.assertNotIn("innerHTML=c.display_name", script)


if __name__ == "__main__":
    unittest.main()
