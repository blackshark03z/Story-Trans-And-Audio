from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GoldenJourneyCertificationTests(unittest.TestCase):
    maxDiff = None

    def test_full_isolated_browser_golden_journey(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="story-audio-golden-protected-",
            ignore_cleanup_errors=True,
        ) as directory:
            protected_db = Path(directory) / "protected.db"
            with sqlite3.connect(protected_db) as connection:
                connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
                connection.execute("INSERT INTO sentinel(value) VALUES ('unchanged')")
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/run_golden_journey_certification.py",
                    "--timeout",
                    "180",
                    "--canonical-db",
                    str(protected_db),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env={**os.environ, "PYTHONUTF8": "1"},
                timeout=240,
            )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"], payload)

        browser = payload["browser"]
        isolated = payload["isolated"]
        protected_target = payload["protected_target"]

        self.assertEqual(browser["stages"], [
            "scope_selection",
            "voice_assignment",
            "preflight_ready",
            "prepare",
            "first_render",
            "first_review_handoff",
            "needs_fixes",
            "repair_handoff",
            "repair_plan_confirmed",
            "repair_draft_confirmed",
            "replacement_render",
            "replacement_review_handoff",
            "accept_replacement",
            "audio_playback",
            "download",
        ])
        self.assertGreater(browser["firstArtifact"], 0)
        self.assertGreater(browser["replacementArtifact"], 0)
        self.assertNotEqual(browser["replacementArtifact"], browser["firstArtifact"])
        self.assertTrue(browser["repairPlan"]["applyEnabled"])
        self.assertEqual(browser["repairPlan"]["confirmCount"], 0)
        self.assertTrue(browser["accessibility"]["buttonsNamed"])

        self.assertEqual(isolated["qa_audit_count"], 2)
        self.assertEqual(isolated["schema"], 16)
        self.assertEqual(isolated["chapter"]["audio_status"], "completed")
        self.assertEqual(int(isolated["chapter"]["active_audio_artifact_id"]), int(browser["replacementArtifact"]))
        self.assertEqual(isolated["active_artifact"]["id"], browser["replacementArtifact"])
        self.assertGreaterEqual(len(isolated["fake_tts_calls"]), 1)
        self.assertEqual(isolated["worker_wake_count"], 2)
        self.assertEqual(len([job for job in isolated["jobs"] if job["status"] == "completed"]), 3)
        self.assertEqual(len(isolated["marker_segments"]), 2)
        self.assertTrue(any(call["defective_fixture"] for call in isolated["fake_tts_calls"]))

        self.assertTrue(protected_target["unchanged"])
        self.assertEqual(protected_target["before"], protected_target["after"])
        self.assertTrue(protected_target["before"]["exists"])
        self.assertEqual(protected_target["before"]["path"], str(protected_db.resolve()))
        self.assertEqual(protected_target["before"]["quick_check"], "ok")
        self.assertEqual(protected_target["before"]["foreign_key_violations"], 0)


if __name__ == "__main__":
    unittest.main()
