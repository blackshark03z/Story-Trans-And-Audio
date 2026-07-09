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
            "Nháp AI / Gợi ý", "Các quyết định ở đây chỉ là tạm thời cho đến khi bạn duyệt cuối.",
            "Tạo / cập nhật Casting Plan từ nháp AI",
            "Nhảy đến phần duyệt Casting Plan",
        ):
            self.assertIn(value, self.html + self.js)
        self.assertIn("draft.stale||count===0", self.js)
        self.assertIn("!row.reviewed&&!decision", self.js)
        self.assertNotIn("Approve all high confidence", self.html)

    def test_active_audio_warning_and_latest_approval_revision_are_rendered(self) -> None:
        for value in (
            "Current playback still uses the active historical plan until a new job is rendered",
            "Lần duyệt gần nhất đã tạo Casting Plan v",
            "Render sẽ dùng đúng Bản đồ giọng cuối đã duyệt này.",
            "Bắt đầu tạo audio (",
            "Chốt bản audio cuối",
        ):
            self.assertIn(value, self.html + self.js)

    def test_character_voices_layout_separates_draft_plan_and_render_areas(self) -> None:
        for value in (
            "Bắt đầu ở đây",
            "Quy trình sản xuất",
            "Bước nên làm tiếp theo",
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
            "Nhân vật / người nói được phát hiện trong chương",
            "Giọng mặc định và bộ nhớ nhân vật của sách",
            "flowVoiceMemoryDetails",
            "speakerDraftExistingPlanWarning",
            "Công cụ nháp AI có thể tạo một plan mới; nếu bạn chỉ muốn duyệt plan hiện tại, hãy quay lại phần Bản đồ giọng cuối.",
            "castingRecommendedActionTitle",
            "castingRecommendedActionBody",
            "castingRecommendedActionState",
            "castingPlanReviewMeta",
            "renderPlanNotice",
            "castingPlanApprovalControls",
            "Duyệt bản đồ giọng cuối & tiếp tục tạo audio",
            "Nghe kiểm tra / Chốt bản cuối",
            "Nâng cao / Gỡ lỗi: công cụ nháp AI cho người nói",
        ):
            self.assertIn(value, self.html + self.js)

    def test_review_voice_map_uses_final_voice_map_as_primary_label(self) -> None:
        for value in (
            "Duyệt bản đồ giọng cuối",
            "Đây là bản đồ giọng cuối mà hệ thống sẽ dùng khi tạo audio.",
            "Chi tiết bản đồ giọng cuối",
            "Hãy duyệt Bản đồ giọng cuối, rồi mới duyệt plan trước khi tạo audio.",
            "Bản đồ giọng cuối này hiện đang được lưu dưới dạng Casting Plan đã duyệt.",
            "Duyệt bản đồ giọng cuối & tiếp tục tạo audio",
            "Technical: Casting Plan #",
        ):
            self.assertIn(value, self.html + self.js)

    def test_assign_voices_uses_operator_language_for_detected_speakers(self) -> None:
        for value in (
            "Nhân vật / người nói được phát hiện trong chương",
            "Hầu hết giọng được tự gán từ giọng kể chuyện, giọng nam/nữ mặc định và bộ nhớ nhân vật đã biết.",
            "Bạn chỉ cần kiểm tra các dòng được đánh dấu Cần kiểm tra, rồi duyệt bản đồ giọng trước khi tạo audio.",
            "Danh sách này cho biết công cụ phát hiện ai trong chương",
            "Giọng sẽ dùng",
            "Nhân vật đã biết",
            "Người nói mới hoặc chưa rõ",
            "Đang dùng giọng mặc định",
            "Cần kiểm tra trước khi tạo audio",
        ):
            self.assertIn(value, self.html + self.js)

    def test_assign_voices_keeps_backend_terms_out_of_primary_labels(self) -> None:
        self.assertIn("Công cụ nháp AI và rà soát người nói", self.html)
        self.assertIn("Character Bible import", self.html)
        self.assertNotIn(">Speaker Assignment Draft</h3>", self.html)
        self.assertNotIn("Current assigned voice", self.js)
        self.assertNotIn("Role / gender", self.js)
        self.assertNotIn("Assigned voice", self.js)

    def test_jump_to_approval_controls_targets_real_casting_plan_area(self) -> None:
        self.assertIn("#castingPlanApprovalControls", self.js)
        self.assertNotIn("#speakerReviewApprovalControls')?.scrollIntoView", self.js)

    def test_existing_plan_deemphasizes_draft_tools(self) -> None:
        for value in (
            "has-existing-plan",
            "speakerDraftExistingPlanWarning",
            "$('#speakerReviewPanel').classList.toggle('has-existing-plan',existingPlan)",
            "$('#approveSpeakerReview').textContent=speakerDraftApprovalLabel",
            "Nâng cao / gợi ý AI",
            "Đừng xem đây là bước duyệt cuối",
        ):
            self.assertIn(value, self.html + self.js + self.css)

    def test_production_flow_guide_lists_core_steps(self) -> None:
        for value in (
            "PRODUCTION_FLOW_STEPS",
            "productionStepTitle",
            "title:'Chọn chương'",
            "title:'Kiểm tra văn bản'",
            "title:'Gán giọng'",
            "title:'Duyệt bản đồ giọng cuối'",
            "title:'Tạo audio chương'",
            "title:'Nghe kiểm tra / Chốt bản cuối'",
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
            "Chọn chương khác",
            "Text revision hiện tại chưa được duyệt.",
            "Chưa có Casting Plan.",
            "Bước tạo audio vẫn bị chặn cho đến khi Bản đồ giọng cuối được duyệt.",
            "Chương này đã có audio; hãy dùng QA hoặc replacement workflow thay vì render thường.",
            "App chưa lưu trạng thái human QA trong database; hãy ghi verdict riêng nếu cần.",
        ):
            self.assertIn(value, self.html + self.js)

    def test_select_chapter_step_resets_on_open_and_does_not_close_on_stepper_click(self) -> None:
        for value in (
            "state.productionFlow={chapterId:id,selectedStepId:null,autoSelected:true}",
            "focusProductionFlowStep(button.dataset.flowStep,{exitToChapterList:false})",
            "$('#productionFlowContinue').onclick=()=>focusProductionFlowStep(selected.id,{exitToChapterList:selected.id==='select-chapter'})",
            "$('#productionFlowPanel')?.scrollIntoView({behavior:'smooth',block:'start'})",
        ):
            self.assertIn(value, self.js)

    def test_opening_flow_aligns_selected_step_with_recommended_step_without_breaking_manual_navigation(self) -> None:
        script = r"""
const PRODUCTION_FLOW_STEPS=[
  {id:'select-chapter',number:1,title:'Chọn chương'},
  {id:'review-text',number:2,title:'Kiểm tra văn bản'},
  {id:'assign-voices',number:3,title:'Gán giọng'},
  {id:'review-voice-map',number:4,title:'Duyệt bản đồ giọng cuối'},
  {id:'render-chapter',number:5,title:'Tạo audio chương'},
  {id:'review-audio',number:6,title:'Nghe kiểm tra / Chốt bản cuối'},
];
const state={productionFlow:null};
function ensureProductionFlowSelection(chapterId,recommendedStepId='select-chapter',reset=false){if(reset||state.productionFlow?.chapterId!==chapterId)state.productionFlow={chapterId,selectedStepId:null,autoSelected:true};if(state.productionFlow?.autoSelected||!state.productionFlow?.selectedStepId)state.productionFlow.selectedStepId=recommendedStepId||'select-chapter';if(!state.productionFlow?.selectedStepId)state.productionFlow.selectedStepId='select-chapter';if(state.productionFlow?.autoSelected===undefined)state.productionFlow.autoSelected=false}
function selectProductionFlowStep(stepId,{auto=false}={}){state.productionFlow={...(state.productionFlow||{}),selectedStepId:stepId||'select-chapter',autoSelected:auto}}
function renderProductionFlow(model,chapterId){ensureProductionFlowSelection(chapterId,model.currentStepId);const recommended=model.steps.find(step=>step.id===model.currentStepId)||model.steps[0];if(!model.steps.some(step=>step.id===state.productionFlow?.selectedStepId)){selectProductionFlowStep(recommended.id,{auto:true})}return {selected:state.productionFlow.selectedStepId,recommended:recommended.id,autoSelected:state.productionFlow.autoSelected}}
const reviewAudioModel={currentStepId:'review-audio',steps:PRODUCTION_FLOW_STEPS};
const renderModel={currentStepId:'render-chapter',steps:PRODUCTION_FLOW_STEPS};
const castingModel={currentStepId:'assign-voices',steps:PRODUCTION_FLOW_STEPS};
const firstOpen=renderProductionFlow(reviewAudioModel,357);
selectProductionFlowStep('review-text');
const manualNav=renderProductionFlow(reviewAudioModel,357);
const reopenSameChapter=(()=>{state.productionFlow={chapterId:357,selectedStepId:null,autoSelected:true};return renderProductionFlow(reviewAudioModel,357)})();
const differentChapter=(()=>{state.productionFlow={chapterId:357,selectedStepId:'review-audio',autoSelected:false};return renderProductionFlow(renderModel,358)})();
const staleReset=(()=>{state.productionFlow={chapterId:358,selectedStepId:'render-chapter',autoSelected:true};return renderProductionFlow(castingModel,358)})();
console.log(JSON.stringify({firstOpen,manualNav,reopenSameChapter,differentChapter,staleReset}));
"""
        result = subprocess.run(
            ["node", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["firstOpen"]["selected"], "review-audio")
        self.assertTrue(payload["firstOpen"]["autoSelected"])
        self.assertEqual(payload["manualNav"]["selected"], "review-text")
        self.assertFalse(payload["manualNav"]["autoSelected"])
        self.assertEqual(payload["reopenSameChapter"]["selected"], "review-audio")
        self.assertTrue(payload["reopenSameChapter"]["autoSelected"])
        self.assertEqual(payload["differentChapter"]["selected"], "render-chapter")
        self.assertEqual(payload["staleReset"]["selected"], "assign-voices")

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
            "Công cụ A/B candidate/original và xử lý segment chỉ thuộc ngữ cảnh QA và phần Nâng cao / Gỡ lỗi.",
            "Nâng cao / Gỡ lỗi: QA và xử lý sự cố segment",
            "Chốt bản audio cuối",
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
