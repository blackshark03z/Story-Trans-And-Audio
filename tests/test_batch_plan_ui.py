from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BatchPlanUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")

    def _function_block(self, name: str) -> str:
        marker = f"function {name}"
        start = self.js.index(marker)
        next_match = re.search(r"\n(?:async\s+)?function\s+\w+", self.js[start + 1 :])
        end = start + 1 + next_match.start() if next_match else len(self.js)
        return self.js[start:end]

    def _batch_html(self) -> str:
        start = self.html.index('id="batchPlanPanel"')
        end = self.html.index('id="productionQueuePanel"')
        return self.html[start:end]

    def test_batch_plan_panel_reuses_range_scope_surface(self) -> None:
        block = self._batch_html()
        for value in (
            'id="batchPlanTargetPhase"',
            'id="buildBatchPlan"',
            'id="batchPlanStatus"',
            'id="batchPlanError"',
            'id="retryBatchPlan"',
            'id="batchPlanResult"',
            "MUTATION_NOT_AUTHORIZED",
            "Chạy readiness trước khi lập kế hoạch batch.",
        ):
            self.assertIn(value, block)
        self.assertLess(self.html.index('id="preview"'), self.html.index('id="batchPlanPanel"'))

    def test_target_phase_selector_contains_only_supported_enums_and_default_prepare(self) -> None:
        block = self._batch_html()
        values = re.findall(r'<option value="([^"]+)"', block)
        self.assertEqual(
            values,
            ["APPROVAL", "PREPARE", "START_RENDER", "RESUME_OR_MONITOR", "QA_CLOSEOUT", "NO_ACTION"],
        )
        self.assertIn('<option value="PREPARE" selected>', block)
        selector = self._function_block("batchPlanTargetPhase")
        self.assertIn("BATCH_TARGET_PHASES.includes(value)", selector)
        self.assertNotIn("fetch", selector)

    def test_batch_plan_accessibility_and_route_isolation_markup(self) -> None:
        block = self._batch_html()
        for value in (
            'aria-labelledby="batchPlanHeading"',
            'for="batchPlanTargetPhase"',
            'aria-describedby="batchPlanStatus"',
            'role="status"',
            'aria-live="polite"',
            'role="alert"',
        ):
            self.assertIn(value, block)
        production_start = self.html.index('id="productionView"')
        production_end = self.html.index('id="voicesView"')
        self.assertGreater(self.html.index('id="batchPlanPanel"'), production_start)
        self.assertLess(self.html.index('id="batchPlanPanel"'), production_end)

    def test_build_batch_plan_uses_get_only_endpoint_and_current_scope(self) -> None:
        block = self._function_block("buildBatchPlan")
        self.assertIn("/api/production/batch-plan?", block)
        self.assertIn("book_id:String(scope.book_id)", block)
        self.assertIn("from_chapter:String(scope.from_chapter)", block)
        self.assertIn("to_chapter:String(scope.to_chapter)", block)
        self.assertIn("target_phase:phase", block)
        self.assertNotIn("data.endpoint", block)
        self.assertNotIn("data?.execution_endpoint", block)
        for method in ("method:'POST'", "method:'PUT'", "method:'PATCH'", "method:'DELETE'"):
            self.assertNotIn(method, block)

    def test_authorization_banner_and_contract_fail_closed(self) -> None:
        build = self._function_block("buildBatchPlan")
        render = self._function_block("renderBatchPlanResult")
        self.assertIn("data?.authorization?.status!=='MUTATION_NOT_AUTHORIZED'", build)
        self.assertIn("data?.authorization?.execution_endpoint_available!==false", build)
        self.assertIn("Batch plan contract changed: mutation is not fail-closed.", build)
        self.assertIn("Chỉ xem trước", render)
        self.assertIn("Không có endpoint thực thi", render)
        self.assertIn("Không có dữ liệu production nào được thay đổi", render)

    def test_summary_included_excluded_safety_and_fingerprint_render_from_backend(self) -> None:
        render = self._function_block("renderBatchPlanResult")
        for field in (
            "data?.summary?.total",
            "data?.summary?.eligible",
            "data?.summary?.excluded",
            "data?.summary?.blocked",
            "data?.summary?.already_complete",
            "data?.plan_fingerprint",
            "data?.execution_contract?.idempotency?.status",
            "data?.execution_contract?.retry?.status",
            "data?.execution_contract?.partial_failure?.status",
        ):
            self.assertIn(field, render)
        self.assertIn("shortFingerprint", render)
        self.assertNotIn("execution token", render.lower())
        self.assertNotIn("data?.included?.length", render)
        self.assertNotIn("data?.excluded?.length", render)

    def test_included_and_excluded_render_backend_rows_without_reclassification(self) -> None:
        render = self._function_block("renderBatchPlanResult")
        rows = self._function_block("renderBatchPlanRows")
        self.assertIn("data?.included", render)
        self.assertIn("data?.excluded", render)
        self.assertEqual(render.count("renderBatchPlanRows(root,data?.included"), 1)
        self.assertEqual(render.count("renderBatchPlanRows(root,data?.excluded"), 1)
        self.assertIn("Array.isArray(items)?items:[]", rows)
        self.assertNotIn(".sort(", render + rows)
        self.assertNotIn("filter(", render + rows)
        self.assertIn("Không có chương nào đủ điều kiện cho phase này.", render)
        self.assertIn("Không có chương nào bị loại khỏi kế hoạch.", render)

    def test_reason_labels_and_unknown_reason_fail_safe(self) -> None:
        labels = self._function_block("batchPlanReasonLabel")
        for code, label in (
            ("HUMAN_QA_NOT_ACCEPTED", "Chưa hoàn tất Human QA"),
            ("ACTIVE_OUTPUT_COMPLETE", "Đã có output hoàn tất"),
            ("CASTING_PLAN_NOT_APPROVED", "Bản đồ giọng chưa được duyệt"),
            ("PREPARED_JOB_EXISTS", "Đã có job được chuẩn bị"),
            ("LIVE_JOB_REQUIRES_MONITOR_OR_RESUME", "Đang render hoặc tạm dừng"),
        ):
            self.assertIn(code, labels)
            self.assertIn(label, labels)
        self.assertIn("Chưa xác định lý do", labels)

    def test_safety_status_labels_do_not_overstate_support(self) -> None:
        labels = self._function_block("batchPlanSupportLabel")
        self.assertIn("PARTIALLY_SUPPORTED", labels)
        self.assertIn("NOT_YET_DEFINED", labels)
        self.assertIn("SUPPORTED", labels)
        self.assertIn("UNSUPPORTED", labels)
        self.assertNotIn("FULLY_SUPPORTED", labels)

    def test_open_chapter_uses_existing_read_only_navigation(self) -> None:
        row = self._function_block("renderBatchPlanRow")
        open_fn = self._function_block("openRangeReadinessChapter")
        self.assertIn("openRangeReadinessChapter(item.chapter_id)", row)
        self.assertIn("setAppRoute('production')", open_fn)
        self.assertIn("openChapter(Number(chapterId),{initialTab:'casting'})", open_fn)
        self.assertNotIn("location.href", row + open_fn)
        self.assertNotIn("item.route", row + open_fn)
        for method in ("method:'POST'", "method:'PUT'", "method:'PATCH'", "method:'DELETE'"):
            self.assertNotIn(method, row + open_fn)

    def test_loading_retry_refresh_scope_and_phase_invalidation_exist(self) -> None:
        build = self._function_block("buildBatchPlan")
        clear = self._function_block("clearBatchPlanResult")
        check = self._function_block("checkRangeReadiness")
        phase_handler = re.search(
            r"on\('#batchPlanTargetPhase','change',\(\)=>\{(?P<body>.*?)\}\);",
            self.js,
        )
        self.assertIsNotNone(phase_handler)
        phase_body = phase_handler.group("body")
        self.assertIn("state.batchPlan.loading=true", build)
        self.assertIn("Đang lập kế hoạch batch", build)
        self.assertIn("on('#retryBatchPlan','click',refreshBatchPlan)", self.js)
        self.assertIn("on('#buildBatchPlan','click',buildBatchPlan)", self.js)
        self.assertIn("on('#batchPlanTargetPhase','change'", self.js)
        self.assertIn("clearBatchPlanResult('Phase lập kế hoạch đã thay đổi.", self.js)
        self.assertIn("clearBatchPlanResult('Đang kiểm tra lại readiness", check)
        self.assertIn("clearElement(result)", clear)

        self.assertNotIn("buildBatchPlan", phase_body)
        self.assertNotIn("api(", phase_body)
        self.assertEqual(self.js.count("on('#buildBatchPlan','click',buildBatchPlan)"), 1)
        self.assertEqual(self.js.count("on('#retryBatchPlan','click',refreshBatchPlan)"), 1)

    def test_stale_response_protection_is_request_scope_and_phase_based(self) -> None:
        build = self._function_block("buildBatchPlan")
        self.assertIn("state.batchPlan.requestId+=1", build)
        self.assertIn("const requestId=state.batchPlan.requestId", build)
        self.assertIn("scopeKey!==batchPlanScopeKey()", build)
        self.assertIn("return", build)

    def test_batch_rendering_uses_safe_dom_without_inner_html(self) -> None:
        for name in (
            "renderBatchPlanResult",
            "renderBatchPlanRow",
            "renderBatchPlanRows",
            "appendBatchMetric",
            "appendBatchDetail",
        ):
            block = self._function_block(name)
            self.assertIn("document.createElement", block)
            self.assertIn("textContent", block)
            self.assertNotIn("innerHTML", block)

    def test_no_execution_controls_or_chapter_369_special_case(self) -> None:
        block = self._batch_html()
        forbidden_ids = (
            "executeBatch",
            "approveBatch",
            "prepareBatch",
            "startBatch",
            "resumeBatch",
            "renderBatch",
            "acceptBatchQa",
            "rejectBatchQa",
        )
        for value in forbidden_ids:
            self.assertNotIn(value, block)
        related = "\n".join(line for line in self.js.splitlines() if "BatchPlan" in line or "batchPlan" in line)
        self.assertNotIn("369", related)
        self.assertNotIn("prepareJob", related)
        self.assertNotIn("startPreparedJob", related)
        for method in ("method:'POST'", "method:'PUT'", "method:'PATCH'", "method:'DELETE'"):
            self.assertNotIn(method, related)

    def test_styles_cover_batch_plan_review_and_mobile(self) -> None:
        for value in (
            ".plan-review-panel",
            ".plan-authorization-banner",
            ".plan-summary-grid",
            ".plan-row",
            ".plan-safety-grid",
            "@media(max-width:900px){.plan-summary-grid",
        ):
            self.assertIn(value, self.css)


if __name__ == "__main__":
    unittest.main()
