from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DailyUseV1UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")
        cls.launcher = (ROOT / "run_app.ps1").read_text(encoding="utf-8")

    def test_daily_use_navigation_and_global_status_are_visible(self) -> None:
        for route in ("production", "assignment", "jobs", "audio", "storage"):
            self.assertIn(f'href="#/{route}"', self.html)
            self.assertIn(f'data-app-route="{route}"', self.html)
        for view in ("assignment", "jobs", "audio", "storage"):
            self.assertIn(f'data-app-view="{view}"', self.html)
        for status_id in (
            "globalRuntimeState",
            "globalSchemaState",
            "globalPrepareState",
            "globalWorkerState",
            "globalAuthState",
            "globalKillSwitchState",
        ):
            self.assertIn(f'id="{status_id}"', self.html)
        self.assertIn("renderGlobalStatus", self.js)

    def test_voice_assignment_reuses_contextual_production_flow(self) -> None:
        self.assertIn('id="openAssignmentWorkspace"', self.html)
        self.assertIn("focusProductionTarget(currentProductionViewModel().targetPanel)", self.js)
        self.assertIn("setProductionScopeRoute(", self.js)
        self.assertIn("buildSpeakerSummaryRows(context)", self.js)
        self.assertIn("state.voiceCatalog?.items?.length", self.js)
        self.assertIn("bulk narrator/unknown", self.js)

    def test_jobs_use_backend_capabilities_and_keep_history_read_only(self) -> None:
        self.assertIn("const actions=job.actions||{}", self.js)
        self.assertIn("actions.can_start", self.js)
        self.assertIn("actions.can_resume", self.js)
        self.assertIn("actions.can_retry", self.js)
        self.assertIn("job.is_historical_output", self.js)
        self.assertIn("Historical evidence only", self.js)
        self.assertIn("copyJobSummary", self.js)

    def test_qa_is_explicit_and_rejection_requires_note(self) -> None:
        self.assertIn('id="productionQaAccept"', self.html)
        self.assertIn('id="productionQaNeedsFixes"', self.html)
        self.assertIn('id="audioQaNote"', self.html)
        self.assertIn("required></textarea>", self.html)
        self.assertIn("if(status==='needs_fixes'&&!notes.trim())", self.js)
        self.assertIn("window.confirm", self.js)
        self.assertIn("/human-approval-history", self.js)
        self.assertEqual(self.js.count("const accept=$('#productionQaAccept'),needs=$('#productionQaNeedsFixes')"), 1)
        self.assertEqual(self.js.count("accept.onclick=()=>updateProductionQa('approved')"), 1)
        self.assertEqual(self.js.count("needs.onclick=()=>updateProductionQa('needs_fixes')"), 1)

    def test_range_archive_is_readiness_gated_and_get_only(self) -> None:
        self.assertIn("/api/audio-library/range-archive-readiness", self.js)
        self.assertIn("/api/audio-library/range-archive?", self.js)
        self.assertIn("state.audioArchive.readiness?.ready", self.js)
        self.assertIn("Các chapter đã chọn không liên tiếp", self.js)
        self.assertNotIn(
            "method:'POST'",
            self.js[
                self.js.index("async function checkAudioRange"):
                self.js.index("function renderStorageReport")
            ],
        )

    def test_storage_and_supervised_restart_are_fail_closed(self) -> None:
        self.assertIn("/api/storage/report", self.js)
        self.assertIn("/api/storage/dry-run", self.js)
        self.assertIn("report.cleanup_confirmation", self.js)
        self.assertIn("report.blockers", self.js)
        self.assertIn("data-action-guarded", self.html)
        self.assertIn(
            "document.querySelectorAll('[data-action-guarded]').forEach(el=>{el.disabled=true})",
            self.js,
        )
        self.assertIn("Đang quét storage", self.js)
        self.assertIn("STORY_AUDIO_SUPERVISED", self.launcher)
        self.assertIn("STORY_AUDIO_RESTART_SIGNAL", self.launcher)
        self.assertIn("/api/runtime/restart", self.js)
        self.assertIn("supervised_restart_available", self.js)

    def test_responsive_styles_cover_new_daily_use_surfaces(self) -> None:
        for selector in (
            ".global-runtime-status",
            ".job-page-card",
            ".audio-library-qa-panel",
            ".audio-range-download",
            ".storage-summary-grid",
        ):
            self.assertIn(selector, self.css)
        self.assertIn("@media(max-width:700px)", self.css)


if __name__ == "__main__":
    unittest.main()
