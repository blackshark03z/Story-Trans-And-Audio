from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from story_audio.range_input import (
    approve_ready_casting_plans,
    approve_ready_speaker_drafts,
    get_range_input_snapshot,
    prepare_range_inputs,
)
from story_audio.voice_eligibility import EffectiveVoiceCatalog
from story_audio.voice_profile import set_book_voice_profile
from tests.base import IsolatedTestCase
from tests.test_speaker_assignment import fake_response, seed


class RangeInputWorkflowTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(dir=self.temp_root)
        (
            self.config,
            self.db,
            self.store,
            self.book_id,
            self.chapter_id,
            self.revision_id,
            self.character_id,
        ) = seed(Path(self.temp.name))
        self.catalog = EffectiveVoiceCatalog.from_ids("narrator", "male", "female")

    def tearDown(self) -> None:
        self.temp.cleanup()
        super().tearDown()

    def snapshot(self) -> dict:
        return get_range_input_snapshot(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=1,
            voice_catalog=self.catalog,
        )

    def prepare_with_provider(self, provider) -> dict:
        with patch.object(type(self.config), "gemini_key", return_value="fake-key"):
            return prepare_range_inputs(
                self.db,
                self.store,
                self.config,
                book_id=self.book_id,
                from_chapter=1,
                to_chapter=1,
                voice_catalog=self.catalog,
                allowed_voice_ids=set(self.catalog.preset_ids),
                provider=provider,
            )

    def test_range_lifecycle_reuses_per_chapter_boundaries(self) -> None:
        initial = self.snapshot()
        self.assertEqual(initial["summary"]["proposal_required_chapters"], 1)
        self.assertEqual(initial["summary"]["speaker_exception_count"], 0)

        prepared = self.prepare_with_provider(
            lambda **kwargs: fake_response(
                kwargs["request_data"], self.character_id
            ),
        )
        self.assertEqual(prepared["status"], "complete")
        self.assertEqual(prepared["results"][0]["operation"], "speaker_proposal")
        review_snapshot = prepared["snapshot"]
        self.assertEqual(review_snapshot["summary"]["speaker_exception_count"], 0)
        self.assertEqual(
            review_snapshot["summary"]["chapters_awaiting_speaker_approval"], 1
        )
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"]), 0
        )

        ready = review_snapshot["ready_speaker_drafts"][0]
        approved = approve_ready_speaker_drafts(
            self.db,
            self.store,
            self.config,
            snapshot=review_snapshot,
            requested=[{
                "chapter_id": ready["chapter_id"],
                "draft_id": ready["draft_id"],
            }],
        )
        self.assertEqual(approved["status"], "complete")
        self.assertEqual(approved["results"][0]["status"], "approved")
        self.assertEqual(
            int(
                self.db.fetch_one(
                    "SELECT COUNT(*) AS n FROM casting_plans"
                )["n"]
            ),
            0,
        )

        voice_snapshot = self.snapshot()
        self.assertEqual(voice_snapshot["summary"]["voice_exception_count"], 0)
        self.assertEqual(voice_snapshot["summary"]["inherited_voice_count"], 2)
        self.assertEqual(
            voice_snapshot["summary"]["casting_generation_ready_chapters"], 1
        )
        plan_result = prepare_range_inputs(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=1,
            voice_catalog=self.catalog,
            allowed_voice_ids=set(self.catalog.preset_ids),
        )
        self.assertEqual(plan_result["status"], "complete")
        self.assertEqual(plan_result["results"][0]["operation"], "casting_plan_draft")
        plan_snapshot = plan_result["snapshot"]
        self.assertEqual(
            plan_snapshot["summary"]["chapters_awaiting_casting_approval"], 1
        )
        plan = plan_snapshot["casting_approvals"][0]
        casting_result = approve_ready_casting_plans(
            self.db,
            self.store,
            snapshot=plan_snapshot,
            requested=[{
                "chapter_id": plan["chapter_id"],
                "plan_id": plan["plan_id"],
            }],
            voice_catalog=self.catalog,
            allowed_voice_ids=set(self.catalog.preset_ids),
        )
        self.assertEqual(casting_result["status"], "complete")
        self.assertEqual(casting_result["results"][0]["status"], "approved")
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"]), 0
        )
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS n FROM artifacts")["n"]), 0
        )

    def test_batch_speaker_approval_is_idempotent_and_rejects_wrong_identity(self) -> None:
        prepared = self.prepare_with_provider(
            lambda **kwargs: fake_response(
                kwargs["request_data"], self.character_id
            ),
        )
        snapshot = prepared["snapshot"]
        item = snapshot["ready_speaker_drafts"][0]
        request = [{
            "chapter_id": item["chapter_id"],
            "draft_id": item["draft_id"],
        }]
        first = approve_ready_speaker_drafts(
            self.db,
            self.store,
            self.config,
            snapshot=snapshot,
            requested=request,
        )
        second = approve_ready_speaker_drafts(
            self.db,
            self.store,
            self.config,
            snapshot=snapshot,
            requested=request,
        )
        wrong = approve_ready_speaker_drafts(
            self.db,
            self.store,
            self.config,
            snapshot=snapshot,
            requested=[{
                "chapter_id": item["chapter_id"],
                "draft_id": item["draft_id"] + 1000,
            }],
        )
        self.assertEqual(first["status"], "complete")
        self.assertTrue(second["results"][0]["reused"])
        self.assertEqual(wrong["status"], "failed")
        self.assertIn("outside", wrong["failures"][0]["error"])
        self.assertEqual(
            int(
                self.db.fetch_one(
                    "SELECT COUNT(*) AS n FROM speaker_assignment_drafts"
                )["n"]
            ),
            1,
        )

    def test_low_confidence_or_unknown_suggestion_stays_in_exception_queue(self) -> None:
        def uncertain_provider(**kwargs):
            response = fake_response(kwargs["request_data"], None)
            for item in response["assignments"]:
                item["confidence"] = 0.60
                item["reason"] = "Identity is not supported by the surrounding text."
            return response

        result = self.prepare_with_provider(uncertain_provider)
        queue = result["snapshot"]["speaker_exception_queue"]
        self.assertEqual(len(queue), 2)
        self.assertEqual([item["sequence"] for item in queue], sorted(
            item["sequence"] for item in queue
        ))
        self.assertEqual(
            result["snapshot"]["summary"]["chapters_awaiting_speaker_approval"],
            0,
        )

    def test_ineligible_existing_plan_is_replaced_after_voice_remediation(self) -> None:
        prepared = self.prepare_with_provider(
            lambda **kwargs: fake_response(
                kwargs["request_data"], self.character_id
            ),
        )
        ready = prepared["snapshot"]["ready_speaker_drafts"][0]
        approve_ready_speaker_drafts(
            self.db,
            self.store,
            self.config,
            snapshot=prepared["snapshot"],
            requested=[{
                "chapter_id": ready["chapter_id"],
                "draft_id": ready["draft_id"],
            }],
        )
        first_plan = prepare_range_inputs(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=1,
            voice_catalog=self.catalog,
            allowed_voice_ids=set(self.catalog.preset_ids),
        )["snapshot"]["casting_approvals"][0]

        reduced_catalog = EffectiveVoiceCatalog.from_ids("narrator", "female")
        blocked = get_range_input_snapshot(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=1,
            voice_catalog=reduced_catalog,
        )
        self.assertEqual(blocked["summary"]["voice_exception_count"], 2)
        self.assertEqual(blocked["summary"]["chapters_awaiting_casting_approval"], 0)

        set_book_voice_profile(
            self.db,
            self.book_id,
            narrator_voice_id="narrator",
            male_dialogue_voice_id="female",
            female_dialogue_voice_id="female",
            allowed_voice_ids=set(reduced_catalog.preset_ids),
        )
        remediated = get_range_input_snapshot(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=1,
            voice_catalog=reduced_catalog,
        )
        self.assertEqual(remediated["summary"]["voice_exception_count"], 0)
        self.assertEqual(
            remediated["casting_generation_ready"][0]["replace_plan_id"],
            first_plan["plan_id"],
        )

        replacement = prepare_range_inputs(
            self.db,
            self.store,
            self.config,
            book_id=self.book_id,
            from_chapter=1,
            to_chapter=1,
            voice_catalog=reduced_catalog,
            allowed_voice_ids=set(reduced_catalog.preset_ids),
        )
        replacement_plan = replacement["snapshot"]["casting_approvals"][0]
        self.assertNotEqual(replacement_plan["plan_id"], first_plan["plan_id"])
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS n FROM casting_plans")["n"]),
            2,
        )
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"]),
            0,
        )
