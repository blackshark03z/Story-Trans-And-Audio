from __future__ import annotations

from typing import Any

from story_audio.book_voice_registry import get_book_voice_registry
from story_audio.casting import approve_plan, create_casting_draft, create_character, split_utterances
from story_audio.db import Database, utcnow
from story_audio.speaker_review_suggestions import (
    SpeakerReviewSuggestionError,
    generate_speaker_review_suggestions,
    get_speaker_review_queue,
    record_speaker_suggestion_decision,
    validate_speaker_review_response,
)
from story_audio.storage import ContentStore
from story_audio.voice_eligibility import EffectiveVoiceCatalog
from story_audio.voice_profile import set_book_voice_profile, set_character_voice_override
from tests.base import IsolatedTestCase


ALL_VOICES = {"narrator", "male", "female", "commander", "new"}


def _catalog() -> EffectiveVoiceCatalog:
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
                for voice_id in sorted(ALL_VOICES)
            ]
        }
    )


class SpeakerReviewSuggestionTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config.ensure_dirs()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        (self.config.root / "secrets" / "gemini_api_key.txt").write_text(
            "fake-gemini-key\n",
            encoding="utf-8",
        )
        self.book_id = self._seed_book()
        self.commander = create_character(self.db, self.book_id, "Gate Commander", None)
        set_character_voice_override(
            self.db,
            int(self.commander["id"]),
            "commander",
            allowed_voice_ids=ALL_VOICES,
        )
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

    def _seed_book(self) -> int:
        now = utcnow()
        with self.db.transaction() as connection:
            book_id = int(
                connection.execute(
                    """
                    INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at)
                    VALUES(?,?,?,?,?,?)
                    """,
                    ("Speaker Review Fixture", "fixture.epub", "fixture-sha", 2, now, now),
                ).lastrowid
            )
        for number in (1, 2):
            self._seed_chapter(book_id, number)
        return book_id

    def _seed_chapter(self, book_id: int, number: int) -> None:
        now = utcnow()
        text = (
            f"Chapter {number} opens. "
            f"- Hold the gate for chapter {number}. "
            f"The soldiers waited. "
            f"- Report the red light for chapter {number}. "
            f"Chapter {number} closes."
        )
        content_path, content_sha = self.store.put_text(text)
        with self.db.transaction() as connection:
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
        utterances = split_utterances(text)
        draft = create_casting_draft(
            self.db,
            self.store,
            chapter_id=chapter_id,
            text_revision_id=revision_id,
            narrator_voice_id="narrator",
            assignments=[
                {
                    "utterance_id": utterance["utterance_id"],
                    "role": "narrator",
                    "character_id": None,
                }
                for utterance in utterances
            ],
            allowed_voice_ids=ALL_VOICES,
        )
        approve_plan(self.db, self.store, int(draft["id"]))

    def _registry(self) -> dict[str, Any]:
        return get_book_voice_registry(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=2,
            skip_completed=False,
            voice_catalog=_catalog(),
        )

    def _suggestion(self, key: str, chapter: int, index: int) -> dict[str, Any]:
        if index == 0:
            return {
                "unresolved_key": key,
                "chapter_number": chapter,
                "proposed_resolution": "EXISTING_CHARACTER",
                "existing_character_id": int(self.commander["id"]),
                "proposed_character_name": None,
                "proposed_aliases": ["gate leader"],
                "confidence": "HIGH",
                "confidence_score": 0.93,
                "evidence_summary": "The dialogue is an order from the gate leader.",
                "context_evidence": ["Hold the gate"],
                "alternative_candidates": [],
                "continuity_notes": "Matches the known commander role.",
                "proposed_voice_handling": "INHERIT_EXISTING_CONFIGURATION",
                "suggested_voice_id": None,
                "voice_rationale": "Use the existing saved character voice.",
                "warnings": [],
            }
        return {
            "unresolved_key": key,
            "chapter_number": chapter,
            "proposed_resolution": "NEEDS_HUMAN_DECISION",
            "existing_character_id": None,
            "proposed_character_name": None,
            "proposed_aliases": [],
            "confidence": "LOW",
            "confidence_score": 0.25,
            "evidence_summary": "The speaker is not named in nearby context.",
            "context_evidence": ["Report the red light"],
            "alternative_candidates": [],
            "continuity_notes": "",
            "proposed_voice_handling": "LEAVE_UNASSIGNED",
            "suggested_voice_id": None,
            "voice_rationale": "Insufficient textual evidence.",
            "warnings": ["Needs human review"],
        }

    def _provider(self, **kwargs: Any) -> dict[str, Any]:
        request_data = kwargs["request_data"]
        suggestions = [
            self._suggestion(
                str(target["unresolved_key"]),
                int(target["chapter_number"]),
                index,
            )
            for index, target in enumerate(request_data["targets"])
        ]
        return {
            "response": {
                "schema": "story-audio-gemini-speaker-review-suggestions/v1",
                "suggestions": suggestions,
            },
            "usage_metadata": {"promptTokenCount": 12, "candidatesTokenCount": 6},
        }

    def test_validate_response_requires_exact_schema_and_chapter_number(self) -> None:
        with self.assertRaises(SpeakerReviewSuggestionError):
            validate_speaker_review_response(
                {
                    "schema": "story-audio-gemini-speaker-review-suggestions/v1",
                    "suggestions": [
                        {
                            key: value
                            for key, value in self._suggestion("u1", 1, 0).items()
                            if key != "chapter_number"
                        }
                    ],
                },
                target_keys=["u1"],
                target_chapter_numbers_by_key={"u1": 1},
                allowed_character_ids={int(self.commander["id"])},
                selectable_voice_ids=ALL_VOICES,
            )

    def test_generate_records_review_queue_without_business_mutation_and_reuses_it(self) -> None:
        registry = self._registry()
        unresolved_keys = [
            row["speaker_key"]
            for row in registry["rows"]
            if row["status"] == "UNRESOLVED_DIALOGUE"
        ]
        before = {
            table: int(self.db.fetch_one(f"SELECT COUNT(*) AS count FROM {table}")["count"])
            for table in ("jobs", "artifacts", "characters", "casting_plans")
        }

        result = generate_speaker_review_suggestions(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=2,
            skip_completed=False,
            registry=registry,
            voice_catalog=_catalog(),
            unresolved_keys=unresolved_keys,
            provider=self._provider,
            idempotency_key="speaker-review-test-0001",
        )
        reused = generate_speaker_review_suggestions(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=2,
            skip_completed=False,
            registry=registry,
            voice_catalog=_catalog(),
            unresolved_keys=unresolved_keys,
            provider=self._provider,
            idempotency_key="speaker-review-test-0001",
        )

        self.assertEqual(result["target_count"], len(unresolved_keys))
        self.assertEqual(result["request_count"], 1)
        self.assertFalse(result["reused"])
        self.assertTrue(reused["reused"])
        self.assertEqual(reused["analysis_run_id"], result["analysis_run_id"])
        self.assertEqual(
            result["suggestions"][0]["effective_inherited_voice"]["id"],
            "commander",
        )
        after = {
            table: int(self.db.fetch_one(f"SELECT COUNT(*) AS count FROM {table}")["count"])
            for table in ("jobs", "artifacts", "characters", "casting_plans")
        }
        self.assertEqual(after, before)

    def test_malformed_provider_response_preserves_unresolved_state(self) -> None:
        registry = self._registry()
        unresolved_keys = [
            row["speaker_key"]
            for row in registry["rows"]
            if row["status"] == "UNRESOLVED_DIALOGUE"
        ]

        def bad_provider(**_kwargs: Any) -> dict[str, Any]:
            return {
                "response": {
                    "schema": "story-audio-gemini-speaker-review-suggestions/v1",
                    "suggestions": [],
                }
            }

        with self.assertRaises(SpeakerReviewSuggestionError):
            generate_speaker_review_suggestions(
                self.db,
                self.store,
                self.config,
                book_id=self.book_id,
                from_chapter=1,
                to_chapter=2,
                skip_completed=False,
                registry=registry,
                voice_catalog=_catalog(),
                unresolved_keys=unresolved_keys,
                provider=bad_provider,
                idempotency_key="speaker-review-test-bad",
            )
        queue = get_speaker_review_queue(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=2,
            skip_completed=False,
            registry=registry,
            voice_catalog=_catalog(),
        )
        self.assertEqual(queue["status"], "not_analyzed")
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS count FROM jobs")["count"]),
            0,
        )

    def test_existing_character_without_id_downgrades_to_human_decision(self) -> None:
        registry = self._registry()
        unresolved_keys = [
            row["speaker_key"]
            for row in registry["rows"]
            if row["status"] == "UNRESOLVED_DIALOGUE"
        ]

        def missing_id_provider(**kwargs: Any) -> dict[str, Any]:
            response = self._provider(**kwargs)
            response["response"]["suggestions"][0]["existing_character_id"] = None
            return response

        run = generate_speaker_review_suggestions(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=2,
            skip_completed=False,
            registry=registry,
            voice_catalog=_catalog(),
            unresolved_keys=unresolved_keys,
            provider=missing_id_provider,
            idempotency_key="speaker-review-test-missing-existing-id",
        )

        first = next(item for item in run["suggestions"] if item["unresolved_key"] == unresolved_keys[0])
        self.assertEqual(first["proposed_resolution"], "NEEDS_HUMAN_DECISION")
        self.assertFalse(first["approval_eligible"])
        self.assertIn("existing_character_id is missing", " ".join(first["warnings"]))

    def test_deferred_suggestion_can_later_be_replaced_by_review_decision(self) -> None:
        registry = self._registry()
        unresolved_keys = [
            row["speaker_key"]
            for row in registry["rows"]
            if row["status"] == "UNRESOLVED_DIALOGUE"
        ]
        result = generate_speaker_review_suggestions(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=2,
            skip_completed=False,
            registry=registry,
            voice_catalog=_catalog(),
            unresolved_keys=unresolved_keys,
            provider=self._provider,
            idempotency_key="speaker-review-test-defer",
        )
        key = unresolved_keys[0]
        record_speaker_suggestion_decision(
            self.db,
            self.store,
            analysis_run_id=result["analysis_run_id"],
            unresolved_key=key,
            decision="DEFERRED",
            reviewer_payload={},
            idempotency_key="speaker-review-test-defer-row",
        )
        record_speaker_suggestion_decision(
            self.db,
            self.store,
            analysis_run_id=result["analysis_run_id"],
            unresolved_key=key,
            decision="ACCEPTED",
            reviewer_payload={"accepted": True},
            idempotency_key="speaker-review-test-accept-row",
        )
        queue = get_speaker_review_queue(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=2,
            skip_completed=False,
            registry=registry,
            voice_catalog=_catalog(),
        )
        reviewed = next(item for item in queue["suggestions"] if item["unresolved_key"] == key)
        self.assertEqual(reviewed["review_state"], "ACCEPTED")
