from __future__ import annotations

from story_audio.book_voice_registry import get_book_voice_registry
from story_audio.casting import approve_plan, create_casting_draft, get_plan, split_utterances
from story_audio.character_assignment import (
    CharacterAssignmentError,
    add_character_aliases,
    apply_speaker_character_mapping,
    clear_speaker_character_mapping,
    create_assignment_character,
    dash_dialogue_utterance_ids,
    unresolved_dialogue_speaker_key,
)
from story_audio.db import Database, utcnow
from story_audio.storage import ContentStore
from story_audio.voice_eligibility import EffectiveVoiceCatalog
from story_audio.voice_profile import set_book_voice_profile, set_character_voice_override
from tests.base import IsolatedTestCase


ALL_VOICES = {"narrator", "male", "female", "commander", "alternate"}


def _catalog(*voice_ids: str) -> EffectiveVoiceCatalog:
    return EffectiveVoiceCatalog.from_payload(
        {
            "items": [
                {
                    "assignment_key": voice_id,
                    "display_name": voice_id.title(),
                    "source_kind": "preset",
                    "active": True,
                    "usable": True,
                    "selectable": True,
                }
                for voice_id in voice_ids
            ]
        }
    )


class CharacterAssignmentServiceTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config.ensure_dirs()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        self.book_id = self._seed_book("Assignment Fixture")
        self.other_book_id = self._seed_book("Other Fixture")
        set_book_voice_profile(
            self.db,
            self.book_id,
            narrator_voice_id="narrator",
            male_dialogue_voice_id="male",
            female_dialogue_voice_id="female",
            unknown_fallback="narrator",
            unknown_voice_id=None,
            allowed_voice_ids=ALL_VOICES,
        )
        set_book_voice_profile(
            self.db,
            self.other_book_id,
            narrator_voice_id="narrator",
            male_dialogue_voice_id="male",
            female_dialogue_voice_id="female",
            unknown_fallback="narrator",
            unknown_voice_id=None,
            allowed_voice_ids=ALL_VOICES,
        )

    def _seed_book(self, title: str) -> int:
        now = utcnow()
        with self.db.transaction() as connection:
            return int(
                connection.execute(
                    """
                    INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at)
                    VALUES(?,?,?,?,?,?)
                    """,
                    (title, f"{title}.epub", f"sha-{title}", 20, now, now),
                ).lastrowid
            )

    def _seed_chapter(
        self,
        number: int,
        *,
        book_id: int | None = None,
        text: str | None = None,
        roles_by_sequence: dict[int, tuple[str, int | None]] | None = None,
        approved_plan: bool = True,
        audio_status: str = "not_created",
    ) -> dict:
        now = utcnow()
        owner = int(book_id or self.book_id)
        content = text or (
            f"Chapter {number} opens. "
            f"- Hold the gate for chapter {number}. "
            f"Chapter {number} closes."
        )
        content_path, content_sha = self.store.put_text(content)
        with self.db.transaction() as connection:
            chapter_id = int(
                connection.execute(
                    """
                    INSERT INTO chapters(book_id,chapter_number,title,char_count,audio_status,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?)
                    """,
                    (owner, number, f"Chapter {number}", len(content), audio_status, now, now),
                ).lastrowid
            )
            revision_id = int(
                connection.execute(
                    """
                    INSERT INTO text_revisions(
                        chapter_id,kind,content_path,content_sha256,lexical_sha256,
                        char_count,processor_version,status,created_at
                    )
                    VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        chapter_id,
                        "reflowed",
                        content_path,
                        content_sha,
                        f"lexical-{number}-{owner}",
                        len(content),
                        "test",
                        "approved",
                        now,
                    ),
                ).lastrowid
            )
            connection.execute(
                "UPDATE chapters SET active_text_revision_id=? WHERE id=?",
                (revision_id, chapter_id),
            )
        chapter = dict(
            self.db.fetch_one(
                "SELECT * FROM chapters WHERE id=?",
                (chapter_id,),
            )
        )
        if approved_plan:
            self._create_approved_plan(chapter, roles_by_sequence or {})
        return chapter

    def _create_approved_plan(
        self,
        chapter: dict,
        roles_by_sequence: dict[int, tuple[str, int | None]],
    ) -> dict:
        revision = self.db.fetch_one(
            "SELECT content_path FROM text_revisions WHERE id=?",
            (int(chapter["active_text_revision_id"]),),
        )
        text = self.store.read_text(str(revision["content_path"]))
        assignments = []
        for utterance in split_utterances(text):
            role, character_id = roles_by_sequence.get(
                int(utterance["sequence"]), ("narrator", None)
            )
            assignments.append(
                {
                    "utterance_id": utterance["utterance_id"],
                    "role": role,
                    "character_id": character_id,
                }
            )
        draft = create_casting_draft(
            self.db,
            self.store,
            chapter_id=int(chapter["id"]),
            text_revision_id=int(chapter["active_text_revision_id"]),
            narrator_voice_id="narrator",
            assignments=assignments,
            allowed_voice_ids=ALL_VOICES,
        )
        return approve_plan(self.db, self.store, int(draft["id"]))

    def _registry(self, start: int, end: int, *, skip_completed: bool = False) -> dict:
        return get_book_voice_registry(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=start,
            to_chapter=end,
            skip_completed=skip_completed,
            voice_catalog=_catalog("narrator", "male", "female", "commander", "alternate"),
        )

    def _latest_plan(self, chapter_id: int) -> dict:
        row = self.db.fetch_one(
            """
            SELECT id
            FROM casting_plans
            WHERE chapter_id=?
            ORDER BY plan_revision DESC,id DESC
            LIMIT 1
            """,
            (chapter_id,),
        )
        return get_plan(self.db, self.store, int(row["id"]))

    def _approved_plan_count(self) -> int:
        return int(
            self.db.fetch_one(
                "SELECT COUNT(*) AS count FROM casting_plans WHERE status='approved'"
            )["count"]
        )

    def _plan_count(self) -> int:
        return int(self.db.fetch_one("SELECT COUNT(*) AS count FROM casting_plans")["count"])

    def test_registry_exposes_dash_dialogue_as_unresolved_not_narrator(self) -> None:
        self._seed_chapter(1)
        self._seed_chapter(2)

        registry = self._registry(1, 2)
        unresolved = [
            row for row in registry["rows"] if row["status"] == "UNRESOLVED_DIALOGUE"
        ]

        self.assertEqual(len(unresolved), 2)
        self.assertEqual(registry["summary"]["unresolved_dialogue"], 2)
        self.assertEqual(registry["summary"]["blocking_rows"], 2)
        self.assertTrue(unresolved[0]["sample_lines"][0]["text"].startswith("- Hold"))
        self.assertTrue(unresolved[0]["actions"]["can_create_character"])
        self.assertTrue(unresolved[0]["actions"]["can_map_to_character"])
        narrator = next(row for row in registry["rows"] if row["speaker_key"] == "narrator")
        self.assertEqual(narrator["line_count"], 4)
        self.assertEqual(len(registry["content_evidence"]["checked_revisions"]), 2)

    def test_dash_dialogue_uses_raw_line_layout_for_continuation_utterances(self) -> None:
        active = "Intro. - Stop? Give me the bag. He turned away."
        source = "Intro.\n- Stop? Give me the bag.\nHe turned away."
        utterances = split_utterances(active)
        target_ids = dash_dialogue_utterance_ids(
            active,
            utterances,
            source_layout_text=source,
        )
        self.assertEqual(
            [item["sequence"] for item in utterances if item["utterance_id"] in target_ids],
            [2, 3],
        )

    def test_registry_blocks_narrator_continuation_on_mapped_dash_dialogue_line(self) -> None:
        character = create_assignment_character(
            self.db,
            book_id=self.book_id,
            display_name="Gate Guard",
            aliases=[],
            idempotency_key="gate-guard-for-continuation",
        )["character"]
        active = "Intro. - Stop? Give me the bag. He turned away."
        source = "Intro.\n- Stop? Give me the bag.\nHe turned away."
        chapter = self._seed_chapter(
            3,
            text=active,
            roles_by_sequence={2: ("character", int(character["id"]))},
        )
        source_path, source_sha = self.store.put_text(source)
        now = utcnow()
        with self.db.transaction() as connection:
            raw_revision_id = int(
                connection.execute(
                    """
                    INSERT INTO text_revisions(
                        chapter_id,kind,content_path,content_sha256,lexical_sha256,
                        char_count,processor_version,status,created_at
                    )
                    VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        int(chapter["id"]),
                        "raw",
                        source_path,
                        source_sha,
                        "raw-layout-lexical",
                        len(source),
                        "test",
                        "approved",
                        now,
                    ),
                ).lastrowid
            )
            connection.execute(
                "UPDATE text_revisions SET parent_revision_id=? WHERE id=?",
                (raw_revision_id, int(chapter["active_text_revision_id"])),
            )

        registry = self._registry(3, 3)
        unresolved = [
            row for row in registry["rows"] if row["status"] == "UNRESOLVED_DIALOGUE"
        ]
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["target_utterances"][0]["sequence"], 3)
        self.assertEqual(unresolved[0]["sample_lines"][0]["text"], "Give me the bag.")

    def test_skip_completed_filters_only_completed_chapters_and_keeps_remaining_dialogue(self) -> None:
        self._seed_chapter(1, audio_status="completed")
        self._seed_chapter(2)

        registry = self._registry(1, 2, skip_completed=True)
        unresolved = [
            row for row in registry["rows"] if row["status"] == "UNRESOLVED_DIALOGUE"
        ]

        self.assertEqual(registry["range"]["from_chapter"], 2)
        self.assertEqual(registry["range"]["to_chapter"], 2)
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["chapter_numbers"], [2])

    def test_create_character_reuses_existing_identity_and_aliases(self) -> None:
        first = create_assignment_character(
            self.db,
            book_id=self.book_id,
            display_name="Gate Commander",
            aliases=["gate chief", "gate chief"],
            idempotency_key="create-gate-commander",
        )
        second = create_assignment_character(
            self.db,
            book_id=self.book_id,
            display_name="Gate Commander",
            aliases=["field commander"],
            idempotency_key="create-gate-commander-replay",
        )

        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertTrue(second["reused"])
        self.assertEqual(
            int(
                self.db.fetch_one(
                    "SELECT COUNT(*) AS count FROM characters WHERE book_id=?",
                    (self.book_id,),
                )["count"]
            ),
            1,
        )
        self.assertEqual(
            int(
                self.db.fetch_one(
                    "SELECT COUNT(*) AS count FROM character_aliases WHERE character_id=?",
                    (int(first["character"]["id"]),),
                )["count"]
            ),
            2,
        )

    def test_mapping_unresolved_dialogue_creates_approved_revision_and_preserves_outputs(self) -> None:
        chapter = self._seed_chapter(1)
        registry = self._registry(1, 1)
        speaker_key = next(
            row["speaker_key"]
            for row in registry["rows"]
            if row["status"] == "UNRESOLVED_DIALOGUE"
        )
        character = create_assignment_character(
            self.db,
            book_id=self.book_id,
            display_name="Gate Commander",
            aliases=[],
            idempotency_key="create-before-map",
        )["character"]
        previous_plan_id = int(
            self.db.fetch_one(
                """
                SELECT id
                FROM casting_plans
                WHERE chapter_id=? AND status='approved'
                ORDER BY plan_revision DESC,id DESC
                LIMIT 1
                """,
                (int(chapter["id"]),),
            )["id"]
        )
        before_plans = self._plan_count()
        before_jobs = int(self.db.fetch_one("SELECT COUNT(*) AS count FROM jobs")["count"])
        before_artifacts = int(self.db.fetch_one("SELECT COUNT(*) AS count FROM artifacts")["count"])

        result = apply_speaker_character_mapping(
            self.db,
            self.store,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=1,
            speaker_key=speaker_key,
            character_id=int(character["id"]),
            aliases=["gate chief"],
            voice_catalog=_catalog("narrator", "male", "female", "commander", "alternate"),
            idempotency_key="map-gate-commander",
        )

        self.assertEqual(result["utterance_count"], 1)
        self.assertEqual(result["alias_result"]["added_count"], 1)
        self.assertEqual(self._plan_count(), before_plans + 1)
        self.assertEqual(self._approved_plan_count(), 1)
        archived = self.db.fetch_one(
            "SELECT status FROM casting_plans WHERE id=?",
            (previous_plan_id,),
        )
        self.assertEqual(str(archived["status"]), "archived")
        plan = self._latest_plan(int(chapter["id"]))["plan"]
        mapped = [
            item
            for item in plan["utterances"]
            if item["utterance_id"] in result["applied"][0]["utterance_ids"]
        ]
        self.assertEqual(mapped[0]["role"], "character")
        self.assertEqual(mapped[0]["character_id"], int(character["id"]))
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS count FROM jobs")["count"]),
            before_jobs,
        )
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS count FROM artifacts")["count"]),
            before_artifacts,
        )

        refreshed = self._registry(1, 1)
        self.assertFalse(
            [row for row in refreshed["rows"] if row["status"] == "UNRESOLVED_DIALOGUE"]
        )
        character_row = next(
            row for row in refreshed["rows"] if row["speaker_key"] == f"character:{int(character['id'])}"
        )
        self.assertEqual(character_row["display_name"], "Gate Commander")

    def test_mapping_replay_reuses_plan_and_alias_without_duplicates(self) -> None:
        self._seed_chapter(1)
        speaker_key = next(
            row["speaker_key"]
            for row in self._registry(1, 1)["rows"]
            if row["status"] == "UNRESOLVED_DIALOGUE"
        )
        character = create_assignment_character(
            self.db,
            book_id=self.book_id,
            display_name="Gate Commander",
            aliases=[],
            idempotency_key="create-replay-target",
        )["character"]

        first = apply_speaker_character_mapping(
            self.db,
            self.store,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=1,
            speaker_key=speaker_key,
            character_id=int(character["id"]),
            aliases=["gate chief"],
            voice_catalog=_catalog("narrator", "male", "female", "commander", "alternate"),
            idempotency_key="map-replay",
        )
        plan_count = self._plan_count()
        second = apply_speaker_character_mapping(
            self.db,
            self.store,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=1,
            speaker_key=speaker_key,
            character_id=int(character["id"]),
            aliases=["gate chief"],
            voice_catalog=_catalog("narrator", "male", "female", "commander", "alternate"),
            idempotency_key="map-replay",
        )

        self.assertFalse(first["applied"][0]["reused"])
        self.assertTrue(second["applied"][0]["reused"])
        self.assertEqual(self._plan_count(), plan_count)
        self.assertEqual(second["alias_result"]["reused_count"], 1)
        self.assertEqual(
            int(
                self.db.fetch_one(
                    "SELECT COUNT(*) AS count FROM character_aliases WHERE character_id=?",
                    (int(character["id"]),),
                )["count"]
            ),
            1,
        )

    def test_mapping_rejects_cross_book_character_without_partial_state(self) -> None:
        self._seed_chapter(1)
        other_chapter = self._seed_chapter(1, book_id=self.other_book_id)
        other_character = create_assignment_character(
            self.db,
            book_id=self.other_book_id,
            display_name="Other Commander",
            idempotency_key="other-commander",
        )["character"]
        before_plans = self._plan_count()
        before_aliases = int(
            self.db.fetch_one("SELECT COUNT(*) AS count FROM character_aliases")["count"]
        )
        speaker_key = next(
            row["speaker_key"]
            for row in self._registry(1, 1)["rows"]
            if row["status"] == "UNRESOLVED_DIALOGUE"
        )

        with self.assertRaises(CharacterAssignmentError):
            apply_speaker_character_mapping(
                self.db,
                self.store,
                book_id=self.book_id,
                from_chapter=1,
                to_chapter=1,
                speaker_key=speaker_key,
                character_id=int(other_character["id"]),
                aliases=["should not persist"],
                voice_catalog=_catalog("narrator", "male", "female", "commander", "alternate"),
                idempotency_key="cross-book-map",
            )

        self.assertEqual(self._plan_count(), before_plans)
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS count FROM character_aliases")["count"]),
            before_aliases,
        )
        self.assertEqual(self._latest_plan(int(other_chapter["id"]))["status"], "approved")

    def test_unresolved_mapping_skips_unrelated_chapter_without_final_voice_map(self) -> None:
        self._seed_chapter(1, approved_plan=False)
        target_chapter = self._seed_chapter(2)
        speaker_key = next(
            row["speaker_key"]
            for row in self._registry(2, 2)["rows"]
            if row["status"] == "UNRESOLVED_DIALOGUE"
        )
        character = create_assignment_character(
            self.db,
            book_id=self.book_id,
            display_name="Range Commander",
            idempotency_key="range-commander",
        )["character"]

        result = apply_speaker_character_mapping(
            self.db,
            self.store,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=2,
            speaker_key=speaker_key,
            character_id=int(character["id"]),
            aliases=[],
            voice_catalog=_catalog("narrator", "male", "female", "commander", "alternate"),
            idempotency_key="range-commander-map",
        )

        self.assertEqual(len(result["applied"]), 1)
        self.assertEqual(result["applied"][0]["chapter_number"], 2)
        self.assertEqual(
            self._latest_plan(int(target_chapter["id"]))["status"],
            "approved",
        )

    def test_partial_range_failure_creates_no_approved_plan_or_alias_rows(self) -> None:
        known = create_assignment_character(
            self.db,
            book_id=self.book_id,
            display_name="Known Unknown",
            idempotency_key="known-unknown",
        )["character"]
        chapter = self._seed_chapter(1, roles_by_sequence={2: ("unknown", None)})
        self._seed_chapter(2, approved_plan=False)
        before_plans = self._plan_count()
        before_aliases = int(
            self.db.fetch_one("SELECT COUNT(*) AS count FROM character_aliases")["count"]
        )

        with self.assertRaises(CharacterAssignmentError):
            apply_speaker_character_mapping(
                self.db,
                self.store,
                book_id=self.book_id,
                from_chapter=1,
                to_chapter=2,
                speaker_key="unknown",
                character_id=int(known["id"]),
                aliases=["range alias"],
                voice_catalog=_catalog("narrator", "male", "female", "commander", "alternate"),
                idempotency_key="range-fail",
            )

        self.assertEqual(self._plan_count(), before_plans)
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS count FROM character_aliases")["count"]),
            before_aliases,
        )
        latest = self._latest_plan(int(chapter["id"]))
        self.assertEqual(latest["status"], "approved")
        self.assertEqual(latest["plan"]["utterances"][1]["role"], "unknown")

    def test_clear_mapping_restores_unresolved_dialogue_row(self) -> None:
        chapter = self._seed_chapter(1)
        original_key = next(
            row["speaker_key"]
            for row in self._registry(1, 1)["rows"]
            if row["status"] == "UNRESOLVED_DIALOGUE"
        )
        character = create_assignment_character(
            self.db,
            book_id=self.book_id,
            display_name="Gate Commander",
            idempotency_key="clear-target",
        )["character"]
        apply_speaker_character_mapping(
            self.db,
            self.store,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=1,
            speaker_key=original_key,
            character_id=int(character["id"]),
            aliases=[],
            voice_catalog=_catalog("narrator", "male", "female", "commander", "alternate"),
            idempotency_key="map-before-clear",
        )

        result = clear_speaker_character_mapping(
            self.db,
            self.store,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=1,
            speaker_key=f"character:{int(character['id'])}",
            voice_catalog=_catalog("narrator", "male", "female", "commander", "alternate"),
            idempotency_key="clear-mapping",
        )

        self.assertEqual(result["utterance_count"], 1)
        plan = self._latest_plan(int(chapter["id"]))["plan"]
        self.assertEqual(plan["utterances"][1]["role"], "narrator")
        self.assertIsNone(plan["utterances"][1]["character_id"])
        registry = self._registry(1, 1)
        unresolved = [
            row for row in registry["rows"] if row["status"] == "UNRESOLVED_DIALOGUE"
        ]
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["speaker_key"], original_key)

    def test_mapping_can_set_voice_after_character_identity_exists(self) -> None:
        self._seed_chapter(1)
        speaker_key = next(
            row["speaker_key"]
            for row in self._registry(1, 1)["rows"]
            if row["status"] == "UNRESOLVED_DIALOGUE"
        )
        character = create_assignment_character(
            self.db,
            book_id=self.book_id,
            display_name="Gate Commander",
            idempotency_key="voice-target",
        )["character"]
        apply_speaker_character_mapping(
            self.db,
            self.store,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=1,
            speaker_key=speaker_key,
            character_id=int(character["id"]),
            aliases=[],
            voice_catalog=_catalog("narrator", "male", "female", "commander", "alternate"),
            idempotency_key="map-before-voice",
        )
        set_character_voice_override(
            self.db,
            int(character["id"]),
            "commander",
            allowed_voice_ids=ALL_VOICES,
        )

        registry = self._registry(1, 1)
        row = next(row for row in registry["rows"] if row["display_name"] == "Gate Commander")
        self.assertEqual(row["status"], "OVERRIDDEN")
        self.assertEqual(row["saved_voice"]["id"], "commander")
        self.assertEqual(row["effective_voice"]["id"], "narrator")
        self.assertTrue(row["actions"]["can_create_range_or_chapter_override"])

    def test_unresolved_speaker_key_round_trip_uses_exact_chapter_and_utterance(self) -> None:
        chapter = self._seed_chapter(7)
        utterance_id = self._latest_plan(int(chapter["id"]))["plan"]["utterances"][1][
            "utterance_id"
        ]
        speaker_key = unresolved_dialogue_speaker_key(int(chapter["id"]), utterance_id)
        self.assertTrue(speaker_key.startswith("unresolved-dialogue:"))
        registry_key = next(
            row["speaker_key"]
            for row in self._registry(7, 7)["rows"]
            if row["status"] == "UNRESOLVED_DIALOGUE"
        )
        self.assertEqual(registry_key, speaker_key)


if __name__ == "__main__":
    import unittest

    unittest.main()
