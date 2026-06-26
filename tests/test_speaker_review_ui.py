from __future__ import annotations

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
            "approveSpeakerReview",
        ):
            self.assertIn(value, self.html)
        self.assertIn("draft.stale||count===0", self.js)
        self.assertIn("!row.reviewed&&!decision", self.js)
        self.assertNotIn("Approve all high confidence", self.html)

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