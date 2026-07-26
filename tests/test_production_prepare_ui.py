from __future__ import annotations

from pathlib import Path

from tests.base import IsolatedTestCase


class ProductionPrepareUiTests(IsolatedTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = Path(__file__).resolve().parents[1]
        cls.html = (root / "ui" / "index.html").read_text(encoding="utf-8")
        cls.js = (root / "ui" / "app.js").read_text(encoding="utf-8")
        cls.production_state = (root / "ui" / "production_state.js").read_text(
            encoding="utf-8"
        )

    def test_ui_has_separate_plan_confirm_prepare_and_status_controls(self):
        for value in (
            'id="productionPreparePanel"',
            'id="productionPrepareExactRange"',
            'id="productionPrepareToken"',
            'id="productionPrepareConfirmation"',
            'id="submitProductionPrepare"',
            'id="refreshProductionPrepareStatus"',
        ):
            self.assertIn(value, self.html)
        panel = self.html[
            self.html.index('id="productionPreparePanel"') :
            self.html.index("</section>", self.html.index('id="productionPreparePanel"'))
        ]
        self.assertNotIn("/start", panel)

    def test_prepare_payload_has_no_client_execution_authority(self):
        marker = "body:JSON.stringify({client_request_id:clientRequestId"
        start = self.js.index(marker)
        payload = self.js[start : self.js.index("})", start) + 2]
        for forbidden in (
            "chapter_id",
            "owner_token",
            "generation",
            "job_id",
            "start_render",
            "render_fields",
        ):
            self.assertNotIn(forbidden, payload.lower())
        for required in (
            "book_id",
            "from_chapter",
            "to_chapter",
            "target_phase:'PREPARE'",
            "plan_fingerprint",
            "confirmation:true",
        ):
            self.assertIn(required, payload)

    def test_ui_gates_start_separately_from_legacy_prepare(self):
        self.assertIn("/api/production/prepare-readiness", self.js)
        self.assertIn("function startRenderAllowed()", self.js)
        self.assertIn("readiness?.start_render_available", self.js)
        self.assertIn("Legacy job preparation", self.js)
        self.assertIn("START_RENDER chưa được operator mở", self.js)
        self.assertIn('button[onclick^="startPreparedJob"]', self.js)
        self.assertNotIn("start_render:", self.js)

    def test_prepared_batch_job_resumes_from_each_covered_chapter(self):
        start = self.js.index("function preparedCastingJob(")
        end = self.js.index("function recommendedChapterAction(", start)
        source = self.js[start:end]
        self.assertIn("Number(job.book_id||0)!==bookId", source)
        self.assertIn("from<=chapterNumber&&chapterNumber<=to", source)
        self.assertIn("!pinnedPlanId||pinnedPlanId===planId", source)
        self.assertNotIn(
            "Number(job.from_chapter||0)===chapterNumber&&"
            "Number(job.to_chapter||0)===chapterNumber",
            source,
        )

    def test_job_polling_preserves_row_review_approval_readiness(self):
        sync_start = self.js.index("function syncMutationControls()")
        sync_end = self.js.index("async function loadRuntimeIdentity", sync_start)
        sync_source = self.js[sync_start:sync_end]
        self.assertIn("draftOnlyApprovalReady(review)", sync_source)
        self.assertNotIn("!reviewReadyForCastingPlan(review)", sync_source)

    def test_invalid_ai_suggestion_can_be_replaced_by_human_row_review(self):
        row_start = self.js.index("function reviewRowElement(row)")
        row_end = self.js.index("function renderSpeakerReview()", row_start)
        row_source = self.js[row_start:row_end]
        self.assertIn("save.disabled=!runtimeAllowsMutation()", row_source)
        self.assertNotIn("save.disabled=!!row.invalid_item", row_source)
        self.assertIn(
            "return (draft.remaining_unreviewed_count??0)===0}",
            self.js,
        )
        self.assertIn("['narrator','Mark Narrator']", row_source)
        self.assertIn(
            "decision.speaker_type==='narrator')return "
            "{decision:'MARK_NARRATOR'}",
            self.js,
        )

    def test_approved_speaker_draft_can_create_map_after_stage_advances(self):
        self.assertIn(
            'data-production-owned-stage="speakers voice_map"',
            self.html,
        )
        self.assertIn(
            "vm.currentStageKey==='voice_map'&&!state.casting?.casting?.id"
            "&&reviewReadyForCastingPlan(state.speakerReview)",
            self.js,
        )
        self.assertIn(
            "if(vm.currentStageKey==='voice_map'&&!state.casting?.casting?.id"
            "&&reviewReadyForCastingPlan(state.speakerReview))return'assign-voices'",
            self.js,
        )

    def test_voice_profile_remains_available_while_reviewing_voice_map(self):
        self.assertIn(
            'id="flowStepAssignVoices" class="flow-step-panel hidden" '
            'data-production-owned-stage="speakers voices"',
            self.html,
        )
        self.assertIn(
            'id="flowVoiceMemoryDetails" class="flow-secondary-details" '
            'data-production-owned-stage="voices"',
            self.html,
        )
        self.assertIn("voiceMemory.open=vm.currentStageKey==='voices'", self.js)

    def test_missing_map_is_resolved_before_voice_eligibility(self):
        missing = self.production_state.index(
            "if(!casting.id)return buildViewModel('CASTING_REVIEW'"
        )
        voice = self.production_state.index(
            "const voiceReason=voiceBlocked(input)",
            missing,
        )
        self.assertLess(missing, voice)


if __name__ == "__main__":
    import unittest

    unittest.main()
