from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable

from .batch_prepare_transaction_manager import IsolatedWriteTransaction
from .batch_prepare_transaction_revalidator import ValidatedPrepareSnapshot
from .db import utcnow


class PreparedJobTransactionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedJobWriteResult:
    job_id: int
    job_chapter_ids: tuple[int, ...]
    chapter_ids: tuple[int, ...]
    status: str = "prepared"
    committed: bool = False


class PreparedJobTransactionRepository:
    """Insert pinned prepared work without owning or committing the transaction."""

    def insert(
        self,
        transaction: IsolatedWriteTransaction,
        validated: ValidatedPrepareSnapshot,
        *,
        output_format: str = "m4a",
        settings_json: str = "{}",
        now: str | None = None,
        stage_hook: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> PreparedJobWriteResult:
        connection = transaction.require_active()
        if transaction.transaction_reference != validated.request.transaction_reference:
            raise PreparedJobTransactionError("transaction reference does not match validated ownership")
        chapters = validated.chapters
        if not chapters:
            raise PreparedJobTransactionError("prepared Job requires at least one chapter")
        chapter_ids = tuple(item.chapter_id for item in chapters)
        if len(chapter_ids) != len(set(chapter_ids)):
            raise PreparedJobTransactionError("duplicate chapters are not allowed")
        if output_format not in {"m4a", "mp3"}:
            raise PreparedJobTransactionError("unsupported output format")
        try:
            parsed_settings = json.loads(settings_json)
        except json.JSONDecodeError as exc:
            raise PreparedJobTransactionError("settings_json is invalid") from exc
        if not isinstance(parsed_settings, dict):
            raise PreparedJobTransactionError("settings_json must encode an object")
        timestamp = now or utcnow()
        narrators = {item.narrator_voice_id for item in chapters}
        if len(narrators) != 1:
            raise PreparedJobTransactionError("one prepared Job requires one narrator voice")
        casting_plan_id = chapters[0].casting_plan_id if len(chapters) == 1 else None
        batch_casting_snapshot = {
            "schema": "story-audio-phase9-isolated-casting-snapshot/v1",
            "chapters": [
                {
                    "chapter_id": item.chapter_id,
                    "casting_plan_id": item.casting_plan_id,
                    "casting_plan_revision": item.casting_plan_revision,
                    "casting_plan_sha256": item.casting_plan_sha256,
                    "casting_snapshot": json.loads(item.casting_snapshot_json),
                }
                for item in chapters
            ],
        }
        cursor = connection.execute(
            """INSERT INTO jobs(
                book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                settings_json,skip_completed,total_chapters,scheduled_at,created_at,updated_at,
                casting_plan_id,casting_snapshot_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                validated.request.book_id, "prepared", validated.request.from_chapter,
                validated.request.to_chapter, next(iter(narrators)), "off", output_format,
                json.dumps(parsed_settings, ensure_ascii=False, sort_keys=True), 0, len(chapters),
                timestamp, timestamp, timestamp, casting_plan_id,
                json.dumps(batch_casting_snapshot, ensure_ascii=False, sort_keys=True),
            ),
        )
        job_id = int(cursor.lastrowid)
        if stage_hook:
            stage_hook("after_job_insert", {"job_id": job_id})
        job_chapter_ids: list[int] = []
        for item in chapters:
            chapter_cursor = connection.execute(
                """INSERT INTO job_chapters(
                    job_id,chapter_id,sequence,status,text_revision_id,casting_plan_id,
                    casting_plan_sha256,voice_snapshot_json
                ) VALUES(?,?,?,'pending',?,?,?,?)""",
                (
                    job_id, item.chapter_id, item.deterministic_order, item.text_revision_id,
                    item.casting_plan_id, item.casting_plan_sha256, item.voice_snapshot_json,
                ),
            )
            job_chapter_ids.append(int(chapter_cursor.lastrowid))
            if stage_hook:
                stage_hook(
                    "after_job_chapter_insert",
                    {"job_id": job_id, "job_chapter_id": int(chapter_cursor.lastrowid), "count": len(job_chapter_ids)},
                )
        return PreparedJobWriteResult(job_id, tuple(job_chapter_ids), chapter_ids)

    @staticmethod
    def inspect(connection: sqlite3.Connection, job_id: int) -> dict[str, Any]:
        job = connection.execute("SELECT * FROM jobs WHERE id=?", (int(job_id),)).fetchone()
        chapters = connection.execute(
            "SELECT * FROM job_chapters WHERE job_id=? ORDER BY sequence,id", (int(job_id),)
        ).fetchall()
        return {"job": dict(job) if job else None, "job_chapters": [dict(row) for row in chapters]}


__all__ = [
    "PreparedJobTransactionError",
    "PreparedJobTransactionRepository",
    "PreparedJobWriteResult",
]
