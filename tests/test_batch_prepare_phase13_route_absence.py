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

    def test_ui_has_no_batch_prepare_mutation_control(self):
        source = (Path.cwd() / "ui" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("/api/production/batch-prepare", source)
        self.assertNotIn("/api/production/prepare-readiness", source)


if __name__ == "__main__":
    unittest.main()
