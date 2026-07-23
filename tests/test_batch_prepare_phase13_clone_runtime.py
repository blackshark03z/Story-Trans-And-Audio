from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from story_audio.batch_prepare_clone_rehearsal import apply_dormant_migration
from story_audio.db import Database
from tests.base import IsolatedTestCase


PYTHON = Path(r"D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Phase13CloneRuntimeTests(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        source = self.temp_root / "source" / "app.db"
        Database(source).initialize()
        self.clone_root = self.temp_root / "external-clone"
        self.clone_root.mkdir()
        self.clone = self.clone_root / "app.db"
        shutil.copyfile(source, self.clone)
        for version in (13, 14, 15):
            apply_dormant_migration(self.clone, version)
        self.environment = dict(os.environ)
        self.environment.update({
            "STORY_AUDIO_TESTING": "1",
            "STORY_AUDIO_DATA_DIR": str(self.clone_root),
            "PREPARE_RUNTIME_MODE": "CLONE_DISABLED",
            "PREPARE_KILL_SWITCH_ACTIVE": "true",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
        })
        self.environment.pop("STORY_AUDIO_ALLOW_LIVE_DB", None)

    def _request(self, port: int, path: str):
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3) as response:
            return response.status, json.loads(response.read().decode())

    def _start(self, port: int):
        process = subprocess.Popen(
            [str(PYTHON), "tests/batch_prepare_phase13_runtime_worker.py", "--port", str(port)],
            cwd=Path.cwd(), env=self.environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                self.fail(f"clone runtime exited early: {stdout} {stderr}")
            try:
                self._request(port, "/api/production/prepare-readiness")
                return process
            except (OSError, urllib.error.URLError):
                time.sleep(0.1)
        process.terminate()
        process.wait(timeout=5)
        self.fail("clone runtime startup timed out")

    def _stop(self, process):
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            self.fail("clone runtime did not stop cleanly")
        finally:
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()

    def test_inspect_has_get_readiness_and_no_batch_mutation_route(self):
        completed = subprocess.run(
            [str(PYTHON), "tests/batch_prepare_phase13_runtime_worker.py", "--inspect"],
            cwd=Path.cwd(), env=self.environment, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        readiness = payload["readiness"]
        self.assertEqual(readiness["runtime_mode"], "CLONE_DISABLED")
        self.assertFalse(readiness["mutation_service_constructed"])
        self.assertFalse(readiness["mutation_authorized"])
        route_map = {item["path"]: set(item["methods"]) for item in payload["routes"]}
        self.assertEqual(route_map["/api/production/prepare-readiness"], {"GET"})
        self.assertNotIn("/api/production/batch-prepare", route_map)

    def test_start_read_restart_preserves_exact_clone_bytes(self):
        before_hash = hashlib.sha256(self.clone.read_bytes()).hexdigest()
        before_size = self.clone.stat().st_size
        observations = []
        ports = []
        for _ in range(2):
            port = _free_port()
            ports.append(port)
            process = self._start(port)
            try:
                status, readiness = self._request(port, "/api/production/prepare-readiness")
                observations.append(readiness)
                self.assertEqual(status, 200)
                self.assertEqual(readiness["schema_version"], 15)
                self.assertTrue(readiness["kill_switch_active"])
                self.assertFalse(readiness["mutation_route_registered"])
                status, runtime = self._request(port, "/api/runtime")
                self.assertEqual(status, 200)
                self.assertEqual(runtime["schema_version"], 15)
                self.assertFalse(runtime["is_canonical_live_db"])
                for path in (
                    "/api/production/range-readiness?book_id=1&from_chapter=369&to_chapter=369",
                    "/api/production/batch-plan?book_id=1&from_chapter=369&to_chapter=369&target_phase=PREPARE",
                ):
                    try:
                        urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3)
                    except urllib.error.HTTPError as exc:
                        self.assertIn(exc.code, {400, 404})
            finally:
                self._stop(process)
        self.assertEqual(observations[0], observations[1])
        self.assertEqual(hashlib.sha256(self.clone.read_bytes()).hexdigest(), before_hash)
        self.assertEqual(self.clone.stat().st_size, before_size)
        self.assertFalse(Path(str(self.clone) + "-wal").exists())
        self.assertFalse(Path(str(self.clone) + "-shm").exists())
        for port in ports:
            with socket.socket() as sock:
                self.assertNotEqual(sock.connect_ex(("127.0.0.1", port)), 0)


if __name__ == "__main__":
    unittest.main()
