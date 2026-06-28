from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .casting import CHUNKER_VERSION, validate_approved_plan
from .custom_voice import CustomVoiceRepository
from .db import Database, utcnow
from .files import atomic_write_json, safe_slug, sha256_file, sha256_text
from .gemini import GeminiRepairError, repair_punctuation
from .gemini_cache import GeminiRepairCache
from .storage import ContentStore
from .synthesis_snapshot import (
    SynthesisSnapshotError,
    load_segment_synthesis_input,
)
from .text import (
    lexical_sha256,
    qa_text,
    split_repair_blocks,
    split_tts_segments,
    validate_lexical_identity,
    validate_repair_candidate,
)
from .voice_ref import CustomVoiceContext, is_custom_ref, parse_custom_ref, resolve_custom_ref
from .tts import TtsService



def _effective_synthesis_settings(settings_snapshot: dict) -> str:
    """Return canonical JSON of effective synthesis settings for voice snapshot."""
    _EXCLUDE = frozenset({
        'db', 'cache', 'store', 'session', 'tmp_dir', 'temp_dir',
        'work_dir', 'log', 'logger', 'connection', 'conn',
    })
    cleaned = {
        k: v for k, v in settings_snapshot.items()
        if v is not None
        and k not in _EXCLUDE
        and not callable(v)
        and not hasattr(v, 'cursor')
        and not hasattr(v, 'execute')
    }
    return json.dumps(cleaned, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


class JobCancelled(RuntimeError):
    pass


class JobPaused(RuntimeError):
    pass


class ChapterNeedsReview(RuntimeError):
    pass


def _repair_validation_error(block_index: int, reason: str) -> ChapterNeedsReview:
    return ChapterNeedsReview(f"Gemini block {block_index} changed content: {reason}")


def create_job(
    db: Database,
    config: Settings,
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    voice_name: str,
    repair_mode: str,
    output_format: str,
    skip_completed: bool,
    casting_plan_id: int | None = None,
    store: ContentStore | None = None,
) -> dict[str, Any]:
    if from_chapter > to_chapter:
        raise ValueError("ChÆ°Æ¡ng báº¯t Ä‘áº§u pháº£i nhá» hÆ¡n hoáº·c báº±ng chÆ°Æ¡ng káº¿t thÃºc.")
    if repair_mode not in {"off", "qa_only", "all_selected"}:
        raise ValueError("Cháº¿ Ä‘á»™ Gemini khÃ´ng há»£p lá»‡.")
    if output_format not in {"m4a", "mp3"}:
        raise ValueError("Äá»‹nh dáº¡ng Ä‘áº§u ra pháº£i lÃ  m4a hoáº·c mp3.")
    book = db.fetch_one("SELECT * FROM books WHERE id=?", (book_id,))
    if not book:
        raise ValueError("KhÃ´ng tÃ¬m tháº¥y sÃ¡ch.")
    chapters = db.fetch_all(
        "SELECT * FROM chapters WHERE book_id=? AND chapter_number BETWEEN ? AND ? ORDER BY chapter_number",
        (book_id, from_chapter, to_chapter),
    )
    if not chapters:
        raise ValueError("Khoáº£ng Ä‘Æ°á»£c chá»n khÃ´ng cÃ³ chÆ°Æ¡ng.")
    expected = list(range(from_chapter, to_chapter + 1))
    actual = [int(row["chapter_number"]) for row in chapters]
    missing = sorted(set(expected) - set(actual))
    if missing:
        raise ValueError(f"Khoáº£ng chÆ°Æ¡ng bá»‹ thiáº¿u: {missing[:20]}")
    selected = [row for row in chapters if not (skip_completed and row["active_audio_artifact_id"])]
    now = datetime.now(timezone.utc)
    scheduled = now + timedelta(seconds=config.undo_seconds)
    settings_snapshot = {
        "tts_mode": config.tts_mode,
        "temperature": config.tts_temperature,
        "top_k": config.tts_top_k,
        "max_chars": config.tts_max_chars,
        "target_chars": config.tts_target_chars,
        "silence_seconds": config.tts_silence_seconds,
        "gemini_model": config.gemini_model,
        "gemini_prompt_version": config.gemini_prompt_version,
        "engine_version": f"vieneu:{config.tts_mode}",
        "chunker_version": CHUNKER_VERSION if casting_plan_id else "tts-segment-v1",
    }
    casting_row = None
    casting_plan = None
    casting_snapshot = None
    if casting_plan_id is not None:
        if store is None:
            raise ValueError("ContentStore is required for a multi-voice job")
        casting_row, casting_plan = validate_approved_plan(db, store, casting_plan_id)
        matching = [row for row in chapters if int(row["id"]) == int(casting_row["chapter_id"])]
        if len(chapters) != 1 or len(matching) != 1:
            raise ValueError("A manual casting job must target exactly its casting-plan chapter")
        if repair_mode != "off":
            raise ValueError("A manual casting job must use its pinned approved TextRevision")
        selected = chapters
        voice_name = str(casting_plan["narrator_voice_id"])
        casting_snapshot = {
            "casting_plan_id": casting_plan_id,
            "casting_plan_sha256": casting_row["plan_sha256"],
            "text_revision_id": casting_row["text_revision_id"],
            "narrator_voice_id": casting_plan["narrator_voice_id"],
            "book_voice_profile": casting_plan.get("book_voice_profile"),
            "utterances": casting_plan["utterances"],
            "resolved_character_voices": {
                str(item["character_id"]): item["resolved_voice_id"]
                for item in casting_plan["utterances"]
                if item["role"] == "character"
            },
            "engine_version": settings_snapshot["engine_version"],
            "tts_settings": settings_snapshot,
            "chunker_version": CHUNKER_VERSION,
        }
    with db.transaction() as connection:
        cursor = connection.execute(
            """INSERT INTO jobs(
                book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                settings_json,skip_completed,total_chapters,scheduled_at,created_at,updated_at,
                casting_plan_id,casting_snapshot_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                book_id,
                "scheduled" if selected else "completed",
                from_chapter,
                to_chapter,
                voice_name,
                repair_mode,
                output_format,
                json.dumps(settings_snapshot, ensure_ascii=False),
                int(skip_completed),
                len(selected),
                scheduled.isoformat(),
                now.isoformat(),
                now.isoformat(),
                casting_plan_id,
                json.dumps(casting_snapshot, ensure_ascii=False, sort_keys=True) if casting_snapshot else None,
            ),
        )
        job_id = int(cursor.lastrowid)
        for sequence, chapter in enumerate(selected, start=1):
            if casting_plan_id and int(chapter["id"]) == int(casting_row["chapter_id"]):
                connection.execute(
                    """INSERT INTO job_chapters(
                        job_id,chapter_id,sequence,status,text_revision_id,casting_plan_id,
                        casting_plan_sha256,voice_snapshot_json
                    ) VALUES(?,?,?,'pending',?,?,?,?)""",
                    (
                        job_id, chapter["id"], sequence, casting_row["text_revision_id"],
                        casting_plan_id, casting_row["plan_sha256"],
                        json.dumps(casting_snapshot, ensure_ascii=False, sort_keys=True),
                    ),
                )
            else:
                connection.execute(
                    "INSERT INTO job_chapters(job_id,chapter_id,sequence,status) VALUES(?,?,?,'pending')",
                    (job_id, chapter["id"], sequence),
                )
    db.audit(
        "job_created",
        job_id=job_id,
        details={
            "from": from_chapter,
            "to": to_chapter,
            "selected": len(selected),
            "skipped": len(chapters) - len(selected),
            "voice": voice_name,
            "repair_mode": repair_mode,
            "casting_plan_id": casting_plan_id,
        },
    )
    return {
        "job_id": job_id,
        "selected_chapters": len(selected),
        "skipped_completed": len(chapters) - len(selected),
        "undo_until": scheduled.isoformat(),
    }


def _effective_synthesis_settings(settings_snapshot: dict) -> str:
    """Return canonical JSON string of effective synthesis settings for snapshot."""
    EXCLUDE_KEYS = {"db", "cache", "store", "session", "tmp_dir", "temp_dir",
                    "work_dir", "log", "logger"}
    cleaned = {
        k: v for k, v in settings_snapshot.items()
        if v is not None and k not in EXCLUDE_KEYS
        and not callable(v) and not hasattr(v, 'cursor')
    }
    return json.dumps(cleaned, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

class PipelineWorker:
    def __init__(self, db: Database, store: ContentStore, tts: TtsService, config: Settings):
        self.db = db
        self.store = store
        self.tts = tts
        self.config = config
        self.repair_cache = GeminiRepairCache(store, config)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_cleanup = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="pipeline-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def wake(self) -> None:
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if time.monotonic() - self._last_cleanup > 300:
                    self.cleanup_expired_segments()
                    self._last_cleanup = time.monotonic()
                job = self._next_job()
                if job:
                    self._run_job(dict(job))
                    continue
            except Exception as exc:
                self.db.audit("worker_loop_error", details={"error": str(exc)})
            self._wake.wait(self.config.worker_poll_seconds)
            self._wake.clear()

    def cleanup_expired_segments(self) -> dict[str, int]:
        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=self.config.successful_segment_retention_hours
        )
        rows = self.db.fetch_all(
            """SELECT s.id,s.wav_path FROM segments s
               JOIN job_chapters jc ON jc.id=s.job_chapter_id
               WHERE jc.status='completed' AND jc.finished_at<? AND s.wav_path IS NOT NULL
               AND EXISTS(SELECT 1 FROM artifacts a WHERE a.job_chapter_id=jc.id AND a.status IN ('active','verified'))""",
            (cutoff.isoformat(),),
        )
        deleted = 0
        bytes_freed = 0
        with self.db.connect() as connection:
            for row in rows:
                path = Path(row["wav_path"])
                try:
                    size = path.stat().st_size if path.exists() else 0
                    path.unlink(missing_ok=True)
                    connection.execute("UPDATE segments SET wav_path=NULL WHERE id=?", (row["id"],))
                    deleted += 1
                    bytes_freed += size
                except OSError:
                    continue
        if deleted:
            self.db.audit(
                "segment_cleanup_completed",
                details={"files": deleted, "bytes_freed": bytes_freed},
            )
        return {"files": deleted, "bytes_freed": bytes_freed}

    def _next_job(self):
        rows = self.db.fetch_all(
            "SELECT * FROM jobs WHERE status IN ('scheduled','queued','interrupted') ORDER BY id"
        )
        now = datetime.now(timezone.utc)
        for row in rows:
            if row["status"] == "scheduled":
                scheduled = datetime.fromisoformat(row["scheduled_at"])
                if scheduled > now:
                    continue
            return row
        return None

    def _control(self, job_id: int) -> None:
        row = self.db.fetch_one("SELECT pause_requested,cancel_requested FROM jobs WHERE id=?", (job_id,))
        if not row:
            raise JobCancelled("Job khÃ´ng cÃ²n tá»“n táº¡i.")
        if row["cancel_requested"]:
            raise JobCancelled("ÄÃ£ yÃªu cáº§u há»§y.")
        if row["pause_requested"]:
            raise JobPaused("ÄÃ£ yÃªu cáº§u táº¡m dá»«ng.")

    def _set_job(self, job_id: int, status: str, stage: str | None = None, **values: Any) -> None:
        fields = ["status=?", "updated_at=?"]
        params: list[Any] = [status, utcnow()]
        if stage is not None:
            fields.append("current_stage=?")
            params.append(stage)
        for key, value in values.items():
            fields.append(f"{key}=?")
            params.append(value)
        params.append(job_id)
        with self.db.connect() as connection:
            connection.execute(f"UPDATE jobs SET {','.join(fields)} WHERE id=?", tuple(params))

    def _run_job(self, job: dict[str, Any]) -> None:
        job_id = int(job["id"])
        self._set_job(job_id, "running", "starting", started_at=job["started_at"] or utcnow(), error_message=None)
        self.db.audit("job_started", job_id=job_id)
        try:
            chapters = self.db.fetch_all(
                """SELECT jc.*,c.chapter_number,c.title,c.book_id,c.active_text_revision_id,
                          b.title AS book_title
                   FROM job_chapters jc
                   JOIN chapters c ON c.id=jc.chapter_id
                   JOIN books b ON b.id=c.book_id
                   WHERE jc.job_id=? AND jc.status NOT IN ('completed','cancelled','skipped')
                   ORDER BY jc.sequence""",
                (job_id,),
            )
            for chapter in chapters:
                self._control(job_id)
                self._set_job(job_id, "running", "chapter", current_chapter_number=chapter["chapter_number"])
                try:
                    self._process_chapter(job, dict(chapter))
                except ChapterNeedsReview as exc:
                    self._fail_job_chapter(chapter["id"], "needs_review", str(exc))
                except JobPaused:
                    raise
                except JobCancelled:
                    raise
                except Exception as exc:
                    self._fail_job_chapter(chapter["id"], "failed", str(exc))
                    self.db.audit("chapter_failed", job_id=job_id, chapter_id=chapter["chapter_id"], details={"error": str(exc)})
            counts = self.db.fetch_one(
                """SELECT
                    SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed,
                    SUM(CASE WHEN status IN ('failed','needs_review') THEN 1 ELSE 0 END) AS failed
                   FROM job_chapters WHERE job_id=?""",
                (job_id,),
            )
            completed = int(counts["completed"] or 0)
            failed = int(counts["failed"] or 0)
            final_status = "completed" if failed == 0 else "completed_with_errors"
            self._set_job(
                job_id,
                final_status,
                "done",
                completed_chapters=completed,
                failed_chapters=failed,
                finished_at=utcnow(),
            )
            self.db.audit("job_finished", job_id=job_id, details={"completed": completed, "failed": failed})
        except JobPaused:
            self._set_job(job_id, "paused", "paused")
            self.db.audit("job_paused", job_id=job_id)
        except JobCancelled:
            with self.db.connect() as connection:
                connection.execute(
                    "UPDATE job_chapters SET status='cancelled',finished_at=? WHERE job_id=? AND status='pending'",
                    (utcnow(), job_id),
                )
            self._set_job(job_id, "cancelled", "cancelled", finished_at=utcnow())
            self.db.audit("job_cancelled", job_id=job_id)
        except Exception as exc:
            self._set_job(job_id, "failed", "system_error", error_message=str(exc), finished_at=utcnow())
            self.db.audit("job_failed", job_id=job_id, details={"error": str(exc)})

    def _fail_job_chapter(self, job_chapter_id: int, status: str, error: str) -> None:
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE job_chapters SET status=?,error_message=?,finished_at=? WHERE id=?",
                (status, error[:2000], utcnow(), job_chapter_id),
            )

    def _process_chapter(self, job: dict[str, Any], chapter: dict[str, Any]) -> None:
        job_id = int(job["id"])
        job_chapter_id = int(chapter["id"])
        chapter_id = int(chapter["chapter_id"])
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE job_chapters SET status='running',started_at=COALESCE(started_at,?),error_message=NULL WHERE id=?",
                (utcnow(), job_chapter_id),
            )
        self._ensure_disk()
        text_revision_id, text = self._prepare_text(job, chapter)
        self._control(job_id)
        settings_snapshot = json.loads(job["settings_json"])
        segments = self._prepare_segments(
            job_chapter_id,
            text_revision_id,
            text,
            settings_snapshot,
            chapter=chapter,
            fallback_voice=str(job["voice_name"]),
        )
        self._set_job(job_id, "synthesizing", "tts", current_chapter_number=chapter["chapter_number"])
        chapter_work = self.config.work_dir / f"job_{job_id}" / f"chapter_{int(chapter['chapter_number']):04d}"
        segment_dir = chapter_work / "segments"
        for position, segment in enumerate(segments):
            self._control(job_id)
            segment_path = segment_dir / f"{int(segment['segment_index']):06d}.wav"

            # Skip verified legacy segments with existing WAV
            if segment["status"] == "verified" and segment_path.exists():
                continue

            # Load snapshot once per segment (immutable, reused for all attempts)
            is_final_segment = (position == len(segments) - 1)
            try:
                synth_input = load_segment_synthesis_input(
                    segment,
                    self.store,
                    is_final_segment=is_final_segment,
                )
            except SynthesisSnapshotError as exc:
                # Snapshot failures are non-retryable
                with self.db.connect() as connection:
                    connection.execute(
                        "UPDATE segments SET status='failed',error_message=? WHERE id=?",
                        (str(exc)[:2000], segment["id"]),
                    )
                raise ChapterNeedsReview(f"Segment {segment['segment_index']} snapshot error: {exc}") from exc

            attempts = int(segment["attempt_count"] or 0)
            while attempts < 3:
                self._control(job_id)
                attempts += 1
                try:
                    with self.db.connect() as connection:
                        connection.execute(
                            "UPDATE segments SET status='running',attempt_count=?,error_message=NULL WHERE id=?",
                            (attempts, segment["id"]),
                        )
                    duration_ms, _sample_rate = self.tts.synthesize(
                        synth_input=synth_input,
                        output_path=segment_path,
                    )
                    audio_hash = sha256_file(segment_path)
                    with self.db.connect() as connection:
                        connection.execute(
                            "UPDATE segments SET status='verified',wav_path=?,audio_sha256=?,duration_ms=?,verified_at=? WHERE id=?",
                            (str(segment_path), audio_hash, duration_ms, utcnow(), segment["id"]),
                        )
                    break
                except Exception as exc:
                    with self.db.connect() as connection:
                        connection.execute(
                            "UPDATE segments SET status='failed',error_message=? WHERE id=?",
                            (str(exc)[:2000], segment["id"]),
                        )
                    if attempts >= 3:
                        raise RuntimeError(f"Segment {segment['segment_index']} lỗi sau 3 lần: {exc}") from exc
                    time.sleep(min(2.0, attempts * 0.5))
        self._control(job_id)
        self._set_job(job_id, "assembling", "assemble", current_chapter_number=chapter["chapter_number"])
        artifact_id = self._assemble(job, chapter, text_revision_id, chapter_work)
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE job_chapters SET status='completed',text_revision_id=?,artifact_id=?,finished_at=? WHERE id=?",
                (text_revision_id, artifact_id, utcnow(), job_chapter_id),
            )
            connection.execute(
                "UPDATE jobs SET completed_chapters=completed_chapters+1,updated_at=? WHERE id=?",
                (utcnow(), job_id),
            )
        self.db.audit("chapter_completed", job_id=job_id, chapter_id=chapter_id, details={"artifact_id": artifact_id})

    def _prepare_text(self, job: dict[str, Any], chapter: dict[str, Any]) -> tuple[int, str]:
        job_id = int(job["id"])
        job_chapter_id = int(chapter["id"])
        chapter_id = int(chapter["chapter_id"])
        if chapter.get("text_revision_id"):
            pinned = self.db.fetch_one(
                "SELECT * FROM text_revisions WHERE id=? AND chapter_id=?",
                (chapter["text_revision_id"], chapter_id),
            )
            if pinned:
                return int(pinned["id"]), self.store.read_text(pinned["content_path"])
        source_revision = self.db.fetch_one(
            "SELECT * FROM text_revisions WHERE chapter_id=? AND kind='reflowed' ORDER BY id DESC LIMIT 1",
            (chapter_id,),
        )
        if not source_revision:
            raise RuntimeError("ChÆ°Æ¡ng chÆ°a cÃ³ reflowed TextRevision.")
        source_text = self.store.read_text(source_revision["content_path"])
        mode = str(job["repair_mode"])
        if mode == "off":
            return int(source_revision["id"]), source_text
        if mode == "qa_only":
            issues = qa_text(source_text)
            if not any(issue.code == "missing_punctuation" for issue in issues):
                return int(source_revision["id"]), source_text
        job_settings = json.loads(job["settings_json"])
        repair_model = str(job_settings.get("gemini_model") or self.config.gemini_model)
        repair_prompt_version = str(
            job_settings.get("gemini_prompt_version") or self.config.gemini_prompt_version
        )
        contract_fingerprint = self.repair_cache.contract_fingerprint(
            model=repair_model, prompt_version=repair_prompt_version
        )
        processor_version = f"gemini-repair:{contract_fingerprint}"
        checkpoint_prompt_version = f"{repair_prompt_version}:{contract_fingerprint}"
        legacy_processor_version = f"{repair_model}:{repair_prompt_version}"
        legacy_compatible = self.repair_cache.legacy_checkpoint_is_compatible()
        reusable = self.db.fetch_all(
            """SELECT * FROM text_revisions
               WHERE chapter_id=? AND parent_revision_id=? AND kind='repaired'
                 AND processor_version IN (?,?) AND status='approved'
               ORDER BY id DESC""",
            (
                chapter_id, source_revision["id"], processor_version,
                legacy_processor_version if legacy_compatible else processor_version,
            ),
        )
        for revision in reusable:
            try:
                repaired = self.store.read_text(revision["content_path"])
                valid, _reason = validate_lexical_identity(source_text, repaired)
                if sha256_text(repaired) != revision["content_sha256"] or not valid:
                    continue
                with self.db.connect() as connection:
                    connection.execute(
                        "UPDATE chapters SET active_text_revision_id=?,updated_at=? WHERE id=?",
                        (revision["id"], utcnow(), chapter_id),
                    )
                self.db.audit(
                    "gemini_checkpoint_reuse", job_id=job_id, chapter_id=chapter_id,
                    details={"scope": "text_revision", "revision_id": int(revision["id"])},
                )
                return int(revision["id"]), repaired
            except (OSError, UnicodeError, ValueError):
                continue
        self._set_job(job_id, "repairing", "gemini", current_chapter_number=chapter["chapter_number"])
        blocks = split_repair_blocks(source_text)
        existing = self.db.fetch_all(
            "SELECT * FROM repair_blocks WHERE job_chapter_id=? ORDER BY block_index",
            (job_chapter_id,),
        )
        if not existing:
            with self.db.transaction() as connection:
                for index, block in enumerate(blocks, start=1):
                    source_path, source_sha = self.store.put_text(block)
                    connection.execute(
                        """INSERT INTO repair_blocks(
                            job_chapter_id,block_index,source_path,source_sha256,lexical_sha256,
                            model_id,prompt_version,status
                        ) VALUES(?,?,?,?,?,?,?,'pending')""",
                        (
                            job_chapter_id,
                            index,
                            source_path,
                            source_sha,
                            lexical_sha256(block),
                            repair_model,
                            checkpoint_prompt_version,
                        ),
                    )
            existing = self.db.fetch_all(
                "SELECT * FROM repair_blocks WHERE job_chapter_id=? ORDER BY block_index",
                (job_chapter_id,),
            )
        expected_blocks = {index: block for index, block in enumerate(blocks, start=1)}
        self._validate_repair_block_structure(existing, expected_blocks)
        repaired_blocks: dict[int, str] = {}
        for row in existing:
            self._control(job_id)
            block_index = int(row["block_index"])
            source = expected_blocks[block_index]
            source_sha = sha256_text(source)
            if row["status"] == "verified" and row["repaired_path"]:
                try:
                    checkpoint_text = self.store.read_text(row["repaired_path"])
                    if (
                        source_sha == row["source_sha256"]
                        and row["model_id"] == repair_model
                        and (
                            row["prompt_version"] == checkpoint_prompt_version
                            or (legacy_compatible and row["prompt_version"] == repair_prompt_version)
                        )
                    ):
                        accepted = self._validate_repaired_block(
                            block_index=block_index,
                            source=source,
                            repaired=checkpoint_text,
                        )
                        if row["prompt_version"] != checkpoint_prompt_version:
                            with self.db.connect() as connection:
                                connection.execute(
                                    "UPDATE repair_blocks SET prompt_version=? WHERE id=?",
                                    (checkpoint_prompt_version, row["id"]),
                                )
                        repaired_blocks[block_index] = accepted
                        self.db.audit(
                            "gemini_checkpoint_reuse", job_id=job_id, chapter_id=chapter_id,
                            details={"scope": "repair_block", "block_index": block_index},
                        )
                        continue
                except (OSError, UnicodeError, ValueError, ChapterNeedsReview):
                    pass

            lookup = self.repair_cache.lookup(
                source=source,
                model=repair_model,
                prompt_version=repair_prompt_version,
            )
            self.db.audit(
                f"gemini_cache_{lookup.status}", job_id=job_id, chapter_id=chapter_id,
                details={
                    "block_index": block_index,
                    "cache_key": lookup.cache_key,
                    "reason": lookup.reason if lookup.status == "invalid" else None,
                    "lookup_ms": round(lookup.lookup_ms, 3),
                    "validation_ms": round(lookup.validation_ms, 3),
                },
            )
            if lookup.status == "hit" and lookup.repaired_text and lookup.repaired_blob_path:
                try:
                    accepted = self._validate_repaired_block(
                        block_index=block_index,
                        source=source,
                        repaired=lookup.repaired_text,
                    )
                except ChapterNeedsReview as exc:
                    with self.db.connect() as connection:
                        connection.execute(
                            "UPDATE repair_blocks SET status='failed',error_message=? WHERE id=?",
                            (str(exc)[:2000], row["id"]),
                        )
                    raise
                repaired_path = lookup.repaired_blob_path
                if accepted != lookup.repaired_text:
                    repaired_path, _ = self.store.put_text(accepted)
                with self.db.connect() as connection:
                    connection.execute(
                        """UPDATE repair_blocks
                           SET status='verified',source_sha256=?,lexical_sha256=?,
                               repaired_path=?,model_id=?,prompt_version=?,verified_at=?,error_message=NULL
                           WHERE id=?""",
                        (
                            source_sha,
                            lexical_sha256(source),
                            repaired_path,
                            repair_model,
                            checkpoint_prompt_version,
                            utcnow(),
                            row["id"],
                        ),
                    )
                repaired_blocks[block_index] = accepted
                continue
            try:
                api_key = self.config.gemini_key()
                if not api_key:
                    raise ChapterNeedsReview("ChÆ°a cáº¥u hÃ¬nh GEMINI_API_KEY hoáº·c file key.")
                with self.db.connect() as connection:
                    connection.execute(
                        "UPDATE repair_blocks SET status='running',attempt_count=attempt_count+1,error_message=NULL WHERE id=?",
                        (row["id"],),
                    )
                self.db.audit(
                    "gemini_api_call", job_id=job_id, chapter_id=chapter_id,
                    details={"block_index": block_index, "cache_key": lookup.cache_key},
                )
                result = repair_punctuation(
                    api_key=api_key,
                    model=repair_model,
                    block_id=f"jc{job_chapter_id}-b{block_index}",
                    text=source,
                )
                accepted = self._validate_repaired_block(
                    block_index=block_index,
                    source=source,
                    repaired=result.text,
                )
                repaired_path, _ = self.store.put_text(accepted)
                try:
                    manifest = self.repair_cache.store_result(
                        source=source,
                        repaired=accepted,
                        model=repair_model,
                        prompt_version=repair_prompt_version,
                    )
                    repaired_path = str(manifest["repaired_blob_path"])
                except (OSError, UnicodeError, ValueError, TypeError) as cache_exc:
                    self.db.audit(
                        "gemini_cache_write_failed", job_id=job_id, chapter_id=chapter_id,
                        details={
                            "block_index": block_index,
                            "error_type": type(cache_exc).__name__,
                        },
                    )
                with self.db.connect() as connection:
                    connection.execute(
                        """UPDATE repair_blocks
                           SET status='verified',source_sha256=?,lexical_sha256=?,
                               repaired_path=?,model_id=?,prompt_version=?,verified_at=?,error_message=NULL
                           WHERE id=?""",
                        (
                            source_sha,
                            lexical_sha256(source),
                            repaired_path,
                            repair_model,
                            checkpoint_prompt_version,
                            utcnow(),
                            row["id"],
                        ),
                    )
                repaired_blocks[block_index] = accepted
            except (GeminiRepairError, ChapterNeedsReview) as exc:
                with self.db.connect() as connection:
                    connection.execute(
                        "UPDATE repair_blocks SET status='failed',error_message=? WHERE id=?",
                        (str(exc)[:2000], row["id"]),
                    )
                raise ChapterNeedsReview(f"Gemini block {row['block_index']} lá»—i: {exc}") from exc
        repaired_text = self._assemble_repaired_blocks(repaired_blocks, expected_blocks)
        content_path, content_sha = self.store.put_text(repaired_text)
        duplicate = self.db.fetch_one(
            """SELECT * FROM text_revisions
               WHERE chapter_id=? AND parent_revision_id=? AND kind='repaired'
                 AND content_sha256=? AND processor_version=? AND status='approved'
               ORDER BY id DESC LIMIT 1""",
            (chapter_id, source_revision["id"], content_sha, processor_version),
        )
        if duplicate:
            with self.db.connect() as connection:
                connection.execute(
                    "UPDATE chapters SET active_text_revision_id=?,updated_at=? WHERE id=?",
                    (duplicate["id"], utcnow(), chapter_id),
                )
            return int(duplicate["id"]), repaired_text
        now = utcnow()
        with self.db.transaction() as connection:
            cursor = connection.execute(
                """INSERT INTO text_revisions(
                    chapter_id,parent_revision_id,kind,content_path,content_sha256,lexical_sha256,
                    char_count,processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    chapter_id,
                    source_revision["id"],
                    "repaired",
                    content_path,
                    content_sha,
                    lexical_sha256(repaired_text),
                    len(repaired_text),
                    processor_version,
                    "approved",
                    now,
                ),
            )
            revision_id = int(cursor.lastrowid)
            connection.execute(
                "UPDATE chapters SET active_text_revision_id=?,updated_at=? WHERE id=?",
                (revision_id, now, chapter_id),
            )
        return revision_id, repaired_text

    def _validate_repair_block_structure(
        self,
        rows: list[Any],
        expected_blocks: dict[int, str],
    ) -> None:
        expected_indexes = set(expected_blocks)
        seen: set[int] = set()
        duplicate: set[int] = set()
        unexpected: set[int] = set()
        for row in rows:
            index = int(row["block_index"])
            if index in seen:
                duplicate.add(index)
            seen.add(index)
            if index not in expected_indexes:
                unexpected.add(index)
        missing = expected_indexes - seen
        if duplicate:
            raise ChapterNeedsReview(f"Gemini repair blocks duplicate indexes: {sorted(duplicate)}")
        if missing:
            raise ChapterNeedsReview(f"Gemini repair blocks missing indexes: {sorted(missing)}")
        if unexpected:
            raise ChapterNeedsReview(f"Gemini repair blocks unexpected indexes: {sorted(unexpected)}")

    def _validate_repaired_block(self, *, block_index: int, source: str, repaired: str) -> str:
        try:
            return validate_repair_candidate(source, repaired).accepted_text
        except ValueError as exc:
            raise _repair_validation_error(block_index, str(exc)) from exc

    def _assemble_repaired_blocks(
        self,
        repaired_blocks: dict[int, str],
        expected_blocks: dict[int, str],
    ) -> str:
        expected_indexes = set(expected_blocks)
        actual_indexes = set(repaired_blocks)
        missing = expected_indexes - actual_indexes
        unexpected = actual_indexes - expected_indexes
        if missing:
            raise ChapterNeedsReview(f"Gemini repair blocks not completed: {sorted(missing)}")
        if unexpected:
            raise ChapterNeedsReview(f"Gemini repair blocks unexpected repaired indexes: {sorted(unexpected)}")
        return "\n\n".join(repaired_blocks[index] for index in sorted(expected_blocks))

    def _prepare_segments(
        self,
        job_chapter_id: int,
        text_revision_id: int,
        text: str,
        settings_snapshot: dict[str, Any],
        *,
        chapter: dict[str, Any] | None = None,
        fallback_voice: str = "",
    ) -> list[dict[str, Any]]:
        existing = self.db.fetch_all(
            "SELECT * FROM segments WHERE job_chapter_id=? ORDER BY segment_index", (job_chapter_id,)
        )
        if existing:
            return [dict(row) for row in existing]

        specs: list[dict[str, Any]] = []
        snapshot = json.loads(chapter["voice_snapshot_json"]) if chapter and chapter.get("voice_snapshot_json") else None
        if snapshot:
            if int(snapshot["text_revision_id"]) != text_revision_id:
                raise RuntimeError("Casting snapshot does not match the pinned TextRevision")
            for utterance in snapshot["utterances"]:
                start, end = int(utterance["start_offset"]), int(utterance["end_offset"])
                utterance_text = text[start:end]
                if sha256_text(utterance_text) != utterance["text_sha256"]:
                    raise RuntimeError("Casting utterance offset/hash does not match TextRevision")
                for chunk in split_tts_segments(
                    utterance_text,
                    maximum=int(settings_snapshot["max_chars"]),
                    target=int(settings_snapshot["target_chars"]),
                ):
                    specs.append(
                        {
                            "text": chunk,
                            "utterance_sequence": int(utterance["sequence"]),
                            "speaker_role": utterance["role"],
                            "character_id": utterance.get("character_id"),
                            "resolved_voice_id": utterance["resolved_voice_id"],
                        }
                    )
        else:
            for chunk in split_tts_segments(
                text,
                maximum=int(settings_snapshot["max_chars"]),
                target=int(settings_snapshot["target_chars"]),
            ):
                specs.append(
                    {
                        "text": chunk,
                        "utterance_sequence": None,
                        "speaker_role": "narrator",
                        "character_id": None,
                        "resolved_voice_id": fallback_voice,
                    }
                )
        if not specs:
            raise RuntimeError("KhÃ´ng táº¡o Ä‘Æ°á»£c TTS segment.")

        now = utcnow()
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE job_chapters SET text_revision_id=? WHERE id=?",
                (text_revision_id, job_chapter_id),
            )
            for index, spec in enumerate(specs, start=1):
                text_path, digest = self.store.put_text(spec["text"])
                synthesis_hash = sha256_text(
                    json.dumps(
                        {
                            "text_sha256": digest,
                            "voice_id": spec["resolved_voice_id"],
                            "engine_version": settings_snapshot.get(
                                "engine_version", f"vieneu:{self.config.tts_mode}"
                            ),
                            "settings": settings_snapshot,
                        },
                        sort_keys=True,
                        ensure_ascii=False,
                    )
                )
                # --- Snapshot construction ---
                voice_id = spec["resolved_voice_id"]
                engine_str = settings_snapshot.get("engine_version", f"vieneu:{self.config.tts_mode}")
                # Parse "provider:model" format, e.g., "vieneu:v3turbo"
                if ":" in engine_str:
                    snap_provider, snap_model = engine_str.split(":", 1)
                else:
                    snap_provider, snap_model = engine_str, self.config.tts_mode

                # Determine source type and refs
                if is_custom_ref(voice_id):
                    snap_source_type = "custom_reference"
                    speaker_role = spec.get("speaker_role", "narrator")
                    character_id = spec.get("character_id")
                    if character_id is not None:
                        snap_logical_ref = voice_id  # direct custom assignment on character
                    else:
                        snap_logical_ref = speaker_role  # narrator/unknown/etc.

                    snap_effective_ref = voice_id  # "custom:<id>" - stable, no revision

                    # Resolve custom ref
                    custom_voice_id = parse_custom_ref(voice_id)
                    if not hasattr(self, "_custom_ctx_cache"):
                        repo = CustomVoiceRepository(self.db, self.store)
                        self._custom_ctx_cache = CustomVoiceContext.from_repository(repo)
                    resolved = resolve_custom_ref(voice_id, self._custom_ctx_cache)

                    # Validate completeness
                    if not resolved.get("audio_sha256") or not resolved.get("audio_storage_key"):
                        raise ValueError(f"Custom reference snapshot for {voice_id} is missing required audio fields")
                    transcript = resolved.get("reference_transcript") or ""
                    if not transcript:
                        raise ValueError(f"Custom reference snapshot for {voice_id} has empty reference_transcript")
                    transcript_sha = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
                    if transcript_sha != resolved.get("transcript_sha256"):
                        raise ValueError(f"Transcript SHA-256 mismatch for {voice_id}")

                    snap_custom_revision_id = resolved["custom_voice_revision_id"]
                    snap_audio_sha = resolved["audio_sha256"]
                    snap_audio_key = resolved["audio_storage_key"]
                    snap_transcript = transcript
                    snap_transcript_sha = transcript_sha
                else:
                    snap_source_type = "preset"
                    speaker_role = spec.get("speaker_role", "narrator")
                    character_id = spec.get("character_id")
                    # Determine logical ref
                    if speaker_role == "narrator":
                        snap_logical_ref = "narrator"
                    elif speaker_role == "unknown":
                        snap_logical_ref = "unknown"
                    elif speaker_role == "character" and character_id is not None:
                        snap_logical_ref = voice_id
                    else:
                        snap_logical_ref = speaker_role
                    snap_effective_ref = voice_id
                    snap_custom_revision_id = None
                    snap_audio_sha = None
                    snap_audio_key = None
                    snap_transcript = None
                    snap_transcript_sha = None

                # Casting plan provenance
                snap_casting_plan_id = spec.get("casting_plan_id")

                # Voice resolution reason
                snap_resolution_reason = spec.get("voice_resolution_reason", "direct_assignment")

                snap_settings_json = _effective_synthesis_settings(settings_snapshot)
                snap_version = 1


                connection.execute(
                    """INSERT INTO segments(
                        job_chapter_id,segment_index,text_path,text_sha256,status,created_at,
                        utterance_sequence,speaker_role,character_id,resolved_voice_id,synthesis_hash,
                        voice_source_type,voice_provider,voice_model,logical_voice_ref,effective_voice_ref,
                        custom_voice_revision_id,reference_audio_sha256,reference_audio_storage_key,
                        reference_transcript,reference_transcript_sha256,
                        synthesis_settings_json,casting_plan_id,voice_resolution_reason,voice_snapshot_version
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        job_chapter_id,
                        index,
                        text_path,
                        digest,
                        "pending",
                        now,
                        spec["utterance_sequence"],
                        spec["speaker_role"],
                        spec["character_id"],
                        spec["resolved_voice_id"],
                        synthesis_hash,
                        snap_source_type,
                        snap_provider,
                        snap_model,
                        snap_logical_ref,
                        snap_effective_ref,
                        snap_custom_revision_id,
                        snap_audio_sha,
                        snap_audio_key,
                        snap_transcript,
                        snap_transcript_sha,
                        snap_settings_json,
                        snap_casting_plan_id,
                        snap_resolution_reason,
                        snap_version,
                    ),
                )
        # Clear custom voice context cache
        self.__dict__.pop("_custom_ctx_cache", None)

        return [
            dict(row)
            for row in self.db.fetch_all(
                "SELECT * FROM segments WHERE job_chapter_id=? ORDER BY segment_index", (job_chapter_id,)
            )
        ]

    def _assemble(
        self, job: dict[str, Any], chapter: dict[str, Any], text_revision_id: int, chapter_work: Path
    ) -> int:
        job_id = int(job["id"])
        job_chapter_id = int(chapter["id"])
        chapter_id = int(chapter["chapter_id"])
        rows = self.db.fetch_all(
            """SELECT s.*,ch.display_name AS character_name
               FROM segments s LEFT JOIN characters ch ON ch.id=s.character_id
               WHERE s.job_chapter_id=? ORDER BY s.segment_index""",
            (job_chapter_id,),
        )
        if not rows or any(row["status"] != "verified" or not row["wav_path"] for row in rows):
            raise RuntimeError("ChÆ°a Ä‘á»§ segment há»£p lá»‡ Ä‘á»ƒ ghÃ©p chÆ°Æ¡ng.")
        job_output_dir = (
            self.config.output_dir
            / f"{int(chapter['book_id'])}-{safe_slug(str(chapter['book_title']), 'book')}"
            / f"chapter_{int(chapter['chapter_number']):04d}"
            / f"job_{job_id}"
        )
        previous_renders = int(
            self.db.fetch_one(
                """SELECT COUNT(*) AS count FROM artifacts
                   WHERE job_chapter_id=? AND artifact_type='chapter_master_wav'""",
                (job_chapter_id,),
            )["count"]
        )
        output_dir = job_output_dir / f"render_{previous_renders + 1:04d}"
        output_dir.mkdir(parents=True, exist_ok=True)
        concat_path = chapter_work / "concat.txt"
        concat_path.parent.mkdir(parents=True, exist_ok=True)
        concat_lines = [f"file '{str(Path(row['wav_path']).resolve()).replace(chr(92), '/')}'" for row in rows]
        concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
        master = output_dir / "chapter_master.wav"
        master_partial = output_dir / "chapter_master.partial.wav"
        self._run_command(
            [
                "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                "-i", str(concat_path), "-c:a", "pcm_s16le", str(master_partial),
            ]
        )
        master_duration = self._ffprobe_ms(master_partial)
        master_partial.replace(master)
        synthesis_hash = sha256_text(
            json.dumps(
                {
                    "text_revision_id": text_revision_id,
                    "voice": job["voice_name"],
                    "casting_plan_sha256": chapter.get("casting_plan_sha256"),
                    "settings": json.loads(job["settings_json"]),
                },
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        master_artifact = self._insert_artifact(
            chapter_id=chapter_id,
            job_chapter_id=job_chapter_id,
            text_revision_id=text_revision_id,
            artifact_type="chapter_master_wav",
            path=master,
            duration_ms=master_duration,
            synthesis_hash=synthesis_hash,
        )
        timeline_items = []
        voice_snapshot = (
            json.loads(chapter["voice_snapshot_json"])
            if chapter.get("voice_snapshot_json")
            else None
        )
        utterance_metadata = {
            int(item["sequence"]): item
            for item in (voice_snapshot or {}).get("utterances", [])
        }
        cursor_ms = 0
        for row in rows:
            duration = int(row["duration_ms"])
            resolution = utterance_metadata.get(int(row["utterance_sequence"])) if row["utterance_sequence"] is not None else None
            timeline_items.append(
                {
                    "index": int(row["segment_index"]),
                    "text": self.store.read_text(row["text_path"]),
                    "start_ms": cursor_ms,
                    "end_ms": cursor_ms + duration,
                    "duration_ms": duration,
                    "segment_sha256": row["audio_sha256"],
                    "utterance_sequence": row["utterance_sequence"],
                    "speaker_role": row["speaker_role"] or "narrator",
                    "character_id": row["character_id"],
                    "character_name": row["character_name"],
                    "voice_id": row["resolved_voice_id"] or job["voice_name"],
                    "resolution_source": resolution.get("resolution_source") if resolution else None,
                    "resolved_gender": resolution.get("resolved_gender") if resolution else None,
                    "needs_review": bool(resolution.get("needs_review")) if resolution else False,
                    "voice_profile_id": resolution.get("voice_profile_id") if resolution else None,
                    "voice_profile_version": resolution.get("voice_profile_version") if resolution else None,
                    "synthesis_hash": row["synthesis_hash"],
                }
            )
            cursor_ms += duration
        timeline_path = output_dir / "segment_timeline.json"
        atomic_write_json(
            timeline_path,
            {
                "schema_version": 2,
                "chapter_id": chapter_id,
                "text_revision_id": text_revision_id,
                "sample_rate": self.config.tts_sample_rate,
                "duration_ms": master_duration,
                "items": timeline_items,
            },
        )
        timeline_artifact = self._insert_artifact(
            chapter_id=chapter_id,
            job_chapter_id=job_chapter_id,
            text_revision_id=text_revision_id,
            artifact_type="segment_timeline_json",
            path=timeline_path,
            duration_ms=master_duration,
            synthesis_hash=synthesis_hash,
        )
        output_format = str(job["output_format"])
        final = output_dir / f"chapter.{output_format}"
        final_partial = output_dir / f"chapter.partial.{output_format}"
        if output_format == "m4a":
            codec = ["-c:a", "aac", "-b:a", "128k"]
        else:
            codec = ["-c:a", "libmp3lame", "-b:a", "128k"]
        self._run_command(["ffmpeg", "-y", "-v", "error", "-i", str(master), *codec, str(final_partial)])
        final_duration = self._ffprobe_ms(final_partial)
        if abs(final_duration - master_duration) > 750:
            raise RuntimeError(
                f"Audio export lá»‡ch duration: master={master_duration}ms, final={final_duration}ms"
            )
        final_partial.replace(final)
        export_hash = sha256_text(json.dumps({"format": output_format, "bitrate": "128k"}, sort_keys=True))
        final_artifact = self._insert_artifact(
            chapter_id=chapter_id,
            job_chapter_id=job_chapter_id,
            text_revision_id=text_revision_id,
            artifact_type=f"chapter_{output_format}",
            path=final,
            duration_ms=final_duration,
            synthesis_hash=synthesis_hash,
            export_hash=export_hash,
        )
        now = utcnow()
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE artifacts SET status='stale' WHERE chapter_id=? AND artifact_type=? AND status='active' AND id<>?",
                (chapter_id, f"chapter_{output_format}", final_artifact),
            )
            connection.execute("UPDATE artifacts SET status='active' WHERE id=?", (final_artifact,))
            connection.execute(
                "INSERT OR IGNORE INTO artifact_dependencies(parent_artifact_id,child_artifact_id) VALUES(?,?)",
                (master_artifact, final_artifact),
            )
            connection.execute(
                "INSERT OR IGNORE INTO artifact_dependencies(parent_artifact_id,child_artifact_id) VALUES(?,?)",
                (timeline_artifact, final_artifact),
            )
            connection.execute(
                "UPDATE chapters SET active_audio_artifact_id=?,audio_status='completed',updated_at=? WHERE id=?",
                (final_artifact, now, chapter_id),
            )
        return final_artifact

    def _insert_artifact(
        self,
        *,
        chapter_id: int,
        job_chapter_id: int,
        text_revision_id: int,
        artifact_type: str,
        path: Path,
        duration_ms: int | None,
        synthesis_hash: str | None = None,
        export_hash: str | None = None,
    ) -> int:
        digest = sha256_file(path)
        now = utcnow()
        with self.db.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO artifacts(
                    chapter_id,job_chapter_id,text_revision_id,artifact_type,synthesis_hash,export_hash,
                    path,sha256,size_bytes,duration_ms,status,created_at,verified_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    chapter_id,
                    job_chapter_id,
                    text_revision_id,
                    artifact_type,
                    synthesis_hash,
                    export_hash,
                    str(path),
                    digest,
                    path.stat().st_size,
                    duration_ms,
                    "verified",
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def _ffprobe_ms(self, path: Path) -> int:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        value = float(result.stdout.strip())
        if value <= 0:
            raise RuntimeError(f"FFprobe duration khÃ´ng há»£p lá»‡: {path}")
        return int(round(value * 1000))

    @staticmethod
    def _run_command(command: list[str]) -> None:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"Command failed: {command[0]}")

    def _ensure_disk(self) -> None:
        usage = shutil.disk_usage(self.config.data_dir)
        free_gb = usage.free / (1024 ** 3)
        if free_gb < self.config.minimum_free_gb:
            raise RuntimeError(f"á»” Ä‘Ä©a chá»‰ cÃ²n {free_gb:.1f} GB, tháº¥p hÆ¡n ngÆ°á»¡ng an toÃ n.")
