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
        self.assertEqual(evidence["journeyEPrepare"]["primary"], ["Chuẩn bị tạo audio"])
        self.assertEqual(evidence["journeyInfrastructure"]["primary"], ["Kiểm tra lại môi trường"])
        self.assertEqual(evidence["journeyInfrastructure"]["back"], "Quay lại cấu hình giọng")
        self.assertEqual(evidence["journeyInfrastructure"]["state"], "INFRASTRUCTURE_BLOCKED")
        self.assertEqual(evidence["voiceReturn"]["route"], "assignment")
        self.assertIn("book=91&from=1&to=5", evidence["voiceReturn"]["hash"])
        self.assertIn("assignment_focus=voices", evidence["voiceReturn"]["hash"])
        self.assertIn("skip_completed=1", evidence["voiceReturn"]["hash"])
        self.assertTrue(evidence["voiceReturn"]["voicesOpen"])
        self.assertEqual(evidence["voiceReturn"]["mutations"], [])
        self.assertFalse(evidence["voiceReturnLayout1366"]["horizontal"])
        self.assertGreater(evidence["voiceReturnLayout1366"]["primary"]["left"], evidence["voiceReturnLayout1366"]["back"]["left"])
        self.assertFalse(evidence["voiceReturnLayout520"]["horizontal"])
        self.assertLess(evidence["voiceReturnLayout520"]["primary"]["top"], evidence["voiceReturnLayout520"]["back"]["top"])
        self.assertEqual(evidence["journeyEStart"]["primary"], ["Bắt đầu tạo audio"])
        self.assertEqual(evidence["preparedEditCancel"]["label"], "Hủy chuẩn bị & chỉnh lại")
        self.assertEqual(evidence["preparedEditCancel"]["declineCalls"], 0)
        self.assertEqual(evidence["preparedEditCancel"]["calls"], [{"path": "/api/jobs/9001/cancel", "method": "POST"}])
        self.assertEqual(evidence["preparedEditCancel"]["target"], "assignment")
        self.assertIn("Job #9001", evidence["preparedEditCancel"]["prompt"])
        self.assertEqual(evidence["preparedEditCancel"]["confirmAttempts"], 2)
        self.assertEqual(evidence["journeyERunning"]["primary"], ["Đang tạo audio…"])
        self.assertEqual(evidence["nullPrimaryMappings"]["prepare"], "PREPARE_RANGE")
        self.assertEqual(evidence["nullPrimaryMappings"]["start"], "START_RENDER_RANGE")
        self.assertEqual(evidence["prepareSkipCompleted"]["calls"], 1)
        self.assertTrue(evidence["prepareSkipCompleted"]["scope"]["skip_completed"])
        self.assertEqual(evidence["prepareSkipCompleted"]["scope"]["from_chapter"], 6)
        self.assertEqual(evidence["prepareSkipCompleted"]["scope"]["to_chapter"], 8)
        self.assertIn("2 chương", evidence["prepareSkipCompleted"]["label"])
        self.assertEqual(evidence["monitorJobsNavigation"], {"label": "Mở Công việc", "route": "jobs"})
        self.assertIn("Tạm dừng", evidence["jobsRecoveryActions"]["labels"])
        self.assertIn("Hủy công việc", evidence["jobsRecoveryActions"]["labels"])
        self.assertEqual(evidence["jobsRecoveryActions"]["calls"], [{"id": 9001, "action": "pause"}, {"id": 9001, "action": "cancel"}])
        self.assertIn("Hủy Job #9001", evidence["jobsRecoveryActions"]["prompt"])
        self.assertFalse(evidence["jobsRecoveryActions"]["technicalStart"])
        self.assertIn("Tiếp tục", evidence["jobsRecoveryVariants"]["pausedLabels"])
        self.assertIn("Thử lại phần lỗi", evidence["jobsRecoveryVariants"]["failedLabels"])
        self.assertEqual(evidence["jobsRecoveryVariants"]["calls"], [{"id": 9002, "action": "resume"}, {"id": 9003, "action": "retry"}])
        self.assertEqual(evidence["journeyF"]["primary"], ["Đang tạo audio…"])
        self.assertEqual(evidence["journeyG"]["primary"], ["Mở Duyệt audio"])
        self.assertFalse(evidence["qaHandoff"]["player"])
        self.assertFalse(evidence["qaHandoff"]["note"])
        self.assertTrue(evidence["qaHandoff"]["qaActionsHidden"])
        self.assertEqual(len(evidence["qaHandoff"]["calls"]), 1)
        self.assertEqual(evidence["journeyH"]["queue"], 10)
        self.assertEqual(evidence["commandLifecycle"]["A"]["calls"], 1)
        self.assertEqual(evidence["commandLifecycle"]["B"]["outcome"], "PARTIAL")
        self.assertEqual(evidence["commandLifecycle"]["EFGH"]["start"], "ACCEPTED")
        self.assertTrue(evidence["commandLifecycle"]["I"]["discarded"])
        self.assertTrue(evidence["commandLifecycle"]["J"]["sameKey"])
        self.assertTrue(evidence["commandLifecycle"]["K"]["restored"])
        self.assertTrue(evidence["desktop"]["primaryVisible"])
        self.assertFalse(evidence["desktop"]["horizontal"])
        for viewport in ("scopeAction1366", "scopeAction820"):
            self.assertEqual(evidence[viewport]["label"], "Đổi sách / chương")
            self.assertTrue(evidence[viewport]["insideIdentity"])
            self.assertTrue(evidence[viewport]["visible"])
            self.assertTrue(evidence[viewport]["progressVisible"])
            self.assertTrue(evidence[viewport]["characterVisible"])
            self.assertFalse(evidence[viewport]["horizontal"])
        self.assertEqual(evidence["inactiveProjectionPolling"]["route"], "assignment")
        self.assertEqual(evidence["inactiveProjectionPolling"]["projection"], 0)
        self.assertEqual(evidence["inactiveProjectionPolling"]["preflight"], 0)
        self.assertEqual(evidence["returnToProduction"]["route"], "production")
        self.assertEqual(evidence["returnToProduction"]["range"], {"book": 1, "from": 1, "to": 1})
        self.assertEqual(evidence["returnToProduction"]["projectionIdentity"], "book:1:1-1")
        self.assertEqual(evidence["returnToProduction"]["requests"], [
            {"kind": "projection", "book": 1, "from": 1, "to": 1},
            {"kind": "preflight", "book": 1, "from": 1, "to": 1},
        ])

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
        self.assertEqual(evidence["scenarioA"]["prepareCalls"], 10)
        self.assertEqual(evidence["scenarioA"]["chapterOpenCalls"], 1)
        self.assertEqual(evidence["scenarioB"]["chapterRows"], 10)
        self.assertEqual(evidence["scenarioC"]["remaining"], 0)
        self.assertEqual(evidence["scenarioD"]["route"], "assignment")
        self.assertEqual(evidence["scenarioD"]["context"]["fromChapter"], 101)
        self.assertEqual(evidence["scenarioD"]["context"]["toChapter"], 110)
        self.assertEqual(evidence["scenarioD"]["context"]["assignmentFocus"], "review")
        self.assertEqual(evidence["scenarioD"]["commandMutations"], 0)
        self.assertEqual(evidence["manualScenarioD"]["remaining"], 4)
        self.assertEqual(evidence["manualScenarioE"]["remaining"], 3)
        self.assertEqual(evidence["scenarioGEnd"]["phase"], "castingGeneration")
        self.assertIn("Giọng chỉ huy", evidence["scenarioCastingEvidence"])
        self.assertEqual(evidence["scenarioH"]["label"], "Chuẩn bị tạo audio")
        self.assertTrue(evidence["scenarioJ"]["ok"])
        self.assertTrue(evidence["layout1366"]["primaryVisible"])
        self.assertEqual(evidence["layout1366"]["scrollY"], 0)
        self.assertFalse(evidence["layout1366"]["horizontal"])
        self.assertEqual(evidence["layout1366"]["nested"], [])
        self.assertTrue(evidence["layout1920"]["primaryVisible"])
        self.assertFalse(evidence["layout1920"]["horizontal"])


if __name__ == "__main__":
    unittest.main()
