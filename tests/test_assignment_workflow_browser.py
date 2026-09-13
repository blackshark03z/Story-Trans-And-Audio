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

from story_audio.db import Database
from story_audio.migrations import LATEST_SCHEMA_VERSION, MigrationRunner, RUNTIME_MIGRATIONS
from tests.test_production_scope_browser import ROOT
from tests.test_speaker_review_workspace_browser import (
    SpeakerReviewWorkspaceFixtureHandler,
)


class AssignmentWorkflowFixtureHandler(SpeakerReviewWorkspaceFixtureHandler):
    plan_ready = False
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
        cls.plan_ready = False
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
        long_context = (
            "Inside the old medicine shop, the marked search area extends across several rooms "
            "and the team has already checked most of the northern wall without finding a clue."
        )
        for row in result["rows"]:
            if row.get("character_id") == 25:
                row["sample_lines"] = [
                    {
                        "chapter_number": 2,
                        "sequence": 16,
                        "text": "- These last few days of searching point to the two rooms inside this area.",
                        "context_before": [{"sequence": 15, "text": long_context}],
                        "context_after": [{"sequence": 17, "text": "The nearby cultivators immediately split up and continued the search."}],
                    },
                    {
                        "chapter_number": 3,
                        "sequence": 8,
                        "text": "- Keep the eastern passage clear until I return.",
                        "context_before": [{"sequence": 7, "text": "A second group arrived from the courtyard and stopped beside the broken gate."}],
                        "context_after": [{"sequence": 9, "text": long_context}],
                    },
                    {
                        "chapter_number": 4,
                        "sequence": 12,
                        "text": "- Search the side chamber before sunset.",
                        "context_before": [{"sequence": 11, "text": long_context}],
                        "context_after": [{"sequence": 13, "text": "The others nodded and moved toward the side chamber."}],
                    },
                    {
                        "chapter_number": 5,
                        "sequence": 21,
                        "text": "- Leave a marker here so the next group can find us.",
                        "context_before": [{"sequence": 20, "text": "The corridor split into three narrow paths."}],
                        "context_after": [{"sequence": 22, "text": long_context}],
                    },
                    {
                        "chapter_number": 6,
                        "sequence": 5,
                        "text": "- Wait here until the signal changes.",
                        "context_before": [{"sequence": 4, "text": long_context}],
                        "context_after": [{"sequence": 6, "text": "No one moved after the order."}],
                    },
                ]
        review_complete = all(
            state in accepted for state in cls.review_states.values()
        )
        for row in result["rows"]:
            if row.get("role") == "narrator" or row.get("character_id"):
                row["actions"]["requires_casting_plan_creation"] = bool(
                    review_complete and not cls.plan_ready
                )
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

        database = Database(
            clone_path,
            migration_runner=MigrationRunner(RUNTIME_MIGRATIONS),
        )
        self.assertEqual(database.initialize(), LATEST_SCHEMA_VERSION)
        destination = sqlite3.connect(clone_path)
        try:
            self.assertEqual(
                destination.execute(
                    "SELECT MAX(version) FROM schema_migrations"
                ).fetchone()[0],
                LATEST_SCHEMA_VERSION,
            )
            self.assertEqual(destination.execute("PRAGMA quick_check").fetchone()[0], "ok")
            self.assertEqual(destination.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            destination.close()

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
        self.assertTrue(evidence["lockedVoiceStep"]["locked"])
        self.assertEqual(evidence["lockedVoiceStep"]["ariaDisabled"], "true")
        self.assertIn("Còn 1", evidence["lockedVoiceStep"]["remaining"])
        self.assertEqual(evidence["lockedVoiceStep"]["voiceRows"], 0)
        self.assertEqual(evidence["lockedVoiceStep"]["voiceActions"], 0)
        self.assertEqual(evidence["layoutEvidence"]["gridColumns"], 2)
        self.assertEqual(evidence["layoutEvidence"]["gridAlign"], "start")
        self.assertGreater(evidence["layoutEvidence"]["textWidthRatio"], 0.70)
        self.assertGreater(evidence["layoutEvidence"]["reviewWidthRatio"], 0.50)
        self.assertTrue(evidence["layoutEvidence"]["contextInsideSpeakerRow"])
        self.assertIn("Đoạn thoại để xác nhận", evidence["layoutEvidence"]["contextLabel"])
        self.assertFalse(evidence["layoutEvidence"]["replacementCharacter"])
        self.assertTrue(evidence["sampleDetailPersistence"]["persisted"])
        self.assertIn("Xem thêm", evidence["sampleDetailPersistence"]["label"])
        self.assertEqual(evidence["initial"]["unresolvedVoiceRows"], 0)
        self.assertEqual(evidence["initial"]["characterRows"], 0)
        self.assertEqual(evidence["initial"]["preflightPrimaryCount"], 1)
        self.assertEqual(evidence["initial"]["sectionTwoPreflightPrimaryCount"], 0)
        self.assertEqual(evidence["initial"]["sectionTwoConditionLink"], "")
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
        self.assertIn("Tiếp tục", evidence["voiceSaveState"]["voiceNextAction"])
        self.assertIn("book=1", evidence["readyNavigation"]["hash"])
        self.assertIn("from=1", evidence["readyNavigation"]["hash"])
        self.assertIn("to=10", evidence["readyNavigation"]["hash"])
        self.assertEqual(evidence["renderCommands"], [])
        self.assertEqual(evidence["repairBlocked"]["heading"], "Sửa audio")
        self.assertEqual(evidence["repairBlocked"]["badge"], "Giai đoạn 4 / 4")
        self.assertEqual(len(evidence["repairBlocked"]["blockers"]), 2)
        self.assertIn("Bản xác định người nói", evidence["repairBlocked"]["blockers"][0])
        self.assertIn("bản đồ giọng", evidence["repairBlocked"]["blockers"][1])
        self.assertEqual(len(evidence["repairBlocked"]["sequence"]), 4)
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
        self.assertEqual(evidence["repairReady"]["nextAction"], "Xác nhận bản sửa")
        self.assertFalse(evidence["repairReady"]["legacyApplyButton"])
        self.assertEqual(evidence["repairPlan"]["mode"], "review")
        self.assertEqual(evidence["repairPlan"]["heading"], "Kiểm tra toàn bộ bản sửa")
        self.assertTrue(evidence["repairPlan"]["repeatedWords"])
        self.assertEqual(evidence["repairPlan"]["speed"], "1.25")
        self.assertTrue(evidence["repairPlan"]["localPacing"])
        self.assertFalse(evidence["repairPlan"]["confirmDisabled"])
        self.assertEqual(evidence["repairCheckCommands"], [])


if __name__ == "__main__":
    unittest.main()
