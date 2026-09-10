from __future__ import annotations

import json
import subprocess
import threading
import unittest
from http.server import ThreadingHTTPServer

from tests.test_production_scope_browser import ROOT, ScopeFixtureHandler


class Phase5UxBrowserTests(unittest.TestCase):
    def test_phase5_states_are_read_only_and_owner_task_first(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), ScopeFixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(
                [
                    "node",
                    "scripts/browser_phase5_ux_acceptance.mjs",
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
        self.assertEqual(evidence["humanQa"]["stage"], "Đã bàn giao")
        self.assertFalse(evidence["humanQa"]["playerVisible"])
        self.assertFalse(evidence["humanQa"]["qaActionsVisible"])
        self.assertEqual(evidence["humanQaHandoffNavigation"]["mutations"], [])
        self.assertTrue(evidence["repairRequired"]["problemBeforePlan"])
        self.assertFalse(evidence["repairRequired"]["rawTechnicalVisible"])
        self.assertEqual(evidence["repairRequired"]["mutations"], [])
        self.assertTrue(evidence["complete"]["completePrimaryVisible"])
        self.assertEqual(evidence["complete"]["completePrimaryLabel"], "Mở audio đã hoàn tất")
        self.assertTrue(evidence["complete"]["downloadVisible"])
        self.assertEqual(evidence["complete"]["mutations"], [])
        self.assertEqual(evidence["completeNavigation"]["route"], "audio")
        self.assertIn("#/audio?book=91&from=401&to=401", evidence["completeNavigation"]["hash"])
        self.assertEqual(evidence["completeNavigation"]["mutations"], [])
        self.assertFalse(evidence["narrow"]["humanQa"]["horizontal"])
        self.assertFalse(evidence["narrow"]["repairRequired"]["horizontal"])
        self.assertFalse(evidence["narrow"]["complete"]["horizontal"])


if __name__ == "__main__":
    unittest.main()
