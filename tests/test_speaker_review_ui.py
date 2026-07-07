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
            "Review flow", "Decisions are local until final approval.",
        ):
            self.assertIn(value, self.html + self.js)
        self.assertIn("draft.stale||count===0", self.js)
        self.assertIn("!row.reviewed&&!decision", self.js)
        self.assertNotIn("Approve all high confidence", self.html)

    def test_active_audio_warning_and_latest_approval_revision_are_rendered(self) -> None:
        for value in (
            "Current active audio: Job",
            "Current playback still uses the active historical plan until a new job is rendered",
            "Latest approval created Casting Plan v",
            "castingPlanGuidance",
            "Review assignments before rendering",
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
