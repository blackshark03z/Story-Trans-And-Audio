from __future__ import annotations

import json
import subprocess
import threading
import unittest
from http.server import ThreadingHTTPServer

from tests.test_character_assignment_browser import CharacterAssignmentFixtureHandler
from tests.test_production_scope_browser import ROOT


class CharacterReviewFixtureHandler(CharacterAssignmentFixtureHandler):
    @classmethod
    def registry(cls, book_id: int, start: int, end: int) -> dict:
        result = super().registry(book_id, start, end)
        if book_id == 1:
            return result
        narrator = result["rows"][0]
        narrator["chapter_numbers"] = list(range(start, end + 1))
        result["book"] = {"id": 2, "title": "Other Book", "chapter_count": 394}
        result["rows"] = [
            narrator,
            {
                "speaker_key": "character:other-book",
                "character_id": 88,
                "display_name": "Other Book Character",
                "role": "character",
                "role_label": "character",
                "chapter_numbers": list(range(start, end + 1)),
                "chapter_range_label": f"{start}-{end}",
                "effective_voice": {"id": "female", "display_name": "Other Book Voice", "available": True},
                "status": "READY",
            },
        ]
        result["summary"]["total_rows"] = 2
        return result


class SelectedCharacterReviewBrowserTests(unittest.TestCase):
    def test_selected_chapter_character_review_in_real_browser(self) -> None:
        CharacterReviewFixtureHandler.reset()
        server = ThreadingHTTPServer(("127.0.0.1", 0), CharacterReviewFixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(
                [
                    "node",
                    "tests/browser_selected_character_review.mjs",
                    f"http://127.0.0.1:{server.server_port}",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=90,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertTrue(evidence["ok"])
        self.assertEqual(evidence["single"]["scope"], "Fixture Book · Chương 2")
        self.assertEqual(evidence["multi"]["scope"], "Fixture Book · Chương 2–4")
        self.assertIn("Existing Commander", evidence["multi"]["names"])
        self.assertIn("Chua xac dinh nhan vat", evidence["multi"]["names"])
        self.assertTrue(evidence["multi"]["unresolved"])
        self.assertIn("Male Default", evidence["multi"]["voices"])
        self.assertEqual(evidence["other_book"]["names"], ["Người kể chuyện", "Other Book Character"])
        self.assertNotIn("Commander Voice", evidence["other_book"]["voices"])
        self.assertEqual(evidence["reloaded"], evidence["multi"])


if __name__ == "__main__":
    unittest.main()
