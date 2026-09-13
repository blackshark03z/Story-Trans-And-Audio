from __future__ import annotations

import json
from pathlib import Path

from story_audio.audio_retention import AudioRetentionError, purge_audio_history
from story_audio.db import utcnow
from tests.base import IsolatedTestCase
from tests.test_active_output import seed_active_output


class AudioRetentionTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        seeded = seed_active_output(self.temp_root)
        self.config = seeded["config"]
        self.db = seeded["db"]
        self.chapter_id = seeded["chapter_one"]
        self.old_artifact_id = seeded["old_artifact_id"]
        self.new_artifact_id = seeded["new_artifact_id"]
        self.old_job_chapter = seeded["old_job_chapter"]
        self.new_job_chapter = seeded["new_job_chapter"]

    def _purge(self, chapter_ids=None):
        return purge_audio_history(
            self.db,
            output_root=self.config.output_dir,
            work_root=self.config.work_dir,
            chapter_ids=chapter_ids,
        )

    def test_full_reconciliation_keeps_only_current_audio_and_preserves_inputs(self) -> None:
        new_path = self.db.fetch_one(
            "SELECT path FROM artifacts WHERE id=?", (self.new_artifact_id,)
        )["path"]
        before = {
            table: int(self.db.fetch_one(f"SELECT COUNT(*) AS count FROM {table}")["count"])
            for table in ("jobs", "text_revisions", "casting_plans")
        }
        self.db.audit(
            "audio_library_outputs_removed",
            chapter_id=self.chapter_id,
            details={"result": {"artifact_ids": [999]}},
        )

        result = self._purge()

        self.assertEqual(result["deleted_artifact_ids"], [self.new_artifact_id])
        self.assertIsNone(
            self.db.fetch_one("SELECT id FROM artifacts WHERE id=?", (self.new_artifact_id,))
        )
        self.assertIsNotNone(
            self.db.fetch_one("SELECT id FROM artifacts WHERE id=?", (self.old_artifact_id,))
        )
        self.assertFalse(self.config.output_dir.joinpath("job_2", "chapter_0010", "chapter.m4a").exists())
        self.assertFalse(Path(new_path).exists())
        for table, count in before.items():
            self.assertEqual(
                int(self.db.fetch_one(f"SELECT COUNT(*) AS count FROM {table}")["count"]),
                count,
            )
        self.assertEqual(result["deleted_operation_events"], 1)

    def test_replacement_removes_old_bundle_qa_and_segment_file(self) -> None:
        now = utcnow()
        old_segment = self.config.work_dir / "job_1" / "chapter_0010" / "segment_0001.wav"
        new_segment = self.config.work_dir / "job_2" / "chapter_0010" / "segment_0001.wav"
        old_segment.parent.mkdir(parents=True, exist_ok=True)
        new_segment.parent.mkdir(parents=True, exist_ok=True)
        old_segment.write_bytes(b"old-segment")
        new_segment.write_bytes(b"new-segment")
        approval = json.dumps({"artifact_id": self.old_artifact_id, "status": "approved"})
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE chapters SET active_audio_artifact_id=?,human_approval_json=? WHERE id=?",
                (self.new_artifact_id, approval, self.chapter_id),
            )
            for job_chapter_id, wav_path in (
                (self.old_job_chapter, old_segment),
                (self.new_job_chapter, new_segment),
            ):
                connection.execute(
                    """INSERT INTO segments(
                        job_chapter_id,segment_index,text_path,text_sha256,status,wav_path,created_at
                    ) VALUES(?,?,?,?,?,?,?)""",
                    (job_chapter_id, 0, "segment.txt", "text-sha", "completed", str(wav_path), now),
                )
        self.db.audit(
            "human_qa_recorded",
            chapter_id=self.chapter_id,
            details={"artifact_id": self.old_artifact_id, "status": "approved"},
        )

        result = self._purge([self.chapter_id])

        self.assertEqual(result["deleted_artifact_ids"], [self.old_artifact_id])
        self.assertFalse(old_segment.exists())
        self.assertTrue(new_segment.exists())
        self.assertIsNone(
            self.db.fetch_one("SELECT wav_path FROM segments WHERE job_chapter_id=?", (self.old_job_chapter,))["wav_path"]
        )
        self.assertEqual(
            self.db.fetch_one("SELECT wav_path FROM segments WHERE job_chapter_id=?", (self.new_job_chapter,))["wav_path"],
            str(new_segment),
        )
        chapter = self.db.fetch_one(
            "SELECT active_audio_artifact_id,human_approval_json FROM chapters WHERE id=?",
            (self.chapter_id,),
        )
        self.assertEqual(int(chapter["active_audio_artifact_id"]), self.new_artifact_id)
        self.assertIsNone(chapter["human_approval_json"])
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS count FROM audit_events WHERE event_code='human_qa_recorded'")["count"]),
            0,
        )

    def test_unsafe_path_aborts_before_database_mutation(self) -> None:
        outside = self.temp_root / "outside-history.m4a"
        outside.write_bytes(b"outside")
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE artifacts SET path=? WHERE id=?",
                (str(outside), self.new_artifact_id),
            )

        with self.assertRaises(AudioRetentionError):
            self._purge([self.chapter_id])

        self.assertTrue(outside.exists())
        self.assertIsNotNone(
            self.db.fetch_one("SELECT id FROM artifacts WHERE id=?", (self.new_artifact_id,))
        )

    def test_empty_explicit_scope_is_a_noop_not_a_full_purge(self) -> None:
        result = self._purge([])

        self.assertEqual(result["deleted_artifacts"], 0)
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS count FROM artifacts")["count"]),
            2,
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
