from __future__ import annotations

import unittest

from story_audio.chapter_voice_overrides import apply_chapter_voice_override
from story_audio.db import Database, utcnow
from story_audio.files import sha256_text
from story_audio.range_readiness import get_range_readiness
from story_audio.speaker_state import (
    ANALYSIS_REQUIRED,
    APPROVED_CURRENT,
    CURRENT_REVIEW_REQUIRED,
    NO_REVIEW_REQUIRED,
    resolve_chapter_speaker_state,
)
from story_audio.storage import ContentStore
from story_audio.voice_eligibility import EffectiveVoiceCatalog
from story_audio.voice_profile import set_book_voice_profile
from tests.base import IsolatedTestCase


class CurrentSpeakerStateTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config.ensure_dirs()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        now = utcnow()
        with self.db.transaction() as connection:
            self.book_id = int(
                connection.execute(
                    """
                    INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at)
                    VALUES(?,?,?,?,?,?)
                    """,
                    ("Speaker State", "speaker-state.epub", "speaker-state", 1, now, now),
                ).lastrowid
            )

    def _chapter(self, text: str) -> tuple[dict, int]:
        now = utcnow()
        path, digest = self.store.put_text(text)
        with self.db.transaction() as connection:
            chapter_id = int(
                connection.execute(
                    """
                    INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at)
                    VALUES(?,?,?,?,?,?)
                    """,
                    (self.book_id, 1, "Chapter 1", len(text), now, now),
                ).lastrowid
            )
            revision_id = int(
                connection.execute(
                    """
                    INSERT INTO text_revisions(
                        chapter_id,kind,content_path,content_sha256,lexical_sha256,
                        char_count,processor_version,status,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        chapter_id,
                        "reflowed",
                        path,
                        digest,
                        sha256_text(text),
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
        chapter = dict(
            self.db.fetch_one(
                "SELECT id,book_id,chapter_number,active_text_revision_id FROM chapters WHERE id=?",
                (chapter_id,),
            )
        )
        return chapter, revision_id

    def _draft(self, chapter_id: int, revision_id: int, *, target_count: int = 0) -> int:
        now = utcnow()
        with self.db.transaction() as connection:
            return int(
                connection.execute(
                    """
                    INSERT INTO speaker_assignment_drafts(
                        book_id,chapter_id,text_revision_id,input_fingerprint,
                        character_bible_fingerprint,model_id,prompt_version,response_schema,
                        mode,status,content_path,content_sha256,target_count,valid_count,
                        invalid_count,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        self.book_id,
                        chapter_id,
                        revision_id,
                        "input",
                        "bible",
                        "gemini-2.5-flash",
                        "speaker-assignment-v2",
                        "story-audio-speaker-assignment-draft/v1",
                        "unassigned_only",
                        "generated",
                        "speaker-state/test.json",
                        "sha",
                        target_count,
                        target_count,
                        0,
                        now,
                    ),
                ).lastrowid
            )

    def test_stale_zero_target_draft_is_history_only(self) -> None:
        chapter, old_revision = self._chapter("Narration only.")
        old_path, old_digest = self.store.put_text("Old narration.")
        now = utcnow()
        with self.db.transaction() as connection:
            old_revision = int(
                connection.execute(
                    """
                    INSERT INTO text_revisions(
                        chapter_id,kind,content_path,content_sha256,lexical_sha256,
                        char_count,processor_version,status,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        chapter["id"],
                        "reflowed",
                        old_path,
                        old_digest,
                        sha256_text("Old narration."),
                        len("Old narration."),
                        "test",
                        "approved",
                        now,
                    ),
                ).lastrowid
            )
            connection.execute(
                "UPDATE chapters SET active_text_revision_id=? WHERE id=?",
                (chapter["active_text_revision_id"], chapter["id"]),
            )
        self._draft(chapter["id"], old_revision)
        state = resolve_chapter_speaker_state(self.db, self.store, chapter)
        self.assertEqual(state["status"], NO_REVIEW_REQUIRED)
        self.assertEqual(state["unresolved_count"], 0)
        self.assertTrue(state["history"][0]["stale"])
        self.assertIn("không khớp", state["history"][0]["impact_reason"])

        readiness = get_range_readiness(
            self.db,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=1,
            store=self.store,
        )
        item = readiness["chapters"][0]
        self.assertNotEqual(item["state"], "SPEAKER_EXCEPTIONS")
        self.assertEqual(item["speaker_state"]["status"], NO_REVIEW_REQUIRED)
        self.assertFalse(any("Speaker Assignment" in blocker for blocker in item["blockers"]))

    def test_current_unresolved_without_draft_requires_analysis(self) -> None:
        chapter, _ = self._chapter("Narration.\n- Hold the gate.")
        state = resolve_chapter_speaker_state(self.db, self.store, chapter)
        self.assertEqual(state["status"], ANALYSIS_REQUIRED)
        self.assertEqual(state["unresolved_count"], 1)

    def test_current_draft_with_target_requires_review(self) -> None:
        chapter, revision_id = self._chapter("Narration.\n- Hold the gate.")
        self._draft(chapter["id"], revision_id, target_count=1)
        state = resolve_chapter_speaker_state(self.db, self.store, chapter)
        self.assertEqual(state["status"], CURRENT_REVIEW_REQUIRED)
        self.assertEqual(state["unresolved_count"], 1)

    def test_approved_current_plan_wins_over_stale_history(self) -> None:
        chapter, revision_id = self._chapter("Narration.\n- Hold the gate.")
        now = utcnow()
        content_path, digest = self.store.put_json(
            {
                "schema": "story-audio-casting-plan/v1",
                "text_revision_id": revision_id,
                "utterances": [],
            },
            namespace="casting",
        )
        with self.db.transaction() as connection:
            connection.execute(
                """
                INSERT INTO casting_plans(
                    chapter_id,text_revision_id,plan_revision,status,content_path,
                    plan_sha256,narrator_voice_id,created_at,approved_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (chapter["id"], revision_id, 1, "approved", content_path, digest, "narrator", now, now),
            )
        state = resolve_chapter_speaker_state(self.db, self.store, chapter)
        self.assertEqual(state["status"], APPROVED_CURRENT)
        self.assertEqual(state["approved_source"], "casting_plan")

    def test_narrator_only_voice_override_creates_current_plan_without_old_draft(self) -> None:
        chapter, revision_id = self._chapter("Narration only.")
        set_book_voice_profile(
            self.db,
            self.book_id,
            narrator_voice_id="narrator",
            male_dialogue_voice_id="male",
            female_dialogue_voice_id="female",
            unknown_fallback="narrator",
            unknown_voice_id=None,
            allowed_voice_ids={"narrator", "male", "female"},
        )
        catalog = EffectiveVoiceCatalog.from_ids("narrator", "male", "female")
        result = apply_chapter_voice_override(
            self.db,
            self.store,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=1,
            speaker_key="narrator",
            operation="set",
            voice_id="narrator",
            voice_catalog=catalog,
            idempotency_key="speaker-state-narrator-only-1",
        )
        self.assertEqual(result["reused_count"], 0)
        plan = self.db.fetch_one(
            "SELECT text_revision_id,status FROM casting_plans WHERE chapter_id=? ORDER BY id DESC LIMIT 1",
            (chapter["id"],),
        )
        self.assertEqual(int(plan["text_revision_id"]), revision_id)
        self.assertEqual(plan["status"], "approved")


if __name__ == "__main__":
    unittest.main()
