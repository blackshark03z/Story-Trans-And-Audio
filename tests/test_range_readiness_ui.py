from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RangeReadinessUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")
        cls.resolver = (ROOT / "ui" / "production_state.js").read_text(encoding="utf-8")

    def _function_block(self, name: str) -> str:
        marker = f"function {name}"
        start = self.js.index(marker)
        next_match = re.search(r"\n(?:async\s+)?function\s+\w+", self.js[start + 1 :])
        end = start + 1 + next_match.start() if next_match else len(self.js)
        return self.js[start:end]

    def _range_html(self) -> str:
        start = self.html.index('id="productionLegacyJobPanel"')
        end = self.html.index('id="productionQueuePanel"')
        return self.html[start:end]

    def test_range_form_has_book_scope_inputs_and_check_action(self) -> None:
        block = self._range_html()
        for value in (
            'id="fromChapter"',
            'id="toChapter"',
            'id="previewBtn"',
            'Kiểm tra phạm vi',
            'id="rangeReadinessStatus"',
            'id="rangeReadinessValidation"',
            'id="refreshRangeReadiness"',
            'id="retryRangeReadiness"',
        ):
            self.assertIn(value, block)
        self.assertIn('id="workspace"', self.html)
        self.assertIn('id="bookTitle"', self.html)

    def test_range_surface_does_not_include_legacy_mutation_controls(self) -> None:
        block = self._range_html()
        forbidden = ("runBtn", "voiceSelect", "loadVoices", "previewVoice", "repairMode", "skipCompleted")
        for value in forbidden:
            self.assertNotIn(value, block)
        self.assertNotIn("Thêm vào hàng đợi", block)

    def test_check_scope_uses_get_only_range_readiness_endpoint(self) -> None:
        block = self._function_block("checkRangeReadiness")
        self.assertIn("/api/production/range-readiness?", block)
        self.assertIn("book_id:String(scope.book_id)", block)
        self.assertIn("from_chapter:String(scope.from_chapter)", block)
        self.assertIn("to_chapter:String(scope.to_chapter)", block)
        for method in ("method:'POST'", "method:'PUT'", "method:'PATCH'", "method:'DELETE'"):
            self.assertNotIn(method, block)

    def test_single_chapter_is_valid_and_invalid_ranges_do_not_fetch(self) -> None:
        validate = self._function_block("validateRangeReadinessScope")
        check = self._function_block("checkRangeReadiness")
        self.assertIn("scope.from_chapter>scope.to_chapter", validate)
        self.assertNotIn("scope.from_chapter>=scope.to_chapter", validate)
        for message in (
            "Hãy chọn sách trước",
            "Hãy nhập chương bắt đầu",
            "Hãy nhập chương kết thúc",
            "Chương bắt đầu không được lớn hơn",
            "Phạm vi chương phải thuộc sách đang chọn",
        ):
            self.assertIn(message, validate)
        self.assertIn("if(!validation.valid)", check)
        self.assertLess(check.index("if(!validation.valid)"), check.index("/api/production/range-readiness?"))

    def test_summary_counts_render_from_api_response_fields(self) -> None:
        block = self._function_block("renderRangeReadinessResult")
        for field in (
            "data?.summary?.total",
            "data?.summary?.complete",
            "data?.summary?.ready_to_prepare",
            "data?.summary?.needs_attention",
            "data?.summary?.prepared",
            "data?.summary?.rendering_or_paused",
        ):
            self.assertIn(field, block)

    def test_chapter_list_and_exception_queue_keep_backend_order(self) -> None:
        block = self._function_block("renderRangeReadinessResult")
        self.assertIn("data?.chapters", block)
        self.assertIn("data.chapters:[]).forEach", block)
        self.assertIn("data?.exceptions", block)
        self.assertIn("exceptionItems.forEach", block)
        self.assertNotIn(".sort(", block)

    def test_readiness_labels_cover_required_states_and_unknown(self) -> None:
        block = self._function_block("rangeReadinessStateLabel")
        for state in (
            "CASTING_REVIEW",
            "READY_TO_PREPARE",
            "RENDERING_OR_PAUSED",
            "RENDERED_NOT_QA",
            "COMPLETE",
            "Chưa xác định",
        ):
            self.assertIn(state, block)
        unknown_tail = block[block.rindex("||") :]
        self.assertNotIn("Hoàn tất", unknown_tail)
        self.assertNotIn("Sẵn sàng chuẩn bị", unknown_tail)

    def test_exception_queue_renders_only_backend_exceptions(self) -> None:
        block = self._function_block("renderRangeReadinessResult")
        self.assertIn("const exceptionItems=Array.isArray(data?.exceptions)?data.exceptions:[]", block)
        self.assertIn("Không có chương nào cần xử lý trước.", block)
        self.assertNotIn("requires_operator_action", block)
        self.assertNotIn("state!=='COMPLETE'", block)

    def test_open_chapter_navigation_uses_existing_production_flow(self) -> None:
        block = self._function_block("openRangeReadinessChapter")
        self.assertIn("setAppRoute('production')", block)
        self.assertIn("openChapter(Number(chapterId),{initialTab:'casting'})", block)
        for method in ("method:'POST'", "method:'PUT'", "method:'PATCH'", "method:'DELETE'"):
            self.assertNotIn(method, block)

    def test_loading_error_retry_refresh_and_scope_invalidation_exist(self) -> None:
        check = self._function_block("checkRangeReadiness")
        clear = self._function_block("clearRangeReadinessResult")
        self.assertIn("state.rangeReadiness.loading=true", check)
        self.assertIn("Đang kiểm tra phạm vi", check)
        self.assertIn("Không tải được readiness cho phạm vi này. Vui lòng kiểm tra lựa chọn rồi thử lại.", check)
        self.assertIn("clearElement(result)", clear)
        self.assertIn("on('#refreshRangeReadiness','click',refreshRangeReadiness)", self.js)
        self.assertIn("on('#retryRangeReadiness','click',refreshRangeReadiness)", self.js)
        self.assertIn("Phạm vi đã thay đổi. Hãy kiểm tra lại", self.js)

    def test_stale_response_protection_is_request_and_scope_key_based(self) -> None:
        block = self._function_block("checkRangeReadiness")
        self.assertIn("state.rangeReadiness.requestId+=1", block)
        self.assertIn("const requestId=state.rangeReadiness.requestId", block)
        self.assertIn("scopeKey!==rangeReadinessScopeKey()", block)
        self.assertIn("return", block)

    def test_range_rendering_uses_safe_dom_without_inner_html(self) -> None:
        for name in ("renderRangeReadinessResult", "renderRangeChapterCard", "renderRangeExceptionCard"):
            block = self._function_block(name)
            self.assertIn("document.createElement", block)
            self.assertIn("textContent", block)
            self.assertNotIn("innerHTML", block)

    def test_no_hard_coded_chapter_369_or_batch_mutation_in_range_code(self) -> None:
        related = "\n".join(line for line in self.js.splitlines() if "RangeReadiness" in line or "rangeReadiness" in line)
        for value in ("369", "/approve", "prepare selected", "regenerate", "human QA mutation", "method:'POST'", "method:'PUT'", "method:'PATCH'", "method:'DELETE'"):
            self.assertNotIn(value, related)

    def test_range_panel_belongs_to_scope_and_prepare_stages_and_is_route_isolated(self) -> None:
        self.assertIn("{id:'productionLegacyJobPanel',stages:['scope','prepare'],kind:'work'}", self.resolver)
        self.assertIn(".app-view[hidden]{display:none!important}", self.css)
        self.assertIn("view.hidden=!active", self.js)
        select_book = self._function_block("selectBook")
        self.assertIn("state.dialog=null", select_book)
        self.assertIn("state.casting=null", select_book)
        self.assertIn("state.speakerReview=null", select_book)
        self.assertLess(select_book.index("state.dialog=null"), select_book.index("setAppRoute('production')"))

    def test_styles_cover_summary_chapters_exceptions_and_mobile(self) -> None:
        for value in (
            ".range-readiness-panel",
            ".range-summary-grid",
            ".range-chapter-card",
            ".range-exception-card",
            "@media(max-width:900px){.range-summary-grid",
        ):
            self.assertIn(value, self.css)


    def test_voice_replacement_details_render_without_fallback(self) -> None:
        helper = self._function_block("appendVoiceEligibilityIssues")
        exception = self._function_block("renderRangeExceptionCard")
        for value in (
            "voice_id",
            "speaker",
            "chapter_number",
            "replacement required",
            "không có fallback",
        ):
            self.assertIn(value, helper)
        self.assertIn("voice_issues", exception)
        self.assertIn(".voice-eligibility-list", self.css)


if __name__ == "__main__":
    unittest.main()
