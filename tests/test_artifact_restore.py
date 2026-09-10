from __future__ import annotations

import json

from story_audio.artifact_restore import (
    AcceptedArtifactRestoreError,
    inspect_accepted_artifact_restore,
    restore_accepted_artifact,
)
from story_audio.db import utcnow
from tests.base import IsolatedTestCase
from tests.test_active_output import seed_active_output


class AcceptedArtifactRestoreTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        seeded = seed_active_output(self.temp_root)
        self.db = seeded["db"]
        self.chapter_id = seeded["chapter_one"]
        self.active_artifact_id = seeded["old_artifact_id"]
        self.accepted_artifact_id = seeded["new_artifact_id"]
        target = self.db.fetch_one(
            "SELECT a.*,jc.job_id FROM artifacts a JOIN job_chapters jc ON jc.id=a.job_chapter_id WHERE a.id=?",
            (self.accepted_artifact_id,),
        )
        self.approval = {
            "status": "approved",
            "notes": "Bản đọc đã duyệt trước đó.",
            "artifact_id": self.accepted_artifact_id,
            "job_id": int(target["job_id"]),
            "sha256": target["sha256"],
            "duration_ms": int(target["duration_ms"]),
            "qa_feedback": {},
        }
        self.db.audit(
            "human_qa_recorded",
            job_id=int(target["job_id"]),
            chapter_id=self.chapter_id,
            details=self.approval,
        )

    def test_restore_switches_only_active_pointer_and_preserves_both_artifacts(self) -> None:
        result = restore_accepted_artifact(
            self.db,
            chapter_id=self.chapter_id,
            artifact_id=self.accepted_artifact_id,
            expected_active_artifact_id=self.active_artifact_id,
        )

        self.assertFalse(result["idempotent_reused"])
        self.assertEqual(result["previous_artifact_id"], self.active_artifact_id)
        chapter = self.db.fetch_one(
            "SELECT active_audio_artifact_id,audio_status,human_approval_json FROM chapters WHERE id=?",
            (self.chapter_id,),
        )
        self.assertEqual(chapter["active_audio_artifact_id"], self.accepted_artifact_id)
        self.assertEqual(chapter["audio_status"], "completed")
        self.assertEqual(
            json.loads(chapter["human_approval_json"])["artifact_id"],
            self.accepted_artifact_id,
        )
        statuses = {
            int(row["id"]): row["status"]
            for row in self.db.fetch_all(
                "SELECT id,status FROM artifacts WHERE id IN (?,?)",
                (self.active_artifact_id, self.accepted_artifact_id),
            )
        }
        self.assertEqual(statuses[self.active_artifact_id], "stale")
        self.assertEqual(statuses[self.accepted_artifact_id], "active")
        self.assertTrue(
            self.db.fetch_one(
                "SELECT 1 FROM audit_events WHERE chapter_id=? AND event_code='accepted_audio_artifact_restored'",
                (self.chapter_id,),
            )
        )

    def test_restore_is_idempotent_for_the_same_completed_transition(self) -> None:
        restore_accepted_artifact(
            self.db,
            chapter_id=self.chapter_id,
            artifact_id=self.accepted_artifact_id,
            expected_active_artifact_id=self.active_artifact_id,
        )
        result = restore_accepted_artifact(
            self.db,
            chapter_id=self.chapter_id,
            artifact_id=self.accepted_artifact_id,
            expected_active_artifact_id=self.active_artifact_id,
        )
        self.assertTrue(result["idempotent_reused"])

    def test_restore_rejects_stale_active_pointer_without_mutation(self) -> None:
        with self.assertRaises(AcceptedArtifactRestoreError) as caught:
            restore_accepted_artifact(
                self.db,
                chapter_id=self.chapter_id,
                artifact_id=self.accepted_artifact_id,
                expected_active_artifact_id=999999,
            )
        self.assertEqual(caught.exception.code, "ACTIVE_ARTIFACT_CHANGED")
        chapter = self.db.fetch_one(
            "SELECT active_audio_artifact_id FROM chapters WHERE id=?",
            (self.chapter_id,),
        )
        self.assertEqual(chapter["active_audio_artifact_id"], self.active_artifact_id)

    def test_restore_rejects_missing_or_mismatched_approval_evidence(self) -> None:
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE audit_events SET details_json=? WHERE chapter_id=? AND event_code='human_qa_recorded'",
                (json.dumps({**self.approval, "sha256": "0" * 64}), self.chapter_id),
            )
        eligibility = inspect_accepted_artifact_restore(
            self.db,
            chapter_id=self.chapter_id,
            artifact_id=self.accepted_artifact_id,
        )
        self.assertFalse(eligibility["eligible"])
        self.assertEqual(eligibility["code"], "APPROVAL_EVIDENCE_MISMATCH")
        with self.assertRaises(AcceptedArtifactRestoreError):
            restore_accepted_artifact(
                self.db,
                chapter_id=self.chapter_id,
                artifact_id=self.accepted_artifact_id,
                expected_active_artifact_id=self.active_artifact_id,
            )

    def test_restore_rejects_changed_file_and_running_render(self) -> None:
        target = self.db.fetch_one("SELECT path FROM artifacts WHERE id=?", (self.accepted_artifact_id,))
        with open(target["path"], "ab") as handle:
            handle.write(b"changed")
        with self.assertRaises(AcceptedArtifactRestoreError) as caught:
            restore_accepted_artifact(
                self.db,
                chapter_id=self.chapter_id,
                artifact_id=self.accepted_artifact_id,
                expected_active_artifact_id=self.active_artifact_id,
            )
        self.assertEqual(caught.exception.code, "ARTIFACT_FILE_CHANGED")

        with open(target["path"], "wb") as handle:
            handle.write(b"new")
        with self.db.transaction() as connection:
            connection.execute("UPDATE jobs SET status='running',updated_at=? WHERE id=2", (utcnow(),))
        with self.assertRaises(AcceptedArtifactRestoreError) as caught:
            restore_accepted_artifact(
                self.db,
                chapter_id=self.chapter_id,
                artifact_id=self.accepted_artifact_id,
                expected_active_artifact_id=self.active_artifact_id,
            )
        self.assertEqual(caught.exception.code, "CHAPTER_RENDER_ACTIVE")


if __name__ == "__main__":
    import unittest

    unittest.main()
