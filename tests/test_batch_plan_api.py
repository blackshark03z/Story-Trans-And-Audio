from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from story_audio.batch_plan import build_batch_plan
from story_audio.db import Database, utcnow
from story_audio.files import sha256_file, sha256_text
from story_audio.storage import ContentStore
from tests.base import IsolatedTestCase


class BatchPlanHelperTests(unittest.TestCase):
    def _readiness(self, state: str, **overrides):
        item = {
            "chapter_id": 1,
            "chapter_number": 10,
            "chapter_title": "Chapter 10",
            "state": state,
            "next_action": "PREPARE",
            "blockers": [],
            "active_text_revision_id": 100,
            "latest_casting_plan_id": 200,
            "latest_casting_plan_revision": 1,
            "latest_casting_plan_status": "approved",
            "active_artifact_id": None,
            "active_output_job_id": None,
            "active_output_job_chapter_id": None,
            "live_job_id": None,
            "live_job_status": None,
            "human_qa_status": "pending",
        }
        item.update(overrides)
        return {
            "scope": {
                "book_id": 1,
                "book_title": "Book",
                "from_chapter": 10,
                "to_chapter": 10,
                "chapter_count": 1,
            },
            "chapters": [item],
            "exceptions": [],
            "summary": {"total": 1},
        }

    def test_ready_to_prepare_is_included_for_prepare(self) -> None:
        plan = build_batch_plan(self._readiness("READY_TO_PREPARE"), target_phase="PREPARE")
        self.assertEqual(plan["summary"]["eligible"], 1)
        self.assertEqual(plan["included"][0]["eligibility"], "ELIGIBLE")
        self.assertEqual(plan["authorization"]["status"], "MUTATION_NOT_AUTHORIZED")
        self.assertFalse(plan["authorization"]["execution_endpoint_available"])

    def test_prepare_exclusions_for_terminal_and_live_states(self) -> None:
        cases = {
            "COMPLETE": "EXCLUDED_COMPLETE",
            "RENDERED_NOT_QA": "EXCLUDED_RENDERED_NOT_QA",
            "PREPARED": "EXCLUDED_ALREADY_PREPARED",
            "RENDERING_OR_PAUSED": "EXCLUDED_RUNNING_OR_PAUSED",
            "STATE_UNRESOLVED": "EXCLUDED_UNSUPPORTED",
        }
        for state, expected in cases.items():
            with self.subTest(state=state):
                plan = build_batch_plan(self._readiness(state), target_phase="PREPARE")
                self.assertEqual(plan["included"], [])
                self.assertEqual(plan["excluded"][0]["eligibility"], expected)

    def test_casting_review_blocked_reason_is_specific_for_prepare(self) -> None:
        readiness = self._readiness(
            "CASTING_REVIEW",
            latest_casting_plan_status="draft",
            blockers=["Final Voice Map is draft/unapproved."],
        )
        plan = build_batch_plan(readiness, target_phase="PREPARE")
        self.assertEqual(plan["excluded"][0]["eligibility"], "EXCLUDED_BLOCKED")
        self.assertIn("CASTING_PLAN_NOT_APPROVED", plan["excluded"][0]["reason_codes"])

    def test_multiple_target_phases_have_explicit_mapping(self) -> None:
        expectations = {
            "APPROVAL": ("CASTING_REVIEW", "ELIGIBLE"),
            "PREPARE": ("READY_TO_PREPARE", "ELIGIBLE"),
            "START_RENDER": ("PREPARED", "ELIGIBLE"),
            "RESUME_OR_MONITOR": ("RENDERING_OR_PAUSED", "ELIGIBLE"),
            "QA_CLOSEOUT": ("RENDERED_NOT_QA", "ELIGIBLE"),
            "NO_ACTION": ("COMPLETE", "ELIGIBLE"),
        }
        for phase, (state, eligibility) in expectations.items():
            with self.subTest(phase=phase):
                plan = build_batch_plan(self._readiness(state), target_phase=phase)
                self.assertEqual(plan["included"][0]["eligibility"], eligibility)

    def test_unknown_readiness_fails_closed(self) -> None:
        plan = build_batch_plan(self._readiness("MYSTERY"), target_phase="PREPARE")
        self.assertEqual(plan["included"], [])
        self.assertEqual(plan["excluded"][0]["eligibility"], "EXCLUDED_UNSUPPORTED")
        self.assertIn("UNSUPPORTED_READINESS_STATE", plan["excluded"][0]["reason_codes"])

    def test_fingerprint_is_deterministic_and_changes_with_immutable_fact(self) -> None:
        readiness = self._readiness("READY_TO_PREPARE", active_text_revision_id=100)
        first = build_batch_plan(readiness, target_phase="PREPARE")
        second = build_batch_plan(readiness, target_phase="PREPARE")
        changed = build_batch_plan(
            self._readiness("READY_TO_PREPARE", active_text_revision_id=101),
            target_phase="PREPARE",
        )
        self.assertEqual(first["plan_fingerprint"], second["plan_fingerprint"])
        self.assertNotEqual(first["plan_fingerprint"], changed["plan_fingerprint"])

    def test_safety_semantics_do_not_overpromise_batch_execution(self) -> None:
        plan = build_batch_plan(self._readiness("READY_TO_PREPARE"), target_phase="PREPARE")
        self.assertEqual(plan["execution_contract"]["idempotency"]["status"], "PARTIALLY_SUPPORTED")
        self.assertEqual(plan["execution_contract"]["retry"]["status"], "PARTIALLY_SUPPORTED")
        self.assertEqual(plan["execution_contract"]["partial_failure"]["policy"], "PLAN_ONLY_NOT_EXECUTED")
        self.assertTrue(plan["execution_contract"]["confirmation_required"])

    def test_invalid_target_phase_fails_clearly(self) -> None:
        with self.assertRaises(ValueError):
            build_batch_plan(self._readiness("READY_TO_PREPARE"), target_phase="DELETE_EVERYTHING")


class BatchPlanApiTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        self._multipart_patcher = patch("fastapi.dependencies.utils.ensure_multipart_is_installed", lambda: None)
        self._multipart_patcher.start()

        import story_audio.api as api_module

        self.api_module = api_module
        self._original_db = api_module.db
        self._original_store = api_module.store
        self._original_worker = api_module.worker
        self._original_tts = api_module.tts_service
        api_module.db = self.db
        api_module.store = self.store
        api_module.worker = MagicMock()
        api_module.tts_service = MagicMock()
        from story_audio.api import app

        self.client = TestClient(app)
        self._seed()

    def tearDown(self) -> None:
        self.api_module.db = self._original_db
        self.api_module.store = self._original_store
        self.api_module.worker = self._original_worker
        self.api_module.tts_service = self._original_tts
        self._multipart_patcher.stop()
        super().tearDown()

    def _execute(self, sql: str, params: tuple = ()):
        with self.db.transaction() as conn:
            return conn.execute(sql, params)

    def _seed(self) -> None:
        now = utcnow()
        with self.db.transaction() as conn:
            self.book_id = int(
                conn.execute(
                    "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    ("Batch Book", "batch.epub", "batch-sha", 9, now, now),
                ).lastrowid
            )
            self.other_book_id = int(
                conn.execute(
                    "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    ("Other Book", "other.epub", "other-sha", 1, now, now),
                ).lastrowid
            )
            self.chapters = {}
            for number in range(1, 10):
                self.chapters[number] = int(
                    conn.execute(
                        "INSERT INTO chapters(book_id,chapter_number,title,char_count,audio_status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                        (self.book_id, number, f"Chapter {number}", 100 + number, "not_created", now, now),
                    ).lastrowid
                )
            self.other_chapter_id = int(
                conn.execute(
                    "INSERT INTO chapters(book_id,chapter_number,title,char_count,audio_status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                    (self.other_book_id, 3, "Other Chapter 3", 300, "not_created", now, now),
                ).lastrowid
            )

        for number, chapter_id in self.chapters.items():
            self._approve_text(chapter_id, f"Chapter {number} approved text.")
        self._approve_text(self.other_chapter_id, "Other approved text.")

        self._active_audio(1, accepted=True)
        self._active_audio(2, accepted=False)
        self._approved_plan(3)
        self._live_job(4, "prepared")
        self._live_job(5, "running")
        self._draft_plan(6)
        self._active_audio(7, accepted=False, with_newer_historical=True)
        self._inactive_historical_audio_with_bad_active_pointer(8)
        with self.db.transaction() as conn:
            conn.execute("UPDATE chapters SET active_text_revision_id=NULL WHERE id=?", (self.chapters[9],))

    def _approve_text(self, chapter_id: int, text: str) -> int:
        content_path, content_sha = self.store.put_text(text)
        now = utcnow()
        revision_id = int(
            self._execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                    processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (chapter_id, "reflowed", content_path, content_sha, sha256_text(text), len(text), "test", "approved", now),
            ).lastrowid
        )
        self._execute("UPDATE chapters SET active_text_revision_id=?,updated_at=? WHERE id=?", (revision_id, now, chapter_id))
        return revision_id

    def _plan(self, number: int, status: str) -> int:
        chapter_id = self.chapters[number]
        revision_id = self.db.fetch_one("SELECT active_text_revision_id FROM chapters WHERE id=?", (chapter_id,))["active_text_revision_id"]
        current_revision = self.db.fetch_one(
            "SELECT MAX(plan_revision) AS revision FROM casting_plans WHERE chapter_id=?",
            (chapter_id,),
        )
        plan_revision = int(current_revision["revision"] or 0) + 1
        content_path, plan_sha = self.store.put_json(
            {
                "schema_version": 1,
                "chapter_id": chapter_id,
                "text_revision_id": revision_id,
                "narrator_voice_id": "ngoc_lan",
                "utterances": [
                    {
                        "utterance_id": f"u{number:04d}",
                        "sequence": 1,
                        "role": "narrator",
                        "character_id": None,
                        "resolved_voice_id": "ngoc_lan",
                    }
                ],
            },
            namespace="casting",
        )
        now = utcnow()
        return int(
            self._execute(
                """INSERT INTO casting_plans(
                    chapter_id,text_revision_id,plan_revision,status,content_path,plan_sha256,
                    narrator_voice_id,created_at,approved_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    chapter_id,
                    revision_id,
                    plan_revision,
                    status,
                    content_path,
                    plan_sha,
                    "ngoc_lan",
                    now,
                    now if status == "approved" else None,
                ),
            ).lastrowid
        )

    def _approved_plan(self, number: int) -> int:
        return self._plan(number, "approved")

    def _draft_plan(self, number: int) -> int:
        return self._plan(number, "draft")

    def _live_job(self, number: int, status: str) -> int:
        chapter_id = self.chapters[number]
        revision_id = self.db.fetch_one("SELECT active_text_revision_id FROM chapters WHERE id=?", (chapter_id,))["active_text_revision_id"]
        plan_id = self._approved_plan(number)
        now = utcnow()
        job_id = int(
            self._execute(
                """INSERT INTO jobs(
                    book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                    settings_json,total_chapters,scheduled_at,created_at,updated_at,casting_plan_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.book_id, status, number, number, "ngoc_lan", "off", "m4a", "{}", 1, now, now, now, plan_id),
            ).lastrowid
        )
        self._execute(
            "INSERT INTO job_chapters(job_id,chapter_id,sequence,status,text_revision_id,casting_plan_id) VALUES(?,?,?,?,?,?)",
            (job_id, chapter_id, 1, status, revision_id, plan_id),
        )
        return job_id

    def _artifact_file(self, number: int, label: str) -> Path:
        path = self.config.output_dir / f"job_{label}" / f"chapter_{number:04d}" / "chapter.m4a"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"audio-{number}-{label}".encode("utf-8"))
        return path

    def _active_audio(self, number: int, *, accepted: bool, with_newer_historical: bool = False) -> int:
        chapter_id = self.chapters[number]
        revision_id = self.db.fetch_one("SELECT active_text_revision_id FROM chapters WHERE id=?", (chapter_id,))["active_text_revision_id"]
        plan_id = self._approved_plan(number)
        now = utcnow()
        job_id = int(
            self._execute(
                """INSERT INTO jobs(
                    book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                    settings_json,total_chapters,scheduled_at,created_at,updated_at,casting_plan_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.book_id, "completed", number, number, "ngoc_lan", "off", "m4a", "{}", 1, now, now, now, plan_id),
            ).lastrowid
        )
        job_chapter_id = int(
            self._execute(
                "INSERT INTO job_chapters(job_id,chapter_id,sequence,status,text_revision_id,casting_plan_id) VALUES(?,?,?,?,?,?)",
                (job_id, chapter_id, 1, "completed", revision_id, plan_id),
            ).lastrowid
        )
        path = self._artifact_file(number, "active")
        artifact_id = int(
            self._execute(
                """INSERT INTO artifacts(
                    chapter_id,job_chapter_id,text_revision_id,artifact_type,path,sha256,size_bytes,
                    duration_ms,status,created_at,verified_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (chapter_id, job_chapter_id, revision_id, "chapter_m4a", str(path), sha256_file(path), path.stat().st_size, 1234, "active", now, now),
            ).lastrowid
        )
        self._execute("UPDATE chapters SET audio_status='completed',active_audio_artifact_id=?,updated_at=? WHERE id=?", (artifact_id, now, chapter_id))
        if accepted:
            approval = {"status": "approved", "artifact_id": artifact_id, "job_id": job_id, "approved_at": now}
            self._execute("UPDATE chapters SET human_approval_json=?,updated_at=? WHERE id=?", (json.dumps(approval), now, chapter_id))
        if with_newer_historical:
            newer_job = int(
                self._execute(
                    """INSERT INTO jobs(
                        book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                        settings_json,total_chapters,scheduled_at,created_at,updated_at,casting_plan_id
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (self.book_id, "completed", number, number, "ngoc_lan", "off", "m4a", "{}", 1, now, now, now, plan_id),
                ).lastrowid
            )
            newer_job_chapter = int(
                self._execute(
                    "INSERT INTO job_chapters(job_id,chapter_id,sequence,status,text_revision_id,casting_plan_id) VALUES(?,?,?,?,?,?)",
                    (newer_job, chapter_id, 1, "completed", revision_id, plan_id),
                ).lastrowid
            )
            newer_path = self._artifact_file(number, "newer")
            self._execute(
                """INSERT INTO artifacts(
                    chapter_id,job_chapter_id,text_revision_id,artifact_type,path,sha256,size_bytes,
                    duration_ms,status,created_at,verified_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (chapter_id, newer_job_chapter, revision_id, "chapter_m4a", str(newer_path), sha256_file(newer_path), newer_path.stat().st_size, 2345, "active", now, now),
            )
        return artifact_id

    def _inactive_historical_audio_with_bad_active_pointer(self, number: int) -> None:
        self._active_audio(number, accepted=True)
        self._execute("UPDATE chapters SET active_audio_artifact_id=? WHERE id=?", (999999, self.chapters[number]))

    def _batch_plan(self, start: int = 1, end: int = 9, phase: str = "PREPARE"):
        response = self.client.get(
            "/api/production/batch-plan",
            params={
                "book_id": self.book_id,
                "from_chapter": start,
                "to_chapter": end,
                "target_phase": phase,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_valid_prepare_plan_is_deterministic_and_summary_consistent(self) -> None:
        first = self._batch_plan()
        second = self._batch_plan()
        self.assertEqual(first, second)
        self.assertEqual(first["scope"]["chapter_count"], 9)
        self.assertEqual(first["summary"]["total"], len(first["included"]) + len(first["excluded"]))
        self.assertEqual(first["summary"]["eligible"], len(first["included"]))
        self.assertEqual(first["summary"]["excluded"], len(first["excluded"]))
        self.assertEqual([item["chapter_number"] for item in first["included"]], [3])
        chapter_ids = [item["chapter_id"] for item in first["included"] + first["excluded"]]
        self.assertEqual(len(chapter_ids), len(set(chapter_ids)))

    def test_api_handles_every_advertised_phase_safely(self) -> None:
        for phase in ["APPROVAL", "PREPARE", "START_RENDER", "RESUME_OR_MONITOR", "QA_CLOSEOUT", "NO_ACTION"]:
            with self.subTest(phase=phase):
                data = self._batch_plan(phase=phase)
                self.assertEqual(data["requested_phase"], phase)
                self.assertEqual(data["authorization"]["status"], "MUTATION_NOT_AUTHORIZED")
                self.assertFalse(data["authorization"]["execution_endpoint_available"])
                self.assertEqual(data["summary"]["total"], len(data["included"]) + len(data["excluded"]))

    def test_response_does_not_expose_paths_or_internal_snapshots(self) -> None:
        data = self._batch_plan()
        encoded = json.dumps(data, ensure_ascii=False)
        self.assertNotIn(str(self.config.output_dir), encoded)
        self.assertNotIn(str(self.config.data_dir), encoded)
        self.assertNotIn("\\", encoded)
        self.assertNotIn("content_path", encoded)
        self.assertNotIn("voice_snapshot_json", encoded)
        self.assertNotIn("casting_snapshot_json", encoded)
        self.assertNotIn("utterances", encoded)

    def test_invalid_scope_and_phase_fail_clearly(self) -> None:
        invalid_order = self.client.get(
            "/api/production/batch-plan",
            params={"book_id": self.book_id, "from_chapter": 3, "to_chapter": 1, "target_phase": "PREPARE"},
        )
        self.assertEqual(invalid_order.status_code, 400)
        missing_book = self.client.get(
            "/api/production/batch-plan",
            params={"book_id": 9999, "from_chapter": 1, "to_chapter": 1, "target_phase": "PREPARE"},
        )
        self.assertEqual(missing_book.status_code, 404)
        missing_range = self.client.get(
            "/api/production/batch-plan",
            params={"book_id": self.book_id, "from_chapter": 1, "to_chapter": 99, "target_phase": "PREPARE"},
        )
        self.assertEqual(missing_range.status_code, 404)
        bad_phase = self.client.get(
            "/api/production/batch-plan",
            params={"book_id": self.book_id, "from_chapter": 1, "to_chapter": 1, "target_phase": "MUTATE"},
        )
        self.assertEqual(bad_phase.status_code, 400)

    def test_prepare_eligibility_cases_and_active_pointer_semantics(self) -> None:
        data = {item["chapter_number"]: item for item in self._batch_plan()["included"] + self._batch_plan()["excluded"]}
        self.assertEqual(data[1]["eligibility"], "EXCLUDED_COMPLETE")
        self.assertEqual(data[2]["eligibility"], "EXCLUDED_RENDERED_NOT_QA")
        self.assertEqual(data[3]["eligibility"], "ELIGIBLE")
        self.assertEqual(data[4]["eligibility"], "EXCLUDED_ALREADY_PREPARED")
        self.assertEqual(data[5]["eligibility"], "EXCLUDED_RUNNING_OR_PAUSED")
        self.assertEqual(data[6]["eligibility"], "EXCLUDED_BLOCKED")
        self.assertIn("CASTING_PLAN_NOT_APPROVED", data[6]["reason_codes"])
        self.assertEqual(data[7]["eligibility"], "EXCLUDED_RENDERED_NOT_QA")
        self.assertEqual(data[7]["active_artifact_id"], self.db.fetch_one("SELECT active_audio_artifact_id FROM chapters WHERE id=?", (self.chapters[7],))["active_audio_artifact_id"])
        self.assertEqual(data[8]["eligibility"], "EXCLUDED_UNSUPPORTED")
        self.assertEqual(data[9]["eligibility"], "EXCLUDED_BLOCKED")

    def test_cross_book_chapter_number_does_not_leak(self) -> None:
        plan = self._batch_plan(3, 3)
        ids = [item["chapter_id"] for item in plan["included"] + plan["excluded"]]
        self.assertEqual(ids, [self.chapters[3]])
        self.assertNotIn(self.other_chapter_id, ids)

    def test_authorization_boundary_and_no_mutation_routes(self) -> None:
        data = self._batch_plan()
        self.assertEqual(data["authorization"]["status"], "MUTATION_NOT_AUTHORIZED")
        self.assertFalse(data["authorization"]["execution_endpoint_available"])
        self.assertTrue(data["authorization"]["requires_explicit_confirmation"])
        from story_audio.api import app

        batch_routes = [
            route
            for route in app.routes
            if getattr(route, "path", "").startswith("/api/production/batch-plan")
        ]
        self.assertEqual(len(batch_routes), 1)
        self.assertEqual(batch_routes[0].methods, {"GET"})

    def test_request_is_read_only_and_does_not_call_worker_or_tts(self) -> None:
        tables = [
            "speaker_assignment_drafts",
            "casting_plans",
            "jobs",
            "job_chapters",
            "segments",
            "artifacts",
        ]
        before = {table: self.db.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"] for table in tables}
        self._batch_plan()
        after = {table: self.db.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"] for table in tables}
        self.assertEqual(before, after)
        self.api_module.worker.wake.assert_not_called()
        self.api_module.tts_service.voices.assert_not_called()

    def test_no_chapter_369_hard_code(self) -> None:
        source = Path("story_audio/batch_plan.py").read_text(encoding="utf-8")
        self.assertNotIn("369", source)


if __name__ == "__main__":
    unittest.main()
