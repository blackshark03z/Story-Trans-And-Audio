from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from story_audio.book_voice_registry import get_book_voice_registry
from story_audio.casting import (
    approve_plan,
    create_casting_draft,
    create_character,
    get_plan,
    split_utterances,
)
from story_audio.db import Database, utcnow
from story_audio.speaker_review_suggestions import (
    SpeakerReviewSuggestionError,
    _latest_queue_for_run,
    accept_speaker_review_suggestion,
    approve_high_confidence_suggestions,
    approve_speaker_review_batch_items,
    generate_speaker_review_suggestions,
    get_speaker_review_queue,
    record_speaker_suggestion_decision,
    record_speaker_suggestion_note,
    restore_speaker_suggestion_pending,
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

    def test_queue_combines_valid_subset_runs_without_provider_call(self) -> None:
        registry = self._registry()
        unresolved_keys = [
            row["speaker_key"]
            for row in registry["rows"]
            if row["status"] == "UNRESOLVED_DIALOGUE"
        ]
        chapter_1 = [key for key in unresolved_keys if ":1:" in key]
        chapter_2 = [key for key in unresolved_keys if ":2:" in key]

        first = generate_speaker_review_suggestions(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=2,
            skip_completed=False,
            registry=registry,
            voice_catalog=_catalog(),
            unresolved_keys=chapter_1,
            provider=self._provider,
            idempotency_key="speaker-review-combine-1",
        )
        second = generate_speaker_review_suggestions(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=2,
            skip_completed=False,
            registry=registry,
            voice_catalog=_catalog(),
            unresolved_keys=chapter_2,
            provider=self._provider,
            idempotency_key="speaker-review-combine-2",
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

        self.assertEqual(queue["status"], "ready_for_human_review")
        self.assertTrue(queue["combined_from_existing_runs"])
        self.assertEqual(queue["target_count"], len(unresolved_keys))
        self.assertEqual([item["unresolved_key"] for item in queue["suggestions"]], unresolved_keys)
        self.assertEqual(queue["summary"]["analyzed"], len(unresolved_keys))
        self.assertEqual(queue["summary"]["pending_review"], len(unresolved_keys))
        source_ids = {item["source_analysis_run_id"] for item in queue["suggestions"]}
        self.assertEqual(source_ids, {first["analysis_run_id"], second["analysis_run_id"]})
        for item in queue["suggestions"]:
            self.assertEqual(
                item["suggestion_id"],
                f"{item['source_analysis_run_id']}:{item['unresolved_key']}",
            )
        self.assertEqual(queue["request_count"], first["request_count"] + second["request_count"])
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS count FROM jobs")["count"]),
            0,
        )
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS count FROM artifacts")["count"]),
            0,
        )

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

    def test_queue_preserves_approved_history_after_registry_mapping_changes(self) -> None:
        registry = self._registry()
        unresolved_keys = [
            row["speaker_key"]
            for row in registry["rows"]
            if row["status"] == "UNRESOLVED_DIALOGUE"
        ]
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
            provider=self._provider,
            idempotency_key="speaker-review-history-projection-run",
        )
        accepted = run["suggestions"][0]
        accept_speaker_review_suggestion(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=2,
            analysis_run_id=run["analysis_run_id"],
            unresolved_key=accepted["unresolved_key"],
            reviewer_payload=accepted,
            voice_catalog=_catalog(),
            idempotency_key="speaker-review-history-projection-accept",
        )

        refreshed_registry = self._registry()
        queue = get_speaker_review_queue(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=2,
            skip_completed=False,
            registry=refreshed_registry,
            voice_catalog=_catalog(),
        )

        self.assertTrue(queue["projected_from_existing_run"])
        self.assertEqual(queue["summary"]["total"], len(unresolved_keys))
        self.assertEqual(queue["summary"]["approved"], 1)
        self.assertEqual(queue["summary"]["pending_review"], len(unresolved_keys) - 1)
        self.assertEqual(
            queue["summary"]["queue_views"]["ALL"]["count"],
            len(unresolved_keys),
        )
        self.assertEqual(queue["summary"]["queue_views"]["APPROVED"]["count"], 1)
        reviewed = next(
            item
            for item in queue["suggestions"]
            if item["unresolved_key"] == accepted["unresolved_key"]
        )
        self.assertEqual(reviewed["review_state"], "ACCEPTED")
        self.assertEqual(
            reviewed["target"]["dialogue_text"],
            accepted["target"]["dialogue_text"],
        )
        self.assertIsNotNone(reviewed["review_audit_event_id"])

    def test_legacy_batch_rollback_error_remains_history_but_not_effective(self) -> None:
        registry = self._registry()
        key = next(
            row["speaker_key"]
            for row in registry["rows"]
            if row["status"] == "UNRESOLVED_DIALOGUE"
        )
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
            unresolved_keys=[key],
            provider=self._provider,
            idempotency_key="speaker-review-legacy-batch-error-run",
        )
        record_speaker_suggestion_decision(
            self.db,
            self.store,
            analysis_run_id=result["analysis_run_id"],
            unresolved_key=key,
            decision="ERROR",
            reviewer_payload={
                "batch_idempotency_key": "speaker-review-legacy-batch-error",
                "reason": "transaction rolled back",
            },
            idempotency_key="speaker-review-legacy-batch-error-row",
        )

        queue = _latest_queue_for_run(
            self.db,
            self.store,
            analysis_run_id=result["analysis_run_id"],
        )
        suggestion = queue["suggestions"][0]
        self.assertEqual(suggestion["review_state"], "PENDING_REVIEW")
        self.assertIsNone(suggestion["human_review"])
        self.assertEqual(suggestion["review_history"][-1]["decision"], "ERROR")

    def test_approved_character_and_voice_correction_preserves_history(self) -> None:
        registry = self._registry()
        key = next(
            row["speaker_key"]
            for row in registry["rows"]
            if row["status"] == "UNRESOLVED_DIALOGUE"
        )
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
            unresolved_keys=[key],
            provider=self._provider,
            idempotency_key="speaker-review-correction-run",
        )
        suggestion = run["suggestions"][0]
        accept_speaker_review_suggestion(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=2,
            analysis_run_id=run["analysis_run_id"],
            unresolved_key=key,
            reviewer_payload=suggestion,
            voice_catalog=_catalog(),
            idempotency_key="speaker-review-correction-accept",
        )
        correct = create_character(self.db, self.book_id, "Correct Captain", None)

        corrected = accept_speaker_review_suggestion(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=2,
            analysis_run_id=run["analysis_run_id"],
            unresolved_key=key,
            reviewer_payload={
                "proposed_resolution": "EXISTING_CHARACTER",
                "existing_character_id": int(correct["id"]),
                "proposed_aliases": ["captain"],
                "voice_mode": "exact",
                "voice_scope": "chapter",
                "suggested_voice_id": "new",
            },
            voice_catalog=_catalog(),
            idempotency_key="speaker-review-correction-replacement",
            decision_override="CORRECTED",
            require_approved=True,
        )

        chapter_id = int(key.split(":", 2)[1])
        latest = self.db.fetch_one(
            """
            SELECT id,plan_revision FROM casting_plans
            WHERE chapter_id=? AND status='approved'
            ORDER BY plan_revision DESC,id DESC LIMIT 1
            """,
            (chapter_id,),
        )
        plan = get_plan(self.db, self.store, int(latest["id"]))["plan"]
        utterance_id = key.split(":", 2)[2]
        target = next(
            item for item in plan["utterances"] if item["utterance_id"] == utterance_id
        )
        self.assertEqual(target["character_id"], int(correct["id"]))
        self.assertEqual(target["resolved_voice_id"], "new")
        self.assertEqual(corrected["review"]["decision"]["decision"], "CORRECTED")

        events = self.db.fetch_all(
            "SELECT details_json FROM audit_events WHERE event_code=? ORDER BY id",
            ("speaker_review_suggestion_reviewed",),
        )
        details = [json.loads(row["details_json"]) for row in events]
        decisions = [item["decision"] for item in details]
        self.assertEqual(decisions, ["ACCEPTED", "CORRECTED"])
        self.assertEqual(
            details[1]["source_suggestion"]["proposed_resolution"],
            "EXISTING_CHARACTER",
        )
        self.assertTrue(details[1]["resulting_mapping"]["applied"])
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS count FROM jobs")["count"]),
            0,
        )
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS count FROM artifacts")["count"]),
            0,
        )

    def test_notes_preserve_state_and_restore_pending_is_downstream_safe(self) -> None:
        registry = self._registry()
        key = next(
            row["speaker_key"]
            for row in registry["rows"]
            if row["status"] == "UNRESOLVED_DIALOGUE"
        )
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
            unresolved_keys=[key],
            provider=self._provider,
            idempotency_key="speaker-review-note-restore-run",
        )
        suggestion = run["suggestions"][0]
        accept_speaker_review_suggestion(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=2,
            analysis_run_id=run["analysis_run_id"],
            unresolved_key=key,
            reviewer_payload=suggestion,
            voice_catalog=_catalog(),
            idempotency_key="speaker-review-note-restore-accept",
        )
        record_speaker_suggestion_note(
            self.db,
            self.store,
            analysis_run_id=run["analysis_run_id"],
            unresolved_key=key,
            note="Keep the original command cadence.",
            idempotency_key="speaker-review-note-restore-note",
        )
        queue = _latest_queue_for_run(
            self.db,
            self.store,
            analysis_run_id=run["analysis_run_id"],
        )
        reviewed = next(item for item in queue["suggestions"] if item["unresolved_key"] == key)
        self.assertEqual(reviewed["review_state"], "ACCEPTED")
        self.assertEqual(reviewed["review_history"][-1]["decision"], "NOTE")

        restore_speaker_suggestion_pending(
            self.db,
            self.store,
            analysis_run_id=run["analysis_run_id"],
            unresolved_key=key,
            reviewer_payload={"note": "operator_restored_pending"},
            idempotency_key="speaker-review-note-restore-pending",
        )
        queue = _latest_queue_for_run(
            self.db,
            self.store,
            analysis_run_id=run["analysis_run_id"],
        )
        restored = next(item for item in queue["suggestions"] if item["unresolved_key"] == key)
        self.assertEqual(restored["review_state"], "PENDING_REVIEW")
        self.assertEqual(restored["human_review"]["decision"], "RESTORED_PENDING")
        with self.assertRaisesRegex(
            SpeakerReviewSuggestionError,
            "Only an approved speaker decision",
        ):
            restore_speaker_suggestion_pending(
                self.db,
                self.store,
                analysis_run_id=run["analysis_run_id"],
                unresolved_key=key,
                reviewer_payload={"note": "duplicate restore"},
                idempotency_key="speaker-review-note-restore-duplicate",
            )

        accept_speaker_review_suggestion(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=2,
            analysis_run_id=run["analysis_run_id"],
            unresolved_key=key,
            reviewer_payload=suggestion,
            voice_catalog=_catalog(),
            idempotency_key="speaker-review-note-restore-reaccept",
        )
        queue = _latest_queue_for_run(
            self.db,
            self.store,
            analysis_run_id=run["analysis_run_id"],
        )
        reaccepted = next(
            item for item in queue["suggestions"] if item["unresolved_key"] == key
        )
        self.assertEqual(reaccepted["review_state"], "ACCEPTED")
        chapter_id = int(key.split(":", 2)[1])
        now = utcnow()
        with self.db.transaction() as connection:
            job_id = int(
                connection.execute(
                    """
                    INSERT INTO jobs(
                        book_id,status,from_chapter,to_chapter,voice_name,repair_mode,
                        output_format,settings_json,skip_completed,pause_requested,
                        cancel_requested,total_chapters,completed_chapters,failed_chapters,
                        scheduled_at,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        self.book_id,
                        "completed",
                        1,
                        1,
                        "narrator",
                        "none",
                        "m4a",
                        "{}",
                        0,
                        0,
                        0,
                        1,
                        1,
                        0,
                        now,
                        now,
                        now,
                    ),
                ).lastrowid
            )
            connection.execute(
                """
                INSERT INTO job_chapters(job_id,chapter_id,sequence,status)
                VALUES(?,?,?,?)
                """,
                (job_id, chapter_id, 1, "completed"),
            )
        with self.assertRaisesRegex(
            SpeakerReviewSuggestionError,
            "replacement decision",
        ):
            restore_speaker_suggestion_pending(
                self.db,
                self.store,
                analysis_run_id=run["analysis_run_id"],
                unresolved_key=key,
                reviewer_payload={"note": "unsafe restore"},
                idempotency_key="speaker-review-note-restore-blocked",
            )

    def test_safe_new_character_batch_is_atomic_and_replayable(self) -> None:
        registry = self._registry()
        key = next(
            row["speaker_key"]
            for row in registry["rows"]
            if row["status"] == "UNRESOLVED_DIALOGUE"
        )

        def new_character_provider(**kwargs: Any) -> dict[str, Any]:
            target = kwargs["request_data"]["targets"][0]
            suggestion = {
                **self._suggestion(
                    str(target["unresolved_key"]),
                    int(target["chapter_number"]),
                    0,
                ),
                "proposed_resolution": "NEW_CHARACTER",
                "existing_character_id": None,
                "proposed_character_name": "New Sentinel",
                "proposed_aliases": ["sentinel"],
                "proposed_voice_handling": "USE_BOOK_DEFAULT",
            }
            return {
                "response": {
                    "schema": "story-audio-gemini-speaker-review-suggestions/v1",
                    "suggestions": [suggestion],
                }
            }

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
            unresolved_keys=[key],
            provider=new_character_provider,
            idempotency_key="speaker-review-new-character-run",
        )
        before = int(
            self.db.fetch_one("SELECT COUNT(*) AS count FROM characters")["count"]
        )
        first = approve_high_confidence_suggestions(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=2,
            analysis_run_id=run["analysis_run_id"],
            unresolved_keys=[key],
            voice_catalog=_catalog(),
            idempotency_key="speaker-review-new-character-batch",
        )
        replay = approve_high_confidence_suggestions(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=2,
            analysis_run_id=run["analysis_run_id"],
            unresolved_keys=[key],
            voice_catalog=_catalog(),
            idempotency_key="speaker-review-new-character-batch",
        )
        after = int(
            self.db.fetch_one("SELECT COUNT(*) AS count FROM characters")["count"]
        )
        self.assertEqual(first["submitted_count"], 1)
        self.assertTrue(replay["reused"])
        self.assertEqual(after, before + 1)

    def test_combined_batch_failure_rolls_back_all_business_rows(self) -> None:
        registry = self._registry()
        keys = [
            row["speaker_key"]
            for row in registry["rows"]
            if row["status"] == "UNRESOLVED_DIALOGUE"
        ]
        key_one = next(key for key in keys if ":1:" in key)
        key_two = next(key for key in keys if ":2:" in key)
        runs = []
        for index, key in enumerate((key_one, key_two), start=1):
            runs.append(
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
                    unresolved_keys=[key],
                    provider=self._provider,
                    idempotency_key=f"speaker-review-rollback-run-{index}",
                )
            )
        plan_count = int(
            self.db.fetch_one("SELECT COUNT(*) AS count FROM casting_plans")["count"]
        )
        original_accept = accept_speaker_review_suggestion
        call_count = 0

        def fail_second(*args: Any, **kwargs: Any) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise SpeakerReviewSuggestionError("injected batch failure")
            return original_accept(*args, **kwargs)

        items = [
            {
                "analysis_run_id": run["analysis_run_id"],
                "unresolved_key": key,
            }
            for run, key in zip(runs, (key_one, key_two), strict=True)
        ]
        with patch(
            "story_audio.speaker_review_suggestions.accept_speaker_review_suggestion",
            side_effect=fail_second,
        ):
            with self.assertRaises(SpeakerReviewSuggestionError):
                approve_speaker_review_batch_items(
                    self.db,
                    self.store,
                    self.config,
                    book_id=self.book_id,
                    from_chapter=1,
                    to_chapter=2,
                    items=items,
                    voice_catalog=_catalog(),
                    idempotency_key="speaker-review-rollback-batch",
                )

        self.assertEqual(
            int(
                self.db.fetch_one(
                    "SELECT COUNT(*) AS count FROM casting_plans"
                )["count"]
            ),
            plan_count,
        )
        events = self.db.fetch_all(
            "SELECT details_json FROM audit_events WHERE event_code=? ORDER BY id",
            ("speaker_review_suggestion_reviewed",),
        )
        details = [json.loads(row["details_json"]) for row in events]
        self.assertEqual(details, [])
