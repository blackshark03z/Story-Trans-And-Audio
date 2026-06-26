from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from story_audio.db import Database, utcnow
from story_audio.files import sha256_text
from story_audio.gemini import RepairResult, repair_punctuation
from story_audio.gemini_cache import GeminiRepairCache
from story_audio.integrity import check_data_integrity, has_errors
from story_audio.pipeline import ChapterNeedsReview, PipelineWorker, create_job
from story_audio.storage import ContentStore
from story_audio.text import lexical_sha256, split_repair_blocks, validate_repair_candidate
from tests.test_recovery import FakeTts, make_config


SOURCE = "Trời đã tối anh bước về nhà"
REPAIRED = "Trời đã tối, anh bước về nhà."


class GeminiCacheTests(unittest.TestCase):

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

    def make_cache(self, root: Path, **overrides):
        config = replace(make_config(root), **overrides)
        config.ensure_dirs()
        store = ContentStore(config)
        return config, store, GeminiRepairCache(store, config)

    def test_store_hit_revalidates_repair_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, _store, cache = self.make_cache(Path(directory))
            cache.store_result(source=SOURCE, repaired=REPAIRED, model="m1", prompt_version="p1")
            with patch(
                "story_audio.gemini_cache.validate_repair_candidate",
                wraps=validate_repair_candidate,
            ) as validator:
                result = cache.lookup(source=SOURCE, model="m1", prompt_version="p1")
            self.assertEqual(result.status, "hit")
            self.assertEqual(result.repaired_text, REPAIRED)
            self.assertGreaterEqual(validator.call_count, 1)

    def test_valid_strict_cache_entry_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, _store, cache = self.make_cache(Path(directory))
            cache.store_result(source=SOURCE, repaired=REPAIRED, model="m", prompt_version="p")
            result = cache.lookup(source=SOURCE, model="m", prompt_version="p")
            self.assertEqual(result.status, "hit")
            self.assertEqual(result.repaired_text, REPAIRED)

    def test_bounded_orthographic_cache_entry_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, _store, cache = self.make_cache(Path(directory))
            source = "tiếng kèn vang lên"
            repaired = "tiếng kền vang lên."
            manifest = cache.store_result(source=source, repaired=repaired, model="m", prompt_version="p")
            self.assertEqual(manifest["repair_validation_classification"], "bounded_orthographic_repair")
            result = cache.lookup(source=source, model="m", prompt_version="p")
            self.assertEqual(result.status, "hit")
            self.assertEqual(result.repaired_text, repaired)

    def test_legacy_punctuation_cache_entry_remains_usable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, _store, cache = self.make_cache(Path(directory))
            with patch("story_audio.gemini_cache.REPAIR_CONTRACT_VERSION", "punctuation-only-v1"):
                legacy = cache.store_result(source=SOURCE, repaired=REPAIRED, model="m", prompt_version="p")
            result = cache.lookup(source=SOURCE, model="m", prompt_version="p")
            self.assertEqual(result.status, "hit")
            self.assertEqual(result.cache_key, legacy["cache_key"])
            self.assertEqual(result.repaired_text, REPAIRED)

    def test_unsafe_semantic_cache_entry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, store, cache = self.make_cache(Path(directory))
            source = "con chó chạy nhanh"
            safe = "con chó chạy nhanh."
            manifest = cache.store_result(source=source, repaired=safe, model="m", prompt_version="p")
            unsafe = "con mèo chạy nhanh."
            unsafe_path, unsafe_hash = store.put_text(unsafe)
            path = cache._manifest_path(manifest["cache_key"])
            data = json.loads(path.read_text(encoding="utf-8"))
            data.update(
                repaired_blob_path=unsafe_path,
                repaired_hash=unsafe_hash,
                repaired_char_count=len(unsafe),
            )
            path.write_text(json.dumps(data), encoding="utf-8")
            result = cache.lookup(source=source, model="m", prompt_version="p")
            self.assertEqual(result.status, "invalid")
            self.assertEqual(result.reason, "repair_candidate_validation_failed")

    def test_number_changing_cache_entry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, store, cache = self.make_cache(Path(directory))
            source = "Có 12 người tới"
            safe = "Có 12 người tới."
            manifest = cache.store_result(source=source, repaired=safe, model="m", prompt_version="p")
            unsafe = "Có 13 người tới."
            unsafe_path, unsafe_hash = store.put_text(unsafe)
            path = cache._manifest_path(manifest["cache_key"])
            data = json.loads(path.read_text(encoding="utf-8"))
            data.update(
                repaired_blob_path=unsafe_path,
                repaired_hash=unsafe_hash,
                repaired_char_count=len(unsafe),
            )
            path.write_text(json.dumps(data), encoding="utf-8")
            result = cache.lookup(source=source, model="m", prompt_version="p")
            self.assertEqual(result.status, "invalid")
            self.assertEqual(result.reason, "repair_candidate_validation_failed")

    def test_cache_validation_and_live_response_validation_are_consistent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, _store, cache = self.make_cache(Path(directory))
            source = "kèn"
            repaired = "kền"
            cache.store_result(source=source, repaired=repaired, model="m", prompt_version="p")
            self.assertEqual(cache.lookup(source=source, model="m", prompt_version="p").repaired_text, repaired)
            with patch("story_audio.gemini.urllib.request.urlopen", return_value=_FakeGeminiResponse(source, repaired)):
                result = repair_punctuation(
                    api_key="fake",
                    model="m",
                    block_id="b1",
                    text=source,
                    max_attempts=1,
                )
            self.assertEqual(result.text, repaired)

    def test_every_output_identity_dimension_changes_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, _store, cache = self.make_cache(Path(directory))
            base = cache.cache_key(cache.identity(source_hash=sha256_text(SOURCE), model="m1", prompt_version="p1"))
            variants = [
                cache.cache_key(cache.identity(source_hash=sha256_text(SOURCE + " khác"), model="m1", prompt_version="p1")),
                cache.cache_key(cache.identity(source_hash=sha256_text(SOURCE), model="m2", prompt_version="p1")),
                cache.cache_key(cache.identity(source_hash=sha256_text(SOURCE), model="m1", prompt_version="p2")),
            ]
            with patch("story_audio.gemini_cache.REPAIR_CONTRACT_VERSION", "contract-v2"):
                variants.append(cache.cache_key(cache.identity(source_hash=sha256_text(SOURCE), model="m1", prompt_version="p1")))
            with patch.dict("story_audio.gemini_cache.GENERATION_SETTINGS", {"temperature": 0.25}, clear=True):
                variants.append(cache.cache_key(cache.identity(source_hash=sha256_text(SOURCE), model="m1", prompt_version="p1")))
            self.assertTrue(all(key != base for key in variants))
            self.assertEqual(len(variants), len(set(variants)))

    def test_corruption_modes_are_safe_invalid_misses(self) -> None:
        mutations = ("payload", "key", "missing", "json", "lexical")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                _config, store, cache = self.make_cache(Path(directory))
                manifest = cache.store_result(source=SOURCE, repaired=REPAIRED, model="m", prompt_version="p")
                path = cache._manifest_path(manifest["cache_key"])
                if mutation == "payload":
                    store.absolute(manifest["repaired_blob_path"]).write_text("damaged", encoding="utf-8")
                elif mutation == "key":
                    data = json.loads(path.read_text(encoding="utf-8")); data["cache_key"] = "0" * 64
                    path.write_text(json.dumps(data), encoding="utf-8")
                elif mutation == "missing":
                    store.absolute(manifest["repaired_blob_path"]).unlink()
                elif mutation == "json":
                    path.write_text("{", encoding="utf-8")
                else:
                    invalid = "Trời đã sáng, anh bước về nhà."
                    invalid_path, invalid_hash = store.put_text(invalid)
                    data = json.loads(path.read_text(encoding="utf-8"))
                    data.update(repaired_blob_path=invalid_path, repaired_hash=invalid_hash, repaired_char_count=len(invalid))
                    path.write_text(json.dumps(data), encoding="utf-8")
                result = cache.lookup(source=SOURCE, model="m", prompt_version="p")
                self.assertEqual(result.status, "invalid")
                self.assertNotIn(SOURCE, result.reason or "")

    def test_atomic_failure_leaves_no_partial_manifest_and_repeat_write_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, _store, cache = self.make_cache(Path(directory))
            with patch("story_audio.gemini_cache.atomic_write_json", side_effect=OSError("disk")):
                with self.assertRaises(OSError):
                    cache.store_result(source=SOURCE, repaired=REPAIRED, model="m", prompt_version="p")
            self.assertFalse(list(config.gemini_cache_dir.rglob("*.json")))
            self.assertFalse(list(config.gemini_cache_dir.rglob("*.partial")))
            first = cache.store_result(source=SOURCE, repaired=REPAIRED, model="m", prompt_version="p")
            second = cache.store_result(source=SOURCE, repaired=REPAIRED, model="m", prompt_version="p")
            self.assertEqual(first["cache_key"], second["cache_key"])
            self.assertEqual(cache.lookup(source=SOURCE, model="m", prompt_version="p").status, "hit")

    def test_cleanup_dry_run_and_apply_never_delete_text_blobs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, store, cache = self.make_cache(
                Path(directory), gemini_cache_retention_days=1, gemini_cache_max_entries=100
            )
            manifest = cache.store_result(source=SOURCE, repaired=REPAIRED, model="m", prompt_version="p")
            manifest_path = cache._manifest_path(manifest["cache_key"])
            old = time.time() - 3 * 86_400
            os.utime(manifest_path, (old, old))
            repaired_blob = store.absolute(manifest["repaired_blob_path"])
            self.assertEqual(cache.cleanup(dry_run=True)["removed"], 1)
            self.assertTrue(manifest_path.exists())
            self.assertEqual(cache.cleanup(dry_run=False)["removed"], 1)
            self.assertFalse(manifest_path.exists())
            self.assertTrue(repaired_blob.exists())
            self.assertTrue(config.blobs_dir.exists())

    def test_doctor_warns_for_corrupt_cache_without_critical_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, _store, cache = self.make_cache(Path(directory))
            db = Database(config.db_path); db.initialize()
            manifest = cache.store_result(source=SOURCE, repaired=REPAIRED, model="m", prompt_version="p")
            cache._manifest_path(manifest["cache_key"]).write_text("{", encoding="utf-8")
            findings = check_data_integrity(config, deep=True)
            self.assertFalse(has_errors(findings))
            self.assertTrue(any(item.level == "WARN" and item.name == "gemini_repair_cache" for item in findings))


