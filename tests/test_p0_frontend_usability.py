from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class P0FrontendUsabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        cls.resolver = (ROOT / "ui" / "production_state.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")

    def test_primary_navigation_is_one_consistent_vietnamese_set(self) -> None:
        nav = re.search(r'<nav id="appNav".*?</nav>', self.html, re.DOTALL)
        self.assertIsNotNone(nav)
        direct = nav.group(0).split('<div id="appNavMore"', 1)[0]
        labels = re.findall(r'<a [^>]*>([^<]+)</a>', direct)
        self.assertEqual(labels, ["Sản xuất", "Gán giọng", "Công việc", "Duyệt audio"])
        for secondary in ("Trang chủ", "Sách", "Giọng", "Dung lượng", "Cài đặt"):
            self.assertIn(secondary, nav.group(0))
        self.assertIn('class="app-nav-group-label">Tài nguyên</span>', nav.group(0))
        self.assertNotIn(">More<", nav.group(0))

    def test_health_summary_hides_diagnostics_until_requested(self) -> None:
        self.assertIn('<details id="systemDiagnostics"', self.html)
        self.assertIn('id="systemHealthLabel"', self.html)
        self.assertIn("'Hệ thống sẵn sàng'", self.js)
        self.assertIn('id="globalRuntimeStatus"', self.html)
        self.assertIn('id="globalSchemaState"', self.html)
        self.assertIn('id="globalAuthState"', self.html)
        self.assertIn('id="globalWorkerState"', self.html)
        self.assertIn("system-diagnostics", self.css)

    def test_scope_dialog_uses_direct_range_form_and_one_primary_action(self) -> None:
        dialog = re.search(
            r'<dialog id="productionScopeDialog".*?</dialog>',
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(dialog)
        markup = dialog.group(0)
        for value in (
            'id="scopeBookSearch"',
            'id="scopeFromChapter"',
            'id="scopeToChapter"',
            'id="scopeSingleChapter"',
            'id="scopeNextMissingAudio"',
            'data-scope-quick="1"',
            'data-scope-quick="5"',
            'data-scope-quick="10"',
            'id="scopeChapterBrowser"',
            'id="reviewProductionScope"',
        ):
            self.assertIn(value, markup)
        self.assertEqual(markup.count('id="reviewProductionScope"'), 1)
        classes = re.findall(r'class="([^"]*)"', markup)
        self.assertEqual(sum("primary" in value.split() for value in classes), 1)
        self.assertNotIn("data-scope-boundary", markup)
        self.assertNotIn('id="confirmProductionScope"', markup)

    def test_direct_entry_quick_selection_rows_and_keyboard_are_wired(self) -> None:
        for value in (
            "pageSize:6",
            "function chooseScopeChapterRow(number)",
            "button.dataset.scopeQuick",
            "event.key==='Enter'",
            "await confirmProductionScope()",
            "status:'not_created'",
        ):
            self.assertIn(value, self.js)

    def test_production_copy_uses_operator_language(self) -> None:
        for value in (
            "Chọn sách và chương",
            "Cần duyệt văn bản",
            "Cần gán giọng",
            "Sẵn sàng chuẩn bị",
            "Bắt đầu render",
            "Cần nghe và duyệt",
        ):
            self.assertIn(value, self.resolver + self.html)

    def test_design_has_no_external_font_or_frontend_framework(self) -> None:
        self.assertNotIn("fonts.googleapis.com", self.html + self.css)
        self.assertNotIn("bootstrap", (self.html + self.js).lower())
        self.assertNotIn("tailwind", (self.html + self.js).lower())
        self.assertIn('"Segoe UI Variable"', self.css)

    def test_calm_production_desk_bounds_daily_long_lists(self) -> None:
        for value in (
            "CALM_PRODUCTION_DESK_V1",
            ".production-task-queue{position:sticky",
            ".production-chapter-queue{max-height:calc(100vh - 165px);overflow-y:auto",
            ".assignment-page #assignmentRows{max-height:min(780px,70vh);overflow-y:auto",
            ".jobs-page-list{max-height:68vh;overflow-y:auto",
            ".audio-library-list{max-height:55vh;overflow-y:auto",
            "@media(prefers-reduced-motion:reduce)",
        ):
            self.assertIn(value, self.css)


if __name__ == "__main__":
    unittest.main()
