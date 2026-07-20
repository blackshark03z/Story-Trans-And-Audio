from __future__ import annotations

import re
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DailyProductionShellUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        cls.resolver_js = (ROOT / "ui" / "production_state.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")

    def test_top_navigation_has_six_canonical_areas(self) -> None:
        expected = [
            ("home", "#/home", "Trang chủ"),
            ("production", "#/production", "Sản xuất"),
            ("voices", "#/voices", "Thư viện giọng"),
            ("books", "#/books", "Sách và nhân vật"),
            ("audio", "#/audio", "Audio đã tạo"),
            ("settings", "#/settings", "Cài đặt"),
        ]
        self.assertIn('id="appNav"', self.html)
        self.assertIn('aria-label="Khu vực chính"', self.html)
        for route, href, label in expected:
            self.assertIn(
                f'href="{href}" data-app-route="{route}" aria-label="{label}">{label}</a>',
                self.html,
            )
            self.assertIn(f"{route}:{{hash:'{href}'", self.js)

    def test_all_top_level_views_are_isolated_by_route(self) -> None:
        for route in ("home", "production", "voices", "books", "audio", "settings"):
            self.assertIn(f'data-app-view="{route}"', self.html)
        self.assertIn(".app-view[hidden]{display:none!important}", self.css)
        self.assertIn("view.hidden=!active", self.js)
        self.assertIn("view.setAttribute('aria-hidden',active?'false':'true')", self.js)
        self.assertIn("link.setAttribute('aria-current','page')", self.js)

    def test_hash_routes_support_default_fallback_and_history(self) -> None:
        script = """
globalThis.window = { location: { hash: '' }, addEventListener(){} };
globalThis.history = { calls: [], replaceState(_a,_b,hash){ this.calls.push(['replace',hash]); window.location.hash = hash; }, pushState(_a,_b,hash){ this.calls.push(['push',hash]); window.location.hash = hash; } };
const views = ['home','production','voices','books','audio','settings'].map(route => ({ dataset: { appView: route }, hidden: null, attrs: {}, setAttribute(k,v){ this.attrs[k]=v; } }));
const links = ['home','production','voices','books','audio','settings'].map(route => ({ dataset: { appRoute: route }, classList: { values: new Set(), toggle(k,v){ v ? this.values.add(k) : this.values.delete(k); } }, attrs: {}, setAttribute(k,v){ this.attrs[k]=v; }, removeAttribute(k){ delete this.attrs[k]; } }));
globalThis.document = { querySelectorAll(selector){ return selector === '[data-app-view]' ? views : links; }, querySelector(selector){ return selector === '#appViewHeading' ? { textContent: '' } : null; } };
const state = { currentRoute: 'home' };
const APP_ROUTES={home:{hash:'#/home',label:'Trang chủ',heading:'Trang chủ'},production:{hash:'#/production',label:'Sản xuất',heading:'Sản xuất'},voices:{hash:'#/voices',label:'Thư viện giọng',heading:'Thư viện giọng'},books:{hash:'#/books',label:'Sách và nhân vật',heading:'Sách và nhân vật'},audio:{hash:'#/audio',label:'Audio đã tạo',heading:'Audio đã tạo'},settings:{hash:'#/settings',label:'Cài đặt',heading:'Cài đặt'}};
function routeFromHash(hash=window.location.hash){const key=String(hash||'').replace(/^#\\/?/,'').split(/[/?]/)[0]||'home';return APP_ROUTES[key]?key:'home'}
function setAppRoute(route,{replace=false}={}){const next=APP_ROUTES[route]?route:'home';state.currentRoute=next;document.querySelectorAll('[data-app-view]').forEach(view=>{const active=view.dataset.appView===next;view.hidden=!active;view.setAttribute('aria-hidden',active?'false':'true')});document.querySelectorAll('[data-app-route]').forEach(link=>{const active=link.dataset.appRoute===next;link.classList.toggle('active',active);if(active)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current')});const heading=document.querySelector('#appViewHeading');if(heading)heading.textContent=APP_ROUTES[next].heading;const desired=APP_ROUTES[next].hash;if(window.location.hash!==desired){if(replace)history.replaceState(null,'',desired);else history.pushState(null,'',desired)}}
console.log(JSON.stringify({
  empty: routeFromHash(''),
  production: routeFromHash('#/production'),
  unknown: routeFromHash('#/missing'),
}));
setAppRoute('voices');
console.log(JSON.stringify({
  route: state.currentRoute,
  hash: window.location.hash,
  visible: views.filter(view => view.hidden === false).map(view => view.dataset.appView),
  active: links.filter(link => link.attrs['aria-current'] === 'page').map(link => link.dataset.appRoute),
}));
"""
        result = subprocess.run(
            ["node", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        lines = result.stdout.strip().splitlines()
        self.assertEqual(lines[0], '{"empty":"home","production":"production","unknown":"home"}')
        self.assertEqual(lines[1], '{"route":"voices","hash":"#/voices","visible":["voices"],"active":["voices"]}')

    def test_production_shell_lists_eight_canonical_stages(self) -> None:
        match = re.search(
            r'<ol id="productionStageShell".*?</ol>',
            self.html,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        stage_html = match.group(0)
        expected = [
            "Phạm vi",
            "Văn bản",
            "Người nói",
            "Giọng",
            "Duyệt bản đồ giọng",
            "Chuẩn bị",
            "Render",
            "QA",
        ]
        self.assertEqual(stage_html.count("<li"), 8)
        for label in expected:
            self.assertIn(f"<strong>{label}</strong>", stage_html)

    def test_production_state_resolver_asset_loads_before_app(self) -> None:
        self.assertLess(self.html.index("/assets/production_state.js"), self.html.index("/assets/app.js"))
        self.assertIn("function renderProductionShell", self.js)
        self.assertIn("resolveProductionState", self.resolver_js)

    def test_production_shell_has_one_primary_action_and_state_card(self) -> None:
        self.assertEqual(self.html.count('id="productionPrimaryAction"'), 1)
        self.assertIn("dominant-production-action", self.html)
        self.assertIn('id="productionCurrentStepHeading"', self.html)
        self.assertIn('role="status"', self.html)
        self.assertIn("primary.onclick=()=>focusProductionTarget(vm.targetPanel)", self.js)

    def test_resolver_renders_completed_current_and_locked_stage_buttons(self) -> None:
        self.assertIn('aria-current="step"', self.js)
        self.assertIn('disabled aria-disabled="true"', self.js)
        self.assertIn("stage.complete?", self.js)
        self.assertIn(".production-stage-shell li.locked button", self.css)
        self.assertIn(".production-stage-shell li.complete button", self.css)

    def test_loading_and_unresolved_states_do_not_expose_mutations(self) -> None:
        self.assertIn("STATE_UNRESOLVED", self.resolver_js)
        self.assertIn("readOnlyOnly:true", self.resolver_js)
        self.assertIn("mutationActionsMayBeDisplayed", self.resolver_js)
        self.assertIn("diagnosticDetails:['loading']", self.resolver_js)

    def test_scope_restoration_uses_hash_and_local_storage_hint(self) -> None:
        self.assertIn("PRODUCTION_SCOPE_STORAGE_KEY", self.js)
        self.assertIn("productionHashForScope", self.js)
        self.assertIn("productionScopeFromHash(window.location.hash)", self.js)
        self.assertIn("storedProductionScope()", self.js)
        self.assertIn("replaceScopeRoute", self.js)

    def test_production_route_restore_uses_only_read_only_requests(self) -> None:
        restore_section = self.js[
            self.js.index("async function restoreProductionScopeFromRoute"):
            self.js.index("async function api")
        ]
        self.assertIn("await loadBooks()", restore_section)
        self.assertIn("await openChapter(scope.chapterId", restore_section)
        self.assertNotIn("method:'POST'", restore_section)
        self.assertNotIn("method:'PUT'", restore_section)
        self.assertNotIn("method:'PATCH'", restore_section)
        self.assertNotIn("method:'DELETE'", restore_section)

    def test_chapter_369_shape_resolves_to_casting_review_without_hardcoding(self) -> None:
        script = """
const resolver = require('./ui/production_state.js');
const vm = resolver.resolveProductionState({
  book: {id: 1},
  chapter: {id: 999, book_id: 1, chapter_number: 999, active_text_revision_id: 738, audio_status: 'not_created'},
  revisions: [{id: 738, status: 'approved'}],
  speakerDraft: {id: 15, status: 'approved', stale: false, remaining_unreviewed_count: 0, invalid_count: 0},
  casting: {voice_profile: {validation: {valid: true}}, casting: {id: 24, status: 'draft', plan_revision: 1, plan: {utterances: [{utterance_id: 'u1', resolved_voice_id: 'custom:26'}]}}},
  jobs: [],
  active_output: {},
});
console.log(JSON.stringify({state: vm.conceptualState, stage: vm.currentStageLabel, action: vm.primaryActionLabel, current: vm.stages.filter(s => s.current).length}));
"""
        result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True, cwd=str(ROOT), encoding="utf-8")
        self.assertEqual(
            json.loads(result.stdout),
            {"state": "CASTING_REVIEW", "stage": "Duyệt bản đồ giọng", "action": "Duyệt bản đồ giọng", "current": 1},
        )

    def test_existing_panels_are_not_duplicated_across_views(self) -> None:
        self.assertEqual(self.html.count('id="workspace"'), 1)
        self.assertEqual(self.html.count('class="panel queue-panel"'), 1)
        self.assertEqual(self.html.count('custom-voice-library-panel'), 1)
        production_section = re.search(
            r'<section id="productionView".*?</section>\s*</section>\s*<section id="voicesView"',
            self.html,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(production_section)
        self.assertIn('id="workspace"', production_section.group(0))
        self.assertNotIn("custom-voice-library-panel", production_section.group(0))

    def test_route_functions_do_not_call_mutation_endpoints(self) -> None:
        route_section = self.js[
            self.js.index("function routeFromHash"):self.js.index("async function api")
        ]
        forbidden = [
            "/api/jobs",
            "/api/jobs/prepare",
            "/start",
            "/api/speaker-assignment",
            "/api/casting",
            "/api/voice-previews",
            "/api/custom-voice-revisions",
        ]
        for endpoint in forbidden:
            self.assertNotIn(endpoint, route_section)

    def test_daily_prod_shell_has_no_chapter_specific_hardcoding(self) -> None:
        changed_ui = self.html + self.js + self.css + self.resolver_js
        self.assertNotIn("Chapter 369", changed_ui)
        self.assertNotIn("chapter 369", changed_ui)
        self.assertNotIn("Chương 369", changed_ui)


if __name__ == "__main__":
    unittest.main()
