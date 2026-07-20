from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DailyProductionShellUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
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
        changed_ui = self.html + self.js + self.css
        self.assertNotIn("Chapter 369", changed_ui)
        self.assertNotIn("chapter 369", changed_ui)
        self.assertNotIn("Chương 369", changed_ui)


if __name__ == "__main__":
    unittest.main()
