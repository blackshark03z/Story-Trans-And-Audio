from __future__ import annotations

from story_audio.book_voice_registry import get_book_voice_registry
from story_audio.casting import approve_plan, create_casting_draft, create_character, split_utterances
from story_audio.db import Database, utcnow
from story_audio.storage import ContentStore
from story_audio.voice_eligibility import EffectiveVoiceCatalog
from story_audio.voice_profile import set_book_voice_profile, set_character_voice_override
from tests.base import IsolatedTestCase


ALL_VOICES = {
    "narrator",
    "male",
    "female",
    "recurring",
    "new",
    "legacy",
    "conflict-a",
    "conflict-b",
}


def _catalog(*voice_ids: str) -> EffectiveVoiceCatalog:
    items = [
        {
            "assignment_key": voice_id,
            "display_name": {
                "narrator": "Narrator Voice",
                "male": "Male Default",
                "female": "Female Default",
                "recurring": "Recurring Voice",
                "new": "New Character Voice",
                "conflict-a": "Conflict A",
                "conflict-b": "Conflict B",
            }.get(voice_id, voice_id),
            "source_kind": "preset",
            "active": True,
            "usable": True,
            "selectable": True,
        }
        for voice_id in voice_ids
    ]
    return EffectiveVoiceCatalog.from_payload({"items": items})


class BookVoiceRegistryTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config.ensure_dirs()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        self.book_id = self._seed_book()
        self.characters = self._seed_characters()
        self._seed_plans()

    def _seed_book(self) -> int:
        now = utcnow()
        book_id: int
        with self.db.transaction() as connection:
            book_id = int(
                connection.execute(
                    """
                    INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at)
                    VALUES(?,?,?,?,?,?)
                    """,
                    ("Golden Book", "golden.epub", "golden-sha", 3, now, now),
                ).lastrowid
            )
            for number in (1, 2, 3):
                text = (
                    f"Chương {number} mở đầu. "
                    f"\"Câu nhân vật một.\" "
                    f"Người kể tiếp tục. "
                    f"\"Câu nhân vật hai.\" "
                    f"Khoảng lặng qua nhanh. "
                    f"\"Câu nhân vật ba.\""
                )
                content_path, content_sha = self.store.put_text(text)
                chapter_id = int(
                    connection.execute(
                        """
                        INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at)
                        VALUES(?,?,?,?,?,?)
                        """,
                        (book_id, number, f"Chapter {number}", len(text), now, now),
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
                            f"lexical-{number}",
                            len(text),
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
        set_book_voice_profile(
            self.db,
            book_id,
            narrator_voice_id="narrator",
            male_dialogue_voice_id="male",
            female_dialogue_voice_id="female",
            unknown_fallback="narrator",
            unknown_voice_id=None,
            allowed_voice_ids=ALL_VOICES,
        )
        return book_id

    def _seed_characters(self) -> dict[str, dict]:
        recurring = create_character(self.db, self.book_id, "Hứa Thanh", "recurring")
        new = create_character(self.db, self.book_id, "Tân khách", None)
        unavailable = create_character(self.db, self.book_id, "Giọng cũ", "legacy")
        conflict = create_character(self.db, self.book_id, "Đổi giọng", "conflict-a")
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO character_aliases(book_id,character_id,alias,alias_normalized,created_at)
                VALUES(?,?,?,?,?)
                """,
                (
                    self.book_id,
                    recurring["id"],
                    "Hứa đạo hữu",
                    "hứa đạo hữu",
                    utcnow(),
                ),
            )
        return {
            "recurring": recurring,
            "new": new,
            "unavailable": unavailable,
            "conflict": conflict,
        }

    def _chapter(self, chapter_number: int):
        return self.db.fetch_one(
            """
            SELECT c.id,c.active_text_revision_id,tr.content_path
            FROM chapters c
            JOIN text_revisions tr ON tr.id=c.active_text_revision_id
            WHERE c.book_id=? AND c.chapter_number=?
            """,
            (self.book_id, chapter_number),
        )

    def _plan(self, chapter_number: int, roles: dict[int, tuple[str, int | None]]) -> None:
        chapter = self._chapter(chapter_number)
        text = self.store.read_text(chapter["content_path"])
        utterances = split_utterances(text)
        assignments = []
        for utterance in utterances:
            role, character_id = roles.get(int(utterance["sequence"]), ("narrator", None))
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
        approve_plan(self.db, self.store, int(draft["id"]))

    def _seed_plans(self) -> None:
        recurring = int(self.characters["recurring"]["id"])
        new = int(self.characters["new"]["id"])
        unavailable = int(self.characters["unavailable"]["id"])
        conflict = int(self.characters["conflict"]["id"])
        self._plan(1, {2: ("character", recurring), 4: ("character", conflict)})
        self.characters["conflict"] = set_character_voice_override(
            self.db,
            conflict,
            "conflict-b",
            allowed_voice_ids=ALL_VOICES,
        )
        self._plan(
            2,
            {
                2: ("character", recurring),
                4: ("character", new),
                6: ("character", unavailable),
            },
        )
        self._plan(3, {2: ("character", new)})

    def _registry(self, start: int, end: int, catalog: EffectiveVoiceCatalog | None = None):
        return get_book_voice_registry(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=start,
            to_chapter=end,
            voice_catalog=catalog or _catalog(
                "narrator",
                "male",
                "female",
                "recurring",
                "new",
                "conflict-a",
                "conflict-b",
            ),
        )

    def test_registry_reuses_existing_book_voice_persistence_and_orders_blockers(self) -> None:
        registry = self._registry(1, 3)
        self.assertEqual(registry["schema"], "story-audio-book-voice-registry/v1")
        self.assertFalse(registry["persistence"]["migration_required"])
        self.assertEqual(
            registry["persistence"]["model"],
            "book_voice_profiles + characters.voice_override_id",
        )

        rows = registry["rows"]
        self.assertEqual(rows[0]["speaker_key"], "narrator")
        by_name = {row["display_name"]: row for row in rows}
        self.assertEqual(by_name["Hứa Thanh"]["status"], "READY")
        self.assertEqual(by_name["Hứa Thanh"]["line_count"], 2)
        self.assertIn("Hứa đạo hữu", by_name["Hứa Thanh"]["aliases"])
        self.assertEqual(by_name["Tân khách"]["status"], "NEW_CHARACTER")
        self.assertEqual(by_name["Tân khách"]["line_count"], 2)
        self.assertEqual(by_name["Giọng cũ"]["status"], "VOICE_UNAVAILABLE")
        self.assertEqual(registry["summary"]["voice_unavailable"], 1)
        self.assertEqual(
            [row["status"] for row in rows[1:4]],
            ["VOICE_UNAVAILABLE", "NEW_CHARACTER", "OVERRIDDEN"],
        )
        self.assertEqual(by_name["Đổi giọng"]["status"], "OVERRIDDEN")

    def test_conflicting_range_voice_snapshots_are_reported(self) -> None:
        conflict = int(self.characters["conflict"]["id"])
        self._plan(2, {2: ("character", conflict)})
        registry = self._registry(1, 2)
        conflict_row = next(row for row in registry["rows"] if row["display_name"] == "Đổi giọng")
        self.assertEqual(conflict_row["status"], "CONFLICT")
        self.assertEqual(
            sorted(item["voice"]["display_name"] for item in conflict_row["conflict_voices"]),
            ["Conflict A", "Conflict B"],
        )

    def test_saved_book_default_immediately_resolves_later_chapter(self) -> None:
        new_id = int(self.characters["new"]["id"])
        set_character_voice_override(
            self.db,
            new_id,
            "new",
            allowed_voice_ids=ALL_VOICES,
        )
        self._plan(3, {2: ("character", new_id)})
        registry = self._registry(3, 3)
        new_row = next(row for row in registry["rows"] if row["display_name"] == "Tân khách")
        self.assertEqual(new_row["status"], "READY")
        self.assertEqual(new_row["assignment_source"], "book default")
        self.assertEqual(new_row["saved_voice"]["display_name"], "New Character Voice")
        self.assertEqual(new_row["effective_voice"]["display_name"], "New Character Voice")


if __name__ == "__main__":
    import unittest

    unittest.main()
