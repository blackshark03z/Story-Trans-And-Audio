from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProductConvergenceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")

    def test_primary_navigation_matches_owner_intent(self) -> None:
        nav = re.search(r'<nav id="appNav".*?</nav>', self.html, re.DOTALL)
        self.assertIsNotNone(nav)
        direct = nav.group(0).split('<details id="appNavMore"', 1)[0]
        labels = re.findall(r'<a [^>]*>([^<]+)</a>', direct)
        self.assertEqual(labels, ["Sách", "Sản xuất", "Giọng", "Audio"])

    def test_selecting_a_book_reveals_the_reused_chapter_workspace(self) -> None:
        self.assertEqual(self.html.count('id="chapterList"'), 1)
        books = re.search(
            r'<section id="booksView".*?</section>\s*</section>',
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(books)
        self.assertIn('id="booksChapterWorkspace"', books.group(0))
        self.assertIn("setAppRoute('books')", self.js)
        self.assertIn("openBookChapterAction", self.js)
        self.assertNotIn("Mở quy trình sản xuất", self.js)

    def test_book_character_action_opens_the_existing_editable_manager_directly(self) -> None:
        start = self.js.index("async function openSelectedBookContext")
        end = self.js.index("async function loadChapters", start)
        action = self.js[start:end]
        self.assertIn("route==='characters'", action)
        self.assertIn("await openCasting()", action)
        self.assertIn("setPanelIsolation(assignment,true)", action)
        self.assertIn("setPanelIsolation(memory,true)", action)
        self.assertIn("memory.open=true", action)

        self.assertIn("if(route==='voices'){setAppRoute('voices');await refreshLibrary()", action)
        restore_start = self.js.index("async function restoreScopedWorkingContextFromRoute")
        restore_end = self.js.index("function rememberProductionRange", restore_start)
        self.assertIn("if(route==='voices')await refreshLibrary()", self.js[restore_start:restore_end])

        production_start = self.html.index('<section id="productionView"')
        production_end = self.html.index('<section id="characterReviewView"')
        review_end = self.html.index('<section id="voicesView"')
        self.assertLess(production_start, production_end)
        self.assertLess(production_end, review_end)

    def test_targeted_text_correction_is_wired_as_a_versioned_action(self) -> None:
        for value in (
            'id="textCorrectionExpected"',
            'id="textCorrectionReplacement"',
            'id="textCorrectionReason"',
            'id="applyTargetedTextCorrection"',
            "/text-revisions/targeted-correction",
            "base_revision_id",
        ):
            self.assertIn(value, self.html + self.js)

    def test_preflight_displays_effective_synthesis_settings_read_only(self) -> None:
        self.assertIn("effective_synthesis_settings", self.js)
        for label in ("Temperature", "Top K", "Ký tự tối đa", "Khoảng nghỉ"):
            self.assertIn(label, self.js)

    def test_native_hidden_attribute_wins_over_component_layout(self) -> None:
        self.assertRegex(self.css, r"(?:^|\})\s*\[hidden\]\s*\{\s*display\s*:\s*none\s*!important")


if __name__ == "__main__":
    unittest.main()
