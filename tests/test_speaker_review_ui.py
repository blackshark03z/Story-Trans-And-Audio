from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tests.base import IsolatedTestCase

ROOT = Path(__file__).resolve().parents[1]


class SpeakerReviewUiContractTests(IsolatedTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")
        cls.api = (ROOT / "story_audio" / "api.py").read_text(encoding="utf-8")

    def test_generate_regenerate_refresh_empty_state_and_draft_selector_exist(self) -> None:
        for value in (
            "generateSpeakerDraft",
            "regenerateSpeakerDraft",
            "refreshSpeakerDrafts",
            "speakerDraftSelect",
            "No speaker-assignment draft exists for this chapter.",
        ):
            self.assertIn(value, self.html + self.js)
        self.assertIn("force_refresh:force", self.js)
        self.assertIn("'unassigned_only'", self.js)

    def test_review_controls_and_staged_draft_action_exist(self) -> None:
        for value in (
            "speakerReviewFilter",
            "reviewSelectVisible",
            "reviewAcceptSuggestions",
            "reviewMarkNarrator",
            "reviewMarkUnknown",
            "reviewClearSelection",
            "approveSpeakerReview",
            "jumpToPendingReview",
            "jumpToApprovalControls",
            "speakerDraftApprovalLabel",
            "reviewReadyForCastingPlan",
            "speakerReviewDecisionCount",
            "speakerReviewApprovalResult",
        ):
            self.assertIn(value, self.html + self.js)
        self.assertIn("reviewReadyForCastingPlan(review)", self.js)
        self.assertIn("!row.reviewed&&!decision", self.js)

    def test_review_button_targets_draft_only_endpoint(self) -> None:
        self.assertIn("speaker-review/casting-plan-draft", self.api)
        self.assertIn("/speaker-review/casting-plan-draft", self.js)
        self.assertIn("speaker_draft_id", self.js)
        self.assertIn("expected_draft_fingerprint", self.js)
        self.assertIn("expected_text_revision_id", self.js)
        self.assertIn("idempotency_key", self.js)
        review_block = self.js[self.js.index("async function approveSpeakerReview"):]
        self.assertNotIn("/api/jobs", review_block.split("function ", 1)[0])

    def test_review_ready_helper_blocks_incomplete_or_stale_reviews(self) -> None:
        script = r"""
function reviewedDecisionCount(review){return Object.keys(review?.decisions||{}).length}
function localRemainingUnreviewedCount(review){const draft=review?.draft;if(!draft)return 0;const pending=Object.values(review?.decisions||{}).filter(item=>!draft.review_rows.find(row=>row.utterance_id===item.utterance_id)?.reviewed).length;return Math.max(0,(draft.remaining_unreviewed_count??0)-pending)}
function reviewReadyForCastingPlan(review){const draft=review?.draft;if(!draft||draft.stale)return false;return localRemainingUnreviewedCount(review)===0&&reviewedDecisionCount(review)>0}
const incomplete={draft:{stale:false,remaining_unreviewed_count:2,review_rows:[{utterance_id:'u1',reviewed:false},{utterance_id:'u2',reviewed:false}]},decisions:{u1:{utterance_id:'u1'}}};
const complete={draft:{stale:false,remaining_unreviewed_count:2,review_rows:[{utterance_id:'u1',reviewed:false},{utterance_id:'u2',reviewed:false}]},decisions:{u1:{utterance_id:'u1'},u2:{utterance_id:'u2'}}};
const stale={draft:{stale:true,remaining_unreviewed_count:0,review_rows:[{utterance_id:'u1',reviewed:true}]},decisions:{u1:{utterance_id:'u1'}}};
console.log(JSON.stringify({incomplete:reviewReadyForCastingPlan(incomplete),complete:reviewReadyForCastingPlan(complete),stale:reviewReadyForCastingPlan(stale)}));
"""
        result = subprocess.run(
            ["node", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        payload = json.loads(result.stdout)
        self.assertFalse(payload["incomplete"])
        self.assertTrue(payload["complete"])
        self.assertFalse(payload["stale"])

    def test_bulk_review_uses_local_state_for_selection_and_remaining_counts(self) -> None:
        for value in (
            "check.checked=!!state.speakerReview.selected?.[row.utterance_id]",
            "Object.keys(state.speakerReview?.selected||{})",
            "localRemainingUnreviewedCount(review)",
            "$('#reviewSelectVisible').onclick=selectVisibleReviewRows;",
            "$('#reviewClearSelection').onclick=clearSelectedReviewRows;",
        ):
            self.assertIn(value, self.js)

    def test_bulk_review_behavior_sets_decisions_and_updates_remaining(self) -> None:
        script = r"""
const state = {
  speakerReview: {
    decisions: {},
    selected: {u0042:true,u0043:true,u0044:true,u0001:true,u0002:true,u0003:true},
    draft: {
      remaining_unreviewed_count: 6,
      review_rows: [
        { utterance_id: 'u0042', reviewed: false, suggestion: { speaker_type: 'character', character_id: 2 } },
        { utterance_id: 'u0043', reviewed: false, suggestion: { speaker_type: 'character', character_id: 2 } },
        { utterance_id: 'u0044', reviewed: false, suggestion: { speaker_type: 'character', character_id: 2 } },
        { utterance_id: 'u0001', reviewed: false, suggestion: { speaker_type: 'narrator', character_id: null } },
        { utterance_id: 'u0002', reviewed: false, suggestion: { speaker_type: 'narrator', character_id: null } },
        { utterance_id: 'u0003', reviewed: false, suggestion: { speaker_type: 'narrator', character_id: null } },
        { utterance_id: 'u0099', reviewed: false, suggestion: { speaker_type: 'narrator', character_id: null } },
      ],
    },
  },
};
function reviewedDecisionCount(review){return Object.keys(review?.decisions||{}).length}
function localRemainingUnreviewedCount(review){const draft=review?.draft;if(!draft)return 0;const pending=Object.values(review?.decisions||{}).filter(item=>!draft.review_rows.find(row=>row.utterance_id===item.utterance_id)?.reviewed).length;return Math.max(0,(draft.remaining_unreviewed_count??0)-pending)}
function reviewDecision(row,value){const suggestion=row.suggestion;if(value==='suggestion'&&suggestion)return {utterance_id:row.utterance_id,speaker_type:suggestion.speaker_type,character_id:suggestion.character_id,decision_source:'gemini_suggestion'};if(value==='narrator')return {utterance_id:row.utterance_id,speaker_type:'narrator',character_id:null,decision_source:'narrator'};if(value==='unknown')return {utterance_id:row.utterance_id,speaker_type:'unknown',character_id:null,decision_source:'unknown'};return null}
function setSpeakerReviewChoice(utteranceId,value){const row=state.speakerReview.draft.review_rows.find(item=>item.utterance_id===utteranceId),decision=row?reviewDecision(row,value):null;if(decision)state.speakerReview.decisions[utteranceId]=decision;else delete state.speakerReview.decisions[utteranceId]}
function selectedReviewRows(){return Object.keys(state.speakerReview?.selected||{}).filter(utteranceId=>state.speakerReview.selected[utteranceId]).map(utteranceId=>state.speakerReview.draft.review_rows.find(row=>row.utterance_id===utteranceId)).filter(Boolean)}
function bulkReview(action){const rows=selectedReviewRows();rows.forEach(row=>{let value='skip';if(action==='suggestion'&&row.suggestion)value='suggestion';if(action==='narrator')value='narrator';if(action==='unknown')value='unknown';setSpeakerReviewChoice(row.utterance_id,value)})}
bulkReview('suggestion');
console.log(JSON.stringify({
  decisionCount: reviewedDecisionCount(state.speakerReview),
  remaining: localRemainingUnreviewedCount(state.speakerReview),
  seq42: state.speakerReview.decisions.u0042,
  narrator: state.speakerReview.decisions.u0001,
  untouched: state.speakerReview.decisions.u0099 || null,
}));
"""
        result = subprocess.run(
            ["node", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["decisionCount"], 6)
        self.assertEqual(payload["remaining"], 0)
        self.assertEqual(payload["seq42"]["speaker_type"], "character")
        self.assertEqual(payload["seq42"]["character_id"], 2)
        self.assertEqual(payload["narrator"]["speaker_type"], "narrator")
        self.assertIsNone(payload["untouched"])

    def test_existing_plan_state_and_review_result_hooks_exist(self) -> None:
        for value in (
            "has-existing-plan",
            "speakerDraftExistingPlanWarning",
            "$('#speakerReviewPanel').classList.toggle('has-existing-plan',existingPlan)",
            "$('#approveSpeakerReview').textContent=speakerDraftApprovalLabel()",
            "review.lastApproval",
            "Final Voice Map draft v${result.casting_plan_revision} created",
        ):
            self.assertIn(value, self.html + self.js + self.css)

    def test_voice_map_and_render_sections_remain_separate(self) -> None:
        for value in (
            "flowStepReviewVoiceMap",
            "castingPlanPanel",
            "castingPlanReviewMeta",
            "castingPlanApprovalControls",
            "approveCastingPlan",
            "flowStepRenderChapter",
            "renderPlanPanel",
            "renderPlanNotice",
            "renderCastingPlan",
            "flowStepReviewAudio",
            "flowFinalApprovalPanel",
        ):
            self.assertIn(value, self.html + self.js)

    def test_render_stage_supports_prepare_then_start(self) -> None:
        for value in (
            "/api/jobs/prepare",
            "/api/jobs/${preparedJob.id}/start",
            "Chuáº©n bá»‹ job audio",
            "Báº¯t Ä‘áº§u render",
            "preparedJob=preparedCastingJob",
            "Job #${preparedJob.id}",
        ):
            self.assertIn(value, self.js)

    def test_production_flow_structure_and_navigation_exist(self) -> None:
        for value in (
            "PRODUCTION_FLOW_STEPS",
            "productionFlowStepper",
            "productionFlowStepTitle",
            "productionFlowStepInputs",
            "productionFlowStepAfter",
            "productionFlowBlockedReason",
            "productionFlowContinue",
            "productionFlowNext",
            "focusProductionFlowStep",
            "state.productionFlow={chapterId:id,selectedStepId:null,autoSelected:true}",
        ):
            self.assertIn(value, self.html + self.js)

    def test_production_flow_model_covers_operator_states(self) -> None:
        script = r"""
function chapterHasApprovedText(detail){const approved=detail?.revisions?.filter(r=>r.status==='approved')||[];if(!approved.length)return false;const activeId=Number(detail?.chapter?.active_text_revision_id||0);return approved.some(item=>Number(item.id)===activeId)}
const runningAudioStatuses=new Set(['scheduled','queued','running','repairing','synthesizing','assembling','paused']);
function buildProductionFlow(detail,context){const chapter=detail?.chapter||{},casting=context?.casting||{},characters=context?.characters||[],active=detail?.active_output||{},hasRevisions=(detail?.revisions||[]).length>0,approvedText=chapterHasApprovedText(detail),hasPlan=!!casting.id,planDraft=casting.status==='draft',planApproved=casting.status==='approved',hasActiveAudio=!!active.active_output_job_id,jobRunning=runningAudioStatuses.has(String(chapter.audio_status||''));let currentStepId='select-chapter';if(!hasRevisions||!approvedText)currentStepId='review-text';else if(!hasPlan)currentStepId='assign-voices';else if(planDraft)currentStepId='review-voice-map';else if(jobRunning||(planApproved&&!hasActiveAudio))currentStepId='render-chapter';else if(hasActiveAudio)currentStepId='review-audio';return {currentStepId}}
console.log(JSON.stringify({
  noText: buildProductionFlow({chapter:{},revisions:[],active_output:{}}, {casting:{},characters:[]}).currentStepId,
  textNotApproved: buildProductionFlow({chapter:{active_text_revision_id:7,audio_status:'pending'},revisions:[{id:7,status:'draft'}],active_output:{}}, {casting:{},characters:[]}).currentStepId,
  noCasting: buildProductionFlow({chapter:{active_text_revision_id:7,audio_status:'pending'},revisions:[{id:7,status:'approved'}],active_output:{}}, {casting:{},characters:[{id:2}]}).currentStepId,
  planDraft: buildProductionFlow({chapter:{active_text_revision_id:7,audio_status:'pending'},revisions:[{id:7,status:'approved'}],active_output:{}}, {casting:{id:4,status:'draft',plan_revision:1},characters:[{id:2}]}).currentStepId,
  planApproved: buildProductionFlow({chapter:{active_text_revision_id:7,audio_status:'pending'},revisions:[{id:7,status:'approved'}],active_output:{}}, {casting:{id:4,status:'approved',plan_revision:1},characters:[{id:2}]}).currentStepId,
  running: buildProductionFlow({chapter:{active_text_revision_id:7,audio_status:'running'},revisions:[{id:7,status:'approved'}],active_output:{}}, {casting:{id:4,status:'approved',plan_revision:1},characters:[{id:2}]}).currentStepId,
  qaReady: buildProductionFlow({chapter:{active_text_revision_id:7,audio_status:'completed'},revisions:[{id:7,status:'approved'}],active_output:{active_output_job_id:11,active_output_casting_plan_revision:1}}, {casting:{id:4,status:'approved',plan_revision:1},characters:[{id:2}]}).currentStepId,
}));
"""
        result = subprocess.run(
            ["node", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["noText"], "review-text")
        self.assertEqual(payload["textNotApproved"], "review-text")
        self.assertEqual(payload["noCasting"], "assign-voices")
        self.assertEqual(payload["planDraft"], "review-voice-map")
        self.assertEqual(payload["planApproved"], "render-chapter")
        self.assertEqual(payload["running"], "render-chapter")
        self.assertEqual(payload["qaReady"], "review-audio")

    def test_story_character_and_reason_are_rendered_with_text_content(self) -> None:
        self.assertIn("text.textContent=row.text", self.js)
        self.assertIn("reasonText.textContent=reason", self.js)
        self.assertIn("new Option(name,value", self.js)
        self.assertIn("context.textContent=item.text", self.js)
        self.assertNotIn("reviewRowHtml", self.js)

    def test_frontend_uses_backend_confidence_and_voice_resolution(self) -> None:
        self.assertIn("s?.confidence_level", self.js)
        self.assertNotIn("confidence >=", self.js)
        self.assertIn("/voice-profile/resolve", self.js)
        self.assertIn("Preview effective voice", self.js)

    def test_layout_has_bounded_rows_and_responsive_constraints(self) -> None:
        self.assertIn("max-height:620px", self.css)
        self.assertIn("speaker-review-row", self.css)
        self.assertIn("@media(max-width:650px)", self.css)


if __name__ == "__main__":
    import unittest

    unittest.main()
