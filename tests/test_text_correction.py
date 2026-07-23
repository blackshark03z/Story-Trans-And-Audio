from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from story_audio.config import Settings
from story_audio.db import Database, utcnow
from story_audio.speaker_assignment import generate_speaker_assignment_draft
from story_audio.speaker_review import get_speaker_review_draft
from story_audio.storage import ContentStore
from story_audio.text import lexical_sha256
from story_audio.text_correction import (
    TARGETED_CORRECTION_PROCESSOR_VERSION,
    TextCorrectionConflict,
    TextCorrectionError,
    TextCorrectionNotFound,
    apply_targeted_text_correction,
)
from tests.base import IsolatedTestCase
from tests.test_text_encoding import legacy_decode_utf8


BASE_TEXT = 'Mở đầu. "Xin chào.... ." Kết thúc.'
EXPECTED_TEXT = '"Xin chào.... ."'
REPLACEMENT_TEXT = '"Xin chào..."'
ALT_TEXT = "Lặp lại. Trời mưa. Trời mưa. Kết thúc."


def _fake_assignment_response(request_data: dict, character_id: int) -> dict:
    assignments = []
    for target_id in request_data["target_utterance_ids"]:
        assignments.append(
            {
                "utterance_id": target_id,
                "speaker_type": "character",
                "character_id": character_id,
                "confidence": 0.95,
                "reason": "Context matches the known character.",
                "alternatives": [{"speaker_type": "narrator", "character_id": None, "confidence": 0.1}],
            }
        )
    return {"schema": "story-audio-speaker-assignment-draft/v1", "assignments": assignments}


def make_config(root: Path):
    return replace(
        Settings(),
        root=root,
        data_dir=root / "data",
        db_path=root / "data" / "app.db",
        blobs_dir=root / "data" / "blobs",
        output_dir=root / "data" / "output",
        work_dir=root / "data" / "work",
        log_dir=root / "logs",
    )


