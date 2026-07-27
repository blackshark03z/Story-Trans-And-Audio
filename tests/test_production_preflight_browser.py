from __future__ import annotations

import json
import subprocess
import threading
import unittest
from http.server import ThreadingHTTPServer

from tests.test_production_scope_browser import ROOT, ScopeFixtureHandler


class ProductionPreflightBrowserTests(unittest.TestCase):
    def test_preflight_scenarios_in_real_browser(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), ScopeFixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(
                [
                    "node",
                    "scripts/browser_production_preflight_smoke.mjs",
                    f"http://127.0.0.1:{server.server_port}",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertTrue(evidence["ok"])
        self.assertEqual(evidence["blockerNavigation"]["chapterId"], 7002)
        self.assertEqual(evidence["blockerNavigation"]["target"], "speakers")
        self.assertEqual(evidence["scenarioB"]["primary"], "Chuẩn bị 2 chương")
        self.assertTrue(evidence["readyDialog"]["open"])
        self.assertTrue(evidence["readyDialogEnabled"])
        self.assertTrue(evidence["authDialog"]["submitDisabled"])
        self.assertEqual(
            evidence["scenarioE"]["primary"],
            "Bắt đầu render 2 chương",
        )
        self.assertTrue(evidence["scenarioG"]["visibleAt1366"])
        self.assertFalse(evidence["scenarioG"]["horizontal"])
        self.assertFalse(evidence["scenarioG"]["rawIdsVisible"])
        self.assertTrue(evidence["scenarioH"]["detailsOpen"])
        self.assertTrue(evidence["scenarioH"]["focus"])
        self.assertTrue(evidence["desktop"]["primaryVisible"])


if __name__ == "__main__":
    unittest.main()
