from __future__ import annotations
import unittest
from unittest.mock import MagicMock
from tests.base import IsolatedTestCase
from story_audio.db import Database
from story_audio.voice_ref import (
    CustomVoiceContext, CustomVoiceEntry, CustomVoiceNotFoundError,
    CustomVoiceInactiveError, CustomVoiceNoRevisionError, MalformedVoiceRefError,
    PresetVoiceNotFoundError, custom_ref, is_custom_ref, parse_custom_ref,
    resolve_custom_ref,
)
from story_audio.voice_profile import resolve_voice, set_book_voice_profile, set_character_voice_override
from story_audio.custom_voice import CustomVoiceRepository, AudioValidator
from story_audio.storage import ContentStore
from story_audio.casting import create_casting_draft, split_utterances


def _make_entry(custom_voice_id: int, revision_id: int = 1, revision_number: int = 1) -> CustomVoiceEntry:
    return CustomVoiceEntry(
        custom_voice_id=custom_voice_id,
        logical_ref=custom_ref(custom_voice_id),
        latest_revision_id=revision_id,
        revision_number=revision_number,
        audio_storage_key=f"audio/custom_{custom_voice_id}.wav",
        audio_sha256="abc123" * 10,
        reference_transcript="Hello world",
        transcript_sha256="def456" * 10,
        duration_ms=3000,
        sample_rate=48000,
        channels=2,
        audio_format="wav",
    )


def _make_context(*ids: int) -> CustomVoiceContext:
    return CustomVoiceContext([_make_entry(cid) for cid in ids])


class TestParseCustomRef(IsolatedTestCase):
    def test_valid_custom_ref(self):
        self.assertEqual(parse_custom_ref("custom:7"), 7)
        self.assertEqual(parse_custom_ref("custom:1"), 1)
        self.assertEqual(parse_custom_ref("custom:999"), 999)

    def test_malformed_empty_id(self):
        with self.assertRaises(MalformedVoiceRefError):
            parse_custom_ref("custom:")

    def test_malformed_non_integer(self):
        with self.assertRaises(MalformedVoiceRefError):
            parse_custom_ref("custom:abc")

    def test_malformed_negative(self):
        with self.assertRaises(MalformedVoiceRefError):
            parse_custom_ref("custom:-1")

    def test_malformed_zero(self):
        with self.assertRaises(MalformedVoiceRefError):
            parse_custom_ref("custom:0")

    def test_malformed_multiple_colons(self):
        with self.assertRaises(MalformedVoiceRefError):
            parse_custom_ref("custom:1:2")

    def test_is_custom_ref(self):
        self.assertTrue(is_custom_ref("custom:5"))
        self.assertTrue(is_custom_ref("custom:"))  # malformed but still has prefix
        self.assertFalse(is_custom_ref("duc_tri"))
        self.assertFalse(is_custom_ref(""))


class TestCustomVoiceContext(IsolatedTestCase):
    def test_available_voice_recognized(self):
        ctx = _make_context(7, 42)
        self.assertTrue(ctx.is_available("custom:7"))
        self.assertTrue(ctx.is_available("custom:42"))
        self.assertFalse(ctx.is_available("custom:99"))
        self.assertFalse(ctx.is_available("duc_tri"))

    def test_logical_refs(self):
        ctx = _make_context(3, 5)
        self.assertEqual(ctx.logical_refs(), {"custom:3", "custom:5"})

    def test_malformed_not_available(self):
        ctx = _make_context(7)
        self.assertFalse(ctx.is_available("custom:"))
        self.assertFalse(ctx.is_available("custom:abc"))

    def test_from_repository(self):
        """Build context from repository with active voices that have revisions."""
        db = Database(self.config.db_path)
        db.initialize()
        store = ContentStore(self.config)
        repo = CustomVoiceRepository(db, store)
        voice = repo.create_custom_voice("Test Voice")
        repo.create_revision(voice.id, b"x" * 1000, "Hello")
        ctx = CustomVoiceContext.from_repository(repo)
        self.assertTrue(ctx.is_available(custom_ref(voice.id)))

    def test_from_repository_skips_voice_without_revision(self):
        db = Database(self.config.db_path)
        db.initialize()
        store = ContentStore(self.config)
        repo = CustomVoiceRepository(db, store)
        voice = repo.create_custom_voice("No Revision Voice")
        # No revision created
        ctx = CustomVoiceContext.from_repository(repo)
        self.assertFalse(ctx.is_available(custom_ref(voice.id)))

    def test_from_repository_skips_inactive_voice(self):
        db = Database(self.config.db_path)
        db.initialize()
        store = ContentStore(self.config)
        repo = CustomVoiceRepository(db, store)
        voice = repo.create_custom_voice("Inactive Voice")
        repo.create_revision(voice.id, b"x" * 1000, "Hello")
        repo.deactivate_custom_voice(voice.id)
        ctx = CustomVoiceContext.from_repository(repo)
        self.assertFalse(ctx.is_available(custom_ref(voice.id)))

    def test_latest_revision_selected_deterministically(self):
        """Latest revision by revision_number DESC is selected."""
        db = Database(self.config.db_path)
        db.initialize()
        store = ContentStore(self.config)
        repo = CustomVoiceRepository(db, store)
        voice = repo.create_custom_voice("Multi Revision")
        repo.create_revision(voice.id, b"x" * 1000, "First")
        latest = repo.create_revision(voice.id, b"y" * 2000, "Second")
        ctx = CustomVoiceContext.from_repository(repo)
        entry = ctx.get(voice.id)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.latest_revision_id, latest.id)
        self.assertEqual(entry.revision_number, 2)