def seed_shared_pipeline(root: Path, source: str = SOURCE, *, chapter_count: int = 2):
    config = make_config(root)
    config.ensure_dirs()
    db = Database(config.db_path); db.initialize()
    store = ContentStore(config)
    path, digest = store.put_text(source)
    now = utcnow()
    with db.transaction() as connection:
        book_id = int(connection.execute(
            "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            ("Cache", "cache.epub", "cache-book", chapter_count, now, now),
        ).lastrowid)
        for number in range(1, chapter_count + 1):
            chapter_id = int(connection.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (book_id, number, f"Chapter {number}", len(source), now, now),
            ).lastrowid)
            revision_id = int(connection.execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                    processor_version,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (chapter_id, "reflowed", path, digest, lexical_sha256(source), len(source), "reflow-v1", "approved", now),
            ).lastrowid)
            connection.execute("UPDATE chapters SET active_text_revision_id=? WHERE id=?", (revision_id, chapter_id))
    created = create_job(
        db, config, book_id=book_id, from_chapter=1, to_chapter=chapter_count, voice_name="Voice",
        repair_mode="all_selected", output_format="m4a", skip_completed=False,
    )
    job = dict(db.fetch_one("SELECT * FROM jobs WHERE id=?", (created["job_id"],)))
    chapters = [dict(row) for row in db.fetch_all(
        """SELECT jc.*,c.chapter_number,c.id AS chapter_id
           FROM job_chapters jc JOIN chapters c ON c.id=jc.chapter_id
           WHERE jc.job_id=? ORDER BY jc.sequence""", (created["job_id"],)
    )]
    return config, db, store, job, chapters


