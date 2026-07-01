"""Tests for offset-based manual character assignment in casting draft API."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from story_audio.casting import (
    CastingError,
    approve_plan,
    create_casting_draft,
    create_character,
    get_plan,
    split_utterances,
)
from story_audio.db import Database, utcnow
from story_audio.storage import ContentStore
from story_audio.voice_profile import set_book_voice_profile
from tests.test_recovery import make_config

# Vietnamese-style text with dialogue and narration
TEXT = 'Trời đã tối. "Xin chào," An nói. Anh khẽ đáp: "Tạm biệt." Bình im lặng.'
VOICES = {"narrator", "voice-a", "voice-b", "voice-c"}


def seed_book(root: Path):
    """Create a test book with characters and voice profile."""
    config = make_config(root)
    config.ensure_dirs()
    db = Database(config.db_path)
    db.initialize()
    store = ContentStore(config)
    content_path, content_sha = store.put_text(TEXT)
    now = utcnow()
    with db.transaction() as connection:
        book_id = int(
            connection.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                ("Book", "book.epub", "book-sha", 1, now, now),
            ).lastrowid
        )
        chapter_id = int(
            connection.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (book_id, 1, "Chapter 1", len(TEXT), now, now),
            ).lastrowid
        )
        revision_id = int(
            connection.execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                    processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (chapter_id, "reflowed", content_path, content_sha, "lexical", len(TEXT), "test", "approved", now),
            ).lastrowid
        )
        connection.execute(
            "UPDATE chapters SET active_text_revision_id=? WHERE id=?", (revision_id, chapter_id)
        )

    # Create characters
    character_an = create_character(db, book_id, "An", "voice-a", gender="male")
    character_binh = create_character(db, book_id, "Bình", "voice-b", gender="female")

    # Set up voice profile
    set_book_voice_profile(
        db, book_id,
        narrator_voice_id="narrator",
        male_dialogue_voice_id="voice-a",
        female_dialogue_voice_id="voice-b",
        unknown_fallback="narrator",
        allowed_voice_ids=VOICES,
        custom_voice_context=None,
    )

    return config, db, store, book_id, chapter_id, revision_id, character_an, character_binh


class OffsetCastingTests(unittest.TestCase):
    """Tests for offset-based casting assignments."""

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

    def test_offset_based_assignment_preserves_characters(self) -> None:
        """Test that offset-based assignments preserve narrator, An, and Bình."""
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, _book, chapter, revision, an, binh = seed_book(Path(directory))

            # Manual assignments: narrator [0, 15), An [15, 37), Bình [58, 71) (adjusted to text length)
            # TEXT = 'Trời đã tối. "Xin chào," An nói. Anh khẽ đáp: "Tạm biệt." Bình im lặng.'
            # Length is 71, not 72
            assignments = [
                {"start_offset": 0, "end_offset": 15, "role": "narrator", "character_id": None},
                {"start_offset": 15, "end_offset": 37, "role": "character", "character_id": an["id"]},
                {"start_offset": 37, "end_offset": 58, "role": "narrator", "character_id": None},
                {"start_offset": 58, "end_offset": 71, "role": "character", "character_id": binh["id"]},  # Fixed: 71 not 72
            ]

            draft = create_casting_draft(
                db, store,
                chapter_id=chapter,
                text_revision_id=revision,
                narrator_voice_id="narrator",
                assignments=assignments,
                allowed_voice_ids=VOICES,
            )

            plan = draft["plan"]
            utterances = plan["utterances"]

            # Verify assignments were applied
            an_utterances = [u for u in utterances if u.get("character_id") == an["id"]]
            binh_utterances = [u for u in utterances if u.get("character_id") == binh["id"]]
            narrator_utterances = [u for u in utterances if u.get("role") == "narrator"]

            self.assertGreater(len(an_utterances), 0, "An should have at least one utterance")
            self.assertGreater(len(binh_utterances), 0, "Bình should have at least one utterance")
            self.assertGreater(len(narrator_utterances), 0, "Narrator should have at least one utterance")

            # Verify all utterances have assignments
            self.assertEqual(
                len(utterances),
                len(an_utterances) + len(binh_utterances) + len(narrator_utterances)
            )

            # Verify character voices resolved correctly
            for u in an_utterances:
                self.assertEqual(u["resolved_voice_id"], "voice-a")
            for u in binh_utterances:
                self.assertEqual(u["resolved_voice_id"], "voice-b")

    def test_long_span_split_preserves_character(self) -> None:
        """Test that a long character span split into multiple utterances preserves character_id."""
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, book, *_rest = seed_book(Path(directory))

            # Create a long text that will split
            long_text = "A" * 300 + " B" * 300  # 603 chars, will split into at least 3 utterances
            content_path, content_sha = store.put_text(long_text)
            now = utcnow()

            with db.transaction() as connection:
                chapter_id = int(
                    connection.execute(
                        "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                        (book, 2, "Long Chapter", len(long_text), now, now),
                    ).lastrowid
                )
                revision_id = int(
                    connection.execute(
                        """INSERT INTO text_revisions(
                            chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                            processor_version,status,created_at
                        ) VALUES(?,?,?,?,?,?,?,?,?)""",
                        (chapter_id, "reflowed", content_path, content_sha, "lexical", len(long_text), "test", "approved", now),
                    ).lastrowid
                )

            character = create_character(db, book, "LongSpeaker", "voice-a")

            # Assign the entire text to one character
            assignments = [
                {"start_offset": 0, "end_offset": len(long_text), "role": "character", "character_id": character["id"]}
            ]

            draft = create_casting_draft(
                db, store,
                chapter_id=chapter_id,
                text_revision_id=revision_id,
                narrator_voice_id="narrator",
                assignments=assignments,
                allowed_voice_ids=VOICES,
            )

            utterances = draft["plan"]["utterances"]

            # Should have multiple utterances (at least 3 for 603 chars with 256 max)
            self.assertGreater(len(utterances), 2)

            # All should have the same character_id
            for u in utterances:
                self.assertEqual(u["character_id"], character["id"])
                self.assertEqual(u["role"], "character")
                self.assertEqual(u["resolved_voice_id"], "voice-a")

    def test_overlapping_spans_rejected(self) -> None:
        """Test that overlapping offset spans are rejected."""
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, _book, chapter, revision, an, binh = seed_book(Path(directory))

            # Overlapping assignments
            assignments = [
                {"start_offset": 0, "end_offset": 20, "role": "narrator", "character_id": None},
                {"start_offset": 15, "end_offset": 30, "role": "character", "character_id": an["id"]},  # Overlaps!
            ]

            with self.assertRaisesRegex(CastingError, "[Oo]verlapping"):
                create_casting_draft(
                    db, store,
                    chapter_id=chapter,
                    text_revision_id=revision,
                    narrator_voice_id="narrator",
                    assignments=assignments,
                    allowed_voice_ids=VOICES,
                )

    def test_foreign_character_rejected(self) -> None:
        """Test that a character from another book is rejected."""
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, book, chapter, revision, *_rest = seed_book(Path(directory))

            # Create another book with a character
            now = utcnow()
            with db.connect() as connection:
                other_book = int(connection.execute(
                    "INSERT INTO books(title,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?)",
                    ("Other Book", "other.epub", "other-sha", now, now),
                ).lastrowid)
            outsider = create_character(db, other_book, "Outsider", "voice-c")

            assignments = [
                {"start_offset": 0, "end_offset": 15, "role": "character", "character_id": outsider["id"]}
            ]

            with self.assertRaisesRegex(CastingError, "(does not exist|inactive|another book)"):
                create_casting_draft(
                    db, store,
                    chapter_id=chapter,
                    text_revision_id=revision,
                    narrator_voice_id="narrator",
                    assignments=assignments,
                    allowed_voice_ids=VOICES,
                )

    def test_inactive_character_rejected(self) -> None:
        """Test that an inactive character is rejected."""
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, _book, chapter, revision, an, _binh = seed_book(Path(directory))

            # Deactivate An
            with db.connect() as connection:
                connection.execute("UPDATE characters SET active=0 WHERE id=?", (an["id"],))

            assignments = [
                {"start_offset": 0, "end_offset": 15, "role": "character", "character_id": an["id"]}
            ]

            with self.assertRaisesRegex(CastingError, "(does not exist|inactive|another book)"):
                create_casting_draft(
                    db, store,
                    chapter_id=chapter,
                    text_revision_id=revision,
                    narrator_voice_id="narrator",
                    assignments=assignments,
                    allowed_voice_ids=VOICES,
                )

    def test_out_of_bounds_offset_rejected(self) -> None:
        """Test that offsets out of text bounds are rejected."""
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, _book, chapter, revision, an, _binh = seed_book(Path(directory))

            text_len = len(TEXT)
            assignments = [
                {"start_offset": 0, "end_offset": text_len + 100, "role": "narrator", "character_id": None}
            ]

            with self.assertRaisesRegex(CastingError, "out of.*bounds"):
                create_casting_draft(
                    db, store,
                    chapter_id=chapter,
                    text_revision_id=revision,
                    narrator_voice_id="narrator",
                    assignments=assignments,
                    allowed_voice_ids=VOICES,
                )

    def test_invalid_offset_order_rejected(self) -> None:
        """Test that start_offset >= end_offset is rejected."""
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, _book, chapter, revision, *_rest = seed_book(Path(directory))

            assignments = [
                {"start_offset": 20, "end_offset": 10, "role": "narrator", "character_id": None}
            ]

            with self.assertRaisesRegex(CastingError, "start_offset.*less than.*end_offset"):
                create_casting_draft(
                    db, store,
                    chapter_id=chapter,
                    text_revision_id=revision,
                    narrator_voice_id="narrator",
                    assignments=assignments,
                    allowed_voice_ids=VOICES,
                )

    def test_mixed_offset_and_utterance_id_rejected(self) -> None:
        """Test that mixing offset and utterance_id in same assignment is rejected."""
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, _book, chapter, revision, *_rest = seed_book(Path(directory))

            utterances = split_utterances(TEXT)
            assignments = [
                {
                    "utterance_id": utterances[0]["utterance_id"],
                    "start_offset": 0,
                    "end_offset": 15,
                    "role": "narrator",
                    "character_id": None
                }
            ]

            with self.assertRaisesRegex(CastingError, "cannot specify both"):
                create_casting_draft(
                    db, store,
                    chapter_id=chapter,
                    text_revision_id=revision,
                    narrator_voice_id="narrator",
                    assignments=assignments,
                    allowed_voice_ids=VOICES,
                )

    def test_utterance_id_based_assignment_still_works(self) -> None:
        """Test backward compatibility: utterance_id-based assignments still work."""
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, _book, chapter, revision, an, binh = seed_book(Path(directory))

            utterances = split_utterances(TEXT)

            # Use utterance_id (existing flow)
            assignments = [
                {"utterance_id": utterances[0]["utterance_id"], "role": "narrator", "character_id": None},
                {"utterance_id": utterances[1]["utterance_id"], "role": "character", "character_id": an["id"]},
            ]

            draft = create_casting_draft(
                db, store,
                chapter_id=chapter,
                text_revision_id=revision,
                narrator_voice_id="narrator",
                assignments=assignments,
                allowed_voice_ids=VOICES,
            )

            result_utterances = draft["plan"]["utterances"]

            # Find the assigned utterances
            u0 = next(u for u in result_utterances if u["utterance_id"] == utterances[0]["utterance_id"])
            u1 = next(u for u in result_utterances if u["utterance_id"] == utterances[1]["utterance_id"])

            self.assertEqual(u0["role"], "narrator")
            self.assertIsNone(u0["character_id"])
            self.assertEqual(u1["role"], "character")
            self.assertEqual(u1["character_id"], an["id"])

    def test_empty_assignments_auto_draft(self) -> None:
        """Test that empty assignments (auto-draft) still works."""
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, _book, chapter, revision, *_rest = seed_book(Path(directory))

            draft = create_casting_draft(
                db, store,
                chapter_id=chapter,
                text_revision_id=revision,
                narrator_voice_id="narrator",
                assignments=[],  # Empty!
                allowed_voice_ids=VOICES,
            )

            utterances = draft["plan"]["utterances"]

            # All should default to narrator
            for u in utterances:
                self.assertEqual(u["resolved_voice_id"], "narrator")

    def test_narrator_cannot_have_character_id(self) -> None:
        """Test that narrator role with character_id is rejected."""
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, _book, chapter, revision, an, _binh = seed_book(Path(directory))

            assignments = [
                {"start_offset": 0, "end_offset": 15, "role": "narrator", "character_id": an["id"]}
            ]

            with self.assertRaisesRegex(CastingError, "narrator.*cannot.*character_id"):
                create_casting_draft(
                    db, store,
                    chapter_id=chapter,
                    text_revision_id=revision,
                    narrator_voice_id="narrator",
                    assignments=assignments,
                    allowed_voice_ids=VOICES,
                )

    def test_character_role_requires_character_id(self) -> None:
        """Test that character role without character_id is rejected."""
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, _book, chapter, revision, *_rest = seed_book(Path(directory))

            assignments = [
                {"start_offset": 0, "end_offset": 15, "role": "character", "character_id": None}
            ]

            with self.assertRaisesRegex(CastingError, "character.*requires.*character_id"):
                create_casting_draft(
                    db, store,
                    chapter_id=chapter,
                    text_revision_id=revision,
                    narrator_voice_id="narrator",
                    assignments=assignments,
                    allowed_voice_ids=VOICES,
                )

    def test_approved_plan_immutable(self) -> None:
        """Test that approved plans remain immutable with new offset-based API."""
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, _book, chapter, revision, an, _binh = seed_book(Path(directory))

            assignments = [
                {"start_offset": 0, "end_offset": 15, "role": "character", "character_id": an["id"]}
            ]

            draft = create_casting_draft(
                db, store,
                chapter_id=chapter,
                text_revision_id=revision,
                narrator_voice_id="narrator",
                assignments=assignments,
                allowed_voice_ids=VOICES,
            )

            approved = approve_plan(db, store, draft["id"])
            sha_before = approved["plan_sha256"]

            # Approve again
            same = approve_plan(db, store, approved["id"])
            self.assertEqual(same["plan_sha256"], sha_before)


if __name__ == "__main__":
    unittest.main()
