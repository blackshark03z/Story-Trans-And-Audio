from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from story_audio.db import Database, utcnow
from story_audio.batch_prepare_transaction_revalidator import (
    BatchPrepareTransactionRevalidator,
)
from story_audio.files import sha256_file, sha256_text
from story_audio.range_readiness import get_range_readiness
from story_audio.storage import ContentStore
from story_audio.voice_eligibility import EffectiveVoiceCatalog
from tests.base import IsolatedTestCase
from tests.test_text_encoding import legacy_decode_utf8


class RangeReadinessApiTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        self._multipart_patcher = patch("fastapi.dependencies.utils.ensure_multipart_is_installed", lambda: None)
        self._multipart_patcher.start()
        import story_audio.api as api_module

        self._original_db = api_module.db
        self._original_voice_catalog_loader = api_module._load_voice_catalog
        api_module.db = self.db
        api_module._load_voice_catalog = lambda: EffectiveVoiceCatalog.from_ids(
            "ngoc_lan"
        )
        from story_audio.api import app

        self.client = TestClient(app)
        self._seed()

    def tearDown(self) -> None:
        import story_audio.api as api_module

        api_module.db = self._original_db
        api_module._load_voice_catalog = self._original_voice_catalog_loader
        self._multipart_patcher.stop()
        super().tearDown()

    def _seed(self) -> None:
        now = utcnow()
        with self.db.transaction() as conn:
            self.book_id = int(
                conn.execute(
                    "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    ("Range Book", "range.epub", "range-sha", 12, now, now),
                ).lastrowid
            )
            self.other_book_id = int(
                conn.execute(
                    "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    ("Other Book", "other.epub", "other-sha", 1, now, now),
                ).lastrowid
            )
            self.chapters: dict[int, int] = {}
            for number in range(1, 13):
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
        self._approve_text(self.other_chapter_id, "Other book text.")

        self._active_audio(1, accepted=False)
        self._active_audio(2, accepted=True)
        self._approved_plan(3)
        self._live_job(4, "prepared")
        self._live_job(5, "running")
        self._draft_plan(6)
        self._approved_plan(7)
        self._inactive_historical_audio_with_bad_active_pointer(8)
        self._speaker_draft(9, "generated")
        self._draft_plan(10)
        self._active_audio(11, accepted=False, with_newer_historical=True)
        # Chapter 12 deliberately loses approved active text.
        with self.db.transaction() as conn:
            conn.execute("UPDATE chapters SET active_text_revision_id=NULL WHERE id=?", (self.chapters[12],))

    def _execute(self, sql: str, params: tuple = ()):
        with self.db.transaction() as conn:
            return conn.execute(sql, params)

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

    def _plan(
        self,
        number: int,
        status: str,
        narrator_voice_id: str = "ngoc_lan",
        utterance_voice_id: str = "ngoc_lan",
    ) -> int:
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
                "narrator_voice_id": narrator_voice_id,
                "utterances": [
                    {
                        "utterance_id": f"u{number:04d}",
                        "sequence": 1,
                        "role": "narrator",
                        "character_id": None,
                        "resolved_voice_id": utterance_voice_id,
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
                    narrator_voice_id,
                    now,
                    now if status == "approved" else None,
                ),
            ).lastrowid
        )

    def _approved_plan(self, number: int) -> int:
        return self._plan(number, "approved")

    def _draft_plan(self, number: int) -> int:
        return self._plan(number, "draft")

    def _speaker_draft(self, number: int, status: str) -> int:
        chapter_id = self.chapters[number]
        revision_id = self.db.fetch_one("SELECT active_text_revision_id FROM chapters WHERE id=?", (chapter_id,))["active_text_revision_id"]
        now = utcnow()
        return int(
            self._execute(
                """INSERT INTO speaker_assignment_drafts(
                    book_id,chapter_id,text_revision_id,input_fingerprint,character_bible_fingerprint,
                    model_id,prompt_version,response_schema,mode,status,content_path,content_sha256,
                    target_count,valid_count,invalid_count,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    self.book_id,
                    chapter_id,
                    revision_id,
                    f"fingerprint-{chapter_id}",
                    "characters",
                    "fake",
                    "speaker-assignment-v2",
                    "story-audio-speaker-assignment-draft/v1",
                    "reanalyze",
                    status,
                    f"speaker/{chapter_id}.json",
                    "draft-sha",
                    1,
                    1,
                    0,
                    now,
                ),
            ).lastrowid
        )

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
        active_job = int(
            self._execute(
                """INSERT INTO jobs(
                    book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                    settings_json,total_chapters,scheduled_at,created_at,updated_at,casting_plan_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.book_id, "completed", number, number, "ngoc_lan", "off", "m4a", "{}", 1, now, now, now, plan_id),
            ).lastrowid
        )
        active_jc = int(
            self._execute(
                "INSERT INTO job_chapters(job_id,chapter_id,sequence,status,text_revision_id,casting_plan_id) VALUES(?,?,?,?,?,?)",
                (active_job, chapter_id, 1, "completed", revision_id, plan_id),
            ).lastrowid
        )
        path = self._artifact_file(number, "active")
        artifact_id = int(
            self._execute(
                """INSERT INTO artifacts(
                    chapter_id,job_chapter_id,text_revision_id,artifact_type,path,sha256,size_bytes,
                    duration_ms,status,created_at,verified_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (chapter_id, active_jc, revision_id, "chapter_m4a", str(path), sha256_file(path), path.stat().st_size, 1234, "active", now, now),
            ).lastrowid
        )
        self._execute("UPDATE chapters SET audio_status='completed',active_audio_artifact_id=?,updated_at=? WHERE id=?", (artifact_id, now, chapter_id))
        if accepted:
            approval = {"status": "approved", "artifact_id": artifact_id, "job_id": active_job, "approved_at": now}
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
            newer_jc = int(
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
                (chapter_id, newer_jc, revision_id, "chapter_m4a", str(newer_path), sha256_file(newer_path), newer_path.stat().st_size, 2345, "active", now, now),
            )
        return artifact_id

    def _inactive_historical_audio_with_bad_active_pointer(self, number: int) -> None:
        self._active_audio(number, accepted=True)
        self._execute("UPDATE chapters SET active_audio_artifact_id=? WHERE id=?", (999999, self.chapters[number]))

    def _readiness(self, start: int = 1, end: int = 12) -> dict:
        response = self.client.get(
            "/api/production/range-readiness",
            params={"book_id": self.book_id, "from_chapter": start, "to_chapter": end},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_valid_range_returns_deterministic_chapter_order(self) -> None:
        data = self._readiness(1, 3)
        self.assertEqual([item["chapter_number"] for item in data["chapters"]], [1, 2, 3])
        self.assertEqual(data["scope"]["book_id"], self.book_id)
        self.assertEqual(data["scope"]["chapter_count"], 3)

    def test_invalid_ranges_fail_clearly_without_cross_book_leakage(self) -> None:
        bad_order = self.client.get(
            "/api/production/range-readiness",
            params={"book_id": self.book_id, "from_chapter": 3, "to_chapter": 1},
        )
        self.assertEqual(bad_order.status_code, 400)
        missing_book = self.client.get(
            "/api/production/range-readiness",
            params={"book_id": 9999, "from_chapter": 1, "to_chapter": 1},
        )
        self.assertEqual(missing_book.status_code, 404)
        empty = self.client.get(
            "/api/production/range-readiness",
            params={"book_id": self.book_id, "from_chapter": 99, "to_chapter": 100},
        )
        self.assertEqual(empty.status_code, 404)
        data = self._readiness(3, 3)
        self.assertEqual(len(data["chapters"]), 1)
        self.assertEqual(data["chapters"][0]["chapter_id"], self.chapters[3])
        self.assertNotEqual(data["chapters"][0]["chapter_id"], self.other_chapter_id)

    def test_one_current_state_per_chapter_and_no_duplicate_exceptions(self) -> None:
        data = self._readiness()
        for item in data["chapters"]:
            self.assertIsInstance(item["state"], str)
            self.assertIsInstance(item["next_action"], str)
        exception_ids = [item["chapter_id"] for item in data["exceptions"]]
        self.assertEqual(len(exception_ids), len(set(exception_ids)))

    def test_workflow_precedence_for_prepared_and_running_over_upstream(self) -> None:
        data = {item["chapter_number"]: item for item in self._readiness()["chapters"]}
        self.assertEqual(data[4]["state"], "PREPARED")
        self.assertEqual(data[4]["next_action"], "START_RENDER")
        self.assertEqual(data[5]["state"], "RENDERING_OR_PAUSED")
        self.assertEqual(data[5]["next_action"], "MONITOR_OR_RESUME")

    def test_voice_blocked_when_approved_plan_lacks_voice(self) -> None:
        self._plan(3, "approved", narrator_voice_id="")
        item = self._readiness(3, 3)["chapters"][0]
        self.assertEqual(item["state"], "VOICE_BLOCKED")
        self.assertEqual(item["next_action"], "CONFIGURE_VOICES")

    def test_voice_blocked_when_approved_plan_has_unresolved_utterance_voice(self) -> None:
        self._plan(3, "approved", utterance_voice_id="")
        item = self._readiness(3, 3)["chapters"][0]
        self.assertEqual(item["state"], "VOICE_BLOCKED")
        self.assertEqual(item["next_action"], "CONFIGURE_VOICES")
        self.assertEqual(item["voice_issues"][0]["voice_id"], "")
        self.assertEqual(item["voice_issues"][0]["speaker"], "narrator")
        self.assertEqual(item["voice_issues"][0]["chapter_number"], 3)
        self.assertTrue(item["voice_issues"][0]["replacement_required"])
        self.assertIn("no fallback", item["voice_issues"][0]["message"])

    def test_active_audio_pending_qa_is_not_complete(self) -> None:
        item = self._readiness(1, 1)["chapters"][0]
        self.assertEqual(item["state"], "RENDERED_NOT_QA")
        self.assertEqual(item["next_action"], "QA")
        self.assertTrue(item["requires_operator_action"])

    def test_rejected_artifact_requires_new_valid_revision_and_matching_plan(self) -> None:
        chapter_id = self.chapters[1]
        artifact_id = self.db.fetch_one(
            "SELECT active_audio_artifact_id FROM chapters WHERE id=?",
            (chapter_id,),
        )["active_audio_artifact_id"]
        approval = {"status": "needs_fixes", "artifact_id": artifact_id}
        self._execute(
            "UPDATE chapters SET human_approval_json=? WHERE id=?",
            (json.dumps(approval), chapter_id),
        )
        same_revision = self._readiness(1, 1)["chapters"][0]
        self.assertEqual(same_revision["state"], "RENDERED_NOT_QA")

        new_revision_id = self._approve_text(
            chapter_id,
            "Corrected replacement source text.",
        )
        stale_plan = self._readiness(1, 1)["chapters"][0]
        self.assertEqual(stale_plan["state"], "CASTING_REVIEW")
        self.assertEqual(stale_plan["replacement_for_artifact_id"], artifact_id)
        self.assertNotEqual(
            stale_plan["active_output_text_revision_id"],
            new_revision_id,
        )

        self._approved_plan(1)
        ready = self._readiness(1, 1)["chapters"][0]
        self.assertEqual(ready["state"], "READY_TO_PREPARE")
        self.assertEqual(ready["replacement_for_artifact_id"], artifact_id)
        with self.db.connect() as connection:
            chapter = connection.execute(
                "SELECT * FROM chapters WHERE id=?",
                (chapter_id,),
            ).fetchone()
            self.assertTrue(
                BatchPrepareTransactionRevalidator._chapter_allows_prepare(
                    connection,
                    chapter,
                )
            )

    def test_rejected_artifact_exposes_invalid_active_text_as_text_blocker(self) -> None:
        chapter_id = self.chapters[1]
        artifact_id = self.db.fetch_one(
            "SELECT active_audio_artifact_id FROM chapters WHERE id=?",
            (chapter_id,),
        )["active_audio_artifact_id"]
        malformed = legacy_decode_utf8("Trời vừa sáng.")
        self._approve_text(chapter_id, malformed)
        self._execute(
            "UPDATE chapters SET human_approval_json=? WHERE id=?",
            (
                json.dumps({"status": "needs_fixes", "artifact_id": artifact_id}),
                chapter_id,
            ),
        )
        item = self._readiness(1, 1)["chapters"][0]
        self.assertEqual(item["state"], "TEXT_BLOCKED")
        self.assertIn("TEXT_ENCODING_INVALID", item["blockers"][0])

    def test_active_audio_accepted_is_complete(self) -> None:
        item = self._readiness(2, 2)["chapters"][0]
        self.assertEqual(item["state"], "COMPLETE")
        self.assertEqual(item["human_qa_status"], "accepted")
        self.assertFalse(item["requires_operator_action"])

    def test_casting_review_draft_plan_does_not_mutate_plan(self) -> None:
        before = self.db.fetch_one("SELECT COUNT(*) AS n FROM casting_plans")["n"]
        item = self._readiness(6, 6)["chapters"][0]
        after = self.db.fetch_one("SELECT COUNT(*) AS n FROM casting_plans")["n"]
        self.assertEqual(item["state"], "CASTING_REVIEW")
        self.assertEqual(item["next_action"], "REVIEW_FINAL_VOICE_MAP")
        self.assertEqual(before, after)

    def test_ready_to_prepare_does_not_create_job(self) -> None:
        before = self.db.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"]
        item = self._readiness(7, 7)["chapters"][0]
        after = self.db.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"]
        self.assertEqual(item["state"], "READY_TO_PREPARE")
        self.assertEqual(item["next_action"], "PREPARE")
        self.assertFalse(item["requires_operator_action"])
        self.assertEqual(before, after)

    def test_active_pointer_wins_over_newest_historical_output(self) -> None:
        item = self._readiness(11, 11)["chapters"][0]
        self.assertEqual(item["active_artifact_id"], self.db.fetch_one("SELECT active_audio_artifact_id FROM chapters WHERE id=?", (self.chapters[11],))["active_audio_artifact_id"])
        self.assertEqual(item["state"], "RENDERED_NOT_QA")

    def test_invalid_active_binding_fails_closed_without_historical_fallback(self) -> None:
        item = self._readiness(8, 8)["chapters"][0]
        self.assertEqual(item["state"], "STATE_UNRESOLVED")
        self.assertIsNone(item["active_artifact_id"])
        self.assertIn("invalid", item["blockers"][0].lower())

    def test_runtime_qa_source_comes_from_database_fixture(self) -> None:
        data = {item["chapter_number"]: item for item in self._readiness(1, 2)["chapters"]}
        self.assertEqual(data[1]["human_qa_status"], "pending")
        self.assertEqual(data[2]["human_qa_status"], "accepted")

    def test_unknown_qa_status_fails_closed_to_pending_review(self) -> None:
        artifact_id = self.db.fetch_one(
            "SELECT active_audio_artifact_id FROM chapters WHERE id=?",
            (self.chapters[2],),
        )["active_audio_artifact_id"]
        approval = {"status": "mystery", "artifact_id": artifact_id}
        self._execute(
            "UPDATE chapters SET human_approval_json=? WHERE id=?",
            (json.dumps(approval), self.chapters[2]),
        )
        item = self._readiness(2, 2)["chapters"][0]
        self.assertEqual(item["human_qa_status"], "pending")
        self.assertEqual(item["state"], "RENDERED_NOT_QA")

    def test_repeated_response_is_deterministic(self) -> None:
        self.assertEqual(self._readiness(), self._readiness())

    def test_implementation_does_not_hard_code_chapter_369(self) -> None:
        source = Path("story_audio/range_readiness.py").read_text(encoding="utf-8")
        self.assertNotIn("369", source)

    def test_summary_consistency_matches_chapters_and_exception_queue(self) -> None:
        data = self._readiness()
        counts: dict[str, int] = {}
        for item in data["chapters"]:
            counts[item["state"]] = counts.get(item["state"], 0) + 1
        self.assertEqual(data["summary"]["total"], len(data["chapters"]))
        self.assertEqual(data["summary"]["state_counts"], counts)
        self.assertEqual(data["summary"]["needs_attention"], len(data["exceptions"]))
        self.assertEqual(data["summary"]["complete"], counts.get("COMPLETE", 0))

    def test_read_only_guarantee_for_core_tables(self) -> None:
        tables = [
            "speaker_assignment_drafts",
            "speaker_assignment_reviews",
            "casting_plans",
            "jobs",
            "job_chapters",
            "segments",
            "artifacts",
        ]
        before = {table: self.db.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"] for table in tables}
        approvals_before = {
            row["id"]: row["human_approval_json"]
            for row in self.db.fetch_all("SELECT id,human_approval_json FROM chapters ORDER BY id")
        }
        self._readiness()
        after = {table: self.db.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"] for table in tables}
        approvals_after = {
            row["id"]: row["human_approval_json"]
            for row in self.db.fetch_all("SELECT id,human_approval_json FROM chapters ORDER BY id")
        }
        self.assertEqual(before, after)
        self.assertEqual(approvals_before, approvals_after)


class RangeReadinessHelperTests(unittest.TestCase):
    def test_helper_rejects_invalid_range_without_database_access(self) -> None:
        class ExplodingDb:
            def fetch_one(self, *_args, **_kwargs):  # pragma: no cover - must not be called
                raise AssertionError("database should not be queried")

        with self.assertRaises(ValueError):
            get_range_readiness(ExplodingDb(), book_id=1, from_chapter=9, to_chapter=1)


if __name__ == "__main__":
    unittest.main()