def seed_correction_fixture(
    config,
    *,
    base_text: str = BASE_TEXT,
    approved: bool = True,
    create_review_context: bool = False,
):
    config.ensure_dirs()
    db = Database(config.db_path)
    db.initialize()
    store = ContentStore(config)
    content_path, content_sha = store.put_text(base_text)
    now = utcnow()
    with db.transaction() as connection:
        book_id = int(
            connection.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                ("Book", "book.epub", "book-sha", 2, now, now),
            ).lastrowid
        )
        chapter_id = int(
            connection.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (book_id, 1, "Chapter 1", len(base_text), now, now),
            ).lastrowid
        )
        status = "approved" if approved else "draft"
        base_revision_id = int(
            connection.execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                    processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    chapter_id,
                    "reflowed",
                    content_path,
                    content_sha,
                    lexical_sha256(base_text),
                    len(base_text),
                    "seed-v1",
                    status,
                    now,
                ),
            ).lastrowid
        )
        connection.execute(
            "UPDATE chapters SET active_text_revision_id=?,raw_text_revision_id=? WHERE id=?",
            (base_revision_id, base_revision_id, chapter_id),
        )
        other_path, other_sha = store.put_text("Other chapter text.")
        other_chapter_id = int(
            connection.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (book_id, 2, "Chapter 2", 17, now, now),
            ).lastrowid
        )
        other_revision_id = int(
            connection.execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                    processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    other_chapter_id,
                    "reflowed",
                    other_path,
                    other_sha,
                    lexical_sha256("Other chapter text."),
                    len("Other chapter text."),
                    "seed-v1",
                    "approved",
                    now,
                ),
            ).lastrowid
        )
        connection.execute(
            "UPDATE chapters SET active_text_revision_id=?,raw_text_revision_id=? WHERE id=?",
            (other_revision_id, other_revision_id, other_chapter_id),
        )
        character_id = None
        if create_review_context:
            character_id = int(
                connection.execute(
                    """INSERT INTO characters(
                        book_id,display_name,default_voice_id,gender,canonical_name,
                        canonical_name_normalized,role,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (book_id, "An", "", "male", "An", "an", "main", now, now),
                ).lastrowid
            )
            connection.execute(
                """INSERT INTO book_voice_profiles(
                    book_id,narrator_voice_id,male_dialogue_voice_id,female_dialogue_voice_id,
                    unknown_fallback,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (book_id, "narrator", "male", "female", "narrator", now, now),
            )
    return {
        "db": db,
        "store": store,
        "book_id": book_id,
        "chapter_id": chapter_id,
        "base_revision_id": base_revision_id,
        "other_chapter_id": other_chapter_id,
        "other_revision_id": other_revision_id,
        "character_id": character_id,
        "base_text": base_text,
    }


class TargetedTextCorrectionServiceTests(IsolatedTestCase):
    def _config_for(self, name: str):
        return make_config(self.temp_root / name)

    def test_mojibake_base_can_be_replaced_only_with_valid_canonical_text(self) -> None:
        correct = 'Trời vừa sáng. "Chào anh, tôi đã đợi từ sớm."'
        malformed = legacy_decode_utf8(correct)
        seeded = seed_correction_fixture(
            self._config_for("encoding-remediation"),
            base_text=malformed,
        )
        before = seeded["db"].fetch_one(
            "SELECT COUNT(*) AS n FROM text_revisions"
        )["n"]
        result = apply_targeted_text_correction(
            seeded["db"],
            seeded["store"],
            chapter_id=seeded["chapter_id"],
            base_revision_id=seeded["base_revision_id"],
            expected_text=malformed,
            replacement_text=correct,
            reason="Exact deterministic encoding remediation",
        )
        self.assertEqual(result["char_count"], len(correct))
        self.assertEqual(
            seeded["store"].read_text(result["content_path"]),
            correct,
        )
        self.assertEqual(
            seeded["db"].fetch_one("SELECT COUNT(*) AS n FROM text_revisions")["n"],
            before + 1,
        )

        second = seed_correction_fixture(
            self._config_for("encoding-rejected"),
            base_text="Valid base text.",
        )
        with self.assertRaises(TextCorrectionError):
            apply_targeted_text_correction(
                second["db"],
                second["store"],
                chapter_id=second["chapter_id"],
                base_revision_id=second["base_revision_id"],
                expected_text="Valid",
                replacement_text=legacy_decode_utf8("Trời"),
                reason="Invalid replacement must fail",
            )
        self.assertEqual(
            second["db"].fetch_one("SELECT COUNT(*) AS n FROM text_revisions")["n"],
            2,
        )

    def test_exact_one_match_creates_new_active_revision_and_preserves_old_revision(self) -> None:
        seeded = seed_correction_fixture(self._config_for("success"))
        db = seeded["db"]
        store = seeded["store"]
        before_revision = dict(
            db.fetch_one("SELECT * FROM text_revisions WHERE id=?", (seeded["base_revision_id"],))
        )

        result = apply_targeted_text_correction(
            db,
            store,
            chapter_id=seeded["chapter_id"],
            base_revision_id=seeded["base_revision_id"],
            expected_text=EXPECTED_TEXT,
            replacement_text=REPLACEMENT_TEXT,
            reason="Fix malformed punctuation span.",
        )

        self.assertEqual(result["old_active_revision_id"], seeded["base_revision_id"])
        self.assertNotEqual(result["new_active_revision_id"], seeded["base_revision_id"])
        self.assertEqual(result["kind"], "repaired")
        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["parent_revision_id"], seeded["base_revision_id"])
        self.assertEqual(result["processor_version"], TARGETED_CORRECTION_PROCESSOR_VERSION)
        self.assertTrue(result["is_active"])
        self.assertEqual(result["replacement_occurrence_count"], 1)

        chapter = db.fetch_one("SELECT active_text_revision_id FROM chapters WHERE id=?", (seeded["chapter_id"],))
        self.assertEqual(int(chapter["active_text_revision_id"]), result["new_active_revision_id"])

        new_revision = db.fetch_one("SELECT * FROM text_revisions WHERE id=?", (result["new_active_revision_id"],))
        corrected_text = store.read_text(str(new_revision["content_path"]))
        self.assertEqual(corrected_text, seeded["base_text"].replace(EXPECTED_TEXT, REPLACEMENT_TEXT, 1))
        self.assertEqual(str(new_revision["content_sha256"]), result["content_sha256"])
        self.assertEqual(str(new_revision["lexical_sha256"]), result["lexical_sha256"])
        self.assertEqual(int(new_revision["char_count"]), result["char_count"])
        self.assertEqual(str(new_revision["status"]), "approved")

        old_revision = dict(db.fetch_one("SELECT * FROM text_revisions WHERE id=?", (seeded["base_revision_id"],)))
        self.assertEqual(before_revision, old_revision)
        self.assertEqual(store.read_text(str(old_revision["content_path"])), seeded["base_text"])

        counts = {
            table: int(db.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"])
            for table in (
                "jobs",
                "job_chapters",
                "repair_blocks",
                "casting_plans",
                "segments",
                "segment_attempts",
                "artifacts",
                "speaker_assignment_drafts",
            )
        }
        self.assertEqual(
            counts,
            {
                "jobs": 0,
                "job_chapters": 0,
                "repair_blocks": 0,
                "casting_plans": 0,
                "segments": 0,
                "segment_attempts": 0,
                "artifacts": 0,
                "speaker_assignment_drafts": 0,
            },
        )
        audit = db.fetch_one(
            "SELECT event_code, details_json FROM audit_events WHERE chapter_id=? ORDER BY id DESC LIMIT 1",
            (seeded["chapter_id"],),
        )
        self.assertEqual(str(audit["event_code"]), "text_revision_targeted_corrected")
        self.assertIn('"base_revision_id"', str(audit["details_json"]))

    def test_zero_and_multiple_occurrence_validations_fail_without_mutation(self) -> None:
        cases = [
            ("zero", BASE_TEXT, "missing"),
            ("multiple", ALT_TEXT, "Trời mưa."),
        ]
        for _label, text, expected in cases:
            with self.subTest(case=_label):
                seeded = seed_correction_fixture(self._config_for(_label), base_text=text)
                db = seeded["db"]
                store = seeded["store"]
                with self.assertRaises(TextCorrectionError):
                    apply_targeted_text_correction(
                        db,
                        store,
                        chapter_id=seeded["chapter_id"],
                        base_revision_id=seeded["base_revision_id"],
                        expected_text=expected,
                        replacement_text="X",
                        reason="test",
                    )
                self.assertEqual(
                    int(db.fetch_one("SELECT COUNT(*) AS n FROM text_revisions WHERE chapter_id=?", (seeded["chapter_id"],))["n"]),
                    1,
                )
                self.assertEqual(
                    int(db.fetch_one("SELECT active_text_revision_id FROM chapters WHERE id=?", (seeded["chapter_id"],))["active_text_revision_id"]),
                    seeded["base_revision_id"],
                )

    def test_inactive_base_other_chapter_unapproved_and_invalid_inputs_are_rejected(self) -> None:
        seeded = seed_correction_fixture(self._config_for("conflict"))
        db = seeded["db"]
        store = seeded["store"]

        first = apply_targeted_text_correction(
            db,
            store,
            chapter_id=seeded["chapter_id"],
            base_revision_id=seeded["base_revision_id"],
            expected_text=EXPECTED_TEXT,
            replacement_text=REPLACEMENT_TEXT,
            reason="first pass",
        )
        with self.assertRaises(TextCorrectionConflict):
            apply_targeted_text_correction(
                db,
                store,
                chapter_id=seeded["chapter_id"],
                base_revision_id=seeded["base_revision_id"],
                expected_text=EXPECTED_TEXT,
                replacement_text=REPLACEMENT_TEXT,
                reason="retry old base",
            )
        self.assertEqual(
            int(db.fetch_one("SELECT COUNT(*) AS n FROM text_revisions WHERE chapter_id=?", (seeded["chapter_id"],))["n"]),
            2,
        )
        self.assertEqual(first["new_active_revision_id"], int(db.fetch_one(
            "SELECT active_text_revision_id FROM chapters WHERE id=?",
            (seeded["chapter_id"],),
        )["active_text_revision_id"]))

        with self.assertRaises(TextCorrectionNotFound):
            apply_targeted_text_correction(
                db,
                store,
                chapter_id=seeded["chapter_id"],
                base_revision_id=seeded["other_revision_id"],
                expected_text="Other",
                replacement_text="New",
                reason="wrong chapter",
            )

        unapproved = seed_correction_fixture(self._config_for("unapproved"), approved=False)
        with self.assertRaises(TextCorrectionConflict):
            apply_targeted_text_correction(
                unapproved["db"],
                unapproved["store"],
                chapter_id=unapproved["chapter_id"],
                base_revision_id=unapproved["base_revision_id"],
                expected_text=EXPECTED_TEXT,
                replacement_text=REPLACEMENT_TEXT,
                reason="draft base",
            )

        invalid_cases = [
            {"expected_text": "", "replacement_text": "x", "reason": "why"},
            {"expected_text": EXPECTED_TEXT, "replacement_text": EXPECTED_TEXT, "reason": "same"},
            {"expected_text": EXPECTED_TEXT, "replacement_text": "x", "reason": "   "},
        ]
        seeded_again = seed_correction_fixture(self._config_for("invalid-inputs"))
        for case in invalid_cases:
            with self.subTest(case=case), self.assertRaises(TextCorrectionError):
                apply_targeted_text_correction(
                    seeded_again["db"],
                    seeded_again["store"],
                    chapter_id=seeded_again["chapter_id"],
                    base_revision_id=seeded_again["base_revision_id"],
                    expected_text=case["expected_text"],
                    replacement_text=case["replacement_text"],
                    reason=case["reason"],
                )

    def test_transaction_failure_rolls_back_insert_and_active_revision_change(self) -> None:
        seeded = seed_correction_fixture(self._config_for("rollback"))
        db = seeded["db"]
        store = seeded["store"]
        with patch("story_audio.text_correction._activate_corrected_revision", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                apply_targeted_text_correction(
                    db,
                    store,
                    chapter_id=seeded["chapter_id"],
                    base_revision_id=seeded["base_revision_id"],
                    expected_text=EXPECTED_TEXT,
                    replacement_text=REPLACEMENT_TEXT,
                    reason="rollback check",
                )
        self.assertEqual(
            int(db.fetch_one("SELECT COUNT(*) AS n FROM text_revisions WHERE chapter_id=?", (seeded["chapter_id"],))["n"]),
            1,
        )
        self.assertEqual(
            int(db.fetch_one("SELECT active_text_revision_id FROM chapters WHERE id=?", (seeded["chapter_id"],))["active_text_revision_id"]),
            seeded["base_revision_id"],
        )

    def test_existing_speaker_draft_becomes_stale_after_active_revision_changes(self) -> None:
        correction_config = self._config_for("stale-draft")
        seeded = seed_correction_fixture(correction_config, create_review_context=True)
        db = seeded["db"]
        store = seeded["store"]
        with patch.object(type(correction_config), "gemini_key", return_value="fake-key"):
            draft = generate_speaker_assignment_draft(
                db,
                store,
                correction_config,
                chapter_id=seeded["chapter_id"],
                provider=lambda **kwargs: _fake_assignment_response(kwargs["request_data"], seeded["character_id"]),
            )
        before = dict(db.fetch_one("SELECT * FROM speaker_assignment_drafts WHERE id=?", (draft["id"],)))

        apply_targeted_text_correction(
            db,
            store,
            chapter_id=seeded["chapter_id"],
            base_revision_id=seeded["base_revision_id"],
            expected_text=EXPECTED_TEXT,
            replacement_text=REPLACEMENT_TEXT,
            reason="fix quote punctuation",
        )

        detail = get_speaker_review_draft(
            db,
            store,
            correction_config,
            chapter_id=seeded["chapter_id"],
            draft_id=draft["id"],
        )
        self.assertTrue(detail["stale"])
        self.assertIn("TextRevision changed", " ".join(detail["stale_reasons"]))
        self.assertTrue(detail["review_rows"])
        after = dict(db.fetch_one("SELECT * FROM speaker_assignment_drafts WHERE id=?", (draft["id"],)))
        self.assertEqual(before, after)


class TargetedTextCorrectionApiTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config = self._config_for("api")
        self.seeded = seed_correction_fixture(self.config)
        self.db = self.seeded["db"]
        self.store = self.seeded["store"]
        self._multipart_patcher = patch(
            "fastapi.dependencies.utils.ensure_multipart_is_installed",
            lambda: None,
        )
        self._multipart_patcher.start()
        import story_audio.api as api_module

        self._original_db = api_module.db
        self._original_store = api_module.store
        self._original_settings = api_module.settings
        api_module.db = self.db
        api_module.store = self.store
        api_module.settings = self.config
        from story_audio.api import app

        self.client = TestClient(app)

    def _config_for(self, name: str):
        return make_config(self.temp_root / name)

    def tearDown(self) -> None:
        import story_audio.api as api_module

        api_module.db = self._original_db
        api_module.store = self._original_store
        api_module.settings = self._original_settings
        self._multipart_patcher.stop()
        super().tearDown()

    def test_success_response_contract(self) -> None:
        response = self.client.post(
            f"/api/chapters/{self.seeded['chapter_id']}/text-revisions/targeted-correction",
            json={
                "base_revision_id": self.seeded["base_revision_id"],
                "expected_text": EXPECTED_TEXT,
                "replacement_text": REPLACEMENT_TEXT,
                "reason": "Fix malformed punctuation.",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["chapter_id"], self.seeded["chapter_id"])
        self.assertEqual(data["old_active_revision_id"], self.seeded["base_revision_id"])
        self.assertNotEqual(data["new_active_revision_id"], self.seeded["base_revision_id"])
        self.assertEqual(data["parent_revision_id"], self.seeded["base_revision_id"])
        self.assertEqual(data["kind"], "repaired")
        self.assertEqual(data["status"], "approved")
        self.assertEqual(data["processor_version"], TARGETED_CORRECTION_PROCESSOR_VERSION)
        self.assertEqual(data["replacement_occurrence_count"], 1)
        self.assertTrue(data["is_active"])

    def test_error_classifications_and_no_partial_mutation(self) -> None:
        zero = self.client.post(
            f"/api/chapters/{self.seeded['chapter_id']}/text-revisions/targeted-correction",
            json={
                "base_revision_id": self.seeded["base_revision_id"],
                "expected_text": "missing",
                "replacement_text": "value",
                "reason": "bad request",
            },
        )
        self.assertEqual(zero.status_code, 400)

        wrong_chapter = self.client.post(
            f"/api/chapters/{self.seeded['chapter_id']}/text-revisions/targeted-correction",
            json={
                "base_revision_id": self.seeded["other_revision_id"],
                "expected_text": "Other",
                "replacement_text": "New",
                "reason": "wrong chapter",
            },
        )
        self.assertEqual(wrong_chapter.status_code, 404)

        success = self.client.post(
            f"/api/chapters/{self.seeded['chapter_id']}/text-revisions/targeted-correction",
            json={
                "base_revision_id": self.seeded["base_revision_id"],
                "expected_text": EXPECTED_TEXT,
                "replacement_text": REPLACEMENT_TEXT,
                "reason": "first pass",
            },
        )
        self.assertEqual(success.status_code, 200)

        stale = self.client.post(
            f"/api/chapters/{self.seeded['chapter_id']}/text-revisions/targeted-correction",
            json={
                "base_revision_id": self.seeded["base_revision_id"],
                "expected_text": EXPECTED_TEXT,
                "replacement_text": REPLACEMENT_TEXT,
                "reason": "retry",
            },
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS n FROM text_revisions WHERE chapter_id=?", (self.seeded["chapter_id"],))["n"]),
            2,
        )


if __name__ == "__main__":
    unittest.main()
