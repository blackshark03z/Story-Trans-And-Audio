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
        reconciliation = self._function_source("submitAndReconcileProductionCommand")
        self.assertIn("/api/production/commands", self.js)
        self.assertIn("idempotencyKey", coordinator)
        self.assertIn("postProductionCommand(commandRequest,authorizationToken)", reconciliation)
        self.assertIn("productionInteractionEpoch", coordinator)
        self.assertIn("VERIFYING_UNKNOWN", reconciliation)
        self.assertIn("productionCommandClientFailure", reconciliation)
        self.assertIn("failProductionCommand", reconciliation)
        self.assertIn("await submit()", reconciliation)
        self.assertIn("applyProductionCommandEnvelope", reconciliation)
        self.assertIn("retryRequest:commandRequest", coordinator)
        self.assertIn("AbortController", self.js)
        self.assertIn("result_metadata", self.js)
        self.assertIn("speakerReviewResponseIsCurrent", self.js)
        self.assertIn("loadSpeakerReviewSuggestions({force:true})", self.js)

    def test_command_verification_does_not_hide_validation_failures(self) -> None:
        coordinator = self._function_source("submitAndReconcileProductionCommand")
        self.assertIn("productionCommandClientFailure(error)", coordinator)
        self.assertIn("status>=400&&status<500", self.js)
        self.assertIn("status:'FAILED'", self.js)
        self.assertIn("Có thể thử lại an toàn", self.js)
        self.assertIn("delays=[300,700,1400]", coordinator)

    def test_same_chapter_command_sync_refreshes_context(self) -> None:
        sync = self._function_source("syncCanonicalProductionContext")
        self.assertIn("sameChapter", sync)
        self.assertIn("await openChapter(chapterId", sync)
        self.assertNotIn("===chapterId)return", sync)
        self.assertIn("syncProductionRangeReadinessFromProjection(projection)", self.js)

    def test_complete_stage_offers_audio_actions(self) -> None:
        self.assertIn("function productionCompleteTaskContent(vm)", self.js)
        self.assertIn("productionCompleteOpenAudio", self.js)
        self.assertIn("productionCompleteDownload", self.js)
        self.assertIn("/api/artifacts/${artifactIds[0]}/file", self.js)
        self.assertIn("vm?.task_type==='COMPLETE'", self.js)

    def test_production_qa_accept_uses_projected_artifact_target(self) -> None:
        self.assertIn("function currentProductionQaCommandTarget()", self.js)
        self.assertIn("qa.artifact_id||state.dialog?.audio_artifact", self.js)
        approval = self._function_source("updateHumanApproval")
        self.assertIn("currentProductionQaCommandTarget()", approval)
        self.assertIn("artifactProductionCommandScope(artifactId)", approval)
        self.assertIn("payload:{chapter_id:target.chapterId,notes}", approval)

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

    def test_apply_repair_plan_is_a_separate_review_only_command(self) -> None:
        source = self._function_source("applyRepairPlan")
        self.assertIn("commandType:'APPLY_REPAIR_PLAN'", source)
        self.assertIn("runProductionCommand", source)
        self.assertIn("Đang áp dụng kế hoạch sửa…", source)
        self.assertIn("repairReviewDraft", self.js)
        self.assertIn("Đã tạo bản sửa để kiểm tra.", self.js)
        self.assertNotIn("prepareReplacementArtifact(vm)", source)

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

    def test_milestone_one_uses_verified_runtime_readiness_and_one_journey_primary(self) -> None:
        for state in (
            "RESOLVE_BLOCKERS",
            "READY_TO_PREPARE",
            "PREPARING",
            "READY_TO_RENDER",
            "RENDERING",
            "READY_FOR_QA",
            "REPAIR_REQUIRED",
            "COMPLETE",
            "INFRASTRUCTURE_BLOCKED",
        ):
            self.assertIn(state, self.js)
        for label in (
            "Xử lý điều kiện còn thiếu",
            "Chuẩn bị audio",
            "Đang chuẩn bị…",
            "Bắt đầu tạo audio",
            "Đang tạo audio…",
            "Nghe và duyệt",
            "Sửa và tạo bản thay thế",
            "Mở audio đã hoàn tất",
            "Kiểm tra lại môi trường",
        ):
            self.assertIn(label, self.js)
        self.assertIn("dataset.journeyPrimary", self.js)
        self.assertIn("operator_authentication_verified", self.js)
        self.assertNotIn("productionTaskOperatorToken", self.js)
        self.assertNotIn("productionPrepareToken", self.js)

    def test_prepare_checkpoint_reuses_the_same_idempotency_request_after_reload(self) -> None:
        self.assertIn("PRODUCTION_COMMAND_CHECKPOINT_KEY", self.js)
        self.assertIn("persistProductionCommandCheckpoint", self.js)
        self.assertIn("restoreProductionCommandCheckpoint", self.js)
        self.assertIn("resumeProductionCommandCheckpoint", self.js)
        self.assertIn("retryRequest:commandRequest", self.js)
        self.assertIn("Đang khôi phục kết quả PREPARE đã gửi", self.js)

    def test_prepared_job_remains_visible_when_render_gate_is_closed(self) -> None:
        self.assertIn("const preparedJob=String(vm?.render?.job_status", self.js)
        self.assertIn("journeyVm.journey_state==='READY_TO_RENDER'&&!startRenderAllowed()", self.js)
        self.assertIn("Audio đã được chuẩn bị. Sẵn sàng bắt đầu tạo audio.", self.js)

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

    def test_repair_workflow_labels_and_context_hooks_are_present(self) -> None:
        for text in (
            "REPAIR_REQUIRED",
            "Bản audio này cần sửa",
            "Xác nhận nội dung và người nói",
            "Hoàn tất cấu hình giọng",
            "Kế hoạch sửa Chương",
            "Xác nhận kế hoạch sửa",
            "Duyệt người nói Chương",
            "Hoàn tất giọng cho Chương",
            "openRepairAssignment",
            "assignmentContextLoading",
            "assignmentReturnToRepair",
            "Đang mở đúng chương để gán giọng.",
        ):
            self.assertIn(text, self.js)
        self.assertIn("Quay lại bản audio cần sửa", self.html)
        self.assertIn("assignment-page-actions", self.css)

    def test_repair_required_hides_legacy_qa_verdict_controls(self) -> None:
        self.assertIn("humanApprovalMatchesActive(state.dialog)", self.js)
        self.assertIn("approvalConcludesActive", self.js)
        self.assertIn("displayState==='REPAIR_REQUIRED'", self.js)
        self.assertIn("hideVerdicts", self.js)
        self.assertIn("flowFinalizeOutput", self.js)
        self.assertIn("flowNeedsFixes", self.js)
        self.assertIn("classList.toggle('hidden',hideVerdicts)", self.js)
        self.assertIn("productionCommandBusy()", self.js)

    def test_repair_plan_confirmation_replaces_handlers_and_blocks_busy_resubmission(self) -> None:
        start = self.js.index("function bindProductionRepairActions")
        end = self.js.index("async function confirmRepairPlan", start)
        bindings = self.js[start:end]
        confirm_start = end
        confirm_end = self.js.index("async function prepareReplacementArtifact", confirm_start)
        confirm = self.js[confirm_start:confirm_end]
        self.assertIn("confirmPlan.onclick=()=>confirmRepairPlan(vm)", bindings)
        self.assertNotIn("repairConfirmPlan')?.addEventListener", bindings)
        self.assertIn("if(productionCommandBusy())return;", confirm)
        self.assertIn("CONFIRM_REPAIR_PLAN", confirm)
        self.assertIn("journey==='REPAIR_REQUIRED'?null:primary", self.js)


if __name__ == "__main__":
    unittest.main()
