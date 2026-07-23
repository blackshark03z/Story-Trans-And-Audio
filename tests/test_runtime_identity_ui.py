from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tests.base import IsolatedTestCase


ROOT = Path(__file__).resolve().parents[1]


class RuntimeIdentityUiTests(IsolatedTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")
        cls.js_lines = cls.js.splitlines()

    @classmethod
    def _line(cls, prefix: str) -> str:
        for line in cls.js_lines:
            if line.startswith(prefix):
                return line
        raise AssertionError(f"Could not find JavaScript line starting with: {prefix}")

    def test_header_renders_persistent_runtime_banner(self) -> None:
        for value in (
            'id="runtimeIdentity"',
            'id="runtimeBadge"',
            'id="runtimePath"',
            "RUNTIME UNKNOWN",
            "topbar-status",
            "runtime-identity",
            "runtime-badge",
            "runtime-path",
        ):
            self.assertIn(value, self.html + self.css)

    def test_runtime_contract_and_labels_are_explicit(self) -> None:
        for value in (
            "api('/api/runtime')",
            "CANONICAL PRODUCTION",
            "ISOLATED / NON-PRODUCTION",
            "RUNTIME UNKNOWN",
            "setRuntimeUnknown('Resolving runtime identity…')",
            "await loadRuntimeIdentity();await loadProductionPrepareReadiness();try{await loadBooks();await loadJobs()}",
            "state.config=await api('/api/config')",
        ):
            self.assertIn(value, self.js)

    def test_primary_mutation_controls_are_runtime_guarded(self) -> None:
        for value in (
            'id="importBtn" class="secondary" data-runtime-mutation-control',
            'id="runBtn" class="primary full" disabled data-runtime-mutation-control',
            'id="generateSpeakerDraft" class="primary" data-runtime-mutation-control',
            'id="approveSpeakerReview" class="primary" disabled data-runtime-mutation-control',
            'id="characterBibleApply" class="primary" disabled data-runtime-mutation-control',
            'id="saveCastingDraft" class="secondary" data-runtime-mutation-control',
            'id="approveCastingPlan" class="primary" disabled data-runtime-mutation-control',
            'id="renderCastingPlan" class="primary" disabled data-runtime-mutation-control',
        ):
            self.assertIn(value, self.html)
        for value in (
            "if(!runtimeAllowsMutation()){toast('Runtime identity must be resolved before mutating actions.',true);return}",
            "document.querySelectorAll('[data-runtime-mutation-control]').forEach(el=>{el.disabled=disable})",
            "data-runtime-mutation-control disabled title=\"Resolve runtime identity before mutating jobs\"",
            "data-runtime-mutation-control disabled title=\"Resolve runtime identity before regenerating\"",
        ):
            self.assertIn(value, self.js)

    def test_runtime_helper_logic_disables_then_reenables_controls(self) -> None:
        script = f"""
const state = {{
  previewOk: true,
  runtimeIdentity: null,
  runtimeIdentityResolved: false,
  speakerReview: null,
  casting: null,
  characterBible: null,
}};
const elements = {{
  runtimeIdentity: {{ classList: {{ remove(){{}}, add(){{}} }}, title: '' }},
  runtimeBadge: {{ textContent: '' }},
  runtimePath: {{ textContent: '', title: '' }},
  importBtn: {{ disabled: false }},
  runBtn: {{ disabled: false }},
  voiceSelect: {{ value: 'ngoc-lan' }},
}};
const mutationControls = [{{ disabled: false }}, {{ disabled: false }}];
globalThis.state = state;
globalThis.$ = selector => elements[selector.slice(1)] || null;
globalThis.document = {{
  querySelector(selector) {{
    return selector.startsWith('#') ? (elements[selector.slice(1)] || null) : null;
  }},
  querySelectorAll(selector) {{
    return selector === '[data-runtime-mutation-control]' ? mutationControls : [];
  }},
}};
function reviewedDecisionCount() {{ return 0; }}
{self._line('function runtimeAllowsMutation()')}
{self._line('function syncMutationControls()')}
state.runtimeIdentityResolved = false;
state.runtimeIdentity = {{ state: 'unknown' }};
syncMutationControls();
const unknown = {{
  importDisabled: elements.importBtn.disabled,
  runDisabled: elements.runBtn.disabled,
  allMutationDisabled: mutationControls.every(item => item.disabled === true),
}};
state.runtimeIdentityResolved = true;
state.runtimeIdentity = {{ state: 'canonical' }};
syncMutationControls();
const canonical = {{
  importDisabled: elements.importBtn.disabled,
  runDisabled: elements.runBtn.disabled,
  allMutationEnabled: mutationControls.every(item => item.disabled === false),
}};
state.runtimeIdentity = {{ state: 'isolated' }};
syncMutationControls();
const isolated = {{
  importDisabled: elements.importBtn.disabled,
  runDisabled: elements.runBtn.disabled,
  allMutationEnabled: mutationControls.every(item => item.disabled === false),
}};
console.log(JSON.stringify({{ unknown, canonical, isolated }}));
"""
        result = subprocess.run(
            ["node", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["unknown"]["importDisabled"])
        self.assertTrue(payload["unknown"]["runDisabled"])
        self.assertTrue(payload["unknown"]["allMutationDisabled"])
        self.assertFalse(payload["canonical"]["importDisabled"])
        self.assertFalse(payload["canonical"]["runDisabled"])
        self.assertTrue(payload["canonical"]["allMutationEnabled"])
        self.assertFalse(payload["isolated"]["importDisabled"])
        self.assertFalse(payload["isolated"]["runDisabled"])
        self.assertTrue(payload["isolated"]["allMutationEnabled"])

    def test_runtime_identity_classification_and_path_shortening_are_stable(self) -> None:
        script = f"""
{self._line('function runtimeIdentityState(payload)')}
{self._line('function shortDataRoot(path)')}
console.log(JSON.stringify({{
  canonical: runtimeIdentityState({{ is_canonical_live_data_root: true, is_canonical_live_db: true }}),
  isolated: runtimeIdentityState({{ data_root: 'D:\\\\StoryAudioAcceptanceRun1\\\\data', db_path: 'D:\\\\StoryAudioAcceptanceRun1\\\\data\\\\app.db' }}),
  unknown: runtimeIdentityState({{ data_root: null, db_path: null }}),
  shortRoot: shortDataRoot('D:\\\\Youtube\\\\Story Trans And Audio\\\\data'),
}}));
"""
        result = subprocess.run(
            ["node", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["canonical"], "canonical")
        self.assertEqual(payload["isolated"], "isolated")
        self.assertEqual(payload["unknown"], "unknown")
        self.assertTrue(payload["shortRoot"].endswith("Story Trans And Audio\\data"))


if __name__ == "__main__":
    import unittest

    unittest.main()
