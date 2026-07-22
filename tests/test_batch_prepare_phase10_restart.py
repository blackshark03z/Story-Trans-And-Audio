from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

from tests.batch_prepare_phase10_fixture import Phase10FixtureMixin


WORKER = Path("tests/batch_prepare_phase10_worker.py").resolve()


class BatchPreparePhase10RestartTests(Phase10FixtureMixin):
    def _run(self, mode: str, request: dict, *, expected_code: int = 0):
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        command = [sys.executable, str(WORKER), mode, str(self.db_path), json.dumps(request, sort_keys=True)]
        self.assertNotIn("owner_token", " ".join(command))
        completed = subprocess.run(command, cwd=Path.cwd(), env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(completed.returncode, expected_code, completed.stderr)
        return json.loads(completed.stdout) if completed.stdout.strip() else None

    def test_process_restart_recovers_committed_job_without_raw_token(self) -> None:
        plan = self.plan()
        request = self.request(plan, client_request_id="restart-commit")
        self._run("exit-after-commit", request, expected_code=19)
        self.assertEqual(self.store.get_request_by_client_request_id("restart-commit").state, "APPLYING")
        self.assertEqual(self.counts()["jobs"], 1)
        recovered = self._run("recover", request)
        self.assertEqual(recovered["request_state"], "APPLIED")
        self.assertTrue(recovered["replay"])
        self.assertEqual(recovered["result"]["recovery_source"], "committed_evidence_recovery")
        self.assertEqual(self.counts()["jobs"], 1)

    def test_process_restart_replays_applied_without_second_job(self) -> None:
        plan = self.plan()
        request = self.request(plan, client_request_id="restart-replay")
        first = self._run("recover", request)
        self.assertEqual(first["request_state"], "APPLIED")
        replay = self._run("recover", request)
        self.assertEqual(replay["status"], "APPLIED_REPLAYED")
        self.assertEqual(self.counts()["jobs"], 1)

    def test_hard_exit_after_job_insert_rolls_back_and_never_leaves_partial_rows(self) -> None:
        plan = self.plan()
        request = self.request(plan, client_request_id="restart-job-exit")
        self._run("exit-after-job", request, expected_code=18)
        counts = self.counts()
        self.assertEqual(counts["jobs"], 0)
        self.assertEqual(counts["job_chapters"], 0)
        self.assertEqual(counts["batch_prepare_job_links"], 0)
        time.sleep(1.2)
        recovered = self._run("recover", request)
        self.assertEqual(recovered["request_state"], "FAILED")
        self.assertEqual(self.counts()["jobs"], 0)

    def test_hard_exit_after_owner_acquisition_creates_no_job(self) -> None:
        plan = self.plan()
        request = self.request(plan, client_request_id="restart-owner-exit")
        self._run("exit-after-owner", request, expected_code=17)
        self.assertEqual(self.counts()["jobs"], 0)
        self.assertEqual(self.store.get_request_by_client_request_id("restart-owner-exit").state, "APPLYING")
        time.sleep(1.2)
        recovered = self._run("recover", request)
        self.assertEqual(recovered["request_state"], "FAILED")
        self.assertEqual(self.counts()["jobs"], 0)


if __name__ == "__main__":
    unittest.main()
