from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def node_json(script: str) -> dict:
    result = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def panel_state_for(payload: dict) -> dict:
    script = f"""
const resolver = require('./ui/production_state.js');
const vm = resolver.resolveProductionState({json.dumps(payload, ensure_ascii=False)});
const active = vm.panelStates.filter(panel => panel.active).map(panel => panel.id);
console.log(JSON.stringify({{
  state: vm.conceptualState,
  stage: vm.currentStageKey,
  active,
  hidden: vm.panelStates.filter(panel => panel.hidden).map(panel => panel.id),
  inert: vm.panelStates.filter(panel => panel.inert).map(panel => panel.id),
  summaries: vm.stageSummaries.reduce((acc, item) => {{ acc[item.state] = (acc[item.state] || 0) + 1; return acc; }}, {{}}),
}}));
"""
    return node_json(script)


def base_payload() -> dict:
    return {
        "book": {"id": 1},
        "chapter": {
            "id": 999,
            "book_id": 1,
            "chapter_number": 999,
            "active_text_revision_id": 738,
            "audio_status": "not_created",
        },
        "revisions": [{"id": 738, "status": "approved"}],
        "speakerDraft": {
            "id": 15,
            "status": "approved",
            "stale": False,
            "remaining_unreviewed_count": 0,
            "invalid_count": 0,
        },
        "casting": {
            "voice_profile": {"validation": {"valid": True}},
            "casting": {
                "id": 24,
                "status": "draft",
                "plan_revision": 1,
                "plan": {"utterances": [{"utterance_id": "u1", "resolved_voice_id": "custom:26"}]},
            },
        },
        "jobs": [],
        "active_output": {},
    }


class DailyProdStepIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        cls.resolver = (ROOT / "ui" / "production_state.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")

    def test_panel_ownership_is_central_and_unique(self) -> None:
        script = """
const resolver = require('./ui/production_state.js');
const ids = resolver.STAGE_PANEL_OWNERSHIP.map(item => item.id);
console.log(JSON.stringify({
  count: ids.length,
  unique: new Set(ids).size,
  hasLegacy: ids.includes('productionLegacyJobPanel'),
  hasQueue: ids.includes('productionQueuePanel'),
  hasVoiceMap: ids.includes('flowStepReviewVoiceMap'),
}));
"""
        data = node_json(script)
        self.assertEqual(data["count"], data["unique"])
        self.assertTrue(data["hasLegacy"])
        self.assertTrue(data["hasQueue"])
        self.assertTrue(data["hasVoiceMap"])

    def test_all_registered_panels_exist_once_in_html(self) -> None:
        data = node_json(
            """
const resolver = require('./ui/production_state.js');
console.log(JSON.stringify(resolver.STAGE_PANEL_OWNERSHIP.map(item => item.id)));
"""
        )
        for panel_id in data:
            self.assertEqual(self.html.count(f'id="{panel_id}"'), 1, panel_id)

    def test_no_scope_only_scope_area_and_shell_are_active(self) -> None:
        state = panel_state_for({})
        self.assertEqual(state["state"], "NO_SCOPE")
        self.assertEqual(state["stage"], "scope")
        self.assertIn("productionStageIsolation", state["active"])
        self.assertIn("workspace", state["active"])
        self.assertNotIn("productionQueuePanel", state["active"])
        self.assertNotIn("productionLegacyJobPanel", state["active"])

    def test_casting_review_shows_only_final_voice_map_work_area(self) -> None:
        state = panel_state_for(base_payload())
        self.assertEqual(state["state"], "CASTING_REVIEW")
        self.assertEqual(state["stage"], "voice_map")
        self.assertIn("flowStepReviewVoiceMap", state["active"])
        self.assertIn("castingPlanPanel", state["active"])
        forbidden = {"speakerReviewPanel", "flowStepRenderChapter", "renderPlanPanel", "flowStepReviewAudio", "flowFinalApprovalPanel"}
        self.assertTrue(forbidden.isdisjoint(state["active"]))

    def test_ready_prepared_rendered_complete_states_isolate_correct_panels(self) -> None:
        payload = base_payload()
        payload["casting"]["casting"]["status"] = "approved"
        ready = panel_state_for(payload)
        self.assertEqual(ready["stage"], "prepare")
        self.assertIn("renderPlanPanel", ready["active"])
        self.assertIn("workspace", ready["active"])
        self.assertIn("productionLegacyJobPanel", ready["active"])
        payload["jobs"] = [{"id": 20, "status": "prepared", "book_id": 1, "from_chapter": 999, "to_chapter": 999, "casting_plan_id": 24}]
        prepared = panel_state_for(payload)
        self.assertEqual(prepared["stage"], "render")
        self.assertIn("productionQueuePanel", prepared["active"])
        payload["jobs"] = []
        payload["active_output"] = {"active_output_job_id": 20, "active_output_artifact_id": 75}
        rendered = panel_state_for(payload)
        self.assertEqual(rendered["stage"], "qa")
        self.assertIn("flowFinalApprovalPanel", rendered["active"])
        payload["human_approval"] = {"status": "approved"}
        complete = panel_state_for(payload)
        self.assertEqual(complete["state"], "COMPLETE")
        self.assertIn("flowStepReviewAudio", complete["active"])
        self.assertNotIn("renderPlanPanel", complete["active"])

    def test_blocked_states_open_only_their_current_area(self) -> None:
        payload = base_payload()
        payload["revisions"] = [{"id": 738, "status": "draft"}]
        self.assertIn("flowStepReviewText", panel_state_for(payload)["active"])
        payload = base_payload()
        payload["speakerDraft"] = {"id": 15, "status": "draft", "stale": False}
        self.assertIn("speakerReviewPanel", panel_state_for(payload)["active"])
        payload = base_payload()
        payload["voice"] = {"missingEffectiveVoiceCount": 1}
        self.assertIn("flowVoiceMemoryDetails", panel_state_for(payload)["active"])

    def test_unresolved_state_hides_mutation_work_panels(self) -> None:
        payload = base_payload()
        payload["active_output"] = {"active_output_job_id": 20}
        state = panel_state_for(payload)
        self.assertEqual(state["state"], "STATE_UNRESOLVED")
        self.assertEqual(state["active"], ["productionStageIsolation"])

    def test_hidden_panels_are_inert_and_aria_hidden(self) -> None:
        state = panel_state_for(base_payload())
        self.assertIn("flowStepRenderChapter", state["hidden"])
        self.assertIn("flowStepRenderChapter", state["inert"])
        self.assertIn("setAttribute('inert','')", self.js)
        self.assertIn("setAttribute('aria-hidden',active?'false':'true')", self.js)

    def test_dialog_stepper_cannot_open_future_or_completed_work_panels(self) -> None:
        render_flow = self.js[self.js.index("function renderProductionFlow"): self.js.index("async function updateHumanApproval")]
        self.assertIn("productionCurrentFlowStep", render_flow)
        self.assertIn("disabled aria-disabled=\"true\"", render_flow)
        self.assertIn("selectProductionFlowStep(canonicalStepId", render_flow)
        self.assertIn("$('#productionFlowNext').disabled=true", render_flow)
        self.assertIn("classList.remove('primary')", render_flow)

    def test_prepare_start_and_qa_controls_are_not_owned_by_casting_review(self) -> None:
        self.assertRegex(self.html, r'id="flowStepReviewVoiceMap"[^>]+data-production-owned-stage="voice_map"')
        self.assertRegex(self.html, r'id="flowStepRenderChapter"[^>]+data-production-owned-stage="prepare render"')
        self.assertRegex(self.html, r'id="flowStepReviewAudio"[^>]+data-production-owned-stage="qa"')
        self.assertNotRegex(self.html, r'id="renderPlanPanel"[^>]+data-production-owned-stage="voice_map"')

    def test_current_work_area_has_completed_and_locked_summaries(self) -> None:
        self.assertIn('id="productionCurrentWorkArea"', self.html)
        self.assertIn('id="productionCompletedSummaries"', self.html)
        self.assertIn('id="productionLockedSummaries"', self.html)
        self.assertIn("renderProductionStageWorkArea(vm)", self.js)
        state = panel_state_for(base_payload())
        self.assertGreaterEqual(state["summaries"].get("complete", 0), 4)
        self.assertGreaterEqual(state["summaries"].get("locked", 0), 3)

    def test_voice_library_remains_outside_production_isolation(self) -> None:
        production_section = re.search(
            r'<section id="productionView".*?</section>\s*</section>\s*<section id="voicesView"',
            self.html,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(production_section)
        self.assertNotIn("customVoiceLibrary", production_section.group(0))
        self.assertIn("custom-voice-library-panel", self.html)
        self.assertIn("next!=='production'&&$('#textDialog')?.open", self.js)

    def test_no_chapter_369_hardcoding_in_isolation_code(self) -> None:
        isolation_source = self.resolver + self.js[self.js.index("const PRODUCTION_STAGE_TO_FLOW_STEP"): self.js.index("async function restoreProductionScopeFromRoute")]
        self.assertNotIn("369", isolation_source)
        self.assertNotIn("Chapter 369", isolation_source)


if __name__ == "__main__":
    unittest.main()
