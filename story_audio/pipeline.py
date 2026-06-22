from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .db import Database, utcnow
from .files import atomic_write_json, safe_slug, sha256_file, sha256_text
from .gemini import GeminiRepairError, repair_punctuation
from .storage import ContentStore
from .text import lexical_sha256, qa_text, split_repair_blocks, split_tts_segments, validate_lexical_identity
from .tts import TtsService


class JobCancelled(RuntimeError):
    pass


class JobPaused(RuntimeError):
    pass


class ChapterNeedsReview(RuntimeError):
    pass


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
) -> dict[str, Any]:
    if from_chapter > to_chapter:
        raise ValueError("Chương bắt đầu phải nhỏ hơn hoặc bằng chương kết thúc.")
    if repair_mode not in {"off", "qa_only", "all_selected"}:
        raise ValueError("Chế độ Gemini không hợp lệ.")
    if output_format not in {"m4a", "mp3"}:
        raise ValueError("Định dạng đầu ra phải là m4a hoặc mp3.")
    book = db.fetch_one("SELECT * FROM books WHERE id=?", (book_id,))
    if not book:
        raise ValueError("Không tìm thấy sách.")
    chapters = db.fetch_all(
        "SELECT * FROM chapters WHERE book_id=? AND chapter_number BETWEEN ? AND ? ORDER BY chapter_number",
        (book_id, from_chapter, to_chapter),
    )
    if not chapters:
        raise ValueError("Khoảng được chọn không có chương.")
    expected = list(range(from_chapter, to_chapter + 1))
    actual = [int(row["chapter_number"]) for row in chapters]
    missing = sorted(set(expected) - set(actual))
    if missing:
        raise ValueError(f"Khoảng chương bị thiếu: {missing[:20]}")
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
    }
    with db.transaction() as connection:
        cursor = connection.execute(
            """INSERT INTO jobs(
                book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                settings_json,skip_completed,total_chapters,scheduled_at,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
            ),
        )
        job_id = int(cursor.lastrowid)
        for sequence, chapter in enumerate(selected, start=1):
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
        },
    )
    return {
        "job_id": job_id,
        "selected_chapters": len(selected),
        "skipped_completed": len(chapters) - len(selected),
        "undo_until": scheduled.isoformat(),
    }


class PipelineWorker:
    def __init__(self, db: Database, store: ContentStore, tts: TtsService, config: Settings):
        self.db = db
        self.store = store
        self.tts = tts
        self.config = config
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
            raise JobCancelled("Job không còn tồn tại.")
        if row["cancel_requested"]:
            raise JobCancelled("Đã yêu cầu hủy.")
        if row["pause_requested"]:
            raise JobPaused("Đã yêu cầu tạm dừng.")

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
        segments = self._prepare_segments(job_chapter_id, text_revision_id, text, settings_snapshot)
        self._set_job(job_id, "synthesizing", "tts", current_chapter_number=chapter["chapter_number"])
        chapter_work = self.config.work_dir / f"job_{job_id}" / f"chapter_{int(chapter['chapter_number']):04d}"
        segment_dir = chapter_work / "segments"
        for position, segment in enumerate(segments):
            self._control(job_id)
            segment_path = segment_dir / f"{int(segment['segment_index']):06d}.wav"
            if segment["status"] == "verified" and segment_path.exists():
                continue
            text_value = self.store.read_text(segment["text_path"])
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
                        text=text_value,
                        voice=str(job["voice_name"]),
                        temperature=float(settings_snapshot["temperature"]),
                        top_k=int(settings_snapshot["top_k"]),
                        max_chars=int(settings_snapshot["max_chars"]),
                        silence_seconds=(float(settings_snapshot["silence_seconds"]) if position < len(segments) - 1 else 0.0),
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
            raise RuntimeError("Chương chưa có reflowed TextRevision.")
        source_text = self.store.read_text(source_revision["content_path"])
        mode = str(job["repair_mode"])
        if mode == "off":
            return int(source_revision["id"]), source_text
        if mode == "qa_only":
            issues = qa_text(source_text)
            if not any(issue.code == "missing_punctuation" for issue in issues):
                return int(source_revision["id"]), source_text
        api_key = self.config.gemini_key()
        if not api_key:
            raise ChapterNeedsReview("Chưa cấu hình GEMINI_API_KEY hoặc file key.")
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
                            self.config.gemini_model,
                            self.config.gemini_prompt_version,
                        ),
                    )
            existing = self.db.fetch_all(
                "SELECT * FROM repair_blocks WHERE job_chapter_id=? ORDER BY block_index",
                (job_chapter_id,),
            )
        repaired_blocks: list[str] = []
        for row in existing:
            self._control(job_id)
            source = self.store.read_text(row["source_path"])
            if row["status"] == "verified" and row["repaired_path"]:
                repaired_blocks.append(self.store.read_text(row["repaired_path"]))
                continue
            try:
                with self.db.connect() as connection:
                    connection.execute(
                        "UPDATE repair_blocks SET status='running',attempt_count=attempt_count+1,error_message=NULL WHERE id=?",
                        (row["id"],),
                    )
                result = repair_punctuation(
                    api_key=api_key,
                    model=self.config.gemini_model,
                    block_id=f"jc{job_chapter_id}-b{row['block_index']}",
                    text=source,
                )
                repaired_path, _ = self.store.put_text(result.text)
                with self.db.connect() as connection:
                    connection.execute(
                        "UPDATE repair_blocks SET status='verified',repaired_path=?,verified_at=? WHERE id=?",
                        (repaired_path, utcnow(), row["id"]),
                    )
                repaired_blocks.append(result.text)
            except GeminiRepairError as exc:
                with self.db.connect() as connection:
                    connection.execute(
                        "UPDATE repair_blocks SET status='failed',error_message=? WHERE id=?",
                        (str(exc)[:2000], row["id"]),
                    )
                raise ChapterNeedsReview(f"Gemini block {row['block_index']} lỗi: {exc}") from exc
        repaired_text = "\n\n".join(repaired_blocks)
        valid, reason = validate_lexical_identity(source_text, repaired_text)
        if not valid:
            raise ChapterNeedsReview(f"Gemini thay đổi nội dung chương: {reason}")
        content_path, content_sha = self.store.put_text(repaired_text)
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
                    f"{self.config.gemini_model}:{self.config.gemini_prompt_version}",
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

    def _prepare_segments(
        self, job_chapter_id: int, text_revision_id: int, text: str, settings_snapshot: dict[str, Any]
    ) -> list[dict[str, Any]]:
        existing = self.db.fetch_all(
            "SELECT * FROM segments WHERE job_chapter_id=? ORDER BY segment_index", (job_chapter_id,)
        )
        if existing:
            return [dict(row) for row in existing]
        values = split_tts_segments(
            text,
            maximum=int(settings_snapshot["max_chars"]),
            target=int(settings_snapshot["target_chars"]),
        )
        if not values:
            raise RuntimeError("Không tạo được TTS segment.")
        now = utcnow()
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE job_chapters SET text_revision_id=? WHERE id=?",
                (text_revision_id, job_chapter_id),
            )
            for index, value in enumerate(values, start=1):
                text_path, digest = self.store.put_text(value)
                connection.execute(
                    "INSERT INTO segments(job_chapter_id,segment_index,text_path,text_sha256,status,created_at) VALUES(?,?,?,?,?,?)",
                    (job_chapter_id, index, text_path, digest, "pending", now),
                )
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
            "SELECT * FROM segments WHERE job_chapter_id=? ORDER BY segment_index", (job_chapter_id,)
        )
        if not rows or any(row["status"] != "verified" or not row["wav_path"] for row in rows):
            raise RuntimeError("Chưa đủ segment hợp lệ để ghép chương.")
        output_dir = (
            self.config.output_dir
            / f"{int(chapter['book_id'])}-{safe_slug(str(chapter['book_title']), 'book')}"
            / f"chapter_{int(chapter['chapter_number']):04d}"
            / f"job_{job_id}"
        )
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
        cursor_ms = 0
        for row in rows:
            duration = int(row["duration_ms"])
            timeline_items.append(
                {
                    "index": int(row["segment_index"]),
                    "text": self.store.read_text(row["text_path"]),
                    "start_ms": cursor_ms,
                    "end_ms": cursor_ms + duration,
                    "duration_ms": duration,
                    "segment_sha256": row["audio_sha256"],
                }
            )
            cursor_ms += duration
        timeline_path = output_dir / "segment_timeline.json"
        atomic_write_json(
            timeline_path,
            {
                "schema_version": 1,
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
                f"Audio export lệch duration: master={master_duration}ms, final={final_duration}ms"
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
            raise RuntimeError(f"FFprobe duration không hợp lệ: {path}")
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
            raise RuntimeError(f"Ổ đĩa chỉ còn {free_gb:.1f} GB, thấp hơn ngưỡng an toàn.")
