from __future__ import annotations

from pathlib import Path

from tests.base import IsolatedTestCase


class CanonicalLauncherRestartHelperTests(IsolatedTestCase):
    def test_helper_targets_only_the_owned_launcher_without_force_termination(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "scripts" / "restart_canonical_launcher.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-NetTCPConnection -LocalPort $Port -State Listen", source)
        self.assertIn("-m story_audio.main", source)
        self.assertIn("Find-OwnedLauncher", source)
        self.assertIn("Stop-Process -Id ([int]$launcher.ProcessId)", source)
        self.assertIn("Request-ApplicationShutdown", source)
        self.assertIn("/api/runtime/restart", source)
        self.assertIn("is_canonical_live_db", source)
        self.assertNotIn("-Force", source)
        self.assertNotIn("Get-Process python", source)
        self.assertIn("operator_authentication_verified", source)
        self.assertIn("run_app.ps1", source)
