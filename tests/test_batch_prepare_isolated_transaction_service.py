from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from story_audio.batch_prepare_execution_attempt_store import (
    COMMITTED,
    OUTCOME_AMBIGUOUS,
    ROLLBACK_CONFIRMED,
    ExecutionAttemptOwnerRejected,
)
from story_audio.batch_prepare_isolated_transaction_service import (
    AmbiguousPrepareOutcome,
    BatchPrepareIsolatedTransactionService,
    CommittedEvidenceUnavailable,
    authorization_flags,
)
from story_audio.batch_prepare_transaction_manager import (
    BatchPrepareTransactionManager,
    IsolatedTransactionBusy,
)
from story_audio.batch_prepare_transaction_revalidator import (
    AuthoritativeChapterSnapshot,
    PrepareTransactionSnapshot,
    chapter_snapshot_digest,
)
from story_audio.db import Database
from tests.phase9_fixture import Phase9FixtureMixin, schema_15_runner


class BatchPrepareIsolatedTransactionServiceTests(Phase9FixtureMixin):
    def _service(self, *, busy_timeout_ms: int = 5000) -> BatchPrepareIsolatedTransactionService:
        return BatchPrepareIsolatedTransactionService(
            Database(self.db_path, migration_runner=schema_15_runner()), busy_timeout_ms=busy_timeout_ms
        )

    def _counts(self, fixture=None):
        facts = fixture or self.fixture
        return {
            "jobs": self.database.fetch_one("SELECT COUNT(*) AS n FROM jobs WHERE book_id=?", (facts["book_id"],))["n"],
            "links": self.database.fetch_one(
                "SELECT COUNT(*) AS n FROM batch_prepare_job_links WHERE batch_prepare_request_id=?",
                (facts["request_id"],),
            )["n"],
            "segments": self.database.fetch_one("SELECT COUNT(*) AS n FROM segments")["n"],
            "artifacts": self.database.fetch_one("SELECT COUNT(*) AS n FROM artifacts")["n"],
        }

    def test_success_commits_one_job_chapters_link_and_attempt_without_render(self) -> None:
        _, snapshot = self.acquire_and_snapshot()
        result = self._service().prepare(snapshot)
        self.assertTrue(result.committed)
        self.assertFalse(result.replay)
        self.assertFalse(result.worker_woken)
        self.assertFalse(result.render_started)
        self.assertEqual(len(result.job_chapter_ids), 2)
        self.assertEqual(self._counts(), {"jobs": 1, "links": 1, "segments": 0, "artifacts": 0})
        self.assertEqual(self.database.fetch_one("SELECT status FROM jobs WHERE id=?", (result.job_id,))["status"], "prepared")
        self.assertEqual(self.database.fetch_one(
            "SELECT state FROM batch_prepare_execution_attempts WHERE batch_prepare_request_id=?",
            (snapshot.request_id,),
        )["state"], COMMITTED)
        self.assertEqual(self.database.fetch_one(
            "SELECT state FROM batch_prepare_requests WHERE id=?", (snapshot.request_id,)
        )["state"], "APPLYING")
        self.assertTrue(result.eligible_for_future_applied_recording)
        self.assertEqual(authorization_flags()["runtime_wiring"], False)

    def test_same_request_replay_and_response_loss_recover_same_job(self) -> None:
        _, snapshot = self.acquire_and_snapshot()
        def lose_response(stage, context):
            if stage == "after_commit_before_evidence":
                raise RuntimeError("response lost")
        with self.assertRaises(RuntimeError):
            self._service().prepare(snapshot, failure_injector=lose_response)
        recovered = self._service().prepare(snapshot)
        direct = self._service().recover(snapshot)
        self.assertTrue(recovered.replay)
        self.assertEqual(recovered.job_id, direct.job_id)
        self.assertEqual(self._counts()["jobs"], 1)

    def test_all_precommit_failure_points_roll_back_every_job_row_and_link(self) -> None:
        stages = [
            "after_request_validation", "after_conflict_check", "after_job_insert",
            "after_job_chapter_insert", "after_linkage_insert", "after_attempt_update", "before_commit",
        ]
        identities = iter("cdef123")
        for index, stage in enumerate(stages, start=1):
            fixture = self.create_scope(
                client_request_id=f"failure-{stage}", request_identity=next(identities) * 64,
                source_suffix=f"failure-{index}", chapter_numbers=(100 + index * 2, 101 + index * 2),
            )
            _, snapshot = self.acquire_and_snapshot(fixture)
            def fail(current, context):
                if current == stage and (stage != "after_job_chapter_insert" or context["count"] == 1):
                    raise RuntimeError(stage)
            with self.subTest(stage=stage), self.assertRaises(RuntimeError):
                self._service().prepare(snapshot, failure_injector=fail)
            self.assertEqual(self._counts(fixture), {"jobs": 0, "links": 0, "segments": 0, "artifacts": 0})
            self.assertEqual(self.database.fetch_one(
                "SELECT state FROM batch_prepare_execution_attempts WHERE batch_prepare_request_id=?",
                (fixture["request_id"],),
            )["state"], ROLLBACK_CONFIRMED)

    def test_stale_text_plan_owner_and_lease_create_no_partial_state(self) -> None:
        cases = ["text", "plan", "token", "generation", "lease"]
        identities = iter("cdef1")
        for index, case in enumerate(cases, start=1):
            fixture = self.create_scope(
                client_request_id=f"stale-{case}", request_identity=next(identities) * 64,
                source_suffix=f"stale-service-{case}", chapter_numbers=(200 + index * 2, 201 + index * 2),
            )
            _, snapshot = self.acquire_and_snapshot(fixture)
            if case == "text":
                with self.database.transaction() as connection:
                    connection.execute("UPDATE chapters SET active_text_revision_id=NULL WHERE id=?", (fixture["chapters"][0]["chapter_id"],))
            elif case == "plan":
                with self.database.transaction() as connection:
                    connection.execute("UPDATE casting_plans SET status='draft',approved_at=NULL WHERE id=?", (fixture["chapters"][0]["casting_plan_id"],))
            elif case == "token":
                snapshot = replace(snapshot, owner_token="wrong")
            elif case == "generation":
                snapshot = replace(snapshot, owner_generation=999)
            else:
                snapshot = replace(snapshot, owner_token=snapshot.owner_token)
                with self.database.transaction() as connection:
                    connection.execute(
                        "UPDATE batch_prepare_execution_attempts SET lease_acquired_at=?,lease_expires_at=? WHERE batch_prepare_request_id=?",
                        ("2000-01-01T00:00:00+00:00", "2000-01-02T00:00:00+00:00", fixture["request_id"]),
                    )
            with self.subTest(case=case), self.assertRaises(Exception):
                self._service().prepare(snapshot)
            self.assertEqual(self._counts(fixture)["jobs"], 0)
            self.assertEqual(self._counts(fixture)["links"], 0)

    def test_same_request_concurrency_has_one_job_and_both_callers_recover_it(self) -> None:
        _, snapshot = self.acquire_and_snapshot()
        results = []
        errors = []
        barrier = threading.Barrier(3)
        def run():
            barrier.wait()
            try:
                results.append(self._service().prepare(snapshot))
            except BaseException as exc:
                errors.append(exc)
        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual({item.job_id for item in results}, {results[0].job_id})
        self.assertEqual(self._counts()["jobs"], 1)

    def test_overlapping_requests_have_one_winner_nonoverlap_both_commit(self) -> None:
        second_request = self.create_request_for_scope(
            self.fixture, client_request_id="overlap-2", request_identity="c" * 64,
            plan_fingerprint="d" * 64,
        )
        _, first = self.acquire_and_snapshot(self.fixture)
        _, second = self.acquire_and_snapshot(second_request)
        outcomes = []
        barrier = threading.Barrier(3)
        def run(snapshot):
            barrier.wait()
            try:
                outcomes.append(("ok", self._service().prepare(snapshot).job_id))
            except Exception as exc:
                outcomes.append(("error", type(exc).__name__))
        threads = [threading.Thread(target=run, args=(item,)) for item in (first, second)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertEqual([kind for kind, _ in outcomes].count("ok"), 1)
        self.assertEqual(self.database.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"], 1)

        other = self.create_scope(
            client_request_id="non-overlap", request_identity="e" * 64,
            source_suffix="non-overlap", chapter_numbers=(50, 51),
        )
        _, other_snapshot = self.acquire_and_snapshot(other)
        self.assertTrue(self._service().prepare(other_snapshot).committed)
        self.assertEqual(self.database.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"], 2)

    def test_bounded_busy_error_has_no_raw_sqlite_or_partial_write(self) -> None:
        _, snapshot = self.acquire_and_snapshot()
        holder = BatchPrepareTransactionManager(self.db_path).begin("holder")
        try:
            with self.assertRaises(IsolatedTransactionBusy):
                self._service(busy_timeout_ms=20).prepare(snapshot)
        finally:
            holder.rollback()
            holder.close()
        self.assertEqual(self._counts()["jobs"], 0)

    def test_commit_exception_after_real_commit_recovers_and_before_commit_is_ambiguous(self) -> None:
        _, snapshot = self.acquire_and_snapshot()
        service = self._service()
        original_begin = service.manager.begin
        def begin_after(reference):
            transaction = original_begin(reference)
            original_commit = transaction.commit
            def commit():
                original_commit()
                raise RuntimeError("commit response lost")
            transaction.commit = commit  # type: ignore[method-assign]
            return transaction
        service.manager.begin = begin_after  # type: ignore[method-assign]
        recovered = service.prepare(snapshot)
        self.assertTrue(recovered.replay)
        self.assertEqual(self._counts()["jobs"], 1)

        fixture = self.create_scope(
            client_request_id="commit-before", request_identity="c" * 64,
            source_suffix="commit-before", chapter_numbers=(60, 61),
        )
        _, second = self.acquire_and_snapshot(fixture)
        service2 = self._service()
        begin2 = service2.manager.begin
        def begin_before(reference):
            transaction = begin2(reference)
            def commit():
                raise RuntimeError("commit failed before outcome")
            transaction.commit = commit  # type: ignore[method-assign]
            return transaction
        service2.manager.begin = begin_before  # type: ignore[method-assign]
        with self.assertRaises(AmbiguousPrepareOutcome):
            service2.prepare(second)
        self.assertEqual(self._counts(fixture)["jobs"], 0)
        self.assertEqual(self.database.fetch_one(
            "SELECT state FROM batch_prepare_execution_attempts WHERE batch_prepare_request_id=?",
            (fixture["request_id"],),
        )["state"], OUTCOME_AMBIGUOUS)

    def test_evidence_reload_failure_does_not_roll_back_or_rerun_committed_transaction(self) -> None:
        _, snapshot = self.acquire_and_snapshot()
        def fail(stage, context):
            if stage == "after_evidence_reload":
                raise RuntimeError("audit storage unavailable")
        with self.assertRaises(CommittedEvidenceUnavailable):
            self._service().prepare(snapshot, failure_injector=fail)
        self.assertEqual(self._counts()["jobs"], 1)
        self.assertEqual(self._service().recover(snapshot).job_id, 1)

    def test_process_restart_prepare_response_loss_and_recovery(self) -> None:
        chapters = tuple(AuthoritativeChapterSnapshot(**item) for item in self.fixture["chapters"])
        digest = chapter_snapshot_digest(chapters)
        worker = Path(__file__).resolve().parent / "batch_prepare_phase9_isolated_worker.py"
        env = os.environ.copy()
        env["STORY_AUDIO_TESTING"] = "1"
        acquired_process = subprocess.run(
            [sys.executable, str(worker), str(self.db_path), "acquire"],
            input=json.dumps({
                "request_id": self.fixture["request_id"],
                "request_identity": self.fixture["request_identity"],
                "plan_fingerprint": self.fixture["plan_fingerprint"],
                "chapter_snapshot_digest": digest,
                "transaction_reference": "process-restart-tx",
            }),
            text=True, capture_output=True, cwd=Path(__file__).resolve().parents[1], env=env,
        )
        self.assertEqual(acquired_process.returncode, 0, acquired_process.stderr)
        owner = json.loads(acquired_process.stdout)
        snapshot = PrepareTransactionSnapshot(
            request_id=self.fixture["request_id"], request_identity=self.fixture["request_identity"],
            book_id=self.fixture["book_id"], from_chapter=self.fixture["from_chapter"],
            to_chapter=self.fixture["to_chapter"], target_phase="PREPARE",
            plan_fingerprint=self.fixture["plan_fingerprint"], chapters=chapters,
            chapter_snapshot_digest=digest, owner_generation=owner["generation"],
            owner_token=owner["owner_token"], transaction_reference=owner["transaction_reference"],
        )
        payload = asdict(snapshot)
        payload["chapters"] = [asdict(item) for item in snapshot.chapters]
        command = [sys.executable, str(worker), str(self.db_path), "prepare"]
        first = subprocess.run(
            command, input=json.dumps(payload), text=True, capture_output=True,
            cwd=Path(__file__).resolve().parents[1], env=env,
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        created = json.loads(first.stdout)
        recovered = subprocess.run(
            [sys.executable, str(worker), str(self.db_path), "recover"],
            input=json.dumps(payload), text=True, capture_output=True,
            cwd=Path(__file__).resolve().parents[1], env=env, check=True,
        )
        self.assertEqual(json.loads(recovered.stdout)["job_id"], created["job_id"])
        bad = {**payload, "owner_token": "wrong"}
        rejected = subprocess.run(
            [sys.executable, str(worker), str(self.db_path), "recover"],
            input=json.dumps(bad), text=True, capture_output=True,
            cwd=Path(__file__).resolve().parents[1], env=env,
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertNotIn(snapshot.owner_token, rejected.stderr)
        self.assertEqual(self._counts()["jobs"], 1)

    def test_source_has_no_runtime_or_provider_wiring_and_all_authorization_gates_are_false(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "story_audio" / "batch_prepare_isolated_transaction_service.py").read_text(encoding="utf-8")
        for forbidden in [
            "from .pipeline", "import story_audio.pipeline", "from .api", "from .batch_prepare_orchestrator",
            "prepare_job(", "create_job(", "start_prepared_job(", "wake_worker(", "chapter 369",
        ]:
            self.assertNotIn(forbidden, source)
        gates = authorization_flags()
        for key in [
            "runtime_wiring", "canonical_activation", "production_job_creation", "api_integration",
            "worker_wake", "start_render", "provider_or_tts",
        ]:
            self.assertFalse(gates[key])


if __name__ == "__main__":
    unittest.main()
