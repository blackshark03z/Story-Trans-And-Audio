from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from tests.test_production_scope_browser import ROOT
from tests.test_speaker_review_workspace_browser import (
    SpeakerReviewWorkspaceFixtureHandler,
)


class AssignmentWorkflowFixtureHandler(SpeakerReviewWorkspaceFixtureHandler):
    unresolved_targets = {
        "unresolved-dialogue:1002:u0002-deadbeef0000": {
            "chapter_id": 1002,
            "chapter_number": 2,
            "utterance_id": "u0002-deadbeef0000",
            "sequence": 2,
            "text": "- Hold the gate and verify every pass.",
        }
    }

    @classmethod
    def reset(cls) -> None:
        super().reset()
        cls.characters[26] = {
            "id": 26,
            "display_name": "Unvoiced Scout",
            "canonical_name": "Unvoiced Scout",
            "role": "minor",
            "gender": "unknown",
            "aliases": [],
            "active": True,
        }

    @classmethod
    def registry(cls, book_id: int, start: int, end: int) -> dict:
        accepted = {"ACCEPTED", "EDITED_AND_ACCEPTED", "CORRECTED"}
        cls.mapped = {
            key: 25 for key, state in cls.review_states.items() if state in accepted
        }
        result = super().registry(book_id, start, end)
        if start <= 3 <= end:
            unvoiced = cls._character_row(
                character_id=26,
                chapters=[3],
                line_count=1,
            )
            unvoiced.update(
                {
                    "current_book_default_voice": None,
                    "saved_voice": None,
                    "base_resolved_voice": None,
                    "effective_voice": None,
                    "effective_voice_display_name": None,
                    "voice_available": False,
                    "assignment_source": "inherited",
                    "resolution_source": "unknown_fallback",
                    "status": "UNASSIGNED",
                }
            )
            result["rows"].append(unvoiced)
            result["summary"]["total_rows"] += 1
            result["summary"]["status_counts"]["UNASSIGNED"] = 1
        return result

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/api/fixture/commands":
            return self._json(type(self).commands)
        return super().do_GET()


