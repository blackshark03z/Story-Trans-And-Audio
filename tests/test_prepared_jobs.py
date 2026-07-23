from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from story_audio.casting import approve_plan, create_casting_draft
from story_audio.db import Database
from story_audio.files import sha256_text
from story_audio.pipeline import (
    JOB_PREPARED_STATUS,
    JobPreparationConflict,
    JobStartConflict,
    PipelineWorker,
    create_job,
    prepare_job,
    start_prepared_job,
)
from story_audio.storage import ContentStore
from story_audio.voice_eligibility import EffectiveVoiceCatalog
from story_audio.voice_profile import set_book_voice_profile
from tests.base import IsolatedTestCase


class PreparedJobLifecycleTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        self.voice_catalog = EffectiveVoiceCatalog.from_ids(
            "ngoc_lan", "duc_tri", "my_duyen"
        )

        with self.db.transaction() as conn:
            self.book_id = int(conn.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,datetime('now'),datetime('now'))",
                ("Prepared Job Book", "test://book", "b" * 64, 1),
            ).lastrowid)
            self.chapter_id = int(conn.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at) VALUES(?,?,?,?,datetime('now'),datetime('now'))",
                (self.book_id, 365, "Chapter 365", 128),
            ).lastrowid)

        text = "“A nói.” Người kể chuyện tiếp tục."
        content_path, content_sha = self.store.put_text(text)
        lexical_sha = sha256_text(text)
        with self.db.transaction() as conn:
            self.text_revision_id = int(conn.execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                    processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,datetime('now'))""",
                (self.chapter_id, "reflowed", content_path, content_sha, lexical_sha, len(text), "v1", "approved"),
            ).lastrowid)
            conn.execute(
                "UPDATE chapters SET active_text_revision_id=?,updated_at=datetime('now') WHERE id=?",
                (self.text_revision_id, self.chapter_id),
            )

        set_book_voice_profile(
            self.db,
            self.book_id,
            narrator_voice_id="ngoc_lan",
            male_dialogue_voice_id="duc_tri",
            female_dialogue_voice_id="my_duyen",
            unknown_fallback="narrator",
            unknown_voice_id=None,
            allowed_voice_ids={"ngoc_lan", "duc_tri", "my_duyen"},
        )
        draft = create_casting_draft(
            self.db,
            self.store,
            chapter_id=self.chapter_id,
            text_revision_id=self.text_revision_id,
            narrator_voice_id="ngoc_lan",
            assignments=[],
            allowed_voice_ids={"ngoc_lan", "duc_tri", "my_duyen"},
        )
        self.plan_id = int(draft["id"])
        approve_plan(self.db, self.store, self.plan_id)

    def _payload(self) -> dict[str, object]:
        return {
            "book_id": self.book_id,
            "from_chapter": 365,
            "to_chapter": 365,
            "voice_name": "ngoc_lan",
            "repair_mode": "off",
            "output_format": "m4a",
            "skip_completed": False,
            "casting_plan_id": self.plan_id,
            "voice_catalog": self.voice_catalog,
        }

    def test_prepare_creates_one_non_executable_job_and_one_job_chapter(self) -> None:
        result = prepare_job(self.db, self.config, store=self.store, **self._payload())
        self.assertEqual(result["status"], JOB_PREPARED_STATUS)
        job = self.db.fetch_one("SELECT * FROM jobs WHERE id=?", (result["job_id"],))
        chapter = self.db.fetch_one("SELECT * FROM job_chapters WHERE job_id=?", (result["job_id"],))
        self.assertEqual(job["status"], JOB_PREPARED_STATUS)
        self.assertEqual(job["casting_plan_id"], self.plan_id)
        self.assertEqual(chapter["chapter_id"], self.chapter_id)
        self.assertEqual(chapter["text_revision_id"], self.text_revision_id)
        self.assertEqual(chapter["casting_plan_id"], self.plan_id)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"], 1)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM job_chapters")["n"], 1)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM segments")["n"], 0)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM artifacts")["n"], 0)

    def test_worker_ignores_prepared_jobs_even_after_restart(self) -> None:
        result = prepare_job(self.db, self.config, store=self.store, **self._payload())
        worker = PipelineWorker(self.db, self.store, MagicMock(), self.config)
        self.assertIsNone(worker._next_job())
        self.db.initialize()
        self.assertEqual(
            self.db.fetch_one("SELECT status FROM jobs WHERE id=?", (result["job_id"],))["status"],
            JOB_PREPARED_STATUS,
        )
        self.assertIsNone(worker._next_job())

    def test_start_transitions_same_job_exactly_once(self) -> None:
        prepared = prepare_job(self.db, self.config, store=self.store, **self._payload())
        started = start_prepared_job(
            self.db,
            self.config,
            job_id=int(prepared["job_id"]),
            voice_catalog=self.voice_catalog,
        )
        self.assertEqual(started["job_id"], prepared["job_id"])
        self.assertEqual(started["status"], "scheduled")
        self.assertEqual(
            self.db.fetch_one("SELECT status FROM jobs WHERE id=?", (prepared["job_id"],))["status"],
            "scheduled",
        )
        with self.assertRaises(JobStartConflict):
            start_prepared_job(
                self.db,
                self.config,
                job_id=int(prepared["job_id"]),
                voice_catalog=self.voice_catalog,
            )

    def test_duplicate_prepare_fails_without_creating_second_job(self) -> None:
        prepare_job(self.db, self.config, store=self.store, **self._payload())
        with self.assertRaises(JobPreparationConflict):
            prepare_job(self.db, self.config, store=self.store, **self._payload())
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"], 1)

    def test_stale_plan_rejected_without_partial_job(self) -> None:
        text = "“A nói lần hai.” Người kể chuyện đổi revision."
        content_path, content_sha = self.store.put_text(text)
        lexical_sha = sha256_text(text)
        with self.db.transaction() as conn:
            new_revision_id = int(conn.execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                    processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,datetime('now'))""",
                (self.chapter_id, "reflowed", content_path, content_sha, lexical_sha, len(text), "v2", "approved"),
            ).lastrowid)
            conn.execute(
                "UPDATE chapters SET active_text_revision_id=?,updated_at=datetime('now') WHERE id=?",
                (new_revision_id, self.chapter_id),
            )
        with self.assertRaisesRegex(ValueError, "stale"):
            prepare_job(self.db, self.config, store=self.store, **self._payload())
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"], 0)

    def test_legacy_create_job_still_creates_one_executable_job(self) -> None:
        result = create_job(self.db, self.config, store=self.store, **self._payload())
        self.assertEqual(result["status"], "scheduled")
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"], 1)
        self.assertEqual(
            self.db.fetch_one("SELECT status FROM jobs WHERE id=?", (result["job_id"],))["status"],
            "scheduled",
        )


class PreparedJobApiTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)

        with self.db.transaction() as conn:
            self.book_id = int(conn.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,datetime('now'),datetime('now'))",
                ("Prepared API Book", "test://book", "c" * 64, 1),
            ).lastrowid)
            self.chapter_id = int(conn.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at) VALUES(?,?,?,?,datetime('now'),datetime('now'))",
                (self.book_id, 365, "Chapter 365", 128),
            ).lastrowid)

        text = "“Api test.” Người kể chuyện tiếp tục."
        content_path, content_sha = self.store.put_text(text)
        lexical_sha = sha256_text(text)
        with self.db.transaction() as conn:
            self.text_revision_id = int(conn.execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                    processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,datetime('now'))""",
                (self.chapter_id, "reflowed", content_path, content_sha, lexical_sha, len(text), "v1", "approved"),
            ).lastrowid)
            conn.execute(
                "UPDATE chapters SET active_text_revision_id=?,updated_at=datetime('now') WHERE id=?",
                (self.text_revision_id, self.chapter_id),
            )

        set_book_voice_profile(
            self.db,
            self.book_id,
            narrator_voice_id="ngoc_lan",
            male_dialogue_voice_id="duc_tri",
            female_dialogue_voice_id="my_duyen",
            unknown_fallback="narrator",
            unknown_voice_id=None,
            allowed_voice_ids={"ngoc_lan", "duc_tri", "my_duyen"},
        )
        draft = create_casting_draft(
            self.db,
            self.store,
            chapter_id=self.chapter_id,
            text_revision_id=self.text_revision_id,
            narrator_voice_id="ngoc_lan",
            assignments=[],
            allowed_voice_ids={"ngoc_lan", "duc_tri", "my_duyen"},
        )
        self.plan_id = int(draft["id"])
        approve_plan(self.db, self.store, self.plan_id)
        self.payload = {
            "book_id": self.book_id,
            "from_chapter": 365,
            "to_chapter": 365,
            "voice_name": "ngoc_lan",
            "repair_mode": "off",
            "output_format": "m4a",
            "skip_completed": False,
            "casting_plan_id": self.plan_id,
        }

        self._multipart_patcher = patch("fastapi.dependencies.utils.ensure_multipart_is_installed", lambda: None)
        self._multipart_patcher.start()
        import story_audio.api as api_module
        self.api_module = api_module
        self._original_db = api_module.db
        self._original_store = api_module.store
        self._original_settings = api_module.settings
        self._original_tts = api_module.tts_service
        self._original_custom_voice_repo = api_module.custom_voice_repo
        self._original_worker = api_module.worker
        api_module.db = self.db
        api_module.store = self.store
        api_module.settings = self.config
        api_module.tts_service = MagicMock()
        api_module.tts_service.voices.return_value = [
            {"id": "ngoc_lan", "label": "Ngoc Lan"},
            {"id": "duc_tri", "label": "Duc Tri"},
            {"id": "my_duyen", "label": "My Duyen"},
        ]
        api_module.custom_voice_repo = self.api_module.custom_voice_repo.__class__(
            self.db, self.store
        )
        api_module.worker = MagicMock()
        from story_audio.api import app
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.api_module.db = self._original_db
        self.api_module.store = self._original_store
        self.api_module.settings = self._original_settings
        self.api_module.tts_service = self._original_tts
        self.api_module.custom_voice_repo = self._original_custom_voice_repo
        self.api_module.worker = self._original_worker
        self._multipart_patcher.stop()
        super().tearDown()

    def test_prepare_route_does_not_wake_worker(self) -> None:
        response = self.client.post("/api/jobs/prepare", json=self.payload)
        self.assertEqual(response.status_code, 200)
        job_id = response.json()["job_id"]
        self.assertEqual(
            self.db.fetch_one("SELECT status FROM jobs WHERE id=?", (job_id,))["status"],
            JOB_PREPARED_STATUS,
        )
        self.api_module.worker.wake.assert_not_called()

    def test_start_route_wakes_once_and_legacy_route_reuses_one_job(self) -> None:
        prepared = self.client.post("/api/jobs/prepare", json=self.payload)
        self.assertEqual(prepared.status_code, 200)
        job_id = prepared.json()["job_id"]
        self.api_module.worker.wake.reset_mock()

        started = self.client.post(f"/api/jobs/{job_id}/start", json={})
        self.assertEqual(started.status_code, 200)
        self.api_module.worker.wake.assert_called_once()

    def test_legacy_submit_route_creates_one_job_and_wakes_once(self) -> None:
        response = self.client.post("/api/jobs", json=self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"], 1)
        self.assertEqual(
            self.db.fetch_one("SELECT status FROM jobs WHERE id=?", (response.json()["job_id"],))["status"],
            "scheduled",
        )
        self.api_module.worker.wake.assert_called_once()

    def test_prepare_rejects_unavailable_voice_without_partial_job(self) -> None:
        payload = dict(self.payload)
        payload["voice_name"] = "voice_missing"
        response = self.client.post("/api/jobs/prepare", json=payload)
        self.assertEqual(response.status_code, 409)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "VOICE_ELIGIBILITY_BLOCKED")
        self.assertTrue(detail["issues"][0]["replacement_required"])
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"], 0)
        self.api_module.worker.wake.assert_not_called()

    def test_start_rechecks_pinned_voice_and_does_not_schedule_on_failure(self) -> None:
        prepared = self.client.post("/api/jobs/prepare", json=self.payload)
        self.assertEqual(prepared.status_code, 200)
        job_id = int(prepared.json()["job_id"])
        self.api_module.worker.wake.reset_mock()
        self.api_module.tts_service.voices.return_value = [
            {"id": "my_duyen", "label": "My Duyen"},
        ]

        response = self.client.post(f"/api/jobs/{job_id}/start", json={})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            self.db.fetch_one("SELECT status FROM jobs WHERE id=?", (job_id,))["status"],
            JOB_PREPARED_STATUS,
        )
        self.api_module.worker.wake.assert_not_called()

    def test_catalog_failure_fails_closed_before_prepare(self) -> None:
        self.api_module.tts_service.voices.side_effect = RuntimeError("catalog offline")

        response = self.client.post("/api/jobs/prepare", json=self.payload)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "VOICE_CATALOG_UNAVAILABLE")
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"], 0)
        self.api_module.worker.wake.assert_not_called()
