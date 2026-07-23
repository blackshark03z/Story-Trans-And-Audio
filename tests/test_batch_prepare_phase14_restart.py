from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import time
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

from tests.batch_prepare_phase10_fixture import Phase10FixtureMixin


PYTHON = Path(r"D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe")
WORKER = Path("tests/batch_prepare_phase13_runtime_worker.py").resolve()
TOKEN = "phase14-restart-synthetic-token"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Phase14CloneRestartTests(Phase10FixtureMixin):
    def setUp(self) -> None:
        super().setUp()
        self.plan_snapshot = self.plan()
        self.clone = self.temp_root / "app.db"
        shutil.copyfile(self.db_path, self.clone)
        self.environment = dict(os.environ)
        self.environment.update(
            {
                "STORY_AUDIO_TESTING": "1",
                "STORY_AUDIO_DATA_DIR": str(self.temp_root),
                "PREPARE_RUNTIME_MODE": "CLONE_DISABLED",
                "PREPARE_FEATURE_AVAILABLE": "true",
                "PREPARE_MUTATION_ENABLED": "true",
                "PREPARE_OPERATOR_WINDOW_OPEN": "true",
                "PREPARE_CANONICAL_SCHEMA_READY": "true",
                "PREPARE_KILL_SWITCH_ACTIVE": "false",
                "PREPARE_CLONE_MUTATION_TEST_AUTHORIZED": "true",
                "PREPARE_OPERATOR_AUTH_ENABLED": "true",
                "PREPARE_OPERATOR_ID": "operator.phase14-restart",
                "PREPARE_OPERATOR_TOKEN_SHA256": hashlib.sha256(TOKEN.encode()).hexdigest(),
                "PREPARE_OPERATOR_TOKEN_VERSION": "phase14-restart-v1",
                "PREPARE_OPERATOR_AUTH_LOCAL_TEST_MODE": "true",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUTF8": "1",
            }
        )
        self.environment.pop("STORY_AUDIO_ALLOW_LIVE_DB", None)

    def _request_payload(self) -> dict:
        scope = self.plan_snapshot["scope"]
        return {
            "client_request_id": "phase14-restart-request",
            "book_id": scope["book_id"],
            "from_chapter": scope["from_chapter"],
            "to_chapter": scope["to_chapter"],
            "target_phase": "PREPARE",
            "plan_fingerprint": self.plan_snapshot["plan_fingerprint"],
            "confirmation": True,
        }

    def _http(self, port: int, method: str, path: str, payload: dict | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            method=method,
            data=data,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode())

    def _start(self, port: int):
        process = subprocess.Popen(
            [str(PYTHON), str(WORKER), "--port", str(port)],
            cwd=Path.cwd(),
            env=self.environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                self.fail(f"clone runtime exited early: {stdout} {stderr}")
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/production/prepare-readiness",
                    timeout=2,
                ):
                    return process
            except (OSError, urllib.error.URLError):
                time.sleep(0.1)
        process.terminate()
        process.wait(timeout=5)
        self.fail("clone runtime startup timed out")

    def _stop(self, process) -> None:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
            self.fail("clone runtime did not stop cleanly")
        self.assertNotIn(TOKEN, stdout)
        self.assertNotIn(TOKEN, stderr)

    def _counts(self) -> dict[str, int]:
        uri = self.clone.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            return {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in (
                    "batch_prepare_requests",
                    "batch_prepare_execution_attempts",
                    "batch_prepare_job_links",
                    "jobs",
                    "job_chapters",
                    "segments",
                    "artifacts",
                )
            }

    def test_post_and_get_replay_same_job_across_runtime_restart(self) -> None:
        payload = self._request_payload()
        first_port = _free_port()
        first_process = self._start(first_port)
        try:
            status, first = self._http(
                first_port,
                "POST",
                "/api/production/batch-prepare",
                payload,
            )
            self.assertEqual(status, 200)
            self.assertEqual(first["request_state"], "APPLIED")
        finally:
            self._stop(first_process)

        second_port = _free_port()
        second_process = self._start(second_port)
        try:
            status, replay = self._http(
                second_port,
                "POST",
                "/api/production/batch-prepare",
                payload,
            )
            self.assertEqual(status, 200)
            status, recovered = self._http(
                second_port,
                "GET",
                f"/api/production/batch-prepare/{payload['client_request_id']}",
            )
            self.assertEqual(status, 200)
            self.assertEqual(first["job_id"], replay["job_id"])
            self.assertEqual(first["job_id"], recovered["job_id"])
        finally:
            self._stop(second_process)

        self.assertEqual(
            self._counts(),
            {
                "batch_prepare_requests": 1,
                "batch_prepare_execution_attempts": 1,
                "batch_prepare_job_links": 1,
                "jobs": 1,
                "job_chapters": 2,
                "segments": 0,
                "artifacts": 0,
            },
        )
if __name__ == "__main__":
    unittest.main()
