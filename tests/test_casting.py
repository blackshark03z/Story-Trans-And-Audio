from __future__ import annotations

import json
import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from story_audio.casting import (
    CastingError,
    approve_plan,
    create_casting_draft,
    create_character,
    get_plan,
    split_utterances,
    update_character,
)
from story_audio.db import Database, utcnow
from story_audio.files import sha256_file
from story_audio.pipeline import PipelineWorker, create_job
from story_audio.storage import ContentStore
from story_audio.voice_eligibility import EffectiveVoiceCatalog
from tests.test_recovery import make_config


TEXT = 'Trời đã tối. "Xin chào." Anh khẽ đáp. "Tạm biệt."'
VOICES = {"narrator", "voice-a", "voice-b"}


class FakeMultiVoiceTts:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def synthesize(self, *, synth_input=None, text: str = None, voice: str = None, output_path: Path, **_kwargs):
        # Support both snapshot-based and legacy API
        if synth_input is not None:
            # Snapshot-based API (Phase 3B3-D)
            actual_text = synth_input.text
            if synth_input.voice_source_type == "preset":
                actual_voice = synth_input.preset_voice_id
            else:
                actual_voice = f"custom:{synth_input.custom_voice_revision_id}"
        else:
            # Legacy API
            actual_text = text
            actual_voice = voice

        self.calls.append((actual_voice, actual_text))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(f"{actual_voice}:{actual_text}".encode("utf-8"))
        return 1000, 48_000


def seed_casting(root: Path):
    config = make_config(root)
    config.ensure_dirs()
    db = Database(config.db_path)
    db.initialize()
    store = ContentStore(config)
    content_path, content_sha = store.put_text(TEXT)
    now = utcnow()
    with db.transaction() as connection:
        book_id = int(
            connection.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                ("Book", "book.epub", "book-sha", 1, now, now),
            ).lastrowid
        )
        chapter_id = int(
            connection.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (book_id, 1, "Chapter 1", len(TEXT), now, now),
            ).lastrowid
        )
        revision_id = int(
            connection.execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                    processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (chapter_id, "reflowed", content_path, content_sha, "lexical", len(TEXT), "test", "approved", now),
            ).lastrowid
        )
        connection.execute(
            "UPDATE chapters SET active_text_revision_id=? WHERE id=?", (revision_id, chapter_id)
        )
    character_a = create_character(db, book_id, "An", "voice-a")
    character_b = create_character(db, book_id, "Bình", "voice-b")
    utterances = split_utterances(TEXT)
    assignments = [
        {
            "utterance_id": utterance["utterance_id"],
            "role": "character" if utterance["sequence"] in {2, 4} else "narrator",
            "character_id": character_a["id"] if utterance["sequence"] == 2 else (
                character_b["id"] if utterance["sequence"] == 4 else None
            ),
        }
        for utterance in utterances
    ]
    draft = create_casting_draft(
        db,
        store,
        chapter_id=chapter_id,
        text_revision_id=revision_id,
        narrator_voice_id="narrator",
        assignments=assignments,
        allowed_voice_ids=VOICES,
    )
    approved = approve_plan(db, store, draft["id"])
    return config, db, store, book_id, chapter_id, revision_id, character_a, character_b, approved


