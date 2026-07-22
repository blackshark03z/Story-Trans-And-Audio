from __future__ import annotations

import json
import unittest
from dataclasses import replace

from story_audio.batch_prepare_execution_attempt_store import BatchPrepareExecutionAttemptStore
from story_audio.batch_prepare_transaction_revalidator import (
    AuthoritativeInputRejected,
    BatchPrepareTransactionRevalidator,
    chapter_snapshot_digest,
)
from story_audio.db import utcnow
from tests.phase9_fixture import Phase9FixtureMixin


class BatchPrepareTransactionRevalidatorTests(Phase9FixtureMixin):
    def _validate(self, snapshot):
        validator = BatchPrepareTransactionRevalidator(BatchPrepareExecutionAttemptStore(self.database))
        with self.database.transaction() as connection:
            before = connection.total_changes
            result = validator.validate(connection, snapshot)
            self.assertEqual(connection.total_changes, before)
            return result

    def test_valid_snapshot_is_deterministic_and_read_only(self) -> None:
        _, snapshot = self.acquire_and_snapshot()
        first = self._validate(snapshot)
        second = self._validate(snapshot)
        self.assertEqual(first, second)
        self.assertEqual([item.chapter_number for item in first.chapters], [10, 11])
        self.assertEqual(len(first.validation_digest), 64)

    def test_request_owner_scope_and_snapshot_bindings_fail_closed(self) -> None:
        _, snapshot = self.acquire_and_snapshot()
        cases = [
            (replace(snapshot, request_id=9999), "REQUEST_NOT_FOUND"),
            (replace(snapshot, request_identity="c" * 64), "REQUEST_BINDING_CHANGED"),
            (replace(snapshot, target_phase="START_RENDER"), "UNSUPPORTED_PHASE"),
            (replace(snapshot, plan_fingerprint="d" * 64), "REQUEST_BINDING_CHANGED"),
            (replace(snapshot, owner_token="wrong"), None),
            (replace(snapshot, owner_generation=2), None),
            (replace(snapshot, transaction_reference="wrong"), None),
            (replace(snapshot, explicit_no_render=False), "UNSUPPORTED_PHASE"),
        ]
        for item, code in cases:
            with self.subTest(code=code), self.assertRaises(Exception) as raised:
                self._validate(item)
            if code:
                self.assertEqual(getattr(raised.exception, "code", None), code)

    def test_duplicate_order_digest_cross_scope_and_exact_set_are_rejected(self) -> None:
        _, snapshot = self.acquire_and_snapshot()
        duplicate = replace(snapshot, chapters=(snapshot.chapters[0], snapshot.chapters[0]))
        reordered_chapters = tuple(replace(item, deterministic_order=index) for index, item in enumerate(reversed(snapshot.chapters), start=1))
        reordered = replace(snapshot, chapters=reordered_chapters, chapter_snapshot_digest=chapter_snapshot_digest(reordered_chapters))
        cross = replace(snapshot.chapters[0], book_id=999)
        cross_chapters = (cross, snapshot.chapters[1])
        cases = [
            (duplicate, "DUPLICATE_CHAPTER"),
            (reordered, None),
            (replace(snapshot, chapter_snapshot_digest="e" * 64), None),
            (replace(snapshot, chapters=cross_chapters, chapter_snapshot_digest=chapter_snapshot_digest(cross_chapters)), None),
            (replace(snapshot, chapters=(snapshot.chapters[0],), chapter_snapshot_digest=chapter_snapshot_digest((snapshot.chapters[0],))), None),
        ]
        for item, code in cases:
            with self.subTest(code=code), self.assertRaises(Exception) as raised:
                self._validate(item)
            if code:
                self.assertEqual(getattr(raised.exception, "code", None), code)

    def test_stale_text_plan_approval_voice_and_eligibility_changes_are_rejected(self) -> None:
        mutations = {
            "stale-text": lambda c, f: c.execute(
                "UPDATE chapters SET active_text_revision_id=NULL WHERE id=?", (f["chapters"][0]["chapter_id"],)
            ),
            "plan-draft": lambda c, f: c.execute(
                "UPDATE casting_plans SET status='draft',approved_at=NULL WHERE id=?", (f["chapters"][0]["casting_plan_id"],)
            ),
            "plan-sha": lambda c, f: c.execute(
                "UPDATE casting_plans SET plan_sha256=? WHERE id=?", ("f" * 64, f["chapters"][0]["casting_plan_id"])
            ),
            "voice": lambda c, f: c.execute(
                "UPDATE casting_plans SET narrator_voice_id='custom:99' WHERE id=?", (f["chapters"][0]["casting_plan_id"],)
            ),
            "active-output": lambda c, f: c.execute(
                "UPDATE chapters SET active_audio_artifact_id=999 WHERE id=?", (f["chapters"][0]["chapter_id"],)
            ),
        }
        identities = iter("cdef1")
        for index, (label, mutate) in enumerate(mutations.items(), start=1):
            fixture = self.create_scope(
                client_request_id=f"stale-{label}", request_identity=next(identities) * 64,
                source_suffix=f"stale-{label}", chapter_numbers=(100 + index * 2, 101 + index * 2),
            )
            _, snapshot = self.acquire_and_snapshot(fixture)
            with self.database.transaction() as connection:
                mutate(connection, fixture)
            with self.subTest(label=label), self.assertRaises(AuthoritativeInputRejected):
                self._validate(snapshot)
            self.assertEqual(self.database.fetch_one(
                "SELECT COUNT(*) AS n FROM jobs WHERE book_id=?", (fixture["book_id"],)
            )["n"], 0)

    def test_invalid_pinned_json_and_changed_request_state_are_rejected(self) -> None:
        self.fixture["chapters"][0]["voice_snapshot_json"] = "not-json"
        _, bad = self.acquire_and_snapshot()
        with self.assertRaises(AuthoritativeInputRejected) as ctx:
            self._validate(bad)
        self.assertEqual(ctx.exception.code, "INVALID_PINNED_JSON")
        snapshot = bad
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE batch_prepare_requests SET state='FAILED',completed_at=?,updated_at=? WHERE id=?",
                (utcnow(), utcnow(), snapshot.request_id),
            )
        with self.assertRaises(AuthoritativeInputRejected) as ctx:
            self._validate(snapshot)
        self.assertEqual(ctx.exception.code, "REQUEST_BINDING_CHANGED")


if __name__ == "__main__":
    unittest.main()
