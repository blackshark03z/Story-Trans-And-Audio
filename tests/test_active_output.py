from __future__ import annotations

from pathlib import Path

from story_audio.active_output import annotate_chapter_rows, annotate_job_rows, get_active_output_bindings
from story_audio.db import utcnow
from story_audio.files import sha256_file
from story_audio.diagnostics import get_job_diagnostics
from tests.base import IsolatedTestCase
from tests.test_recovery import make_config


def seed_active_output(root: Path):
    config = make_config(root)
    config.ensure_dirs()
    from story_audio.db import Database
    from story_audio.storage import ContentStore

    database = Database(config.db_path)
    database.initialize()
    store = ContentStore(config)
    now = utcnow()
    with database.transaction() as connection:
        book_id = int(
            connection.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                ("Book", "book.epub", "sha", 2, now, now),
            ).lastrowid
        )
        chapter_one = int(
            connection.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at,audio_status) VALUES(?,?,?,?,?,?,?)",
                (book_id, 10, "Chapter 10", 1200, now, now, "completed"),
            ).lastrowid
        )
        chapter_two = int(
            connection.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at,audio_status) VALUES(?,?,?,?,?,?,?)",
                (book_id, 11, "Chapter 11", 900, now, now, "pending"),
            ).lastrowid
        )
        revision_one = int(
            connection.execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                    processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (chapter_one, "reflowed") + store.put_text("Chapter 10 text.") + ("lexical", 16, "test", "approved", now),
            ).lastrowid
        )
        revision_two = int(
            connection.execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                    processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (chapter_two, "reflowed") + store.put_text("Chapter 11 text.") + ("lexical", 16, "test", "approved", now),
            ).lastrowid
        )
        for chapter_id, revision_id in ((chapter_one, revision_one), (chapter_two, revision_two)):
            connection.execute(
                "UPDATE chapters SET active_text_revision_id=? WHERE id=?",
                (revision_id, chapter_id),
            )
        plan_old = int(
            connection.execute(
                """INSERT INTO casting_plans(
                    chapter_id,text_revision_id,plan_revision,status,content_path,plan_sha256,
                    narrator_voice_id,created_at,approved_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (chapter_one, revision_one, 4, "approved", "plans/old.json", "old-plan-sha", "ngoc_lan", now, now),
            ).lastrowid
        )
        plan_new = int(
            connection.execute(
                """INSERT INTO casting_plans(
                    chapter_id,text_revision_id,plan_revision,status,content_path,plan_sha256,
                    narrator_voice_id,created_at,approved_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (chapter_one, revision_one, 6, "approved", "plans/new.json", "new-plan-sha", "ngoc_lan", now, now),
            ).lastrowid
        )
        settings_json = '{"max_chars":256}'
        job_old = int(
            connection.execute(
                """INSERT INTO jobs(
                    book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                    settings_json,total_chapters,scheduled_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (book_id, "completed", 10, 10, "Voice A", "off", "m4a", settings_json, 1, now, now, now),
            ).lastrowid
        )
        job_new = int(
            connection.execute(
                """INSERT INTO jobs(
                    book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                    settings_json,total_chapters,scheduled_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (book_id, "completed", 10, 10, "Voice B", "off", "m4a", settings_json, 1, now, now, now),
            ).lastrowid
        )
        old_job_chapter = int(
            connection.execute(
                "INSERT INTO job_chapters(job_id,chapter_id,sequence,status,text_revision_id,casting_plan_id) VALUES(?,?,?,?,?,?)",
                (job_old, chapter_one, 1, "completed", revision_one, plan_old),
            ).lastrowid
        )
        new_job_chapter = int(
            connection.execute(
                "INSERT INTO job_chapters(job_id,chapter_id,sequence,status,text_revision_id,casting_plan_id) VALUES(?,?,?,?,?,?)",
                (job_new, chapter_one, 1, "completed", revision_one, plan_new),
            ).lastrowid
        )
        old_artifact = config.output_dir / "job_1" / "chapter_0010" / "chapter.m4a"
        old_artifact.parent.mkdir(parents=True, exist_ok=True)
        old_artifact.write_bytes(b"old")
        new_artifact = config.output_dir / "job_2" / "chapter_0010" / "chapter.m4a"
        new_artifact.parent.mkdir(parents=True, exist_ok=True)
        new_artifact.write_bytes(b"new")
        old_artifact_id = int(
            connection.execute(
                """INSERT INTO artifacts(
                    chapter_id,job_chapter_id,text_revision_id,artifact_type,path,sha256,size_bytes,
                    duration_ms,status,created_at,verified_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    chapter_one,
                    old_job_chapter,
                    revision_one,
                    "chapter_m4a",
                    str(old_artifact),
                    sha256_file(old_artifact),
                    old_artifact.stat().st_size,
                    1000,
                    "active",
                    now,
                    now,
                ),
            ).lastrowid
        )
        new_artifact_id = int(
            connection.execute(
                """INSERT INTO artifacts(
                    chapter_id,job_chapter_id,text_revision_id,artifact_type,path,sha256,size_bytes,
                    duration_ms,status,created_at,verified_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    chapter_one,
                    new_job_chapter,
                    revision_one,
                    "chapter_m4a",
                    str(new_artifact),
                    sha256_file(new_artifact),
                    new_artifact.stat().st_size,
                    1000,
                    "active",
                    now,
                    now,
                ),
            ).lastrowid
        )
        connection.execute(
            "UPDATE chapters SET active_audio_artifact_id=? WHERE id=?",
            (old_artifact_id, chapter_one),
        )
    return {
        "config": config,
        "db": database,
        "chapter_one": chapter_one,
        "chapter_two": chapter_two,
        "job_old": job_old,
        "job_new": job_new,
        "old_job_chapter": old_job_chapter,
        "new_job_chapter": new_job_chapter,
        "old_artifact_id": old_artifact_id,
        "new_artifact_id": new_artifact_id,
    }


class ActiveOutputTests(IsolatedTestCase):
    def test_binding_uses_active_artifact_not_newest_completed_job(self) -> None:
        seeded = seed_active_output(self.temp_root)
        binding = get_active_output_bindings(seeded["db"], [seeded["chapter_one"]])[seeded["chapter_one"]]
        self.assertEqual(binding["active_output_artifact_id"], seeded["old_artifact_id"])
        self.assertEqual(binding["active_output_job_id"], seeded["job_old"])
        self.assertNotEqual(binding["active_output_job_id"], seeded["job_new"])
        self.assertEqual(binding["active_output_casting_plan_revision"], 4)
        self.assertTrue(binding["active_output_has_trustworthy_binding"])

    def test_chapter_rows_include_active_job_and_plan_metadata(self) -> None:
        seeded = seed_active_output(self.temp_root)
        rows = annotate_chapter_rows(
            seeded["db"],
            [
                {"id": seeded["chapter_one"], "audio_status": "completed", "qa_count": 0},
                {"id": seeded["chapter_two"], "audio_status": "pending", "qa_count": 0},
            ],
        )
        active = rows[0]
        pending = rows[1]
        self.assertEqual(active["active_output_job_id"], seeded["job_old"])
        self.assertEqual(active["active_output_casting_plan_revision"], 4)
        self.assertTrue(active["has_active_audio"])
        self.assertFalse(pending["has_active_audio"])
        self.assertIsNone(pending["active_output_job_id"])

    def test_job_rows_mark_only_bound_job_as_active_output(self) -> None:
        seeded = seed_active_output(self.temp_root)
        rows = annotate_job_rows(
            seeded["db"],
            [
                {"id": seeded["job_new"], "status": "completed"},
                {"id": seeded["job_old"], "status": "completed"},
            ],
        )
        historical = rows[0]
        active = rows[1]
        self.assertFalse(historical["is_active_output"])
        self.assertTrue(historical["is_historical_output"])
        self.assertTrue(active["is_active_output"])
        self.assertFalse(active["is_historical_output"])
        self.assertEqual(active["active_output_chapters"][0]["active_output_casting_plan_revision"], 4)

    def test_job_diagnostics_surface_active_and_historical_state(self) -> None:
        seeded = seed_active_output(self.temp_root)
        active = get_job_diagnostics(seeded["db"], seeded["job_old"])
        historical = get_job_diagnostics(seeded["db"], seeded["job_new"])
        self.assertTrue(active["job"]["is_active_output"])
        self.assertFalse(active["job"]["is_historical_output"])
        self.assertTrue(active["chapters"][0]["is_active_output"])
        self.assertFalse(historical["job"]["is_active_output"])
        self.assertTrue(historical["job"]["is_historical_output"])


if __name__ == "__main__":
    import unittest

    unittest.main()
