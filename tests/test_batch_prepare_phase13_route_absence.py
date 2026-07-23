from __future__ import annotations

import unittest
from pathlib import Path


class Phase13RouteAbsenceTests(unittest.TestCase):
    def test_readiness_is_get_only_and_batch_mutation_route_is_disabled_by_default(self):
        from story_audio.api import app, batch_prepare_api_service

        route_methods = {
            route.path: set(getattr(route, "methods", None) or ())
            for route in app.routes
            if hasattr(route, "path")
        }
        self.assertEqual(route_methods["/api/production/prepare-readiness"], {"GET"})
        self.assertEqual(route_methods["/api/production/batch-prepare"], {"POST"})
        self.assertEqual(route_methods["/api/production/batch-prepare/{client_request_id}"], {"GET"})
        self.assertIsNone(batch_prepare_api_service)
        self.assertIn("/api/jobs/prepare", route_methods)
        self.assertIn("/api/jobs/{job_id}/start", route_methods)

    def test_ui_prepare_control_is_runtime_gated_and_has_no_start_render_request(self):
        source = (Path.cwd() / "ui" / "app.js").read_text(encoding="utf-8")
        self.assertIn("/api/production/batch-prepare", source)
        self.assertIn("/api/production/prepare-readiness", source)
        self.assertIn("readiness?.mutation_authorized", source)
        prepare_block = source[
            source.index("async function submitProductionPrepare") :
            source.index("async function refreshProductionPrepareStatus")
        ]
        self.assertNotIn("/start", prepare_block)
        self.assertNotIn("start_render", prepare_block.lower())


if __name__ == "__main__":
    unittest.main()
