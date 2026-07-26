from __future__ import annotations

import json
import subprocess
import threading
import unittest
from http.server import ThreadingHTTPServer

from tests.test_production_scope_browser import ROOT, ScopeFixtureHandler


class ProductionWorkflowBrowserTests(unittest.TestCase):
    def test_four_phase_workflow_states_in_real_browser(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), ScopeFixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(
                [
                    "node",
                    "scripts/browser_production_workflow_smoke.mjs",
                    f"http://127.0.0.1:{server.server_port}",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=45,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertTrue(evidence["ok"])
        self.assertEqual(evidence["castingReview"]["primary"], "Duyệt và tiếp tục")
        self.assertEqual(evidence["ready"]["primary"], "Chuẩn bị")
        self.assertEqual(evidence["prepared"]["primary"], "Bắt đầu render")
        self.assertEqual(evidence["running"]["primary"], "Theo dõi tiến độ")
        self.assertEqual(evidence["failed"]["primary"], "Theo dõi tiến độ")
        self.assertEqual(evidence["qa"]["primary"], "Cần nghe và duyệt")
        self.assertTrue(evidence["qa"]["audioVisible"])
        self.assertEqual(evidence["qa"]["accept"], "Chấp nhận")
        self.assertEqual(evidence["qa"]["needsFixes"], "Cần sửa")
        self.assertTrue(evidence["layout1920"]["primaryVisible"])
        self.assertFalse(evidence["layout1920"]["horizontal"])


if __name__ == "__main__":
    unittest.main()
