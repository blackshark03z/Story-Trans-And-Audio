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
            "generateSpeakerDraft", "regenerateSpeakerDraft", "refreshSpeakerDrafts",
            "speakerDraftSelect", "No speaker-assignment draft exists for this chapter.",
        ):
            self.assertIn(value, self.html)
        self.assertIn("force_refresh:force", self.js)
        self.assertIn("'unassigned_only'", self.js)

    def test_review_controls_filters_bulk_and_approve_are_explicit(self) -> None:
        for value in (
            "speakerReviewFilter", "reviewSelectVisible", "reviewAcceptSuggestions",
            "reviewMarkNarrator", "reviewMarkUnknown", "reviewClearSelection",
            "approveSpeakerReview", "jumpToPendingReview", "jumpToApprovalControls",
            "AI Draft / Suggestions", "Decisions are local until final approval.",
            "Create/Update Casting Plan from AI Draft",
            "Jump to Casting Plan approval",
        ):
            self.assertIn(value, self.html + self.js)
        self.assertIn("draft.stale||count===0", self.js)
        self.assertIn("!row.reviewed&&!decision", self.js)
        self.assertNotIn("Approve all high confidence", self.html)

    def test_active_audio_warning_and_latest_approval_revision_are_rendered(self) -> None:
        for value in (
            "Current playback still uses the active historical plan until a new job is rendered",
            "Latest approval created Casting Plan v",
            "Render / Production Output will use the exact approved Casting Plan below.",
            "Start Render (",
            "Finalize Output",
        ):
            self.assertIn(value, self.html + self.js)

    def test_character_voices_layout_separates_draft_plan_and_render_areas(self) -> None:
        for value in (
            "Start Here",
            "Production Flow",
            "Recommended Next Action",
            "productionFlowStepper",
            "productionFlowBack",
            "productionFlowContinue",
            "productionFlowNext",
            "productionFlowStepTitle",
            "productionFlowStepInputs",
            "productionFlowStepAfter",
            "flowStepSelectChapter",
            "flowStepReviewText",
            "flowStepAssignVoices",
            "flowStepReviewVoiceMap",
            "flowStepRenderChapter",
            "flowStepReviewAudio",
            "speakerDraftExistingPlanWarning",
            "AI Draft tools can create a new plan; use Casting Plan Review to approve the current plan.",
            "castingRecommendedActionTitle",
            "castingRecommendedActionBody",
            "castingRecommendedActionState",
            "castingPlanReviewMeta",
            "renderPlanNotice",
            "castingPlanApprovalControls",
            "Approve Voice Map & Continue to Render",
            "Review Audio / Finalize",
            "Advanced / Debug: AI speaker draft tools",
        ):
            self.assertIn(value, self.html + self.js)

    def test_jump_to_approval_controls_targets_real_casting_plan_area(self) -> None:
        self.assertIn("#castingPlanApprovalControls", self.js)
        self.assertNotIn("#speakerReviewApprovalControls')?.scrollIntoView", self.js)

    def test_existing_plan_deemphasizes_draft_tools(self) -> None:
        for value in (
            "has-existing-plan",
            "speakerDraftExistingPlanWarning",
            "$('#speakerReviewPanel').classList.toggle('has-existing-plan',existingPlan)",
            "$('#approveSpeakerReview').textContent=speakerDraftApprovalLabel",
            "Advanced / AI suggestions",
            "Do not treat this area as final approval",
        ):
            self.assertIn(value, self.html + self.js + self.css)

    def test_production_flow_guide_lists_core_steps(self) -> None:
        for value in (
            "PRODUCTION_FLOW_STEPS",
            "productionStepTitle",
            "title:'Select Chapter'",
            "title:'Review Text'",
            "title:'Assign Voices'",
            "title:'Review Voice Map'",
            "title:'Render Chapter'",
            "title:'Review Audio / Finalize'",
        ):
            self.assertIn(value, self.js + self.html)

    def test_production_flow_model_covers_operator_states(self) -> None:
        script = r"""
function chapterHasApprovedText(detail){const approved=detail?.revisions?.filter(r=>r.status==='approved')||[];if(!approved.length)return false;const activeId=Number(detail?.chapter?.active_text_revision_id||0);return approved.some(item=>Number(item.id)===activeId)}
function humanQaAccepted(detail){const value=String(detail?.chapter?.human_qa_status||'').toLowerCase();return value==='accepted'||value==='pass'||value==='human_qa_pass_with_minor_pronunciation_notes'}
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
  accepted: buildProductionFlow({chapter:{active_text_revision_id:7,audio_status:'completed',human_qa_status:'accepted'},revisions:[{id:7,status:'approved'}],active_output:{active_output_job_id:11,active_output_casting_plan_revision:1}}, {casting:{id:4,status:'approved',plan_revision:1},characters:[{id:2}]}).currentStepId,
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
        self.assertEqual(payload["accepted"], "review-audio")

    def test_step_flow_navigation_and_blockers_are_explicit(self) -> None:
        for value in (
            "productionFlowStepInputs",
            "productionFlowStepAfter",
            "productionFlowBlockedReason",
            "Choose another chapter",
            "Text revision is not approved yet.",
            "No casting plan exists yet.",
            "Render stays blocked until the voice map is approved.",
            "Audio already exists; use QA or replacement workflow instead of normal render.",
            "Human QA state is not stored in the database here; record the verdict separately if needed.",
        ):
            self.assertIn(value, self.html + self.js)

    def test_select_chapter_step_resets_on_open_and_does_not_close_on_stepper_click(self) -> None:
        for value in (
            "state.productionFlow={chapterId:id,selectedStepId:'select-chapter'}",
            "focusProductionFlowStep(button.dataset.flowStep,{exitToChapterList:false})",
            "$('#productionFlowContinue').onclick=()=>focusProductionFlowStep(selected.id,{exitToChapterList:selected.id==='select-chapter'})",
            "$('#productionFlowPanel')?.scrollIntoView({behavior:'smooth',block:'start'})",
        ):
            self.assertIn(value, self.js)

    def test_primary_flow_panels_match_guided_operator_steps(self) -> None:
        for value in (
            "flowStepSelectChapter",
            "flowStepReviewText",
            "flowStepAssignVoices",
            "flowStepReviewVoiceMap",
            "flowStepRenderChapter",
            "flowStepReviewAudio",
            "flowSelectSummary",
            "flowTextPreview",
            "flowSpeakerSummary",
            "flowVoiceMapTable",
            "flowRenderSummary",
            "flowAudioSummary",
        ):
            self.assertIn(value, self.html + self.js)

    def test_review_audio_keeps_candidate_controls_out_of_primary_flow(self) -> None:
        for value in (
            "Candidate/original A/B tools and segment troubleshooting belong only to QA context and Advanced / Debug.",
            "Advanced / Debug: QA and segment troubleshooting",
            "Finalize Output",
        ):
            self.assertIn(value, self.html + self.js)

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
    selected: {
      u0042: true, u0043: true, u0044: true,
      u0001: true, u0002: true, u0003: true,
    },
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
  seq43: state.speakerReview.decisions.u0043,
  seq44: state.speakerReview.decisions.u0044,
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
        self.assertEqual(payload["seq43"]["speaker_type"], "character")
        self.assertEqual(payload["seq44"]["speaker_type"], "character")
        self.assertEqual(payload["narrator"]["speaker_type"], "narrator")
        self.assertIsNone(payload["untouched"])

    def test_story_character_and_reason_are_rendered_with_text_content(self) -> None:
        self.assertIn("text.textContent=row.text", self.js)
        self.assertIn("reasonText.textContent=reason", self.js)
        self.assertIn("new Option(name,value", self.js)
        self.assertIn("context.textContent=item.text", self.js)
        self.assertNotIn("reviewRowHtml", self.js)
        for payload in ("<script>alert(1)</script>", "<img src=x onerror=alert(1)>"):
            self.assertNotIn(payload, self.html)

    def test_frontend_uses_backend_confidence_and_voice_resolution(self) -> None:
        self.assertIn("s?.confidence_level", self.js)
        self.assertNotIn("confidence >=", self.js)
        self.assertIn("/voice-profile/resolve", self.js)
        self.assertIn("Preview effective voice", self.js)

    def test_approval_contract_has_stale_and_idempotency_fields_without_job_creation(self) -> None:
        for value in (
            "base_casting_plan_revision_id", "expected_draft_fingerprint",
            "expected_text_revision_id", "idempotency_key",
        ):
            self.assertIn(value, self.js)
        self.assertIn("speaker-assignment/drafts/{draft_id}/approve", self.api)
        review_block = self.js[self.js.index("async function approveSpeakerReview"):]
        self.assertNotIn("/api/jobs", review_block.split("function ", 1)[0])

    def test_layout_has_bounded_rows_and_responsive_constraints(self) -> None:
        self.assertIn("max-height:620px", self.css)
        self.assertIn("speaker-review-row", self.css)
        self.assertIn("@media(max-width:650px)", self.css)

if __name__ == "__main__":
    import unittest
    unittest.main()