class CastingTests(unittest.TestCase):

    def setUp(self) -> None:
        super().setUp()
        self._original_testing = os.environ.get("STORY_AUDIO_TESTING")
        os.environ["STORY_AUDIO_TESTING"] = "1"

    def tearDown(self) -> None:
        if self._original_testing is None:
            os.environ.pop("STORY_AUDIO_TESTING", None)
        else:
            os.environ["STORY_AUDIO_TESTING"] = self._original_testing
        super().tearDown()

    def test_splitter_is_deterministic_and_defaults_to_narrator(self) -> None:
        first = split_utterances(TEXT)
        second = split_utterances(TEXT)
        self.assertEqual(first, second)
        self.assertTrue(first)
        self.assertTrue(all(item["role"] == "narrator" for item in first))
        self.assertTrue(all(item["end_offset"] - item["start_offset"] <= 256 for item in first))

    def test_splitter_avoids_one_word_orphan_tail(self) -> None:
        text = (
            "- Ch\u1ee7 t\u1eed, v\u1eeba n\u00e3y ta c\u00f3 ch\u00fat kh\u00f4ng kh\u1ed1ng ch\u1ebf \u0111\u01b0\u1ee3c, "
            "ti\u1ebfp theo ta s\u1ebd ch\u1ec9 h\u1ea5p thu b\u1ea3y th\u00e0nh v\u00e0 l\u01b0u l\u1ea1i ba th\u00e0nh, "
            "nh\u01b0 v\u1eady v\u1eabn c\u00f3 th\u1ec3 b\u00e1n l\u1ea5y ti\u1ec1n, ta th\u00e2n l\u00e0 kh\u00ed linh cho n\u00ean "
            "c\u00f3 n\u1eafm ch\u1eafc l\u00e0m \u0111\u01b0\u1ee3c \u0111i\u1ec1u n\u00e0y, ch\u1ec9 c\u1ea7n ta b\u1ed1 tr\u00ed "
            "m\u1ed9t phen th\u00ec c\u1eeda h\u00e0ng r\u1ea5t kh\u00f3 ph\u00e1t hi\u1ec7n."
        )
        utterances = split_utterances(text, maximum=256)
        pieces = [text[item["start_offset"]:item["end_offset"]] for item in utterances]
        self.assertEqual(len(utterances), 2)
        self.assertNotEqual(pieces[-1], "hi\u1ec7n.")
        self.assertTrue(pieces[0].endswith("l\u00e0m \u0111\u01b0\u1ee3c \u0111i\u1ec1u n\u00e0y,"))
        self.assertTrue(pieces[1].startswith("ch\u1ec9 c\u1ea7n ta b\u1ed1 tr\u00ed"))
        self.assertIn("kh\u00f3 ph\u00e1t hi\u1ec7n.", pieces[-1])
        self.assertTrue(all(item["end_offset"] - item["start_offset"] <= 256 for item in utterances))

    def test_splitter_avoids_short_phrase_orphan_tail(self) -> None:
        text = (
            "mot mot mot mot mot mot mot mot mot mot mot mot mot mot mot mot mot mot mot mot "
            "mot mot mot mot mot mot mot mot mot mot phat hien."
        )
        utterances = split_utterances(text, maximum=60)
        pieces = [text[item["start_offset"]:item["end_offset"]] for item in utterances]
        self.assertNotIn("phat hien.", pieces)
        self.assertTrue(all(item["end_offset"] - item["start_offset"] <= 60 for item in utterances))

    def test_splitter_prefers_clause_punctuation_over_late_whitespace(self) -> None:
        text = (
            "mot mot mot mot mot mot mot mot mot mot, "
            "mot mot mot mot mot mot mot mot mot mot mot mot mot mot mot mot"
        )
        utterances = split_utterances(text, maximum=50)
        pieces = [text[item["start_offset"]:item["end_offset"]] for item in utterances]
        self.assertTrue(pieces[0].endswith(","))

    def test_splitter_falls_back_to_whitespace_when_no_punctuation_exists(self) -> None:
        text = "mot " * 30
        utterances = split_utterances(text, maximum=40)
        self.assertGreater(len(utterances), 1)
        self.assertTrue(all(text[item["start_offset"]:item["end_offset"]].strip() for item in utterances))

    def test_splitter_keeps_normal_sentence_unchanged(self) -> None:
        text = "Xin ch\u00e0o c\u1ea3 nh\u00e0."
        utterances = split_utterances(text, maximum=256)
        self.assertEqual(len(utterances), 1)
        self.assertEqual(text[utterances[0]["start_offset"]:utterances[0]["end_offset"]], text)

    def test_splitter_keeps_balanced_multisentence_quote_atomic_when_under_limit(self) -> None:
        text = (
            'Tr\u01b0\u1edbc \u0111\u00f3. '
            '"Ph\u00e1p l\u1ef1c m\u00e0u \u0111\u1ecf! Nhanh ph\u00e1 hu\u1ef7 tr\u1eadn ph\u00e1p!" '
            'Sau \u0111\u00f3.'
        )
        utterances = split_utterances(text, maximum=256)
        pieces = [text[item["start_offset"]:item["end_offset"]] for item in utterances]
        self.assertEqual(
            pieces,
            [
                "Tr\u01b0\u1edbc \u0111\u00f3.",
                '"Ph\u00e1p l\u1ef1c m\u00e0u \u0111\u1ecf! Nhanh ph\u00e1 hu\u1ef7 tr\u1eadn ph\u00e1p!"',
                "Sau \u0111\u00f3.",
            ],
        )
        self.assertTrue(pieces[1].startswith('"'))
        self.assertTrue(pieces[1].endswith('"'))

    def test_splitter_keeps_curly_multisentence_quote_atomic_when_under_limit(self) -> None:
        text = (
            "M\u1edf \u0111\u1ea7u. "
            "\u201cC\u00e2u th\u1ee9 nh\u1ea5t! C\u00e2u th\u1ee9 hai?\u201d "
            "K\u1ebft."
        )
        utterances = split_utterances(text, maximum=256)
        pieces = [text[item["start_offset"]:item["end_offset"]] for item in utterances]
        self.assertEqual(pieces[1], "\u201cC\u00e2u th\u1ee9 nh\u1ea5t! C\u00e2u th\u1ee9 hai?\u201d")

    def test_splitter_still_splits_long_balanced_quote_to_respect_limit(self) -> None:
        text = '"' + ("mot " * 40).strip() + '!"'
        utterances = split_utterances(text, maximum=50)
        pieces = [text[item["start_offset"]:item["end_offset"]] for item in utterances]
        self.assertGreater(len(pieces), 1)
        self.assertTrue(all(len(piece) <= 50 for piece in pieces))

    def test_splitter_unmatched_quote_does_not_swallow_following_narration(self) -> None:
        text = 'Tr\u01b0\u1edbc \u0111\u00f3. "C\u00e2u m\u1edf kh\u00f4ng \u0111\u00f3ng. Sau \u0111\u00f3.'
        utterances = split_utterances(text, maximum=256)
        pieces = [text[item["start_offset"]:item["end_offset"]] for item in utterances]
        self.assertEqual(
            pieces,
            ['Tr\u01b0\u1edbc \u0111\u00f3.', '"C\u00e2u m\u1edf kh\u00f4ng \u0111\u00f3ng.', 'Sau \u0111\u00f3.'],
        )

    def test_splitter_preserves_exact_text_without_overlap_or_loss(self) -> None:
        text = (
            "  \u0110\u00e2y l\u00e0 m\u1ed9t c\u00e2u h\u01a1i d\u00e0i, c\u00f3 d\u1ea5u ph\u1ea9y, c\u00f3 kho\u1ea3ng tr\u1eafng, "
            "v\u00e0 c\u00f3 c\u1ea3 ti\u1ebfng Vi\u1ec7t \u0111\u1ec3 ki\u1ec3m tra t\u00ednh to\u00e0n v\u1eb9n.  "
        )
        utterances = split_utterances(text, maximum=40)
        rebuilt: list[str] = []
        cursor = 0
        for item in utterances:
            self.assertGreaterEqual(item["start_offset"], cursor)
            self.assertLessEqual(item["end_offset"], len(text))
            rebuilt.append(text[cursor:item["start_offset"]])
            rebuilt.append(text[item["start_offset"]:item["end_offset"]])
            cursor = item["end_offset"]
        rebuilt.append(text[cursor:])
        self.assertEqual("".join(rebuilt), text)
        self.assertTrue(all(item["end_offset"] - item["start_offset"] <= 40 for item in utterances))

    def test_splitter_preserves_unicode_with_punctuation_aware_boundary(self) -> None:
        text = (
            "Ng\u1ecdc Lan k\u1ec3: m\u1ed9t c\u00e2u r\u1ea5t d\u00e0i, c\u00f3 d\u1ea5u ph\u1ea9y, c\u00f3 d\u1ea5u ch\u1ea5m ph\u1ea9y; "
            "v\u00e0 c\u00f2n c\u1ea3 d\u1ea5u n\u1eb7ng \u0111\u1ec3 ki\u1ec3m tra Unicode."
        )
        utterances = split_utterances(text, maximum=64)
        rebuilt: list[str] = []
        cursor = 0
        for item in utterances:
            rebuilt.append(text[cursor:item["start_offset"]])
            rebuilt.append(text[item["start_offset"]:item["end_offset"]])
            cursor = item["end_offset"]
        rebuilt.append(text[cursor:])
        self.assertEqual("".join(rebuilt), text)
        self.assertTrue(all(item["end_offset"] - item["start_offset"] <= 64 for item in utterances))

    def test_casting_does_not_create_text_revision_and_approved_plan_is_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, _book, _chapter, _revision, character, _b, approved = seed_casting(Path(directory))
            count_before = db.fetch_one("SELECT COUNT(*) AS n FROM text_revisions")["n"]
            sha_before = approved["plan_sha256"]
            update_character(db, character["id"], voice_id="voice-b")
            same = approve_plan(db, store, approved["id"])
            self.assertEqual(same["plan_sha256"], sha_before)
            self.assertEqual(db.fetch_one("SELECT COUNT(*) AS n FROM text_revisions")["n"], count_before)

    def test_character_from_another_book_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, db, store, _book, chapter, revision, *_rest = seed_casting(Path(directory))
            now = utcnow()
            with db.connect() as connection:
                other_book = int(connection.execute(
                    "INSERT INTO books(title,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?)",
                    ("Other", "other.epub", "other-sha", now, now),
                ).lastrowid)
            outsider = create_character(db, other_book, "Outsider", "voice-a")
            utterance = split_utterances(TEXT)[0]
            with self.assertRaisesRegex(CastingError, "(does not belong|does not exist|inactive|another book)"):
                create_casting_draft(
                    db, store, chapter_id=chapter, text_revision_id=revision,
                    narrator_voice_id="narrator",
                    assignments=[{"utterance_id": utterance["utterance_id"], "role": "character", "character_id": outsider["id"]}],
                    allowed_voice_ids=VOICES,
                )

    def test_plan_with_text_revision_from_another_chapter_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, book, chapter, _revision, *_rest = seed_casting(Path(directory))
            path, digest = store.put_text("Other chapter text.")
            now = utcnow()
            with db.connect() as connection:
                other_chapter = int(connection.execute(
                    "INSERT INTO chapters(book_id,chapter_number,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (book, 2, "Other", now, now),
                ).lastrowid)
                other_revision = int(connection.execute(
                    """INSERT INTO text_revisions(
                        chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                        processor_version,status,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (other_chapter, "reflowed", path, digest, "lex", 19, "test", "approved", now),
                ).lastrowid)
            with self.assertRaisesRegex(CastingError, "approved TextRevision"):
                create_casting_draft(
                    db, store, chapter_id=chapter, text_revision_id=other_revision,
                    narrator_voice_id="narrator", assignments=[], allowed_voice_ids=VOICES,
                )

    def test_job_snapshot_survives_character_default_voice_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, db, store, book, _chapter, _revision, character, _b, approved = seed_casting(Path(directory))
            result = create_job(
                db, config, book_id=book, from_chapter=1, to_chapter=1,
                voice_name="narrator", repair_mode="off", output_format="m4a",
                skip_completed=False, casting_plan_id=approved["id"], store=store,
                voice_catalog=EffectiveVoiceCatalog.from_ids(*VOICES),
            )
            snapshot_before = db.fetch_one("SELECT casting_snapshot_json FROM jobs WHERE id=?", (result["job_id"],))["casting_snapshot_json"]
            update_character(db, character["id"], voice_id="voice-b")
            snapshot_after = db.fetch_one("SELECT casting_snapshot_json FROM jobs WHERE id=?", (result["job_id"],))["casting_snapshot_json"]
            self.assertEqual(snapshot_before, snapshot_after)
            self.assertIn('"voice-a"', snapshot_after)

    def test_multi_voice_pipeline_calls_tts_in_speaker_order_and_never_mixes_speakers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, db, store, book, _chapter, _revision, _a, _b, approved = seed_casting(Path(directory))
            result = create_job(
                db, config, book_id=book, from_chapter=1, to_chapter=1,
                voice_name="narrator", repair_mode="off", output_format="m4a",
                skip_completed=False, casting_plan_id=approved["id"], store=store,
                voice_catalog=EffectiveVoiceCatalog.from_ids(*VOICES),
            )
            job = dict(db.fetch_one("SELECT * FROM jobs WHERE id=?", (result["job_id"],)))
            chapter = dict(db.fetch_one(
                """SELECT jc.*,c.chapter_number,c.title,c.book_id,b.title AS book_title
                   FROM job_chapters jc JOIN chapters c ON c.id=jc.chapter_id
                   JOIN books b ON b.id=c.book_id WHERE jc.job_id=?""", (job["id"],)
            ))
            fake = FakeMultiVoiceTts()
            worker = PipelineWorker(db, store, fake, config)
            with patch.object(worker, "_assemble", return_value=999):
                worker._process_chapter(job, chapter)
            self.assertEqual([voice for voice, _text in fake.calls], ["narrator", "voice-a", "narrator", "voice-b"])
            rows = db.fetch_all("SELECT utterance_sequence,resolved_voice_id,speaker_role FROM segments ORDER BY segment_index")
            per_utterance: dict[int, set[str]] = {}
            for row in rows:
                per_utterance.setdefault(row["utterance_sequence"], set()).add(row["resolved_voice_id"])
            self.assertTrue(all(len(voices) == 1 for voices in per_utterance.values()))

    def test_voice_change_changes_synthesis_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, db, store, book, _chapter, _revision, _a, _b, approved = seed_casting(Path(directory))
            result = create_job(
                db, config, book_id=book, from_chapter=1, to_chapter=1,
                voice_name="narrator", repair_mode="off", output_format="m4a",
                skip_completed=False, casting_plan_id=approved["id"], store=store,
                voice_catalog=EffectiveVoiceCatalog.from_ids(*VOICES),
            )
            job = dict(db.fetch_one("SELECT * FROM jobs WHERE id=?", (result["job_id"],)))
            chapter = dict(db.fetch_one("SELECT * FROM job_chapters WHERE job_id=?", (job["id"],)))
            text = store.read_text(db.fetch_one("SELECT content_path FROM text_revisions WHERE id=?", (chapter["text_revision_id"],))["content_path"])
            worker = PipelineWorker(db, store, FakeMultiVoiceTts(), config)
            segments = worker._prepare_segments(chapter["id"], chapter["text_revision_id"], text, json.loads(job["settings_json"]), chapter=chapter, fallback_voice=job["voice_name"])
            hashes = {(row["resolved_voice_id"], row["synthesis_hash"]) for row in segments}
            self.assertEqual(len({digest for _voice, digest in hashes}), len(hashes))

    def test_multi_voice_retry_reuses_verified_segment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, db, store, book, _chapter, _revision, _a, _b, approved = seed_casting(Path(directory))
            result = create_job(
                db, config, book_id=book, from_chapter=1, to_chapter=1,
                voice_name="narrator", repair_mode="off", output_format="m4a",
                skip_completed=False, casting_plan_id=approved["id"], store=store,
                voice_catalog=EffectiveVoiceCatalog.from_ids(*VOICES),
            )
            job = dict(db.fetch_one("SELECT * FROM jobs WHERE id=?", (result["job_id"],)))
            chapter = dict(db.fetch_one(
                """SELECT jc.*,c.chapter_number,c.title,c.book_id,b.title AS book_title
                   FROM job_chapters jc JOIN chapters c ON c.id=jc.chapter_id
                   JOIN books b ON b.id=c.book_id WHERE jc.job_id=?""", (job["id"],)
            ))
            revision = db.fetch_one("SELECT content_path FROM text_revisions WHERE id=?", (chapter["text_revision_id"],))
            worker = PipelineWorker(db, store, FakeMultiVoiceTts(), config)
            segments = worker._prepare_segments(
                chapter["id"], chapter["text_revision_id"], store.read_text(revision["content_path"]),
                json.loads(job["settings_json"]), chapter=chapter, fallback_voice=job["voice_name"],
            )
            verified_path = config.work_dir / f"job_{job['id']}" / "chapter_0001" / "segments" / "000001.wav"
            verified_path.parent.mkdir(parents=True, exist_ok=True)
            verified_path.write_bytes(b"verified")
            original_hash = sha256_file(verified_path)
            with db.connect() as connection:
                connection.execute(
                    "UPDATE segments SET status='verified',wav_path=?,audio_sha256=?,duration_ms=1000 WHERE id=?",
                    (str(verified_path), original_hash, segments[0]["id"]),
                )
                connection.execute("UPDATE segments SET status='failed' WHERE id=?", (segments[1]["id"],))
            fake = FakeMultiVoiceTts()
            worker = PipelineWorker(db, store, fake, config)
            with patch.object(worker, "_assemble", return_value=999):
                worker._process_chapter(job, chapter)
            self.assertEqual(sha256_file(verified_path), original_hash)
            self.assertEqual([voice for voice, _ in fake.calls], ["voice-a", "narrator", "voice-b"])

    def test_timeline_contains_speaker_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, db, store, book, _chapter, _revision, _a, _b, approved = seed_casting(Path(directory))
            result = create_job(
                db, config, book_id=book, from_chapter=1, to_chapter=1,
                voice_name="narrator", repair_mode="off", output_format="m4a",
                skip_completed=False, casting_plan_id=approved["id"], store=store,
                voice_catalog=EffectiveVoiceCatalog.from_ids(*VOICES),
            )
            job = dict(db.fetch_one("SELECT * FROM jobs WHERE id=?", (result["job_id"],)))
            chapter = dict(db.fetch_one(
                """SELECT jc.*,c.chapter_number,c.title,c.book_id,b.title AS book_title
                   FROM job_chapters jc JOIN chapters c ON c.id=jc.chapter_id
                   JOIN books b ON b.id=c.book_id WHERE jc.job_id=?""", (job["id"],)
            ))
            revision = db.fetch_one("SELECT * FROM text_revisions WHERE id=?", (chapter["text_revision_id"],))
            worker = PipelineWorker(db, store, FakeMultiVoiceTts(), config)
            segments = worker._prepare_segments(
                chapter["id"], chapter["text_revision_id"], store.read_text(revision["content_path"]),
                json.loads(job["settings_json"]), chapter=chapter, fallback_voice=job["voice_name"],
            )
            segment_dir = config.work_dir / f"job_{job['id']}" / "chapter_0001" / "segments"
            segment_dir.mkdir(parents=True, exist_ok=True)
            with db.connect() as connection:
                for row in segments:
                    wav = segment_dir / f"{row['segment_index']:06d}.wav"
                    wav.write_bytes(b"wav")
                    connection.execute(
                        "UPDATE segments SET status='verified',wav_path=?,audio_sha256=?,duration_ms=1000 WHERE id=?",
                        (str(wav), sha256_file(wav), row["id"]),
                    )
            def fake_command(command):
                Path(command[-1]).write_bytes(b"audio")
            with patch.object(worker, "_run_command", side_effect=fake_command), patch.object(worker, "_ffprobe_ms", return_value=4000):
                worker._assemble(job, chapter, chapter["text_revision_id"], config.work_dir / f"job_{job['id']}" / "chapter_0001")
                first_artifacts = [dict(row) for row in db.fetch_all(
                    "SELECT path,sha256 FROM artifacts WHERE job_chapter_id=?", (chapter["id"],)
                )]
                worker._assemble(job, chapter, chapter["text_revision_id"], config.work_dir / f"job_{job['id']}" / "chapter_0001")
            self.assertTrue(all(sha256_file(Path(row["path"])) == row["sha256"] for row in first_artifacts))
            timeline = next(config.output_dir.rglob("segment_timeline.json"))
            payload = json.loads(timeline.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual([item["voice_id"] for item in payload["items"]], ["narrator", "voice-a", "narrator", "voice-b"])
            self.assertEqual(payload["items"][1]["character_name"], "An")
            self.assertIn("resolution_source", payload["items"][1])
            self.assertIn("needs_review", payload["items"][1])


if __name__ == "__main__":
    unittest.main()
