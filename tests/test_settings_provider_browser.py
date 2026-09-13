from __future__ import annotations

import json
import subprocess
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse

from tests.test_production_scope_browser import ROOT, ScopeFixtureHandler


class SettingsProviderFixtureHandler(ScopeFixtureHandler):
    keys: list[str] = []
    tts_status = "not_loaded"

    @classmethod
    def reset(cls) -> None:
        cls.keys = []
        cls.tts_status = "not_loaded"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            return self._json({
                "gemini_configured": bool(self.keys),
                "gemini_key_count": len(self.keys),
                "gemini_key_storage": "secrets/gemini_api_key.txt",
                "gemini_model": "fixture",
                "tts_status": self.tts_status,
                "tts_error": None,
                "tts_provider_available": True,
                "available_epubs": [],
            })
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0") or 0)
        if parsed.path == "/api/settings/gemini-keys":
            body = json.loads(self.rfile.read(length) or b"{}")
            submitted = [str(value).strip() for value in body.get("keys") or [] if str(value).strip()]
            added = 0
            duplicates = 0
            for value in submitted:
                if value in self.keys:
                    duplicates += 1
                else:
                    type(self).keys.append(value)
                    added += 1
            return self._json({"configured": bool(self.keys), "submitted_count": len(submitted), "added_count": added, "duplicate_count": duplicates, "total_count": len(self.keys), "storage": "secrets/gemini_api_key.txt"})
        if parsed.path == "/api/settings/tts/probe":
            if length:
                self.rfile.read(length)
            type(self).tts_status = "ready"
            return self._json({"status": "ready", "voice_count": 10, "provider_available": True})
        return super().do_POST()


class SettingsProviderBrowserTests(unittest.TestCase):
    def test_settings_completes_gemini_and_tts_recovery_in_browser(self) -> None:
        SettingsProviderFixtureHandler.reset()
        server = ThreadingHTTPServer(("127.0.0.1", 0), SettingsProviderFixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(["node", "scripts/browser_settings_provider_smoke.mjs", f"http://127.0.0.1:{server.server_port}"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertTrue(evidence["ok"])
        self.assertIn("Chưa có Gemini API key", evidence["before"]["status"])
        self.assertIn("Đã thêm 2 key", evidence["first"]["result"])
        self.assertIn("2 key đang khả dụng", evidence["first"]["status"])
        self.assertTrue(evidence["first"]["cleared"])
        self.assertFalse(evidence["first"]["secretVisible"])
        self.assertIn("bỏ qua 1 key trùng", evidence["duplicate"])
        self.assertIn("TTS sẵn sàng", evidence["tts"]["result"])
        self.assertIn("Đọc giọng: sẵn sàng", evidence["tts"]["health"])
        self.assertEqual(evidence["providerRecovery"]["key"], "OPEN_PROVIDER_SETTINGS")
        self.assertEqual(evidence["providerRecovery"]["label"], "Mở Cài đặt TTS")
        self.assertTrue(evidence["providerRecovery"]["hash"].startswith("#/settings"))
        self.assertEqual(evidence["providerRecovery"]["focused"], "settingsProbeTts")


if __name__ == "__main__":
    unittest.main()
