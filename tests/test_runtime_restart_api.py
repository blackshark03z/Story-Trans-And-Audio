from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests.base import IsolatedTestCase


class RuntimeRestartApiTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._multipart_patcher = patch(
            "fastapi.dependencies.utils.ensure_multipart_is_installed",
            lambda: None,
        )
        self._multipart_patcher.start()
        import story_audio.api as api_module

        self.api_module = api_module
        self.original_settings = api_module.settings
        api_module.settings = self.config
        self.client = TestClient(api_module.app)

    def tearDown(self) -> None:
        self.api_module.settings = self.original_settings
        self._multipart_patcher.stop()
        super().tearDown()

    def test_restart_is_unavailable_without_durable_supervisor(self) -> None:
        with patch.dict(
            os.environ,
            {
                "STORY_AUDIO_SUPERVISED": "0",
                "STORY_AUDIO_RESTART_SIGNAL": "",
            },
            clear=False,
        ):
            response = self.client.post(
                "/api/runtime/restart",
                json={"confirmation": "RESTART_STORY_AUDIO"},
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"]["code"],
            "SUPERVISED_RESTART_UNAVAILABLE",
        )

    def test_restart_rejects_signal_path_outside_managed_runtime(self) -> None:
        unsafe_path = self.temp_root / "outside-runtime.request"
        with patch.dict(
            os.environ,
            {
                "STORY_AUDIO_SUPERVISED": "1",
                "STORY_AUDIO_RESTART_SIGNAL": str(unsafe_path),
            },
            clear=False,
        ):
            response = self.client.post(
                "/api/runtime/restart",
                json={"confirmation": "RESTART_STORY_AUDIO"},
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"]["code"],
            "RESTART_SIGNAL_PATH_UNSAFE",
        )
        self.assertFalse(unsafe_path.exists())

    def test_restart_writes_managed_signal_and_schedules_shutdown(self) -> None:
        signal_path = self.config.data_dir / "runtime" / "restart.request"
        with (
            patch.dict(
                os.environ,
                {
                    "STORY_AUDIO_SUPERVISED": "1",
                    "STORY_AUDIO_RESTART_SIGNAL": str(signal_path),
                },
                clear=False,
            ),
            patch("story_audio.api.threading.Timer") as timer,
        ):
            response = self.client.post(
                "/api/runtime/restart",
                json={"confirmation": "RESTART_STORY_AUDIO"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "state": "restarting"})
        self.assertEqual(signal_path.read_text(encoding="ascii"), "restart\n")
        timer.assert_called_once_with(
            0.75,
            self.api_module._signal_supervised_restart,
        )
        timer.return_value.start.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
