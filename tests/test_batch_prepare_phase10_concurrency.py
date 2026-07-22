from __future__ import annotations

import sqlite3
import threading
import time
import unittest

from story_audio.batch_prepare_isolated_transaction_service import BatchPrepareIsolatedTransactionService
from tests.batch_prepare_phase10_fixture import Phase10FixtureMixin


class _FailAppliedOnceStore:
    def __init__(self, inner):
        self.inner = inner
        self.failed = False

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def record_applied_result(self, *args, **kwargs):
        if not self.failed:
            self.failed = True
            raise RuntimeError("simulated terminal persistence loss")
        return self.inner.record_applied_result(*args, **kwargs)


class BatchPreparePhase10ConcurrencyTests(Phase10FixtureMixin):
    def _run_concurrently(self, calls):
        start = threading.Barrier(len(calls))
        results = []
        errors = []
        lock = threading.Lock()

        def worker(call):
            try:
                start.wait(timeout=5)
                value = call()
                with lock:
                    results.append(value)
            except Exception as exc:  # noqa: BLE001 - test captures thread failures.
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(call,)) for call in calls]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        return results

    def test_same_request_concurrency_creates_one_job_and_one_applied_result(self) -> None:
        plan = self.plan()
        request = self.request(plan)
        first, _ = self.orchestrator()
        second, _ = self.orchestrator()
        results = self._run_concurrently((lambda: first.prepare(request), lambda: second.prepare(request)))
        self.assertEqual(self.counts()["jobs"], 1)
        self.assertEqual(self.counts()["job_chapters"], 2)
        self.assertEqual(self.counts()["batch_prepare_job_links"], 1)
        self.assertEqual(self.counts()["batch_prepare_requests"], 1)
        self.assertEqual(sum(result["request_state"] == "APPLIED" for result in results), 1)
        self.assertTrue(any(result["request_state"] in {"APPLYING", "APPLIED"} for result in results))

    def test_overlapping_requests_are_serialized_to_one_job(self) -> None:
        plan_a = self.plan(from_chapter=10, to_chapter=11)
        plan_b = self.plan(from_chapter=11, to_chapter=12)
        gate = threading.Barrier(2)

        def hook(stage, _context):
            if stage == "before_transaction":
                gate.wait(timeout=5)

        first, _ = self.orchestrator(lifecycle_hook=hook)
        second, _ = self.orchestrator(lifecycle_hook=hook)
        results = self._run_concurrently(
            (
                lambda: first.prepare(self.request(plan_a, client_request_id="overlap-a")),
                lambda: second.prepare(self.request(plan_b, client_request_id="overlap-b")),
            )
        )
        self.assertEqual(self.counts()["jobs"], 1)
        self.assertEqual(self.counts()["batch_prepare_job_links"], 1)
        self.assertEqual(sum(result["request_state"] == "APPLIED" for result in results), 1)
        self.assertEqual(sum(result["request_state"] == "REJECTED" for result in results), 1)

    def test_non_overlapping_requests_create_two_distinct_jobs(self) -> None:
        plan_a = self.plan(from_chapter=10, to_chapter=11)
        plan_b = self.plan(from_chapter=12, to_chapter=13)
        gate = threading.Barrier(2)

        def hook(stage, _context):
            if stage == "before_transaction":
                gate.wait(timeout=5)

        first, _ = self.orchestrator(lifecycle_hook=hook)
        second, _ = self.orchestrator(lifecycle_hook=hook)
        results = self._run_concurrently(
            (
                lambda: first.prepare(self.request(plan_a, client_request_id="non-overlap-a")),
                lambda: second.prepare(self.request(plan_b, client_request_id="non-overlap-b")),
            )
        )
        self.assertEqual(self.counts()["jobs"], 2)
        self.assertEqual(self.counts()["job_chapters"], 4)
        self.assertEqual(self.counts()["batch_prepare_job_links"], 2)
        self.assertTrue(all(result["request_state"] == "APPLIED" for result in results))

    def test_same_client_id_different_payload_has_one_binding_and_at_most_one_job(self) -> None:
        plan_a = self.plan(from_chapter=10, to_chapter=11)
        plan_b = self.plan(from_chapter=12, to_chapter=13)
        first, _ = self.orchestrator()
        second, _ = self.orchestrator()
        results = self._run_concurrently(
            (
                lambda: first.prepare(self.request(plan_a, client_request_id="same-client")),
                lambda: second.prepare(self.request(plan_b, client_request_id="same-client")),
            )
        )
        self.assertEqual(self.counts()["batch_prepare_requests"], 1)
        self.assertLessEqual(self.counts()["jobs"], 1)
        self.assertEqual(sum(result["status"] == "REQUEST_ID_CONFLICT" for result in results), 1)

    def test_concurrent_same_request_has_no_raw_sql_error_or_deadlock(self) -> None:
        plan = self.plan()
        request = self.request(plan, client_request_id="bounded-concurrency")
        orchestrators = [self.orchestrator()[0] for _ in range(4)]
        results = self._run_concurrently(tuple(lambda item=item: item.prepare(request) for item in orchestrators))
        self.assertEqual(len(results), 4)
        encoded = str(results).lower()
        self.assertNotIn("database is locked", encoded)
        self.assertNotIn("sqlite", encoded)
        self.assertEqual(self.counts()["jobs"], 1)

    def test_observer_between_request_cas_and_attempt_acquisition_stays_in_progress(self) -> None:
        plan = self.plan()
        request = self.request(plan, client_request_id="observer-window")
        first, adapter = self.orchestrator()
        observer, _ = self.orchestrator()
        entered = threading.Event()
        release = threading.Event()
        original = adapter.acquire

        def delayed_acquire(context):
            entered.set()
            self.assertTrue(release.wait(timeout=5))
            return original(context)

        adapter.acquire = delayed_acquire  # type: ignore[method-assign]
        result_holder = []
        worker = threading.Thread(target=lambda: result_holder.append(first.prepare(request)))
        worker.start()
        self.assertTrue(entered.wait(timeout=5))
        observed = observer.prepare(request)
        self.assertEqual(observed["request_state"], "APPLYING")
        self.assertEqual(observed["status"], "REQUEST_APPLYING")
        release.set()
        worker.join(timeout=10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result_holder[0]["request_state"], "APPLIED")
        self.assertEqual(self.counts()["jobs"], 1)

    def test_concurrent_committed_recovery_replays_terminal_winner(self) -> None:
        plan = self.plan()
        request = self.request(plan, client_request_id="terminal-race")
        initial, _ = self.orchestrator(request_store=_FailAppliedOnceStore(self.store))
        initial_result = initial.prepare(request)
        self.assertEqual(initial_result["request_state"], "APPLYING")
        first, first_adapter = self.orchestrator()
        second, second_adapter = self.orchestrator()
        entered = threading.Barrier(2)

        def synchronize(adapter):
            original = adapter.validate_applied_result

            def synchronized_validate(**kwargs):
                original(**kwargs)
                entered.wait(timeout=5)

            adapter.validate_applied_result = synchronized_validate  # type: ignore[method-assign]

        synchronize(first_adapter)
        synchronize(second_adapter)
        results = self._run_concurrently((lambda: first.prepare(request), lambda: second.prepare(request)))
        self.assertEqual(self.counts()["jobs"], 1)
        self.assertTrue(all(result["request_state"] == "APPLIED" for result in results))
        self.assertNotIn("PREPARE_FAILED", {result["status"] for result in results})

    def test_expired_observer_waits_for_committing_owner_and_recovers_same_job(self) -> None:
        plan = self.plan()
        request = self.request(plan, client_request_id="expired-commit-race")
        at_commit = threading.Event()
        release_commit = threading.Event()

        def transaction_hook(stage, _context):
            if stage == "before_commit":
                at_commit.set()
                self.assertTrue(release_commit.wait(timeout=5))

        owner, _ = self.orchestrator(lease_seconds=1, transaction_failure_injector=transaction_hook)
        observer, _ = self.orchestrator(recovery_busy_timeout_ms=1000)
        owner_results = []
        owner_thread = threading.Thread(target=lambda: owner_results.append(owner.prepare(request)))
        owner_thread.start()
        self.assertTrue(at_commit.wait(timeout=5))
        time.sleep(1.05)
        observer_results = []
        observer_thread = threading.Thread(target=lambda: observer_results.append(observer.prepare(request)))
        observer_thread.start()
        time.sleep(0.05)
        release_commit.set()
        owner_thread.join(timeout=10)
        observer_thread.join(timeout=10)
        self.assertFalse(owner_thread.is_alive())
        self.assertFalse(observer_thread.is_alive())
        self.assertEqual(self.counts()["jobs"], 1)
        self.assertEqual(self.store.get_request(owner_results[0]["request_id"]).state, "APPLIED")
        self.assertNotEqual(observer_results[0]["request_state"], "FAILED")

    def test_busy_writer_returns_bounded_nonterminal_response_without_sql_leak(self) -> None:
        plan = self.plan()
        request = self.request(plan, client_request_id="busy-writer")
        lock_connection = sqlite3.connect(self.db_path, timeout=1, check_same_thread=False)
        held = []

        def hook(stage, _context):
            if stage == "before_transaction" and not held:
                lock_connection.execute("BEGIN IMMEDIATE")
                held.append(True)

        service = BatchPrepareIsolatedTransactionService(self.database, busy_timeout_ms=20)
        orchestrator, _ = self.orchestrator(transaction_service=service, lifecycle_hook=hook)
        started = time.monotonic()
        try:
            result = orchestrator.prepare(request)
        finally:
            lock_connection.rollback()
            lock_connection.close()
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertEqual(result["request_state"], "APPLYING")
        self.assertEqual(result["status"], "REQUEST_APPLYING")
        self.assertEqual(self.counts()["jobs"], 0)
        self.assertNotIn("sqlite", str(result).lower())
        self.assertNotIn("database is locked", str(result).lower())


if __name__ == "__main__":
    unittest.main()
