from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import story_audio.api as api_module
from story_audio.backup import create_backup, restore_backup
from story_audio.character_bible import (
    CharacterBibleError,
    SCHEMA,
    apply_character_bible_import,
    normalize_identity,
    parse_character_bible,
    plan_character_bible_import,
)
from story_audio.casting import create_character
from story_audio.db import Database, utcnow
from story_audio.integrity import check_data_integrity
from story_audio.voice_profile import get_book_voice_profile, resolve_voice, set_book_voice_profile
from tests.test_recovery import make_config


VOICES = {"narrator", "male", "female", "override", "legacy"}


def bible_bytes(characters, *, schema: str = SCHEMA) -> bytes:
    return json.dumps(
        {"schema": schema, "book": {"title": "Quang Âm Chi Ngoại"}, "characters": characters},
        ensure_ascii=False,
    ).encode("utf-8")


def record(
    key: str,
    name: str,
    *,
    aliases=None,
    gender="unknown",
    role="unknown",
    age_group="unknown",
    voice=None,
    description="",
):
    return {
        "external_key": key,
        "canonical_name": name,
        "aliases": aliases or [],
        "gender": gender,
        "role": role,
        "age_group": age_group,
        "description": description,
        "speech_style": "",
        "visual_notes": "",
        "notes": "",
        "voice_override_id": voice,
    }


