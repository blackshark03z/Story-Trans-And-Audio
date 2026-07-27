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
        self.assertEqual(evidence["journeyDEdit"]["primary"], ["Lưu bản nháp"])
        self.assertEqual(evidence["journeyDReview"]["primary"], ["Duyệt và tiếp tục"])
        self.assertEqual(evidence["journeyEPrepare"]["primary"], ["Chuẩn bị 1 chương"])
        self.assertEqual(evidence["journeyEStart"]["primary"], ["Bắt đầu render 1 chương"])
        self.assertEqual(evidence["journeyERunning"]["primary"], ["Xem tiến độ"])
        self.assertEqual(evidence["journeyF"]["primary"], ["Thử lại phần lỗi"])
        self.assertEqual(evidence["journeyG"]["primary"], ["Chấp nhận"])
        self.assertEqual(evidence["journeyH"]["queue"], 10)
        self.assertTrue(evidence["desktop"]["primaryVisible"])
        self.assertFalse(evidence["desktop"]["horizontal"])


if __name__ == "__main__":
    unittest.main()