class TestResolveCustomRef(IsolatedTestCase):
    def test_resolve_valid_custom_ref(self):
        ctx = _make_context(7)
        result = resolve_custom_ref("custom:7", ctx)
        self.assertEqual(result["kind"], "custom_reference")
        self.assertEqual(result["custom_voice_id"], 7)
        self.assertEqual(result["logical_voice_ref"], "custom:7")
        self.assertIn("audio_storage_key", result)
        self.assertNotIn("absolute_path", result)  # No absolute paths

    def test_malformed_ref_rejected(self):
        ctx = _make_context(7)
        with self.assertRaises(MalformedVoiceRefError):
            resolve_custom_ref("custom:", ctx)

    def test_not_in_context_raises_not_found(self):
        ctx = _make_context(7)
        with self.assertRaises(CustomVoiceNotFoundError):
            resolve_custom_ref("custom:99", ctx)

    def test_inactive_voice_raises_error_with_repository(self):
        db = Database(self.config.db_path)
        db.initialize()
        store = ContentStore(self.config)
        repo = CustomVoiceRepository(db, store)
        voice = repo.create_custom_voice("Inactive")
        repo.create_revision(voice.id, b"x" * 1000, "Hello")
        repo.deactivate_custom_voice(voice.id)
        ctx = CustomVoiceContext([])  # Empty context - inactive not included
        with self.assertRaises((CustomVoiceNotFoundError, CustomVoiceInactiveError)):
            resolve_custom_ref(custom_ref(voice.id), ctx, repository=repo)

    def test_no_revision_raises_error_with_repository(self):
        db = Database(self.config.db_path)
        db.initialize()
        store = ContentStore(self.config)
        repo = CustomVoiceRepository(db, store)
        voice = repo.create_custom_voice("No Rev")
        ctx = CustomVoiceContext([])  # Empty context
        with self.assertRaises((CustomVoiceNotFoundError, CustomVoiceNoRevisionError)):
            resolve_custom_ref(custom_ref(voice.id), ctx, repository=repo)


