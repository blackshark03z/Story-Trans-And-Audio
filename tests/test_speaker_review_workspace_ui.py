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
            "Đề xuất của Gemini",
            "Quyết định cuối cùng của bạn",
            "Chấp nhận đề xuất Gemini",
            "Lưu chỉnh sửa và duyệt",
            "Bỏ chỉnh sửa",
            "Sửa người nói",
            "Chọn tạo nhân vật mới",
            "Sửa cấu hình giọng",
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

    def test_proposal_and_human_decision_have_one_state_driven_submit(self) -> None:
        for marker in (
            "speakerReviewProposalPayload",
            "speakerReviewDecisionChanges",
            "speakerReviewDecisionValidation",
            "speakerReviewDecisionMeta",
            "submitSpeakerReviewDecision",
            'data-speaker-suggestion-submit',
            'data-speaker-submit-mode',
        ):
            self.assertIn(marker, self.js)
        self.assertIn("Đang giữ nguyên đề xuất Gemini", self.js)
        self.assertIn("Đã chỉnh sửa ${meta.changes.length} trường", self.js)
        self.assertIn("root.querySelectorAll('[data-speaker-suggestion-submit]')", self.js)
        self.assertIn("meta.edited?'EDIT_AND_ACCEPT_SPEAKER_SUGGESTION':'ACCEPT_SPEAKER_SUGGESTION'", self.js)

    def test_shortcuts_and_discard_are_local_only(self) -> None:
        self.assertIn("applySpeakerReviewShortcut", self.js)
        self.assertIn("discardSpeakerSuggestionEdits", self.js)
        self.assertIn("clearSpeakerSuggestionDraft(key)", self.js)
        self.assertIn("shortcutsNoMutation", (ROOT / "scripts" / "browser_speaker_review_workspace_smoke.mjs").read_text(encoding="utf-8"))

    def test_analyze_progress_is_visible_truthful_and_bounded(self) -> None:
        for label in (
            "Đang chuẩn bị ${Number(progress.targetCount||0)} câu",
            "Đang gửi Gemini — nhóm 1/đang xác định",
            "Đang kiểm tra kết quả",
            "Gemini vẫn đang phân tích. Bạn có thể tiếp tục chờ; không cần bấm lại.",
            "Đang xác minh kết quả đã lưu",
            "Đã tạo ${Number(summary.total||progress.targetCount||0)} đề xuất",
        ):
            self.assertIn(label, self.js)
        self.assertIn("speakerAnalysisProgressTimer", self.js)
        self.assertIn("executeSpeakerAnalysis", self.js)

    def test_background_group_decision_is_bounded_and_explains_voice_scope(self) -> None:
        for marker in (
            "BACKGROUND_GROUP",
            "data-speaker-suggestion-group",
            "speaker_classification",
            "gender_hint",
            "grouping_reason",
            "generic_speaker_evidence",
            "continuity_evidence",
            "background_group",
        ):
            self.assertIn(marker, self.js)
        for label in (
            "Nhóm quần chúng / nhân vật phụ",
            "Quần chúng nam",
            "Quần chúng nữ",
            "Quần chúng trung tính",
            "Toàn bộ sách",
            "nhóm tạo / tái sử dụng",
            "nhóm chưa có giọng",
        ):
            self.assertIn(label, self.js)
        self.assertIn(".speaker-classification-summary", self.css)

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
        self.assertIn("speakerReviewDurableBatchResult", self.js)
        self.assertIn("latest_batch_result", self.js)
        self.assertIn("unsaved_human_edit", self.js)
        self.assertIn("approval_exclusion_reasons", self.js)
        self.assertIn("Không PREPARE và không render", self.js)
        self.assertIn("APPROVE_SPEAKER_REVIEW_BATCH", self.js)
        self.assertIn("background_voice_unassigned", self.js)
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

    def test_active_review_controls_defer_changed_snapshots_without_stopping_polling(self) -> None:
        for marker in (
            "speakerReviewQueueFingerprint",
            "activeSpeakerReviewControl",
            "deferredResult",
            "showSpeakerReviewDeferredNotice",
            "applyDeferredSpeakerReviewUpdate",
            "Có dữ liệu mới — sẽ cập nhật sau khi bạn hoàn tất chỉnh sửa.",
            "state.currentRoute!=='assignment'",
        ):
            self.assertIn(marker, self.js)
        self.assertIn("speaker-review-deferred-notice", self.css)


if __name__ == "__main__":
    unittest.main()