class SharedPipelineCacheTests(unittest.TestCase):

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

    def test_pipeline_persists_bounded_orthographic_repair_without_restoring_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = "con kền kèn chạy qua"
            repaired = "con kền kền chạy qua."
            config, db, store, job, chapters = seed_shared_pipeline(Path(directory), source, chapter_count=1)
            raw_before = store.read_text(db.fetch_one("SELECT content_path FROM text_revisions WHERE kind='reflowed'")["content_path"])
            worker = PipelineWorker(db, store, FakeTts(), config)
            with patch.object(type(config), "gemini_key", return_value="fake-key"), patch(
                "story_audio.pipeline.repair_punctuation",
                return_value=RepairResult(repaired, "{}"),
            ):
                revision_id, text = worker._prepare_text(job, chapters[0])
            self.assertIn("con kền kền", text)
            self.assertNotIn("con kền kèn", text)
            revision = db.fetch_one("SELECT * FROM text_revisions WHERE id=?", (revision_id,))
            self.assertEqual(revision["kind"], "repaired")
            self.assertEqual(store.read_text(revision["content_path"]), text)
            self.assertEqual(raw_before, source)

    def test_pipeline_validates_bounded_repairs_per_block_not_whole_chapter_budget(self) -> None:
        sentences = [
            ("la " * 550).strip() + " kèn.",
            ("ra " * 550).strip() + " kèn.",
            ("na " * 550).strip() + " kèn.",
        ]
        source = " ".join(sentences)
        self.assertGreaterEqual(len(split_repair_blocks(source)), 3)
        with self.assertRaises(ValueError):
            validate_repair_candidate(source, source.replace("kèn", "kền"))
        with tempfile.TemporaryDirectory() as directory:
            config, db, store, job, chapters = seed_shared_pipeline(Path(directory), source, chapter_count=1)
            worker = PipelineWorker(db, store, FakeTts(), config)

            def fake_repair(**kwargs):
                return RepairResult(kwargs["text"].replace("kèn", "kền"), "{}")

            with patch.object(type(config), "gemini_key", return_value="fake-key"), patch(
                "story_audio.pipeline.repair_punctuation",
                side_effect=fake_repair,
            ) as fake:
                _revision_id, text = worker._prepare_text(job, chapters[0])
            self.assertEqual(fake.call_count, len(split_repair_blocks(source)))
            self.assertEqual(text.count("kền"), len(split_repair_blocks(source)))

    def test_pipeline_rejects_semantic_block_without_repaired_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = "con chó chạy nhanh"
            config, db, store, job, chapters = seed_shared_pipeline(Path(directory), source, chapter_count=1)
            worker = PipelineWorker(db, store, FakeTts(), config)
            with patch.object(type(config), "gemini_key", return_value="fake-key"), patch(
                "story_audio.pipeline.repair_punctuation",
                return_value=RepairResult("con mèo chạy nhanh.", "{}"),
            ):
                with self.assertRaises(ChapterNeedsReview):
                    worker._prepare_text(job, chapters[0])
            self.assertEqual(db.fetch_one("SELECT COUNT(*) AS n FROM text_revisions WHERE kind='repaired'")["n"], 0)
            self.assertEqual(db.fetch_one("SELECT status FROM repair_blocks")["status"], "failed")

    def test_pipeline_reuses_verified_bounded_block_without_gemini_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = "tiếng kèn vang lên"
            repaired = "tiếng kền vang lên"
            config, db, store, job, chapters = seed_shared_pipeline(Path(directory), source, chapter_count=1)
            block = split_repair_blocks(source)[0]
            source_path, source_hash = store.put_text(block)
            repaired_path, _ = store.put_text(repaired)
            prompt = f"{config.gemini_prompt_version}:{GeminiRepairCache(store, config).contract_fingerprint(model=config.gemini_model, prompt_version=config.gemini_prompt_version)}"
            with db.connect() as connection:
                connection.execute(
                    """INSERT INTO repair_blocks(
                        job_chapter_id,block_index,source_path,repaired_path,source_sha256,
                        lexical_sha256,model_id,prompt_version,status,verified_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        chapters[0]["id"], 1, source_path, repaired_path, source_hash,
                        lexical_sha256(block), config.gemini_model, prompt, "verified", utcnow(),
                    ),
                )
            worker = PipelineWorker(db, store, FakeTts(), config)
            with patch("story_audio.pipeline.repair_punctuation") as fake:
                _revision_id, text = worker._prepare_text(job, chapters[0])
            fake.assert_not_called()
            self.assertEqual(text, repaired)

    def test_source_hash_mismatch_prevents_verified_block_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = "tiếng kèn vang lên"
            config, db, store, job, chapters = seed_shared_pipeline(Path(directory), source, chapter_count=1)
            block = split_repair_blocks(source)[0]
            source_path, _source_hash = store.put_text(block)
            stale_repaired_path, _ = store.put_text("stale kền")
            prompt = f"{config.gemini_prompt_version}:{GeminiRepairCache(store, config).contract_fingerprint(model=config.gemini_model, prompt_version=config.gemini_prompt_version)}"
            with db.connect() as connection:
                connection.execute(
                    """INSERT INTO repair_blocks(
                        job_chapter_id,block_index,source_path,repaired_path,source_sha256,
                        lexical_sha256,model_id,prompt_version,status,verified_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        chapters[0]["id"], 1, source_path, stale_repaired_path, "0" * 64,
                        lexical_sha256(block), config.gemini_model, prompt, "verified", utcnow(),
                    ),
                )
            worker = PipelineWorker(db, store, FakeTts(), config)
            with patch.object(type(config), "gemini_key", return_value="fake-key"), patch(
                "story_audio.pipeline.repair_punctuation",
                return_value=RepairResult("tiếng kền vang lên", "{}"),
            ) as fake:
                _revision_id, text = worker._prepare_text(job, chapters[0])
            self.assertEqual(fake.call_count, 1)
            self.assertEqual(text, "tiếng kền vang lên")

    def test_missing_repair_block_indexes_fail_before_assembly_and_duplicate_detection_is_reachable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sentence = ("la " * 550).strip() + " kèn."
            source = f"{sentence} {sentence}"
            config, db, store, job, chapters = seed_shared_pipeline(Path(directory), source, chapter_count=1)
            block = split_repair_blocks(source)[0]
            source_path, source_hash = store.put_text(block)
            with db.connect() as connection:
                connection.execute(
                    """INSERT INTO repair_blocks(
                        job_chapter_id,block_index,source_path,source_sha256,
                        lexical_sha256,model_id,prompt_version,status
                    ) VALUES(?,?,?,?,?,?,?,'pending')""",
                    (
                        chapters[0]["id"], 1, source_path, source_hash, lexical_sha256(block),
                        config.gemini_model, config.gemini_prompt_version,
                    ),
                )
            worker = PipelineWorker(db, store, FakeTts(), config)
            with self.assertRaises(ChapterNeedsReview):
                worker._prepare_text(job, chapters[0])

            with self.assertRaises(ChapterNeedsReview):
                worker._validate_repair_block_structure(
                    [{"block_index": 1}, {"block_index": 1}],
                    {1: "first", 2: "second"},
                )

    def test_pre_cache_verified_block_is_adopted_without_gemini_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, db, store, job, chapters = seed_shared_pipeline(Path(directory))
            source_path, source_hash = store.put_text(SOURCE)
            repaired_path, _ = store.put_text(REPAIRED)
            with db.connect() as connection:
                connection.execute(
                    """INSERT INTO repair_blocks(
                        job_chapter_id,block_index,source_path,repaired_path,source_sha256,
                        lexical_sha256,model_id,prompt_version,status,verified_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        chapters[0]["id"], 1, source_path, repaired_path, source_hash,
                        lexical_sha256(SOURCE), config.gemini_model,
                        config.gemini_prompt_version, "verified", utcnow(),
                    ),
                )
            worker = PipelineWorker(db, store, FakeTts(), config)
            with patch("story_audio.pipeline.repair_punctuation") as fake:
                _revision_id, repaired = worker._prepare_text(job, chapters[0])
            self.assertEqual(repaired, REPAIRED)
            fake.assert_not_called()
            adopted = db.fetch_one(
                "SELECT prompt_version FROM repair_blocks WHERE job_chapter_id=?",
                (chapters[0]["id"],),
            )["prompt_version"]
            self.assertTrue(adopted.startswith(config.gemini_prompt_version + ":"))

    def test_repair_uses_immutable_job_model_and_prompt_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, db, store, job, chapters = seed_shared_pipeline(Path(directory))
            runtime_config = replace(config, gemini_model="runtime-model", gemini_prompt_version="runtime-prompt")
            worker = PipelineWorker(db, store, FakeTts(), runtime_config)
            snapshot = json.loads(job["settings_json"])
            with patch.object(type(config), "gemini_key", return_value="fake-key"), patch(
                "story_audio.pipeline.repair_punctuation",
                return_value=RepairResult(REPAIRED, "{}"),
            ) as fake:
                worker._prepare_text(job, chapters[0])
            self.assertEqual(fake.call_args.kwargs["model"], snapshot["gemini_model"])
            persisted = json.loads(db.fetch_one("SELECT settings_json FROM jobs WHERE id=?", (job["id"],))["settings_json"])
            self.assertEqual(persisted, snapshot)

    def test_second_job_chapter_reuses_shared_result_and_cache_deletion_keeps_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, db, store, job, chapters = seed_shared_pipeline(Path(directory))
            worker = PipelineWorker(db, store, FakeTts(), config)
            with patch.object(type(config), "gemini_key", return_value="fake-key"), patch(
                "story_audio.pipeline.repair_punctuation",
                return_value=RepairResult(REPAIRED, "{}"),
            ) as fake:
                first_id, _ = worker._prepare_text(job, chapters[0])
                second_id, _ = worker._prepare_text(job, chapters[1])
                self.assertEqual(fake.call_count, 1)
                self.assertNotEqual(first_id, second_id)
                codes = [row["event_code"] for row in db.fetch_all("SELECT event_code FROM audit_events")]
                self.assertIn("gemini_cache_miss", codes)
                self.assertIn("gemini_cache_hit", codes)
                self.assertEqual(codes.count("gemini_api_call"), 1)
                worker.repair_cache.clear_manifests()
                revision_count = db.fetch_one("SELECT COUNT(*) AS n FROM text_revisions")["n"]
                again_id, again_text = worker._prepare_text(job, chapters[0])
                self.assertEqual(again_id, first_id)
                self.assertEqual(again_text, REPAIRED)
                self.assertEqual(fake.call_count, 1)
                self.assertEqual(db.fetch_one("SELECT COUNT(*) AS n FROM text_revisions")["n"], revision_count)

    def test_corrupt_shared_payload_calls_fake_gemini_again_without_logging_secret_or_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, db, store, job, chapters = seed_shared_pipeline(Path(directory))
            worker = PipelineWorker(db, store, FakeTts(), config)
            with patch.object(type(config), "gemini_key", return_value="super-secret-key"), patch(
                "story_audio.pipeline.repair_punctuation",
                return_value=RepairResult(REPAIRED, "{}"),
            ) as fake:
                worker._prepare_text(job, chapters[0])
                manifest_path = next(config.gemini_cache_dir.rglob("*.json"))
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                store.absolute(manifest["repaired_blob_path"]).write_text("damaged", encoding="utf-8")
                worker._prepare_text(job, chapters[1])
            self.assertEqual(fake.call_count, 2)
            self.assertEqual(
                worker.repair_cache.lookup(
                    source=SOURCE, model=config.gemini_model,
                    prompt_version=config.gemini_prompt_version,
                ).status,
                "hit",
            )
            audit_payload = "\n".join(str(row["details_json"]) for row in db.fetch_all("SELECT details_json FROM audit_events"))
            self.assertNotIn("super-secret-key", audit_payload)
            self.assertNotIn(SOURCE, audit_payload)
            self.assertTrue(any(
                row["event_code"] == "gemini_cache_invalid"
                for row in db.fetch_all("SELECT event_code FROM audit_events")
            ))


class _FakeGeminiResponse:
    def __init__(self, source: str, repaired: str):
        del source
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {"block_id": "b1", "repaired_text": repaired},
                                    ensure_ascii=False,
                                )
                            }
                        ]
                    }
                }
            ]
        }
        self.body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return self.body


if __name__ == "__main__":
    unittest.main()
