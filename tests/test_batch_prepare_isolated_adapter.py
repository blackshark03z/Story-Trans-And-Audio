from __future__ import annotations

import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from story_audio.batch_prepare_isolated_adapter import (
    BatchPrepareIsolatedAdapter,
    DurablePrepareEvidence,
    IsolatedAdapterError,
    assert_phase10_temporary_database,
    authorization_flags,
)
from story_audio.batch_prepare_orchestrator import STATUS_ACCEPTED, STATUS_CONFLICT, STATUS_FAILED, STATUS_REJECTED
from story_audio.files import sha256_text
from story_audio.text import split_tts_segments
from tests.batch_prepare_phase10_fixture import Phase10FixtureMixin


class CountingPlanProvider:
    def __init__(self, provider):
        self.provider = provider
        self.calls = 0

    def __call__(self, **kwargs):
        self.calls += 1
        return self.provider(**kwargs)


class SequencePlanProvider:
    def __init__(self, *plans):
        self.plans = list(plans)
        self.calls = 0

    def __call__(self, **_kwargs):
        self.calls += 1
        if len(self.plans) > 1:
            return self.plans.pop(0)
        return self.plans[0]


class BatchPrepareIsolatedAdapterTests(Phase10FixtureMixin):
    def test_happy_path_creates_one_atomic_prepared_job_and_applied_result(self) -> None:
        plan = self.plan()
        orchestrator, _adapter = self.orchestrator()
        result = orchestrator.prepare(self.request(plan))
        self.assertEqual(result["status"], STATUS_ACCEPTED)
        self.assertEqual(result["request_state"], "APPLIED")
        payload = result["result"]
        self.assertTrue(payload["transaction_committed"])
        self.assertTrue(payload["durable_linkage_verified"])
        self.assertEqual(payload["prepared_status"], "prepared")
        self.assertEqual(payload["chapter_count"], 2)
        self.assertFalse(payload["worker_woken"])
        self.assertFalse(payload["render_started"])
        self.assertFalse(payload["real_job_execution"])
        self.assertFalse(payload["mutation_authorized"])
        self.assertFalse(payload["execution_endpoint_available"])
        counts = self.counts()
        self.assertEqual(counts["batch_prepare_requests"], 1)
        self.assertEqual(counts["batch_prepare_execution_attempts"], 1)
        self.assertEqual(counts["batch_prepare_job_links"], 1)
        self.assertEqual(counts["jobs"], 1)
        self.assertEqual(counts["job_chapters"], 2)
        self.assertEqual(counts["segments"], 0)
        self.assertEqual(counts["artifacts"], 0)
        record = self.store.get_request(result["request_id"])
        self.assertIsNotNone(record)
        self.assertEqual(record.state, "APPLIED")
        self.assertEqual(record.job_id, payload["job_id"])

    def test_prepared_pins_are_render_compatible_without_segment_or_provider_work(self) -> None:
        plan = self.plan()
        orchestrator, _adapter = self.orchestrator()
        result = orchestrator.prepare(self.request(plan))
        with self.database.connect() as connection:
            job = connection.execute("SELECT * FROM jobs WHERE id=?", (result["result"]["job_id"],)).fetchone()
            chapters = connection.execute(
                """SELECT jc.*,tr.content_path FROM job_chapters jc
                   JOIN text_revisions tr ON tr.id=jc.text_revision_id
                   WHERE jc.job_id=? ORDER BY jc.sequence""",
                (result["result"]["job_id"],),
            ).fetchall()
        settings = json.loads(job["settings_json"])
        self.assertGreater(int(settings["max_chars"]), 0)
        self.assertGreater(int(settings["target_chars"]), 0)
        planned_chunks = []
        for chapter in chapters:
            snapshot = json.loads(chapter["voice_snapshot_json"])
            self.assertEqual(snapshot["tts_settings"], settings)
            text = self.content_store.read_text(chapter["content_path"])
            for utterance in snapshot["utterances"]:
                utterance_text = text[int(utterance["start_offset"]):int(utterance["end_offset"])]
                self.assertEqual(sha256_text(utterance_text), utterance["text_sha256"])
                planned_chunks.extend(
                    split_tts_segments(
                        utterance_text,
                        maximum=int(settings["max_chars"]),
                        target=int(settings["target_chars"]),
                    )
                )
        self.assertTrue(planned_chunks)
        self.assertEqual(self.counts()["segments"], 0)
        self.assertEqual(self.counts()["artifacts"], 0)

    def test_large_committed_evidence_uses_compact_bounded_references(self) -> None:
        count = 100
        evidence = DurablePrepareEvidence(
            request_id=1,
            request_identity="a" * 64,
            job_id=99,
            job_chapter_ids=tuple(range(1000, 1000 + count)),
            chapter_ids=tuple(range(2000, 2000 + count)),
            chapter_numbers=tuple(range(1, count + 1)),
            linkage_id=7,
            execution_generation=1,
            plan_fingerprint="b" * 64,
            chapter_snapshot_digest="c" * 64,
            transaction_committed_at="2026-07-22T00:00:00+00:00",
        )
        result = BatchPrepareIsolatedAdapter._success_result(
            evidence,
            recovery_source="transaction_commit",
            replay=False,
        )
        self.assertEqual(result.chapter_results, ())
        self.assertEqual(len(result.durable_fields["chapter_job_chapter_refs"]), count)
        self.assertLess(len(json.dumps(result.durable_fields).encode("utf-8")), 16 * 1024)

    def test_temporary_root_requires_explicit_marker_and_containment(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            root = Path(other).resolve()
            with self.assertRaises(IsolatedAdapterError):
                assert_phase10_temporary_database(root / "fixture.db", root)
            (root / ".story-audio-phase10-temporary").write_text("PHASE10_TEMPORARY_ONLY", encoding="utf-8")
            with self.assertRaises(IsolatedAdapterError):
                assert_phase10_temporary_database(self.db_path, root)

    def test_applied_replay_precedes_changed_current_plan(self) -> None:
        provider = CountingPlanProvider(self.plan_provider)
        plan = self.plan()
        orchestrator, _adapter = self.orchestrator(current_plan_provider=provider)
        first = orchestrator.prepare(self.request(plan))
        calls_after_first = provider.calls
        with self.database.transaction() as connection:
            connection.execute("UPDATE chapters SET audio_status='complete' WHERE chapter_number=10")
        replay = orchestrator.prepare(self.request(plan))
        self.assertEqual(replay["status"], "APPLIED_REPLAYED")
        self.assertTrue(replay["replay"])
        self.assertEqual(provider.calls, calls_after_first)
        self.assertEqual(replay["result"], first["result"])
        self.assertEqual(self.counts()["jobs"], 1)

    def test_same_client_id_different_payload_conflicts_before_plan_read(self) -> None:
        plan = self.plan()
        orchestrator, _adapter = self.orchestrator()
        orchestrator.prepare(self.request(plan))
        provider = CountingPlanProvider(self.plan_provider)
        other_plan = self.plan(from_chapter=12, to_chapter=13)
        conflict_orchestrator, _ = self.orchestrator(current_plan_provider=provider)
        conflict = conflict_orchestrator.prepare(self.request(other_plan))
        self.assertEqual(conflict["status"], STATUS_CONFLICT)
        self.assertEqual(provider.calls, 0)
        self.assertEqual(self.counts()["jobs"], 1)

    def test_second_fingerprint_validation_cancels_owner_and_creates_no_job(self) -> None:
        first = self.plan()
        changed = copy.deepcopy(first)
        changed["plan_fingerprint"] = "0" * 64
        provider = SequencePlanProvider(first, changed)
        orchestrator, _adapter = self.orchestrator(current_plan_provider=provider)
        result = orchestrator.prepare(self.request(first))
        self.assertEqual(result["status"], STATUS_REJECTED)
        self.assertEqual(result["error_code"], "STALE_PLAN")
        self.assertEqual(self.counts()["jobs"], 0)
        with self.database.connect() as connection:
            attempt = connection.execute("SELECT state FROM batch_prepare_execution_attempts").fetchone()
        self.assertEqual(attempt["state"], "ROLLBACK_CONFIRMED")

    def test_authoritative_revision_change_before_transaction_rolls_back(self) -> None:
        plan = self.plan()

        def hook(stage, _context):
            if stage == "before_transaction":
                with self.database.transaction() as connection:
                    chapter = connection.execute("SELECT id FROM chapters WHERE chapter_number=10").fetchone()
                    connection.execute("UPDATE chapters SET active_text_revision_id=NULL WHERE id=?", (chapter["id"],))

        orchestrator, _adapter = self.orchestrator(lifecycle_hook=hook)
        result = orchestrator.prepare(self.request(plan))
        self.assertEqual(result["status"], STATUS_REJECTED)
        self.assertEqual(self.counts()["jobs"], 0)
        self.assertEqual(self.counts()["job_chapters"], 0)
        self.assertEqual(self.counts()["batch_prepare_job_links"], 0)

    def test_missing_confirmation_is_invalid_without_persistence(self) -> None:
        plan = self.plan()
        request = self.request(plan)
        request["explicit_confirmation"] = False
        orchestrator, _adapter = self.orchestrator()
        result = orchestrator.prepare(request)
        self.assertEqual(result["status"], "INVALID_REQUEST")
        self.assertEqual(self.counts()["batch_prepare_requests"], 0)
        self.assertEqual(self.counts()["jobs"], 0)

    def test_unsupported_phase_is_invalid_without_persistence(self) -> None:
        plan = self.plan()
        request = self.request(plan)
        request["target_phase"] = "START_RENDER"
        orchestrator, _adapter = self.orchestrator()
        result = orchestrator.prepare(request)
        self.assertEqual(result["status"], "INVALID_REQUEST")
        self.assertEqual(self.counts()["batch_prepare_requests"], 0)

    def test_no_eligible_chapters_is_durable_rejection(self) -> None:
        with self.database.transaction() as connection:
            connection.execute("UPDATE casting_plans SET status='draft',approved_at=NULL")
        plan = self.plan()
        orchestrator, _adapter = self.orchestrator()
        result = orchestrator.prepare(self.request(plan))
        self.assertEqual(result["status"], STATUS_REJECTED)
        self.assertEqual(result["error_code"], "NO_ELIGIBLE_CHAPTERS")
        self.assertEqual(self.counts()["jobs"], 0)
        replay = orchestrator.prepare(self.request(plan))
        self.assertEqual(replay["status"], "REJECTED_REPLAYED")

    def test_public_result_contains_no_token_path_text_or_plan_blob(self) -> None:
        plan = self.plan()
        orchestrator, _adapter = self.orchestrator()
        result = orchestrator.prepare(self.request(plan))
        encoded = json.dumps(result, sort_keys=True)
        self.assertNotIn(str(self.db_path), encoded)
        self.assertNotIn("owner_token", encoded)
        self.assertNotIn("owner_token_hash", encoded)
        self.assertNotIn("voice_snapshot_json", encoded)
        self.assertNotIn("casting_snapshot_json", encoded)
        self.assertLess(len(encoded), 16 * 1024)

    def test_internal_exception_never_leaks_secret_path_text_or_sql(self) -> None:
        plan = self.plan()

        def hook(stage, _context):
            if stage == "before_transaction":
                raise RuntimeError(
                    f"owner_token=raw-secret SELECT private text from {self.db_path}"
                )

        orchestrator, _adapter = self.orchestrator(lifecycle_hook=hook)
        result = orchestrator.prepare(self.request(plan))
        encoded = json.dumps(result, sort_keys=True)
        self.assertNotIn("raw-secret", encoded)
        self.assertNotIn(str(self.db_path), encoded)
        self.assertNotIn("private text", encoded)
        self.assertNotIn("SELECT", encoded)

    def test_raw_owner_token_is_not_stored(self) -> None:
        captured = []
        plan = self.plan()
        orchestrator, adapter = self.orchestrator()
        original = adapter.acquire

        def acquire(context):
            lease = original(context)
            captured.append(lease.owner_token)
            return lease

        adapter.acquire = acquire  # type: ignore[method-assign]
        orchestrator.prepare(self.request(plan))
        with self.database.connect() as connection:
            row = connection.execute("SELECT owner_token_hash FROM batch_prepare_execution_attempts").fetchone()
        self.assertNotEqual(row["owner_token_hash"], captured[0])
        self.assertEqual(len(row["owner_token_hash"]), 64)

    def test_authorization_flags_remain_false_for_runtime_execution(self) -> None:
        flags = authorization_flags()
        self.assertTrue(flags["isolated_only"])
        self.assertTrue(flags["temporary_database_only"])
        for key in (
            "runtime_wiring", "canonical_activation", "production_prepare", "api_route",
            "ui_control", "worker_wake", "start_render", "provider_or_tts",
        ):
            self.assertFalse(flags[key])

    def test_applied_payload_mismatch_is_rejected_before_terminal_persistence(self) -> None:
        plan = self.plan()
        orchestrator, adapter = self.orchestrator()
        original = adapter.prepare

        def tampered(context):
            result = original(context)
            return replace(result, job_id=int(result.job_id or 0) + 999)

        adapter.prepare = tampered  # type: ignore[method-assign]
        response = orchestrator.prepare(self.request(plan))
        self.assertEqual(response["status"], STATUS_FAILED)
        record = self.store.get_request(response["request_id"])
        self.assertEqual(record.state, "APPLYING")
        self.assertEqual(self.counts()["jobs"], 1)
        self.assertEqual(self.counts()["batch_prepare_job_links"], 1)

    def test_runtime_modules_do_not_import_isolated_adapter(self) -> None:
        for path in (Path("story_audio/api.py"), Path("story_audio/pipeline.py"), Path("story_audio/db.py")):
            self.assertNotIn("batch_prepare_isolated_adapter", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