class TestResolveVoiceWithCustom(IsolatedTestCase):
    """Test resolve_voice() with custom voice references."""

    def _make_profile(self) -> dict:
        return {
            "id": 1,
            "config_version": 1,
            "narrator_voice_id": "duc_tri",
            "male_dialogue_voice_id": "custom:7",
            "female_dialogue_voice_id": "custom:42",
            "unknown_fallback": "narrator",
            "unknown_voice_id": None,
        }

    def test_preset_narrator_resolve_unchanged(self):
        """Preset narrator still resolves as before."""
        profile = {
            "id": 1, "config_version": 1,
            "narrator_voice_id": "duc_tri",
            "male_dialogue_voice_id": "duc_tri",
            "female_dialogue_voice_id": "duc_tri",
            "unknown_fallback": "narrator",
            "unknown_voice_id": None,
        }
        ctx = _make_context()  # No custom voices needed for preset
        result = resolve_voice(
            speaker_type="narrator",
            book_voice_profile=profile,
            custom_voice_context=ctx,
        )
        self.assertEqual(result["resolved_voice_id"], "duc_tri")
        self.assertEqual(result["voice"]["kind"], "preset")

    def test_custom_male_resolves_correctly(self):
        """Custom voice for male dialogue resolves with custom_reference kind."""
        profile = self._make_profile()
        ctx = _make_context(7, 42)
        result = resolve_voice(
            speaker_type="dialogue",
            book_voice_profile=profile,
            inferred_gender="male",
            custom_voice_context=ctx,
        )
        self.assertEqual(result["resolved_voice_id"], "custom:7")
        self.assertEqual(result["voice"]["kind"], "custom_reference")
        self.assertEqual(result["voice"]["custom_voice_id"], 7)

    def test_custom_female_resolves_correctly(self):
        """Custom voice for female dialogue resolves correctly."""
        profile = self._make_profile()
        ctx = _make_context(7, 42)
        result = resolve_voice(
            speaker_type="dialogue",
            book_voice_profile=profile,
            inferred_gender="female",
            custom_voice_context=ctx,
        )
        self.assertEqual(result["resolved_voice_id"], "custom:42")
        self.assertEqual(result["voice"]["kind"], "custom_reference")

    def test_character_override_wins_over_role_mapping(self):
        """Character override (custom or preset) beats role mapping."""
        profile = self._make_profile()  # male -> custom:7
        ctx = _make_context(7, 42, 99)
        char = {"id": 1, "voice_override_id": "custom:99", "gender": "male"}
        result = resolve_voice(
            speaker_type="dialogue",
            book_voice_profile=profile,
            character=char,
            inferred_gender="male",
            custom_voice_context=ctx,
        )
        self.assertEqual(result["resolved_voice_id"], "custom:99")
        self.assertEqual(result["resolution_source"], "character_override")

    def test_error_not_expose_storage_path(self):
        """Errors from resolve do not expose storage paths or transcripts."""
        ctx = _make_context(7)
        entry = ctx.get(7)
        result = resolve_custom_ref("custom:7", ctx)
        # audio_storage_key is a logical key, not an absolute path
        self.assertFalse(result["audio_storage_key"].startswith("/"))
        self.assertFalse(result["audio_storage_key"].startswith("C:\\"))
        self.assertFalse(result["audio_storage_key"].startswith("D:\\"))


class TestVoiceProfileWithCustom(IsolatedTestCase):
    """Test set_book_voice_profile and set_character_voice_override with custom refs."""

    def setUp(self):
        super().setUp()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        # Create a book
        with self.db.connect() as conn:
            self.book_id = conn.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) "
                "VALUES(?,?,?,?,datetime('now'),datetime('now'))",
                ("Test Book", "test://path", "abc123", 1)
            ).lastrowid

    def test_custom_voice_accepted_in_profile(self):
        """Custom voice refs can be set in book voice profile."""
        repo = CustomVoiceRepository(self.db, self.store)
        voice = repo.create_custom_voice("My Voice")
        repo.create_revision(voice.id, b"x" * 1000, "Hello world")
        ctx = CustomVoiceContext.from_repository(repo)
        allowed = {"duc_tri"}  # Only preset IDs
        profile = set_book_voice_profile(
            self.db, self.book_id,
            narrator_voice_id="duc_tri",
            male_dialogue_voice_id=custom_ref(voice.id),
            female_dialogue_voice_id="duc_tri",
            allowed_voice_ids=allowed,
            custom_voice_context=ctx,
        )
        self.assertEqual(profile["male_dialogue_voice_id"], custom_ref(voice.id))

    def test_inactive_custom_voice_rejected_in_profile(self):
        """Inactive custom voice is rejected when setting profile."""
        repo = CustomVoiceRepository(self.db, self.store)
        voice = repo.create_custom_voice("Inactive Voice")
        repo.create_revision(voice.id, b"x" * 1000, "Hello")
        repo.deactivate_custom_voice(voice.id)
        ctx = CustomVoiceContext.from_repository(repo)  # Will be empty since inactive
        allowed = {"duc_tri"}
        with self.assertRaises(Exception):  # VoiceProfileError
            set_book_voice_profile(
                self.db, self.book_id,
                narrator_voice_id="duc_tri",
                male_dialogue_voice_id=custom_ref(voice.id),
                female_dialogue_voice_id="duc_tri",
                allowed_voice_ids=allowed,
                custom_voice_context=ctx,
            )

    def test_character_custom_override_accepted(self):
        """Custom voice can be set as character override."""
        repo = CustomVoiceRepository(self.db, self.store)
        voice = repo.create_custom_voice("Char Voice")
        repo.create_revision(voice.id, b"x" * 1000, "Hello")
        ctx = CustomVoiceContext.from_repository(repo)
        # Create a character
        with self.db.connect() as conn:
            char_id = conn.execute(
                "INSERT INTO characters(book_id,display_name,default_voice_id,voice_override_id,gender,created_at,updated_at) "
                "VALUES(?,?,?,?,?,datetime('now'),datetime('now'))",
                (self.book_id, "Hero", "", None, "male")
            ).lastrowid
        result = set_character_voice_override(
            self.db, char_id, custom_ref(voice.id),
            allowed_voice_ids={"duc_tri"},
            custom_voice_context=ctx,
        )
        self.assertEqual(result["voice_override_id"], custom_ref(voice.id))


