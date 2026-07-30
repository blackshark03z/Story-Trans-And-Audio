from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SpeakerReviewWorkspaceUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")

    def test_queue_views_counts_and_combined_filters_are_explicit(self) -> None:
        for label in (
            "Cần duyệt",
            "Cần quyết định",
            "Đã chỉnh sửa",
            "Đã duyệt",
            "Để sau",
            "Có lỗi",
            "Tất cả",
        ):
            self.assertIn(label, self.js)
        self.assertIn("speakerReviewViewCounts", self.js)
        self.assertIn("speakerReviewFilterMatches", self.js)
        for filter_name in (
            "chapter",
            "confidence",
            "resolution",
            "review",
            "voice",
            "warning",
        ):
            self.assertIn(f'data-speaker-review-filter="{filter_name}"', self.js)

    def test_each_card_has_evidence_decision_provenance_and_owned_actions(self) -> None:
        for marker in (
            "data-speaker-suggestion-card",
            "speaker-card-evidence",
            "speaker-card-decision",
            "speaker-card-actions",
            "data-speaker-suggestion-context",
            "effective_voice_source",
            "future-render-notice",
        ):
            self.assertIn(marker, self.js)
        for label in (
            "Chấp nhận đề xuất",
            "Lưu chỉnh sửa",
            "Chọn nhân vật khác",
            "Tạo nhân vật mới",
            "Đổi giọng",
            "Đánh dấu chưa chắc",
            "Để sau",
            "Chỉnh sửa người nói",
            "Chỉnh sửa giọng",
            "Chỉnh sửa alias",
            "Để lại ghi chú",
            "Khôi phục về chưa duyệt",
            "Tạo quyết định thay thế",
        ):
            self.assertIn(label, self.js)
        self.assertIn(".speaker-suggestion-card", self.css)
        self.assertIn(".status-symbol", self.css)
        self.assertIn(".speaker-suggestion-card.is-editing", self.css)

    def test_command_lifecycle_is_visible_retryable_and_idempotent(self) -> None:
        for status in (
            "SUBMITTING",
            "VERIFYING",
            "VERIFYING_UNKNOWN",
            "APPLIED",
            "PARTIAL",
            "FAILED",
        ):
            self.assertIn(status, self.js)
        self.assertIn("command-spinner", self.js)
        self.assertIn("retryRequest:commandRequest", self.js)
        self.assertIn("retryProductionCommand", self.js)
        self.assertIn("postProductionCommand(commandRequest,authorizationToken)", self.js)
        self.assertIn("Bản nháp vẫn được giữ", self.js)

    def test_batch_preview_excludes_unsaved_or_unsafe_items_and_never_renders(self) -> None:
        self.assertIn("speakerReviewBatchImpact", self.js)
        self.assertIn("unsaved_human_edit", self.js)
        self.assertIn("approval_exclusion_reasons", self.js)
        self.assertIn("Không PREPARE và không render", self.js)
        self.assertIn("APPROVE_SPEAKER_REVIEW_BATCH", self.js)
        for label in ("Yêu cầu:", "Đã duyệt:", "Bị loại:", "Thất bại:"):
            self.assertIn(label, self.js)

    def test_approved_history_and_corrections_preserve_future_render_boundary(self) -> None:
        self.assertIn("review_history", self.js)
        self.assertIn("audit_event_id", self.js)
        self.assertIn("resulting_mapping", self.js)
        self.assertIn("CORRECT_APPROVED_SPEAKER_SUGGESTION", self.js)
        self.assertIn("CREATE_SPEAKER_REPLACEMENT_DECISION", self.js)
        self.assertIn("ADD_SPEAKER_REVIEW_NOTE", self.js)
        self.assertIn("RESTORE_SPEAKER_SUGGESTION_PENDING", self.js)
        self.assertIn("Audio đã chấp nhận hiện tại không bị thay đổi", self.js)
        self.assertIn("downstream_stale", self.js)

    def test_polling_keeps_local_state_separate_from_authoritative_rows(self) -> None:
        for bucket in (
            "drafts",
            "selected",
            "openDetails",
            "filters",
            "cardErrors",
        ):
            self.assertIn(bucket, self.js)
        self.assertIn(
            "speakerReviewResponseIsCurrent(requestId,mutationEpoch)",
            self.js,
        )
        self.assertIn(
            "mutationEpoch===state.productionInteractionEpoch",
            self.js,
        )
        self.assertIn("speakerReviewCardSnapshot", self.js)
        self.assertIn("restoreSpeakerReviewCardSnapshot", self.js)


if __name__ == "__main__":
    unittest.main()
