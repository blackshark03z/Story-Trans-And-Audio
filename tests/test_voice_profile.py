from __future__ import annotations

import json
import tempfile
import os
import unittest
from pathlib import Path

from story_audio.casting import approve_plan, create_casting_draft, split_utterances
from story_audio.pipeline import create_job
from story_audio.voice_profile import (
    VoiceProfileError,
    get_book_voice_profile,
    profile_validation,
    resolve_voice,
    set_book_voice_profile,
    set_character_gender,
    set_character_voice_override,
)
from tests.test_casting import VOICES, seed_casting


ALL_VOICES = VOICES | {"male", "female", "unknown", "override"}


class VoiceProfileTests(unittest.TestCase):

    def setUp(self) -> None:
        super().setUp()
        self._original_testing = os.environ.get("STORY_AUDIO_TESTING")
        os.environ["STORY_AUDIO_TESTING"] = "1"
    
    def tearDown(self) -> None:
        if self._original_testing is None:
            os.environ.pop("STORY_AUDIO_TESTING", None)
        else:
            os.environ["STORY_AUDIO_TESTING"] = self._original_testing
        super().tearDown()

    def profile(self, db, book_id, **changes):
        values = {
            "narrator_voice_id": "narrator",
            "male_dialogue_voice_id": "male",
            "female_dialogue_voice_id": "female",
            "unknown_fallback": "narrator",
            "unknown_voice_id": None,
        }
        values.update(changes)
        return set_book_voice_profile(
            db, book_id, allowed_voice_ids=ALL_VOICES, **values
        )

    def test_profile_create_read_update_and_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, db, _store, book, *_ = seed_casting(Path(directory))
            first = self.profile(db, book)
            second = self.profile(db, book, male_dialogue_voice_id="voice-a")
            self.assertEqual(first["id"], second["id"])
            self.assertEqual(second["config_version"], 2)
            self.assertEqual(get_book_voice_profile(db, book)["male_dialogue_voice_id"], "voice-a")
            self.assertEqual(profile_validation(second, ALL_VOICES), {"valid": True, "missing_preset_ids": []})
            self.assertFalse(profile_validation(second, {"narrator"})["valid"])

    def test_invalid_preset_and_explicit_fallback_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, db, _store, book, *_ = seed_casting(Path(directory))
            with self.assertRaises(VoiceProfileError):
                self.profile(db, book, male_dialogue_voice_id="missing")
            with self.assertRaises(VoiceProfileError):
                self.profile(db, book, unknown_fallback="explicit_voice")

    def test_resolver_narrator_gender_and_unknown_policies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, db, _store, book, *_ = seed_casting(Path(directory))
            profile = self.profile(db, book)
            narrator = resolve_voice(speaker_type="narrator", book_voice_profile=profile)
            male = resolve_voice(speaker_type="dialogue", book_voice_profile=profile, inferred_gender="male")
            female = resolve_voice(speaker_type="dialogue", book_voice_profile=profile, inferred_gender="female")
            unknown = resolve_voice(speaker_type="dialogue", book_voice_profile=profile)
            self.assertEqual(narrator["resolved_voice_id"], "narrator")
            self.assertEqual(male["resolution_source"], "book_male")
            self.assertEqual(female["resolved_voice_id"], "female")
            self.assertTrue(unknown["needs_review"])
            self.assertEqual(unknown["resolved_voice_id"], "narrator")
            for policy, expected in (("male_dialogue", "male"), ("female_dialogue", "female")):
                profile = self.profile(db, book, unknown_fallback=policy)
                self.assertEqual(
                    resolve_voice(speaker_type="dialogue", book_voice_profile=profile)["resolved_voice_id"],
                    expected,
                )
            profile = self.profile(
                db, book, unknown_fallback="explicit_voice", unknown_voice_id="unknown"
            )
            self.assertEqual(
                resolve_voice(speaker_type="dialogue", book_voice_profile=profile)["resolved_voice_id"],
                "unknown",
            )

    def test_confirmed_character_gender_beats_inferred_and_override_wins(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, db, _store, book, _chapter, _revision, character, *_ = seed_casting(Path(directory))
            profile = self.profile(db, book)
            set_character_gender(db, character["id"], "male")
            character = set_character_voice_override(
                db, character["id"], None, allowed_voice_ids=ALL_VOICES
            )
            result = resolve_voice(
                speaker_type="dialogue", book_voice_profile=profile,
                character=character, inferred_gender="female",
            )
            self.assertEqual(result["resolved_voice_id"], "male")
            character = set_character_voice_override(
                db, character["id"], "override", allowed_voice_ids=ALL_VOICES
            )
            result = resolve_voice(
                speaker_type="dialogue", book_voice_profile=profile, character=character
            )
            self.assertEqual(result["resolved_voice_id"], "override")
            self.assertEqual(result["resolution_source"], "character_override")

    def test_profile_casting_and_job_snapshot_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, db, store, book, chapter, revision, character, _b, _old = seed_casting(Path(directory))
            self.profile(db, book)
            set_character_gender(db, character["id"], "male")
            set_character_voice_override(db, character["id"], None, allowed_voice_ids=ALL_VOICES)
            utterances = split_utterances(store.read_text(db.fetch_one(
                "SELECT content_path FROM text_revisions WHERE id=?", (revision,)
            )["content_path"]))
            draft = create_casting_draft(
                db, store, chapter_id=chapter, text_revision_id=revision,
                narrator_voice_id="voice-b",
                assignments=[{
                    "utterance_id": utterances[1]["utterance_id"],
                    "role": "character", "character_id": character["id"],
                }],
                allowed_voice_ids=ALL_VOICES,
            )
            plan = approve_plan(db, store, draft["id"])
            self.assertEqual(plan["plan"]["narrator_voice_id"], "narrator")
            self.assertEqual(plan["plan"]["utterances"][1]["resolved_voice_id"], "male")
            self.assertEqual(plan["plan"]["utterances"][1]["resolution_source"], "book_male")
            created = create_job(
                db, config, book_id=book, from_chapter=1, to_chapter=1,
                voice_name="narrator", repair_mode="off", output_format="m4a",
                skip_completed=False, casting_plan_id=plan["id"], store=store,
            )
            before = db.fetch_one(
                "SELECT casting_snapshot_json FROM jobs WHERE id=?", (created["job_id"],)
            )["casting_snapshot_json"]
            self.profile(db, book, male_dialogue_voice_id="voice-a")
            set_character_voice_override(db, character["id"], "override", allowed_voice_ids=ALL_VOICES)
            after = db.fetch_one(
                "SELECT casting_snapshot_json FROM jobs WHERE id=?", (created["job_id"],)
            )["casting_snapshot_json"]
            self.assertEqual(before, after)
            snapshot = json.loads(after)
            self.assertEqual(snapshot["book_voice_profile"]["config_version"], 1)
            self.assertEqual(snapshot["utterances"][1]["resolved_voice_id"], "male")

            new_draft = create_casting_draft(
                db, store, chapter_id=chapter, text_revision_id=revision,
                narrator_voice_id="narrator",
                assignments=[{
                    "utterance_id": utterances[1]["utterance_id"],
                    "role": "character", "character_id": character["id"],
                }],
                allowed_voice_ids=ALL_VOICES,
            )
            new_plan = approve_plan(db, store, new_draft["id"])
            new_job = create_job(
                db, config, book_id=book, from_chapter=1, to_chapter=1,
                voice_name="narrator", repair_mode="off", output_format="m4a",
                skip_completed=False, casting_plan_id=new_plan["id"], store=store,
            )
            new_snapshot = json.loads(db.fetch_one(
                "SELECT casting_snapshot_json FROM jobs WHERE id=?", (new_job["job_id"],)
            )["casting_snapshot_json"])
            self.assertEqual(new_snapshot["book_voice_profile"]["config_version"], 2)
            self.assertEqual(new_snapshot["utterances"][1]["resolved_voice_id"], "override")


if __name__ == "__main__":
    unittest.main()
