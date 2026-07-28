from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProductionCommandUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        cls.html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")

    def _function_source(self, name: str) -> str:
        marker = f"async function {name}("
        start = self.js.find(marker)
        self.assertNotEqual(start, -1, name)
        candidates = [
            position
            for position in (
                self.js.find("\nasync function ", start + len(marker)),
                self.js.find("\nfunction ", start + len(marker)),
            )
            if position >= 0
        ]
        end = min(candidates) if candidates else len(self.js)
        return self.js[start:end]

    def test_shared_coordinator_owns_command_lifecycle(self) -> None:
        coordinator = self._function_source("runProductionCommand")
        self.assertIn("/api/production/commands", coordinator)
        self.assertIn("idempotencyKey", coordinator)
        self.assertIn("productionInteractionEpoch", coordinator)
        self.assertIn("VERIFYING_UNKNOWN", coordinator)
        self.assertIn("await submit()", coordinator)
        self.assertIn("applyProductionCommandEnvelope", coordinator)
        self.assertIn("AbortController", self.js)

    def test_production_handlers_do_not_post_directly(self) -> None:
        handlers = (
            "prepareRangeInputs",
            "approveRangeSpeakerDrafts",
            "saveRangeSpeakerException",
            "approveRangeReadySpeakers",
            "saveRangeVoiceException",
            "approveRangeCastingPlans",
            "saveProductionVoiceAssignments",
            "saveVoiceProfile",
            "generateSpeakerDraft",
            "saveSpeakerReviewRow",
            "approveSpeakerReview",
            "createSpeakerReviewCastingPlan",
            "saveCastingDraft",
            "approveCastingPlan",
            "renderCastingPlan",
            "startPreparedJob",
            "retryChapter",
            "retrySegmentAction",
            "regenerateSegment",
            "createRepairBlock",
            "acceptRepairBlock",
            "rejectRepairBlock",
            "acceptCandidate",
            "rejectCandidate",
            "submitAudioQa",
        )
        for name in handlers:
            source = self._function_source(name)
            self.assertTrue(
                "runProductionCommand" in source
                or "approveRangeSpeakerDrafts" in source,
                name,
            )
            self.assertNotIn("method:'POST'", source, name)
            self.assertNotIn("method:'PUT'", source, name)
        self.assertNotIn("fetch('/api/production/batch-prepare", self.js)
        self.assertNotIn("api('/api/production/range-inputs/", self.js)

    def test_visible_status_is_not_toast_only(self) -> None:
        self.assertEqual(self.html.count('id="productionCommandStatus"'), 1)
        for state in (
            "SUBMITTING",
            "APPLIED",
            "PARTIAL",
            "FAILED",
            "ACCEPTED_ASYNC",
            "VERIFYING_UNKNOWN",
        ):
            self.assertIn(state, self.js)
        self.assertIn("production-command-status", self.css)
        self.assertIn("failedItems", self.js)

    def test_approval_evidence_is_human_readable(self) -> None:
        for evidence in (
            "proposal_source",
            "draft_revision",
            "stale",
            "effective_voice_map",
            "speaker_name",
            "effective_voice_name",
            "assignment_source",
            "line_count",
            "affected_chapters",
            "changed_mapping_warning",
        ):
            self.assertIn(evidence, self.js)
        self.assertIn("Chi tiết kỹ thuật", self.js)

    def test_queue_distinguishes_status_rows_from_inspection_controls(self) -> None:
        self.assertIn("Việc tiếp theo", self.js)
        self.assertIn("Đang xử lý", self.js)
        self.assertIn("Đang xem", self.js)
        self.assertIn("Chờ cập nhật", self.js)
        self.assertIn("Đã hoàn tất", self.js)
        self.assertIn("status-only", self.js)
        self.assertIn("Quay lại việc tiếp theo", self.html)


if __name__ == "__main__":
    unittest.main()