class AssignmentWorkflowBrowserTests(unittest.TestCase):
    def test_three_step_assignment_journey_in_real_browser(self) -> None:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        test_root = Path(r"C:\StoryAudio_AssignmentFlow_Test") / timestamp
        test_root.mkdir(parents=True, exist_ok=False)
        clone_path = test_root / "app.db"
        canonical_path = ROOT / "data" / "app.db"

        source = sqlite3.connect(
            f"{canonical_path.as_uri()}?mode=ro",
            uri=True,
        )
        destination = sqlite3.connect(clone_path)
        try:
            source.backup(destination)
            self.assertEqual(
                destination.execute(
                    "SELECT MAX(version) FROM schema_migrations"
                ).fetchone()[0],
                15,
            )
            self.assertEqual(destination.execute("PRAGMA quick_check").fetchone()[0], "ok")
            self.assertEqual(destination.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            destination.close()
            source.close()

        AssignmentWorkflowFixtureHandler.reset()
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            AssignmentWorkflowFixtureHandler,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        env = os.environ.copy()
        env["STORY_AUDIO_ASSIGNMENT_TEST_ROOT"] = str(test_root)
        try:
            result = subprocess.run(
                [
                    "node",
                    "scripts/browser_assignment_flow_smoke.mjs",
                    f"http://127.0.0.1:{server.server_port}",
                ],
                cwd=ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            shutil.rmtree(test_root, ignore_errors=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertTrue(evidence["ok"])
        self.assertEqual(len(evidence["initial"]["steps"]), 3)
        self.assertTrue(evidence["initial"]["reviewOpen"])
        self.assertFalse(evidence["initial"]["voicesOpen"])
        self.assertTrue(evidence["initial"]["sectionsSeparate"])
        self.assertTrue(evidence["initial"]["unresolvedNotice"])
        self.assertEqual(evidence["initial"]["unresolvedVoiceRows"], 0)
        self.assertGreaterEqual(evidence["initial"]["characterRows"], 2)
        self.assertEqual(evidence["initial"]["preflightPrimaryCount"], 1)
        self.assertEqual(evidence["initial"]["sectionTwoPreflightPrimaryCount"], 0)
        self.assertEqual(
            evidence["initial"]["sectionTwoConditionLink"],
            "Xem điều kiện để tiếp tục",
        )
        self.assertTrue(evidence["unresolvedNavigation"])
        self.assertEqual(evidence["navigationState"]["filter"], evidence["filterBeforeJump"])
        self.assertIn("book=1", evidence["navigationState"]["hash"])
        self.assertIn("from=1", evidence["navigationState"]["hash"])
        self.assertIn("to=10", evidence["navigationState"]["hash"])
        self.assertTrue(evidence["reviewCompletion"]["reviewComplete"])
        self.assertTrue(evidence["reviewCompletion"]["voiceEmphasized"])
        self.assertTrue(evidence["reviewCompletion"]["voiceOpen"])
        self.assertEqual(evidence["reviewCompletion"]["characterRows"], 1)
        self.assertEqual(evidence["reviewCompletion"]["unresolvedRows"], 0)
        polling = evidence["pollingStability"]
        self.assertTrue(polling["sameVoiceNode"])
        self.assertTrue(polling["sameScopeNode"])
        self.assertTrue(polling["focused"])
        self.assertEqual(polling["voice"], "commander")
        self.assertEqual(polling["scope"], "range")
        self.assertTrue(polling["sectionOpen"])
        self.assertTrue(polling["scrollStable"])
        self.assertIn("Commander Voice", polling["impact"])
        self.assertIn("Ghi đè đúng phạm vi", polling["impact"])
        self.assertIn("book=1", evidence["readyNavigation"]["hash"])
        self.assertIn("from=1", evidence["readyNavigation"]["hash"])
        self.assertIn("to=10", evidence["readyNavigation"]["hash"])
        self.assertEqual(evidence["renderCommands"], [])
        self.assertEqual(evidence["repairBlocked"]["heading"], "Cần sửa và tạo bản thay thế")
        self.assertEqual(evidence["repairBlocked"]["badge"], "Luồng tạo bản thay thế")
        self.assertEqual(len(evidence["repairBlocked"]["blockers"]), 2)
        self.assertIn("Bản xác định người nói", evidence["repairBlocked"]["blockers"][0])
        self.assertIn("bản đồ giọng", evidence["repairBlocked"]["blockers"][1])
        self.assertEqual(len(evidence["repairBlocked"]["sequence"]), 5)
        self.assertFalse(evidence["repairBlocked"]["prepareEnabled"])
        self.assertTrue(evidence["repairBlocked"]["qaControlsHidden"])
        self.assertIn("from=1", evidence["speakerRepairNavigation"]["hash"])
        self.assertIn("to=1", evidence["speakerRepairNavigation"]["hash"])
        self.assertIn("assignment_focus=review", evidence["speakerRepairNavigation"]["hash"])
        self.assertEqual(evidence["speakerRepairNavigation"]["returnTask"], "REPAIR_PREFLIGHT")
        self.assertTrue(evidence["speakerRepairNavigation"]["reviewOpen"])
        self.assertIn("assignment_focus=voices", evidence["voiceRepairNavigation"]["hash"])
        self.assertEqual(evidence["voiceRepairNavigation"]["returnTask"], "REPAIR_PREFLIGHT")
        self.assertTrue(evidence["voiceRepairNavigation"]["voicesOpen"])
        self.assertEqual(evidence["voiceRepairNavigation"]["unresolvedVoiceRows"], 0)
        self.assertEqual(
            evidence["voiceRepairNavigation"]["returnLabel"],
            "Quay lại chuẩn bị bản thay thế",
        )
        self.assertEqual(evidence["repairReady"]["blockers"], 0)
        self.assertIn("Mở Preflight bản thay thế", evidence["repairReady"]["nextAction"])
        self.assertFalse(evidence["repairReady"]["prepareButton"])
        self.assertEqual(evidence["replacementPreflight"]["mode"], "same_data")
        self.assertIn("Chuẩn bị bản thay thế", evidence["replacementPreflight"]["heading"])
        self.assertIn("Artifact cũ #39", evidence["replacementPreflight"]["pins"])
        self.assertEqual(evidence["repairCheckCommands"], [])


if __name__ == "__main__":
    unittest.main()
