from __future__ import annotations

from pathlib import Path

from tests.base import IsolatedTestCase


class ProductionPrepareUiTests(IsolatedTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = Path(__file__).resolve().parents[1]
        cls.html = (root / "ui" / "index.html").read_text(encoding="utf-8")
        cls.js = (root / "ui" / "app.js").read_text(encoding="utf-8")

    def test_ui_has_separate_plan_confirm_prepare_and_status_controls(self):
        for value in (
            'id="productionPreparePanel"',
            'id="productionPrepareExactRange"',
            'id="productionPrepareToken"',
            'id="productionPrepareConfirmation"',
            'id="submitProductionPrepare"',
            'id="refreshProductionPrepareStatus"',
        ):
            self.assertIn(value, self.html)
        panel = self.html[
            self.html.index('id="productionPreparePanel"') :
            self.html.index("</section>", self.html.index('id="productionPreparePanel"'))
        ]
        self.assertNotIn("/start", panel)

    def test_prepare_payload_has_no_client_execution_authority(self):
        marker = "body:JSON.stringify({client_request_id:clientRequestId"
        start = self.js.index(marker)
        payload = self.js[start : self.js.index("})", start) + 2]
        for forbidden in (
            "chapter_id",
            "owner_token",
            "generation",
            "job_id",
            "start_render",
            "render_fields",
        ):
            self.assertNotIn(forbidden, payload.lower())
        for required in (
            "book_id",
            "from_chapter",
            "to_chapter",
            "target_phase:'PREPARE'",
            "plan_fingerprint",
            "confirmation:true",
        ):
            self.assertIn(required, payload)

    def test_ui_fetches_readiness_and_blocks_legacy_start_in_production_mode(self):
        self.assertIn("/api/production/prepare-readiness", self.js)
        self.assertIn("function startRenderAllowed()", self.js)
        self.assertIn("START_RENDER và legacy job preparation không khả dụng", self.js)
        self.assertIn("button[onclick^=\"startPreparedJob\"]", self.js)
        self.assertNotIn("start_render:", self.js)


if __name__ == "__main__":
    import unittest

    unittest.main()
