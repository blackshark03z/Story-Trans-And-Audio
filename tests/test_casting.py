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
            with self.assertRaisesRegex(CastingError, "does not belong"):
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
