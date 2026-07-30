from __future__ import annotations

from story_audio.background_speakers import (
    ensure_background_group_character,
    normalize_generic_speaker_label,
    resolve_background_group_voice,
)
from story_audio.casting import create_character
from story_audio.db import Database, utcnow
from story_audio.voice_eligibility import EffectiveVoiceCatalog
from tests.base import IsolatedTestCase


def _catalog(*voice_ids: str) -> EffectiveVoiceCatalog:
    return EffectiveVoiceCatalog.from_payload(
        {
            "items": [
                {
                    "assignment_key": voice_id,
                    "display_name": voice_id,
                    "source_kind": "preset",
                    "active": True,
                    "usable": True,
                    "selectable": True,
                }
                for voice_id in voice_ids
            ]
        }
    )


class BackgroundSpeakerTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config.ensure_dirs()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        now = utcnow()
        with self.db.transaction() as connection:
            self.book_id = int(
                connection.execute(
                    """
                    INSERT INTO books(
                        title,source_path,source_sha256,chapter_count,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    ("Background fixture", "fixture.epub", "fixture-sha", 0, now, now),
                ).lastrowid
            )

    def test_generic_normalization_is_conservative_and_respects_bound_identity(self) -> None:
        signal = normalize_generic_speaker_label("Một gã đại hán")
        self.assertTrue(signal["is_generic_candidate"])
        self.assertEqual(signal["gender_hint"], "MALE")
        self.assertTrue(
            normalize_generic_speaker_label("đại hán nọ")["is_generic_candidate"]
        )

        bound = normalize_generic_speaker_label(
            "Một gã đại hán",
            bound_identities=["Đại hán"],
        )
        self.assertFalse(bound["is_generic_candidate"])
        self.assertTrue(bound["bound_to_existing_character"])

        named = normalize_generic_speaker_label("Hứa Thanh")
        self.assertFalse(named["is_generic_candidate"])

    def test_reserved_group_is_created_once_per_book_and_reused(self) -> None:
        with self.db.transaction() as connection:
            first = ensure_background_group_character(
                connection,
                book_id=self.book_id,
                gender_hint="MALE",
                idempotency_key="group-create-1",
            )
            second = ensure_background_group_character(
                connection,
                book_id=self.book_id,
                gender_hint="MALE",
                idempotency_key="group-create-2",
            )
        self.assertTrue(first["created"])
        self.assertTrue(second["reused"])
        self.assertEqual(first["character"]["id"], second["character"]["id"])
        self.assertEqual(
            int(
                self.db.fetch_one(
                    """
                    SELECT COUNT(*) AS count FROM characters
                    WHERE book_id=? AND external_key_normalized='background-group:male'
                    """,
                    (self.book_id,),
                )["count"]
            ),
            1,
        )

    def test_gender_voice_precedence_and_neutral_never_falls_back_to_male(self) -> None:
        profile = {
            "narrator_voice_id": "narrator",
            "male_dialogue_voice_id": "male",
            "female_dialogue_voice_id": "female",
            "unknown_fallback": "narrator",
            "unknown_voice_id": None,
        }
        catalog = _catalog("narrator", "male", "female", "saved")
        male, male_source = resolve_background_group_voice(
            gender_hint="MALE",
            book_profile=profile,
            catalog=catalog,
        )
        female, female_source = resolve_background_group_voice(
            gender_hint="FEMALE",
            book_profile=profile,
            catalog=catalog,
        )
        neutral, neutral_source = resolve_background_group_voice(
            gender_hint="NEUTRAL_OR_UNKNOWN",
            book_profile=profile,
            catalog=catalog,
        )
        self.assertEqual(male["id"], "male")
        self.assertEqual(female["id"], "female")
        self.assertEqual(neutral["id"], "narrator")
        self.assertNotEqual(neutral["id"], "male")
        self.assertIn("nam", male_source.lower())
        self.assertIn("nữ", female_source.lower())
        self.assertIn("chung", neutral_source.lower())

        profile["unknown_fallback"] = "male"
        missing, reason = resolve_background_group_voice(
            gender_hint="NEUTRAL_OR_UNKNOWN",
            book_profile=profile,
            catalog=catalog,
        )
        self.assertIsNone(missing)
        self.assertIn("trung tính", reason)

        group = create_character(
            self.db,
            self.book_id,
            "Existing neutral group",
            "saved",
            gender="unknown",
        )
        saved, saved_source = resolve_background_group_voice(
            gender_hint="NEUTRAL_OR_UNKNOWN",
            book_profile=profile,
            catalog=catalog,
            group_character=group,
        )
        self.assertEqual(saved["id"], "saved")
        self.assertIn("đã lưu", saved_source)