def seed(root: Path):
    config = make_config(root)
    config.ensure_dirs()
    db = Database(config.db_path)
    db.initialize()
    now = utcnow()
    with db.connect() as connection:
        book_id = int(connection.execute(
            "INSERT INTO books(title,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?)",
            ("Book", "book.epub", "book-sha", now, now),
        ).lastrowid)
    profile = set_book_voice_profile(
        db, book_id, narrator_voice_id="narrator", male_dialogue_voice_id="male",
        female_dialogue_voice_id="female", allowed_voice_ids=VOICES,
    )
    legacy = create_character(db, book_id, "Smoke An", "legacy")
    with db.connect() as connection:
        connection.execute(
            "UPDATE characters SET description='keep me' WHERE id=?", (legacy["id"],)
        )
        connection.execute(
            """INSERT INTO jobs(book_id,status,from_chapter,to_chapter,voice_name,repair_mode,
               output_format,settings_json,total_chapters,scheduled_at,created_at,updated_at,
               casting_snapshot_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (book_id, "completed", 1, 1, "narrator", "off", "m4a", "{}", 0,
             now, now, now, '{"immutable":"snapshot"}'),
        )
    return config, db, book_id, profile, legacy


class CharacterBibleTests(unittest.TestCase):
    def test_parse_valid_json_preserves_vietnamese_and_normalizes_without_removing_marks(self) -> None:
        parsed = parse_character_bible(bible_bytes([
            record("char_hua", "  Hứa   Thanh ", aliases=["Hứa công tử"], gender="male", role="main")
        ]), source_label=r"C:\private\character_bible.json")
        self.assertEqual(parsed.records[0]["canonical_name"], "Hứa Thanh")
        self.assertEqual(parsed.source_label, "character_bible.json")
        self.assertEqual(normalize_identity("HỨA Thanh"), "hứa thanh")
        self.assertNotEqual(normalize_identity("Hứa Thanh"), normalize_identity("Hua Thanh"))

    def test_invalid_json_schema_duplicates_and_enums_are_rejected_safely(self) -> None:
        with self.assertRaises(CharacterBibleError):
            parse_character_bible(b"not-json")
        with self.assertRaises(CharacterBibleError):
            parse_character_bible(bible_bytes([], schema="future/v2"))
        parsed = parse_character_bible(bible_bytes([
            record("same", "A", gender="invalid"), record("SAME", " a ")
        ]))
        self.assertTrue(all(item["errors"] for item in parsed.records))
        self.assertTrue(any("duplicate normalized external_key" in error for error in parsed.records[0]["errors"]))
        self.assertTrue(any("duplicate normalized canonical_name" in error for error in parsed.records[1]["errors"]))

    def test_alias_validation_and_generic_alias_warning(self) -> None:
        parsed = parse_character_bible(bible_bytes([
            record("a", "Hứa Thanh", aliases=["hắn", "Hứa Thanh", ""])
        ]))
        item = parsed.records[0]
        self.assertTrue(any("generic alias" in warning for warning in item["warnings"]))
        self.assertTrue(any("duplicates canonical" in error for error in item["errors"]))
        self.assertTrue(any("must not be empty" in error for error in item["errors"]))

    def test_dry_run_is_read_only_and_apply_creates_aliases_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, db, book, _profile, _legacy = seed(Path(directory))
            parsed = parse_character_bible(bible_bytes([
                record("char_binh", "Smoke Bình", aliases=["Bình"], gender="female", role="supporting")
            ]))
            before = dict(db.fetch_one("SELECT COUNT(*) AS chars,(SELECT COUNT(*) FROM character_aliases) AS aliases FROM characters"))
            plan = plan_character_bible_import(db, book, parsed, allowed_voice_ids=VOICES)
            self.assertEqual(plan["summary"]["create_count"], 1)
            self.assertEqual(before, dict(db.fetch_one("SELECT COUNT(*) AS chars,(SELECT COUNT(*) FROM character_aliases) AS aliases FROM characters")))
            result = apply_character_bible_import(db, plan)
            self.assertTrue(result["applied"])
            created = db.fetch_one("SELECT * FROM characters WHERE external_key='char_binh'")
            self.assertEqual(created["canonical_name"], "Smoke Bình")
            self.assertEqual(created["gender"], "female")
            self.assertIsNone(created["voice_override_id"])
            self.assertEqual(db.fetch_one("SELECT alias FROM character_aliases")["alias"], "Bình")
            self.assertNotIn(str(Path(directory).resolve()), created["bible_source_label"])

    def test_reimport_is_idempotent_without_timestamp_or_import_row_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, db, book, _profile, _legacy = seed(Path(directory))
            raw = bible_bytes([record("char_binh", "Bình", aliases=["B"] , gender="female")])
            parsed = parse_character_bible(raw)
            apply_character_bible_import(db, plan_character_bible_import(db, book, parsed, allowed_voice_ids=VOICES))
            before = dict(db.fetch_one("SELECT id,updated_at,bible_last_imported_at FROM characters WHERE external_key='char_binh'"))
            imports_before = db.fetch_one("SELECT COUNT(*) AS n FROM character_bible_imports")["n"]
            second = plan_character_bible_import(db, book, parsed, allowed_voice_ids=VOICES)
            self.assertEqual(second["records"][0]["action"], "match")
            result = apply_character_bible_import(db, second)
            self.assertFalse(result["applied"])
            self.assertEqual(before, dict(db.fetch_one("SELECT id,updated_at,bible_last_imported_at FROM characters WHERE external_key='char_binh'")))
            self.assertEqual(imports_before, db.fetch_one("SELECT COUNT(*) AS n FROM character_bible_imports")["n"])

    def test_match_priority_external_canonical_and_unique_alias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, db, book, _profile, legacy = seed(Path(directory))
            first = parse_character_bible(bible_bytes([
                record("char_an", "Smoke An", aliases=["An"], gender="male", role="main")
            ]))
            plan = plan_character_bible_import(db, book, first, allowed_voice_ids=VOICES)
            self.assertEqual(plan["records"][0]["character_id"], legacy["id"])
            apply_character_bible_import(db, plan)
            external = plan_character_bible_import(db, book, first, allowed_voice_ids=VOICES)
            self.assertEqual(external["records"][0]["character_id"], legacy["id"])
            other = create_character(db, book, "Bình", None)
            with db.connect() as connection:
                connection.execute(
                    "INSERT INTO character_aliases(book_id,character_id,alias,alias_normalized,created_at) VALUES(?,?,?,?,?)",
                    (book, other["id"], "Bình nhỏ", normalize_identity("Bình nhỏ"), utcnow()),
                )
            alias_plan = plan_character_bible_import(db, book, parse_character_bible(bible_bytes([
                record("char_binh", "Bình nhỏ", gender="female")
            ])), allowed_voice_ids=VOICES)
            self.assertEqual(alias_plan["records"][0]["character_id"], other["id"])

    def test_ambiguous_alias_and_cross_identity_are_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, db, book, _profile, legacy = seed(Path(directory))
            other = create_character(db, book, "Other", None)
            now = utcnow()
            with db.connect() as connection:
                for character_id in (legacy["id"], other["id"]):
                    connection.execute(
                        "INSERT INTO character_aliases(book_id,character_id,alias,alias_normalized,created_at) VALUES(?,?,?,?,?)",
                        (book, character_id, "Boss", "boss", now),
                    )
                connection.execute(
                    "UPDATE characters SET external_key='other',external_key_normalized='other' WHERE id=?",
                    (other["id"],),
                )
            ambiguous = plan_character_bible_import(db, book, parse_character_bible(bible_bytes([
                record("new", "Boss")
            ])), allowed_voice_ids=VOICES)
            self.assertEqual(ambiguous["records"][0]["action"], "conflict")
            cross = plan_character_bible_import(db, book, parse_character_bible(bible_bytes([
                record("other", "Smoke An")
            ])), allowed_voice_ids=VOICES)
            self.assertEqual(cross["records"][0]["action"], "conflict")

    def test_metadata_policy_and_voice_override_safety(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, db, book, _profile, legacy = seed(Path(directory))
            parsed = parse_character_bible(bible_bytes([
                record("char_an", "Smoke An", gender="male", role="main",
                       description="replace me", voice=None)
            ]))
            plan = plan_character_bible_import(db, book, parsed, allowed_voice_ids=VOICES)
            apply_character_bible_import(db, plan)
            row = db.fetch_one("SELECT * FROM characters WHERE id=?", (legacy["id"],))
            self.assertEqual(row["description"], "keep me")
            self.assertEqual(row["voice_override_id"], "legacy")
            update = plan_character_bible_import(db, book, parsed, allowed_voice_ids=VOICES, update_existing=True)
            apply_character_bible_import(db, update)
            self.assertEqual(db.fetch_one("SELECT description FROM characters WHERE id=?", (legacy["id"],))["description"], "replace me")
            unknown_voice = parse_character_bible(bible_bytes([
                record("new_voice", "New Voice", gender="male", voice="missing")
            ]))
            voice_plan = plan_character_bible_import(db, book, unknown_voice, allowed_voice_ids=VOICES)
            self.assertEqual(voice_plan["summary"]["warning_count"], 1)
            apply_character_bible_import(db, voice_plan)
            self.assertIsNone(db.fetch_one("SELECT voice_override_id FROM characters WHERE external_key='new_voice'")["voice_override_id"])

    def test_new_character_without_override_uses_book_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, db, book, _profile, _legacy = seed(Path(directory))
            parsed = parse_character_bible(bible_bytes([
                record("new_male", "New Male", gender="male", role="minor")
            ]))
            apply_character_bible_import(db, plan_character_bible_import(db, book, parsed, allowed_voice_ids=VOICES))
            character = dict(db.fetch_one("SELECT * FROM characters WHERE external_key='new_male'"))
            resolved = resolve_voice(
                speaker_type="dialogue", character=character,
                book_voice_profile=get_book_voice_profile(db, book),
            )
            self.assertEqual(resolved["resolved_voice_id"], "male")
            self.assertEqual(resolved["resolution_source"], "book_male")

    def test_backend_character_bible_endpoints_return_structured_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, db, book, _profile, _legacy = seed(Path(directory))
            payload = {
                "schema": SCHEMA,
                "book": {"title": "Book"},
                "characters": [record("api_char", "API Char", aliases=["API"], gender="male", role="minor")],
            }
            request = api_module.CharacterBibleImportRequest(
                payload=payload,
                source_label=r"C:\unsafe\api.json",
            )
            with patch.object(api_module, "db", db), patch.object(
                api_module, "_preset_voice_ids", return_value=VOICES
            ):
                dry_run = api_module.dry_run_character_bible(book, request)
                applied = api_module.apply_character_bible(book, request)
            self.assertEqual(dry_run["summary"]["create_count"], 1)
            self.assertEqual(applied["result"]["changed_records"], 1)
            self.assertEqual(db.fetch_one("SELECT alias FROM character_aliases WHERE book_id=?", (book,))["alias"], "API")

    def test_import_does_not_change_job_snapshot_or_legacy_character_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, db, book, _profile, legacy = seed(Path(directory))
            snapshot = db.fetch_one("SELECT casting_snapshot_json FROM jobs")["casting_snapshot_json"]
            parsed = parse_character_bible(bible_bytes([
                record("char_an", "Smoke An", aliases=["An"], gender="male", role="main")
            ]))
            apply_character_bible_import(db, plan_character_bible_import(db, book, parsed, allowed_voice_ids=VOICES))
            self.assertEqual(db.fetch_one("SELECT id FROM characters WHERE external_key='char_an'")["id"], legacy["id"])
            self.assertEqual(db.fetch_one("SELECT casting_snapshot_json FROM jobs")["casting_snapshot_json"], snapshot)
            self.assertEqual(db.fetch_one("SELECT voice_override_id FROM characters WHERE id=?", (legacy["id"],))["voice_override_id"], "legacy")

    def test_backup_restore_preserves_character_bible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, db, book, _profile, _legacy = seed(root / "source")
            parsed = parse_character_bible(bible_bytes([
                record("char_binh", "Bình", aliases=["B"], gender="female")
            ]))
            apply_character_bible_import(db, plan_character_bible_import(db, book, parsed, allowed_voice_ids=VOICES))
            backup = root / "backup"
            create_backup(config, backup)
            restored = root / "restored" / "data"
            restore_backup(backup, restored)
            restored_db = Database(restored / "app.db")
            self.assertEqual(restored_db.fetch_one("SELECT canonical_name FROM characters WHERE external_key='char_binh'")["canonical_name"], "Bình")
            self.assertEqual(restored_db.fetch_one("SELECT alias FROM character_aliases")["alias"], "B")

    def test_doctor_detects_orphan_alias_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, db, book, _profile, _legacy = seed(Path(directory))
            connection = sqlite3.connect(config.db_path)
            try:
                connection.execute("PRAGMA foreign_keys=OFF")
                connection.execute(
                    "INSERT INTO character_aliases(book_id,character_id,alias,alias_normalized,created_at) VALUES(?,?,?,?,?)",
                    (book, 999999, "Ghost", "ghost", utcnow()),
                )
                connection.commit()
            finally:
                connection.close()
            finding = next(item for item in check_data_integrity(config) if item.name == "character_bible_integrity")
            self.assertEqual(finding.level, "ERROR")
            self.assertIn("orphan_aliases=1", finding.detail)


if __name__ == "__main__":
    unittest.main()
