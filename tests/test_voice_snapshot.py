"""
tests/test_voice_snapshot.py
Phase 3A Slice 2: voice snapshot construction tests.
"""
import hashlib
import json
import os
import unittest


from tests.base import IsolatedTestCase
from story_audio.db import Database, utcnow
from story_audio.storage import ContentStore
from story_audio.files import sha256_text
from story_audio.config import Settings


def _make_job_fixture(db, store):
    """Create minimal but schema-valid book/chapter/revision/job/job_chapter."""
    now = utcnow()
    with db.connect() as conn:
        book_id = conn.execute(
            "INSERT INTO books(title, source_path, source_sha256, chapter_count, created_at, updated_at) VALUES(?,?,?,?,?,?)",
            ("TestBook", "/test/fake.epub", "a"*64, 1, now, now)
        ).lastrowid
        chapter_id = conn.execute(
            "INSERT INTO chapters(book_id, title, chapter_number, created_at, updated_at) VALUES(?,?,?,?,?)",
            (book_id, "Ch1", 1, now, now)
        ).lastrowid
        content_path, sha = store.put_text("Narrator says something interesting.")
        rev_id = conn.execute(
            "INSERT INTO text_revisions(chapter_id, kind, content_path, content_sha256, lexical_sha256, char_count, processor_version, status, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (chapter_id, "imported", content_path, sha, sha, 38, "test-1.0", "approved", now)
        ).lastrowid
        conn.execute("UPDATE chapters SET active_text_revision_id=? WHERE id=?", (rev_id, chapter_id))
        job_id = conn.execute(
            """INSERT INTO jobs(book_id, status, from_chapter, to_chapter, voice_name,
               repair_mode, output_format, settings_json, skip_completed, pause_requested,
               cancel_requested, total_chapters, completed_chapters, failed_chapters,
               scheduled_at, created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (book_id, "pending", 1, 1, "duc_tri", "auto", "mp3", "{}", 1, 0, 0, 1, 0, 0, now, now, now)
        ).lastrowid
        jc_id = conn.execute(
            "INSERT INTO job_chapters(job_id, chapter_id, sequence, status) VALUES(?,?,?,?)",
            (job_id, chapter_id, 1, "pending")
        ).lastrowid
    return book_id, chapter_id, rev_id, job_id, jc_id


def _make_custom_voice(db, store, transcript="Hello reference"):
    """Create a custom voice with one revision."""
    now = utcnow()
    audio_data = b"FAKE_AUDIO_DATA_FOR_TEST"
    audio_sha = hashlib.sha256(audio_data).hexdigest()
    transcript_sha = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
    # Store fake audio file
    audio_rel = f"audio/{audio_sha[:2]}/{audio_sha}.wav"
    audio_abs = store.config.blobs_dir / "audio" / audio_sha[:2] / f"{audio_sha}.wav"
    audio_abs.parent.mkdir(parents=True, exist_ok=True)
    audio_abs.write_bytes(audio_data)
    with db.connect() as conn:
        cv_id = conn.execute(
            "INSERT INTO custom_voices(display_name, is_active, created_at, updated_at) VALUES(?,?,?,?)",
            ("TestVoice", 1, now, now)
        ).lastrowid
        rev_id = conn.execute(
            """INSERT INTO custom_voice_revisions(
                custom_voice_id, revision_number, audio_storage_key, audio_sha256,
                reference_transcript, transcript_sha256, duration_ms, sample_rate,
                channels, audio_format, created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (cv_id, 1, audio_rel, audio_sha, transcript, transcript_sha, 1000, 22050, 1, "wav", now)
        ).lastrowid
    return cv_id, rev_id, audio_sha, audio_rel, transcript, transcript_sha


def _make_worker(db, store, config):
    """Create a bare PipelineWorker with minimal config."""
    from story_audio.pipeline import PipelineWorker
    worker = PipelineWorker.__new__(PipelineWorker)
    worker.db = db
    worker.store = store
    worker.config = config
    return worker


SNAP = {"engine_version": "vieneu:v3turbo", "max_chars": 256, "target_chars": 200, "speed": 1.0}


class TestPresetSnapshot(IsolatedTestCase):
    def test_preset_snapshot_fields(self):
        """Preset: 5 custom fields NULL, baseline populated, version=1."""
        db = Database(self.config.db_path)
        db.initialize()
        store = ContentStore(self.config)
        _, _, rev_id, _, jc_id = _make_job_fixture(db, store)
        worker = _make_worker(db, store, self.config)
        worker._prepare_segments(
            job_chapter_id=jc_id, text_revision_id=rev_id,
            text="Narrator says something interesting.",
            settings_snapshot=SNAP, fallback_voice="duc_tri",
        )
        rows = db.fetch_all("SELECT * FROM segments WHERE job_chapter_id=?", (jc_id,))
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertEqual(row["voice_source_type"], "preset")
            self.assertEqual(row["voice_provider"], "vieneu")
            self.assertEqual(row["voice_model"], "v3turbo")
            self.assertIsNotNone(row["logical_voice_ref"])
            self.assertIsNotNone(row["effective_voice_ref"])
            self.assertEqual(row["voice_snapshot_version"], 1)
            self.assertIsNone(row["custom_voice_revision_id"])
            self.assertIsNone(row["reference_audio_sha256"])
            self.assertIsNone(row["reference_audio_storage_key"])
            self.assertIsNone(row["reference_transcript"])
            self.assertIsNone(row["reference_transcript_sha256"])
            parsed = json.loads(row["synthesis_settings_json"])
            self.assertNotIn(None, parsed.values())
            self.assertIn("engine_version", parsed)


class TestCustomSnapshot(IsolatedTestCase):
    def test_custom_snapshot_exact_fields(self):
        """Custom reference: all 14 fields pinned exactly."""
        db = Database(self.config.db_path)
        db.initialize()
        store = ContentStore(self.config)
        _, _, rev_id, _, jc_id = _make_job_fixture(db, store)
        cv_id, cv_rev_id, audio_sha, storage_key, transcript, transcript_sha = _make_custom_voice(db, store)
        custom_ref = f"custom:{cv_id}"
        worker = _make_worker(db, store, self.config)
        worker._prepare_segments(
            job_chapter_id=jc_id, text_revision_id=rev_id,
            text="Narrator says something interesting.",
            settings_snapshot=SNAP, fallback_voice=custom_ref,
        )
        rows = db.fetch_all("SELECT * FROM segments WHERE job_chapter_id=?", (jc_id,))
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertEqual(row["voice_source_type"], "custom_reference")
            self.assertEqual(row["custom_voice_revision_id"], cv_rev_id)
            self.assertEqual(row["reference_audio_sha256"], audio_sha)
            self.assertEqual(row["reference_audio_storage_key"], storage_key)
            self.assertEqual(row["reference_transcript"], transcript)
            self.assertEqual(row["reference_transcript_sha256"], transcript_sha)
            self.assertEqual(row["effective_voice_ref"], custom_ref)
            self.assertNotEqual(row["voice_provider"], "custom")
            self.assertNotEqual(row["voice_model"], "custom_reference")
            self.assertEqual(row["voice_snapshot_version"], 1)
            computed = hashlib.sha256(row["reference_transcript"].encode("utf-8")).hexdigest()
            self.assertEqual(computed, row["reference_transcript_sha256"])


class TestCastingPlanProvenance(IsolatedTestCase):
    def test_null_casting_plan_id_when_no_plan(self):
        """Without a casting plan, casting_plan_id is NULL."""
        db = Database(self.config.db_path)
        db.initialize()
        store = ContentStore(self.config)
        _, _, rev_id, _, jc_id = _make_job_fixture(db, store)
        worker = _make_worker(db, store, self.config)
        worker._prepare_segments(
            job_chapter_id=jc_id, text_revision_id=rev_id,
            text="Something here.", settings_snapshot=SNAP, fallback_voice="duc_tri",
        )
        rows = db.fetch_all("SELECT * FROM segments WHERE job_chapter_id=?", (jc_id,))
        for row in rows:
            self.assertIsNone(row["casting_plan_id"])


class TestRevisionImmutability(IsolatedTestCase):
    def test_new_revision_does_not_alter_snapshot(self):
        """Adding a newer revision after job creation must not alter existing snapshot."""
        db = Database(self.config.db_path)
        db.initialize()
        store = ContentStore(self.config)
        _, _, rev_id, _, jc_id = _make_job_fixture(db, store)
        cv_id, cv_rev_id, _, _, _, _ = _make_custom_voice(db, store)
        custom_ref = f"custom:{cv_id}"
        worker = _make_worker(db, store, self.config)
        worker._prepare_segments(
            job_chapter_id=jc_id, text_revision_id=rev_id,
            text="Something.", settings_snapshot=SNAP, fallback_voice=custom_ref,
        )
        before = db.fetch_all("SELECT * FROM segments WHERE job_chapter_id=?", (jc_id,))
        # Add second revision
        now = utcnow()
        new_t = "New reference"; new_sha = hashlib.sha256(new_t.encode()).hexdigest()
        with db.connect() as conn:
            conn.execute(
                """INSERT INTO custom_voice_revisions(
                    custom_voice_id, revision_number, audio_storage_key, audio_sha256,
                    reference_transcript, transcript_sha256, duration_ms, sample_rate,
                    channels, audio_format, created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (cv_id, 2, "audio/new.wav", "a"*64, new_t, new_sha, 2000, 22050, 1, "wav", now)
            )
        after = db.fetch_all("SELECT * FROM segments WHERE job_chapter_id=?", (jc_id,))
        for b, a in zip(before, after):
            self.assertEqual(b["custom_voice_revision_id"], a["custom_voice_revision_id"])
            self.assertEqual(b["reference_audio_sha256"], a["reference_audio_sha256"])
            self.assertEqual(b["reference_transcript"], a["reference_transcript"])


class TestVoiceDeactivationImmutability(IsolatedTestCase):
    def test_deactivating_voice_does_not_alter_snapshot(self):
        """Deactivating custom voice after job creation must not alter snapshot."""
        db = Database(self.config.db_path)
        db.initialize()
        store = ContentStore(self.config)
        _, _, rev_id, _, jc_id = _make_job_fixture(db, store)
        cv_id, _, audio_sha, _, _, _ = _make_custom_voice(db, store)
        custom_ref = f"custom:{cv_id}"
        worker = _make_worker(db, store, self.config)
        worker._prepare_segments(
            job_chapter_id=jc_id, text_revision_id=rev_id,
            text="Something.", settings_snapshot=SNAP, fallback_voice=custom_ref,
        )
        before = db.fetch_all("SELECT * FROM segments WHERE job_chapter_id=?", (jc_id,))
        with db.connect() as conn:
            conn.execute("UPDATE custom_voices SET is_active=0 WHERE id=?", (cv_id,))
        after = db.fetch_all("SELECT * FROM segments WHERE job_chapter_id=?", (jc_id,))
        for b, a in zip(before, after):
            self.assertEqual(b["reference_audio_sha256"], a["reference_audio_sha256"])
            self.assertEqual(b["custom_voice_revision_id"], a["custom_voice_revision_id"])


class TestSettingsJSON(IsolatedTestCase):
    def test_settings_no_none_values(self):
        """_effective_synthesis_settings excludes None and runtime objects."""
        from story_audio.pipeline import _effective_synthesis_settings
        snap = {"engine_version": "vieneu:v3turbo", "max_chars": 256, "speed": None, "db": None}
        result = json.loads(_effective_synthesis_settings(snap))
        self.assertNotIn("speed", result)
        self.assertNotIn("db", result)
        self.assertIn("engine_version", result)
        self.assertIn("max_chars", result)

    def test_settings_deterministic(self):
        from story_audio.pipeline import _effective_synthesis_settings
        snap = {"engine_version": "vieneu:v3turbo", "speed": 1.0, "max_chars": 256}
        self.assertEqual(_effective_synthesis_settings(snap), _effective_synthesis_settings(snap))

    def test_settings_unicode(self):
        from story_audio.pipeline import _effective_synthesis_settings
        snap = {"engine_version": "vieneu:v3turbo", "label": "Tiếng Việt"}
        result = _effective_synthesis_settings(snap)
        self.assertIn("Tiếng Việt", result)


class TestTranscriptHash(IsolatedTestCase):
    def test_transcript_sha256_matches_stored_bytes(self):
        """Stored transcript_sha256 must equal SHA-256 of stored reference_transcript UTF-8."""
        db = Database(self.config.db_path)
        db.initialize()
        store = ContentStore(self.config)
        _, _, rev_id, _, jc_id = _make_job_fixture(db, store)
        cv_id, _, _, _, transcript, _ = _make_custom_voice(db, store, transcript="Tiếng Việt reference")
        custom_ref = f"custom:{cv_id}"
        worker = _make_worker(db, store, self.config)
        worker._prepare_segments(
            job_chapter_id=jc_id, text_revision_id=rev_id,
            text="Something.", settings_snapshot=SNAP, fallback_voice=custom_ref,
        )
        rows = db.fetch_all("SELECT * FROM segments WHERE job_chapter_id=?", (jc_id,))
        for row in rows:
            if row["reference_transcript"]:
                expected = hashlib.sha256(row["reference_transcript"].encode("utf-8")).hexdigest()
                self.assertEqual(expected, row["reference_transcript_sha256"])


class TestLegacyCompatibility(IsolatedTestCase):
    def test_legacy_null_snapshot_rows_readable(self):
        """Rows with NULL snapshot fields remain readable without error."""
        db = Database(self.config.db_path)
        db.initialize()
        store = ContentStore(self.config)
        _, _, _, _, jc_id = _make_job_fixture(db, store)
        text_path, digest = store.put_text("Legacy text")
        syn_hash = sha256_text(json.dumps({"text_sha256": digest, "voice_id": "duc_tri"}, sort_keys=True))
        now = utcnow()
        with db.connect() as conn:
            conn.execute(
                """INSERT INTO segments(job_chapter_id, segment_index, text_path, text_sha256,
                    status, created_at, utterance_sequence, speaker_role, character_id,
                    resolved_voice_id, synthesis_hash)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (jc_id, 1, text_path, digest, "pending", now, None, "narrator", None, "duc_tri", syn_hash)
            )
        rows = db.fetch_all("SELECT * FROM segments WHERE job_chapter_id=?", (jc_id,))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIsNone(row["voice_source_type"])
        self.assertIsNone(row["voice_snapshot_version"])
        self.assertEqual(row["resolved_voice_id"], "duc_tri")


class TestUpdatePathImmutability(IsolatedTestCase):
    def test_status_update_preserves_snapshot(self):
        """Normal status update must preserve all snapshot columns."""
        db = Database(self.config.db_path)
        db.initialize()
        store = ContentStore(self.config)
        _, _, rev_id, _, jc_id = _make_job_fixture(db, store)
        worker = _make_worker(db, store, self.config)
        worker._prepare_segments(
            job_chapter_id=jc_id, text_revision_id=rev_id,
            text="Something.", settings_snapshot=SNAP, fallback_voice="duc_tri",
        )
        before = db.fetch_all("SELECT * FROM segments WHERE job_chapter_id=?", (jc_id,))[0]
        with db.connect() as conn:
            conn.execute("UPDATE segments SET status='done' WHERE job_chapter_id=?", (jc_id,))
        after = db.fetch_all("SELECT * FROM segments WHERE job_chapter_id=?", (jc_id,))[0]
        for col in ["voice_source_type", "voice_provider", "voice_model",
                    "logical_voice_ref", "effective_voice_ref",
                    "synthesis_settings_json", "voice_snapshot_version"]:
            self.assertEqual(before[col], after[col], f"Column {col} altered by status update")


if __name__ == "__main__":
    unittest.main()
