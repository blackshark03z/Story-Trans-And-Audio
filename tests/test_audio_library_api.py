from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from story_audio.db import utcnow
from story_audio.files import sha256_file
from tests.base import IsolatedTestCase
from tests.test_active_output import seed_active_output


class AudioLibraryApiTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        seeded = seed_active_output(self.temp_root)
        self.db = seeded["db"]
        self.chapter_id = seeded["chapter_one"]
        self.pending_chapter_id = seeded["chapter_two"]
        self.old_artifact_id = seeded["old_artifact_id"]
        self.new_artifact_id = seeded["new_artifact_id"]
        self._multipart_patcher = patch("fastapi.dependencies.utils.ensure_multipart_is_installed", lambda: None)
        self._multipart_patcher.start()
        import story_audio.api as api_module

        self._original_db = api_module.db
        self._original_settings = api_module.settings
        api_module.db = self.db
        api_module.settings = seeded["config"]
        from story_audio.api import app

        self.client = TestClient(app)

    def tearDown(self) -> None:
        import story_audio.api as api_module

        api_module.db = self._original_db
        api_module.settings = self._original_settings
        self._multipart_patcher.stop()
        super().tearDown()

    def _items(self) -> list[dict]:
        response = self.client.get("/api/audio-library")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], len(data["items"]))
        return data["items"]

    def test_active_pointer_wins_over_newest_completed_job(self) -> None:
        items = self._items()
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["chapter_id"], self.chapter_id)
        self.assertEqual(item["artifact_id"], self.old_artifact_id)
        self.assertNotEqual(item["artifact_id"], self.new_artifact_id)
        self.assertEqual(item["job_id"], 1)
        self.assertEqual(item["casting_plan_revision"], 4)

    def test_chapter_without_active_artifact_is_absent(self) -> None:
        chapter_ids = {item["chapter_id"] for item in self._items()}
        self.assertIn(self.chapter_id, chapter_ids)
        self.assertNotIn(self.pending_chapter_id, chapter_ids)

    def test_remove_current_audio_deletes_media_and_qa_but_preserves_inputs(self) -> None:
        artifact = self.db.fetch_one(
            "SELECT path,job_chapter_id,sha256 FROM artifacts WHERE id=?",
            (self.old_artifact_id,),
        )
        path = artifact["path"]
        self.db.audit(
            "human_qa_recorded",
            job_id=1,
            chapter_id=self.chapter_id,
            details={"artifact_id": self.old_artifact_id, "status": "approved"},
        )
        preview_response = self.client.post(
            "/api/audio-library/removal-preview",
            json={"artifact_ids": [self.old_artifact_id]},
        )
        self.assertEqual(preview_response.status_code, 200)
        preview = preview_response.json()
        self.assertEqual(preview["confirmation"], "XOA 1 AUDIO")

        response = self.client.post(
            "/api/audio-library/remove",
            json={
                "artifact_ids": [self.old_artifact_id],
                "fingerprint": preview["fingerprint"],
                "confirmation": preview["confirmation"],
                "idempotency_key": "audio-remove-test-001",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["removed_count"], 1)
        self.assertEqual(self._items(), [])
        chapter = self.db.fetch_one(
            "SELECT active_audio_artifact_id,audio_status FROM chapters WHERE id=?",
            (self.chapter_id,),
        )
        self.assertIsNone(chapter["active_audio_artifact_id"])
        self.assertEqual(chapter["audio_status"], "not_created")
        self.assertIsNone(self.db.fetch_one("SELECT id FROM artifacts WHERE id=?", (self.old_artifact_id,)))
        self.assertFalse(__import__("pathlib").Path(path).exists())
        self.assertIsNotNone(self.db.fetch_one("SELECT id FROM jobs WHERE id=1"))
        self.assertIsNone(
            self.db.fetch_one(
                "SELECT id FROM audit_events WHERE event_code='human_qa_recorded' AND chapter_id=?",
                (self.chapter_id,),
            )
        )

    def test_stale_removal_preview_fails_closed_without_partial_mutation(self) -> None:
        preview = self.client.post(
            "/api/audio-library/removal-preview",
            json={"artifact_ids": [self.old_artifact_id]},
        ).json()
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE chapters SET active_audio_artifact_id=? WHERE id=?",
                (self.new_artifact_id, self.chapter_id),
            )
        response = self.client.post(
            "/api/audio-library/remove",
            json={
                "artifact_ids": [self.old_artifact_id],
                "fingerprint": preview["fingerprint"],
                "confirmation": preview["confirmation"],
                "idempotency_key": "audio-remove-stale-001",
            },
        )
        self.assertEqual(response.status_code, 409)
        chapter = self.db.fetch_one(
            "SELECT active_audio_artifact_id,audio_status FROM chapters WHERE id=?",
            (self.chapter_id,),
        )
        self.assertEqual(chapter["active_audio_artifact_id"], self.new_artifact_id)
        self.assertEqual(chapter["audio_status"], "completed")

    def test_removal_preview_blocks_chapter_with_non_terminal_job(self) -> None:
        now = utcnow()
        chapter = self.db.fetch_one("SELECT book_id FROM chapters WHERE id=?", (self.chapter_id,))
        with self.db.transaction() as connection:
            connection.execute(
                """INSERT INTO jobs(book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                   settings_json,total_chapters,scheduled_at,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (chapter["book_id"], "prepared", 10, 10, "Voice", "off", "m4a", "{}", 1, now, now, now),
            )
            job_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
            connection.execute(
                "INSERT INTO job_chapters(job_id,chapter_id,sequence,status) VALUES(?,?,?,?)",
                (job_id, self.chapter_id, 1, "pending"),
            )
        response = self.client.post(
            "/api/audio-library/removal-preview",
            json={"artifact_ids": [self.old_artifact_id]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["code"], "ACTIVE_JOB_CONFLICT")
        self.assertEqual(self._items()[0]["artifact_id"], self.old_artifact_id)

    def test_repeated_removal_does_not_retain_history_or_delete_again(self) -> None:
        preview = self.client.post(
            "/api/audio-library/removal-preview",
            json={"artifact_ids": [self.old_artifact_id]},
        ).json()
        body = {
            "artifact_ids": [self.old_artifact_id],
            "fingerprint": preview["fingerprint"],
            "confirmation": preview["confirmation"],
            "idempotency_key": "audio-remove-replay-001",
        }
        first = self.client.post("/api/audio-library/remove", json=body)
        second = self.client.post("/api/audio-library/remove", json=body)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertFalse(first.json()["reused"])
        self.assertEqual(second.json()["detail"]["code"], "STALE_SCOPE")
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS count FROM audit_events WHERE event_code='audio_library_outputs_removed'")["count"]),
            0,
        )

    def test_batch_removal_applies_to_every_exact_previewed_artifact(self) -> None:
        now = utcnow()
        chapter = self.db.fetch_one(
            "SELECT book_id,active_text_revision_id FROM chapters WHERE id=?",
            (self.pending_chapter_id,),
        )
        second_path = self.temp_root / "data" / "output" / "job_bulk" / "chapter.m4a"
        second_path.parent.mkdir(parents=True, exist_ok=True)
        second_path.write_bytes(b"bulk-second")
        with self.db.transaction() as connection:
            job_id = int(connection.execute(
                """INSERT INTO jobs(book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                   settings_json,total_chapters,scheduled_at,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (chapter["book_id"], "completed", 11, 11, "Voice", "off", "m4a", "{}", 1, now, now, now),
            ).lastrowid)
            job_chapter_id = int(connection.execute(
                "INSERT INTO job_chapters(job_id,chapter_id,sequence,status,text_revision_id) VALUES(?,?,?,?,?)",
                (job_id, self.pending_chapter_id, 1, "completed", chapter["active_text_revision_id"]),
            ).lastrowid)
            second_id = int(connection.execute(
                """INSERT INTO artifacts(chapter_id,job_chapter_id,text_revision_id,artifact_type,path,sha256,
                   size_bytes,duration_ms,status,created_at,verified_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (self.pending_chapter_id, job_chapter_id, chapter["active_text_revision_id"], "chapter_m4a",
                 str(second_path), sha256_file(second_path), second_path.stat().st_size, 1000, "active", now, now),
            ).lastrowid)
            connection.execute(
                "UPDATE chapters SET active_audio_artifact_id=?,audio_status='completed' WHERE id=?",
                (second_id, self.pending_chapter_id),
            )
        artifact_ids = [self.old_artifact_id, second_id]
        preview = self.client.post(
            "/api/audio-library/removal-preview", json={"artifact_ids": artifact_ids}
        ).json()
        self.assertEqual(preview["count"], 2)
        response = self.client.post(
            "/api/audio-library/remove",
            json={
                "artifact_ids": artifact_ids,
                "fingerprint": preview["fingerprint"],
                "confirmation": preview["confirmation"],
                "idempotency_key": "audio-remove-batch-001",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["removed_count"], 2)
        self.assertEqual(self._items(), [])
        self.assertFalse(second_path.exists())

    def test_safe_file_url_does_not_expose_absolute_path(self) -> None:
        item = self._items()[0]
        self.assertEqual(item["file_url"], f"/api/artifacts/{self.old_artifact_id}/file")
        self.assertEqual(item["download_url"], item["file_url"])
        self.assertNotIn(":", item["file_url"])
        self.assertNotIn("\\", item["file_url"])
        self.assertNotIn("path", item)
        self.assertNotIn("output_path", item)

    def test_qa_state_uses_database_approval_semantics(self) -> None:
        item = self._items()[0]
        self.assertEqual(item["human_qa_status"], "pending")
        self.assertEqual(item["human_approval_status"], "pending")
        self.assertIsNone(item["human_approval_matches_active_artifact"])

        now = utcnow()
        stale_rejection = {
            "status": "needs_fixes",
            "recorded_at": now,
            "artifact_id": self.new_artifact_id,
            "job_id": 2,
        }
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE chapters SET human_approval_json=?, updated_at=? WHERE id=?",
                (json.dumps(stale_rejection), now, self.chapter_id),
            )
        item = self._items()[0]
        self.assertEqual(item["human_qa_status"], "pending")
        self.assertEqual(item["human_approval_status"], "pending")
        self.assertEqual(item["human_approval_label"], "Chưa chốt")
        self.assertIsNone(item["human_approval_matches_active_artifact"])

        approval = {
            "status": "approved",
            "recorded_at": now,
            "approved_at": now,
            "artifact_id": self.old_artifact_id,
            "job_id": 1,
            "output_path": "D:/not/exposed/chapter.m4a",
            "sha256": "sha",
            "duration_ms": 1000,
        }
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE chapters SET human_approval_json=?, updated_at=? WHERE id=?",
                (json.dumps(approval), now, self.chapter_id),
            )
        item = self._items()[0]
        self.assertEqual(item["human_qa_status"], "accepted")
        self.assertEqual(item["human_approval_status"], "approved")
        self.assertTrue(item["human_approval_matches_active_artifact"])
        self.assertNotIn("human_approval", item)

    def test_invalid_active_binding_does_not_fallback_to_historical_artifact(self) -> None:
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE chapters SET active_audio_artifact_id=? WHERE id=?",
                (999999, self.chapter_id),
            )
        self.assertEqual(self._items(), [])

    def test_artifact_configuration_uses_pinned_job_chapter_snapshot(self) -> None:
        snapshot = {
            "engine_version": "pinned-engine:v1",
            "tts_settings": {"tts_mode": "pinned-mode"},
            "character_labels": {"42": "Quần chúng nam"},
            "utterances": [
                {"sequence": 21, "utterance_id": "u0021", "role": "narrator", "resolved_voice_id": "custom:narrator", "resolution_source": "narrator"},
                {"sequence": 22, "utterance_id": "u0022", "role": "character", "character_id": 42, "resolved_voice_id": "custom:commander", "resolution_source": "character"},
            ],
        }
        with self.db.transaction() as connection:
            rendered_revision = connection.execute(
                "SELECT text_revision_id FROM artifacts WHERE id=?",
                (self.old_artifact_id,),
            ).fetchone()["text_revision_id"]
            raw_revision = int(
                connection.execute(
                    """INSERT INTO text_revisions(
                        chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                        processor_version,status,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (self.chapter_id, "raw", "text/raw.txt", "raw-sha", "lexical", 16, "test", "verified", utcnow()),
                ).lastrowid
            )
            connection.execute(
                "UPDATE text_revisions SET parent_revision_id=? WHERE id=?",
                (raw_revision, rendered_revision),
            )
            connection.execute(
                "UPDATE jobs SET settings_json=? WHERE id=1",
                (json.dumps({"engine_version": "mutable-engine", "tts_mode": "mutable-mode"}),),
            )
            connection.execute(
                "UPDATE job_chapters SET voice_snapshot_json=? WHERE id=(SELECT job_chapter_id FROM artifacts WHERE id=?)",
                (json.dumps(snapshot), self.old_artifact_id),
            )

        response = self.client.get(f"/api/artifacts/{self.old_artifact_id}/configuration")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["schema"], "story-audio-artifact-configuration/v1")
        self.assertTrue(data["artifact"]["active"])
        self.assertEqual(data["provider"], {"engine": "pinned-engine:v1", "mode": "pinned-mode"})
        self.assertEqual(data["casting_plan"], {"id": 1, "revision": 4})
        self.assertEqual([actor["voice_id"] for actor in data["actors"]], ["custom:narrator", "custom:commander"])
        self.assertEqual(data["actors"][1]["label"], "Quần chúng nam")
        self.assertEqual(data["actors"][1]["provenance"], "casting_plan_snapshot")
        self.assertEqual(data["actors"][0]["sequences"], [21])
        self.assertEqual(data["actors"][1]["sequences"], [22])
        self.assertEqual(data["utterances"][1]["utterance_id"], "u0022")
        self.assertEqual(data["utterances"][1]["voice_id"], "custom:commander")
        self.assertEqual(data["source_revision"]["parent_id"], raw_revision)
        self.assertEqual(data["source_revision"]["parent_kind"], "raw")
        self.assertEqual(data["synthesis"]["segment_count"], 0)

    def test_artifact_configuration_uses_artifact_specific_qa_history(self) -> None:
        self.db.audit(
            "human_qa_recorded",
            job_id=1,
            chapter_id=self.chapter_id,
            details={"artifact_id": self.old_artifact_id, "status": "needs_fixes"},
        )
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE chapters SET human_approval_json=? WHERE id=?",
                (
                    json.dumps({"artifact_id": self.new_artifact_id, "status": "approved"}),
                    self.chapter_id,
                ),
            )

        data = self.client.get(f"/api/artifacts/{self.old_artifact_id}/configuration").json()
        self.assertEqual(data["artifact"]["human_qa_status"], "needs_fixes")
        self.assertIsInstance(data["artifact"]["human_qa_event_id"], int)
        self.assertTrue(data["artifact"]["active"])

    def test_artifact_download_filename_identifies_book_chapter_and_artifact(self) -> None:
        response = self.client.get(f"/api/artifacts/{self.old_artifact_id}/file")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"old")
        self.assertIn(
            f"book-1-chapter-0010-artifact-{self.old_artifact_id}.m4a",
            response.headers["content-disposition"],
        )

    def test_unknown_artifact_configuration_returns_404(self) -> None:
        response = self.client.get("/api/artifacts/999999/configuration")
        self.assertEqual(response.status_code, 404)

    def test_items_are_ordered_by_book_title_then_chapter_number(self) -> None:
        now = utcnow()
        artifact_path = self.temp_root / "data" / "output" / "job_3" / "chapter_0011" / "chapter.m4a"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(b"pending-now-active")
        chapter = self.db.fetch_one(
            "SELECT book_id, active_text_revision_id FROM chapters WHERE id=?",
            (self.pending_chapter_id,),
        )
        with self.db.transaction() as connection:
            job_id = int(
                connection.execute(
                    """INSERT INTO jobs(
                        book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                        settings_json,total_chapters,scheduled_at,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (chapter["book_id"], "completed", 11, 11, "Voice C", "off", "m4a", "{}", 1, now, now, now),
                ).lastrowid
            )
            job_chapter_id = int(
                connection.execute(
                    "INSERT INTO job_chapters(job_id,chapter_id,sequence,status,text_revision_id) VALUES(?,?,?,?,?)",
                    (job_id, self.pending_chapter_id, 1, "completed", chapter["active_text_revision_id"]),
                ).lastrowid
            )
            artifact_id = int(
                connection.execute(
                    """INSERT INTO artifacts(
                        chapter_id,job_chapter_id,text_revision_id,artifact_type,path,sha256,size_bytes,
                        duration_ms,status,created_at,verified_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        self.pending_chapter_id,
                        job_chapter_id,
                        chapter["active_text_revision_id"],
                        "chapter_m4a",
                        str(artifact_path),
                        sha256_file(artifact_path),
                        artifact_path.stat().st_size,
                        2000,
                        "active",
                        now,
                        now,
                    ),
                ).lastrowid
            )
            connection.execute(
                "UPDATE chapters SET audio_status='completed', active_audio_artifact_id=? WHERE id=?",
                (artifact_id, self.pending_chapter_id),
            )
        items = self._items()
        self.assertEqual([item["chapter_number"] for item in items], [10, 11])

    def test_audio_history_and_restore_are_not_product_capabilities(self) -> None:
        self.assertEqual(
            self.client.get(f"/api/chapters/{self.chapter_id}/human-approval-history").status_code,
            404,
        )
        with patch(
            "story_audio.api._project_production_command",
            lambda _scope: ({"canonical_task": {"task_key": "audio:no-history"}}, None),
        ):
            response = self.client.post(
                "/api/production/commands",
                json={
                    "command_type": "RESTORE_ACCEPTED_ARTIFACT",
                    "idempotency_key": "restore-accepted-artifact-0001",
                    "scope": {"artifact": {"id": self.new_artifact_id}},
                    "payload": {
                        "chapter_id": self.chapter_id,
                        "artifact_id": self.new_artifact_id,
                        "expected_active_artifact_id": self.old_artifact_id,
                    },
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["outcome"], "REJECTED")
        self.assertEqual(self._items()[0]["artifact_id"], self.old_artifact_id)


if __name__ == "__main__":
    unittest.main()
