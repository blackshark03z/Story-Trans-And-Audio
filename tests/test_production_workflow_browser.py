from __future__ import annotations

import json
import subprocess
import threading
import unittest
from http.server import ThreadingHTTPServer

from tests.test_production_scope_browser import ROOT, ScopeFixtureHandler


class ProductionWorkflowBrowserTests(unittest.TestCase):
    def test_task_workbench_journeys_in_real_browser(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), ScopeFixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(
                [
                    "node",
                    "scripts/browser_production_task_workbench_smoke.mjs",
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
        self.assertEqual(evidence["journeyB"]["primary"], ["Tạo đề xuất người nói"])
        self.assertEqual(evidence["journeyC"]["primary"], ["Xác nhận và tiếp tục"])
        self.assertTrue(evidence["pollingStability"])
        self.assertEqual(evidence["journeyDEdit"]["primary"], ["Gán giọng"])
        self.assertEqual(evidence["journeyDReview"]["primary"], ["Kiểm tra bản đồ giọng"])
        self.assertEqual(evidence["journeyEPrepare"]["primary"], ["Chuẩn bị 1 chương"])
        self.assertEqual(evidence["journeyEStart"]["primary"], ["Bắt đầu render 1 chương"])
        self.assertEqual(evidence["journeyERunning"]["primary"], ["Theo dõi render"])
        self.assertEqual(evidence["journeyF"]["primary"], ["Xử lý render"])
        self.assertEqual(evidence["journeyG"]["primary"], ["Chấp nhận"])
        self.assertEqual(evidence["journeyH"]["queue"], 10)
        self.assertTrue(evidence["desktop"]["primaryVisible"])
        self.assertFalse(evidence["desktop"]["horizontal"])

    def test_range_input_exception_journeys_in_real_browser(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), ScopeFixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(
                [
                    "node",
                    "scripts/browser_range_input_workflow_smoke.mjs",
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
        self.assertEqual(evidence["scenarioA"]["prepareCalls"], 1)
        self.assertEqual(evidence["scenarioA"]["chapterOpenCalls"], 0)
        self.assertEqual(evidence["scenarioB"]["chapterRows"], 10)
        self.assertEqual(evidence["scenarioC"]["remaining"], 0)
        self.assertEqual(evidence["scenarioD"]["remaining"], 4)
        self.assertEqual(evidence["scenarioE"]["remaining"], 3)
        self.assertEqual(evidence["scenarioGEnd"]["phase"], "castingGeneration")
        self.assertEqual(evidence["scenarioH"]["label"], "Chuẩn bị 9 chương")
        self.assertTrue(evidence["scenarioJ"])
        self.assertTrue(evidence["layout1366"]["primaryVisible"])
        self.assertFalse(evidence["layout1366"]["horizontal"])
        self.assertEqual(evidence["layout1366"]["nested"], [])
        self.assertTrue(evidence["layout1920"]["primaryVisible"])
        self.assertFalse(evidence["layout1920"]["horizontal"])


if __name__ == "__main__":
    unittest.main()