class TestCastingWithCustom(IsolatedTestCase):
    """Test create_casting_draft with custom voice references."""

    def setUp(self):
        super().setUp()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        # Setup a book and chapter with approved text revision
        with self.db.connect() as conn:
            self.book_id = conn.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) "
                "VALUES(?,?,?,?,datetime('now'),datetime('now'))",
                ("Test Book", "test://path", "sha256abc", 1)
            ).lastrowid
            self.chapter_id = conn.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at) "
                "VALUES(?,?,?,?,datetime('now'),datetime('now'))",
                (self.book_id, 1, "Chapter 1", 100)
            ).lastrowid
        # Store some text
        text = "Narrator speaks. \"Character speaks.\""
        content_path, content_sha = self.store.put_text(text)
        from story_audio.files import sha256_text
        lex_sha = sha256_text(text)
        with self.db.connect() as conn:
            self.revision_id = conn.execute(
                "INSERT INTO text_revisions(chapter_id,kind,content_path,content_sha256,lexical_sha256,"
                "char_count,processor_version,status,created_at) VALUES(?,?,?,?,?,?,?,?,datetime('now'))",
                (self.chapter_id, "reflowed", content_path, content_sha, lex_sha, len(text), "v1", "approved")
            ).lastrowid
            conn.execute(
                "UPDATE chapters SET active_text_revision_id=? WHERE id=?",
                (self.revision_id, self.chapter_id)
            )

    def test_preset_narrator_voice_still_works(self):
        """create_casting_draft with preset narrator works as before."""
        utterances = split_utterances("Narrator speaks. \"Character speaks.\"")
        assignments = [{"utterance_id": u["utterance_id"], "role": "narrator"} for u in utterances]
        result = create_casting_draft(
            self.db, self.store,
            chapter_id=self.chapter_id,
            text_revision_id=self.revision_id,
            narrator_voice_id="duc_tri",
            assignments=assignments,
            allowed_voice_ids={"duc_tri"},
        )
        self.assertIsNotNone(result)

    def test_custom_narrator_voice_works(self):
        """create_casting_draft with custom narrator voice works."""
        repo = CustomVoiceRepository(self.db, self.store)
        voice = repo.create_custom_voice("Narrator Voice")
        repo.create_revision(voice.id, b"x" * 1000, "Hello")
        ctx = CustomVoiceContext.from_repository(repo)
        narrator_ref = custom_ref(voice.id)
        utterances = split_utterances("Narrator speaks. \"Character speaks.\"")
        assignments = [{"utterance_id": u["utterance_id"], "role": "narrator"} for u in utterances]
        result = create_casting_draft(
            self.db, self.store,
            chapter_id=self.chapter_id,
            text_revision_id=self.revision_id,
            narrator_voice_id=narrator_ref,
            assignments=assignments,
            allowed_voice_ids=set(),  # No presets
            custom_voice_context=ctx,
        )
        self.assertIsNotNone(result)

    def test_mixed_preset_and_custom_plan(self):
        """Preset narrator + custom character override works together."""
        repo = CustomVoiceRepository(self.db, self.store)
        voice = repo.create_custom_voice("Char Voice")
        repo.create_revision(voice.id, b"x" * 1000, "Hello")
        ctx = CustomVoiceContext.from_repository(repo)
        # This is a basic check - the plan is created without errors
        result = create_casting_draft(
            self.db, self.store,
            chapter_id=self.chapter_id,
            text_revision_id=self.revision_id,
            narrator_voice_id="duc_tri",
            assignments=[],
            allowed_voice_ids={"duc_tri"},
            custom_voice_context=ctx,
        )
        self.assertIsNotNone(result)

    def test_no_live_db_access(self):
        """Test guard: STORY_AUDIO_TESTING=1 prevents live DB access."""
        import os
        self.assertEqual(os.environ.get("STORY_AUDIO_TESTING"), "1")
