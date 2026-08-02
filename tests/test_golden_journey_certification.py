from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(r"D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe")


class GoldenJourneyCertificationTests(unittest.TestCase):
    maxDiff = None

    def test_full_isolated_browser_golden_journey(self) -> None:
        result = subprocess.run(
            [
                str(PYTHON),
                "scripts/run_golden_journey_certification.py",
                "--timeout",
                "180",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=240,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"], payload)

        browser = payload["browser"]
        isolated = payload["isolated"]
        canonical = payload["canonical"]

        self.assertEqual(browser["stages"], [
            "scope_selection",
            "voice_assignment",
            "preflight_ready",
            "prepare",
            "first_render",
            "needs_fixes",
            "repair_plan_confirmed",
        ])
        self.assertGreater(browser["firstArtifact"], 0)
        self.assertTrue(browser["repairPlan"]["applyDisabled"])
        self.assertEqual(browser["repairPlan"]["confirmCount"], 0)
        self.assertTrue(browser["accessibility"]["buttonsNamed"])
        self.assertTrue(browser["accessibility"]["applyDisabled"])
        self.assertTrue(browser["accessibility"]["confirmAbsent"])

        self.assertEqual(isolated["qa_audit_count"], 1)
        self.assertEqual(isolated["chapter"]["audio_status"], "completed")
        self.assertEqual(int(isolated["chapter"]["active_audio_artifact_id"]), int(browser["firstArtifact"]))
        self.assertEqual(isolated["active_artifact"]["id"], browser["firstArtifact"])
        self.assertGreaterEqual(len(isolated["provider_calls"]), 1)
        self.assertEqual(isolated["worker_wake_count"], 1)
        self.assertEqual(len([job for job in isolated["jobs"] if job["status"] == "completed"]), 2)
        self.assertEqual(len(isolated["marker_segments"]), 1)
        self.assertTrue(any(call["defective_fixture"] for call in isolated["provider_calls"]))

        self.assertEqual(canonical["schema"], 15)
        self.assertEqual(canonical["quick_check"], "ok")
        self.assertEqual(canonical["foreign_key_violations"], 0)
        chapter_state = lambda number: canonical["chapters"].get(str(number)) or canonical["chapters"][number]
        self.assertEqual(chapter_state(372)["audio_status"], "completed")
        self.assertEqual(chapter_state(372)["active_audio_artifact_id"], 99)
        self.assertEqual(chapter_state(373)["active_audio_artifact_id"], 96)
        self.assertEqual(chapter_state(369)["audio_status"], "not_created")


if __name__ == "__main__":
    unittest.main()
