from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .db import Database, utcnow


MAX_AUDIO_REMOVAL_ITEMS = 500
NON_TERMINAL_JOB_STATUSES = (
    "prepared",
    "scheduled",
    "queued",
    "running",
    "repairing",
    "synthesizing",
    "assembling",
    "paused",
    "interrupted",
)


@dataclass
class AudioLibraryRemovalError(RuntimeError):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


def _normalise_ids(artifact_ids: list[int]) -> list[int]:
    ids = [int(value) for value in artifact_ids]
    if not ids:
        raise AudioLibraryRemovalError("EMPTY_SCOPE", "Chưa chọn audio nào.")
    if len(ids) > MAX_AUDIO_REMOVAL_ITEMS:
        raise AudioLibraryRemovalError(
            "SCOPE_TOO_LARGE",
            f"Mỗi lần chỉ được xóa tối đa {MAX_AUDIO_REMOVAL_ITEMS} audio.",
        )
    if len(set(ids)) != len(ids):
        raise AudioLibraryRemovalError("DUPLICATE_ARTIFACT", "Danh sách audio bị trùng.")
    return sorted(ids)


def _rows(connection, artifact_ids: list[int]) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in artifact_ids)
    rows = connection.execute(
        f"""
        SELECT a.id AS artifact_id,a.sha256,a.size_bytes,
               c.id AS chapter_id,c.chapter_number,c.title AS chapter_title,
               b.id AS book_id,b.title AS book_title
        FROM artifacts a
        JOIN chapters c ON c.active_audio_artifact_id=a.id
        JOIN books b ON b.id=c.book_id
        WHERE a.id IN ({placeholders}) AND a.deleted_at IS NULL
        ORDER BY a.id
        """,
        tuple(artifact_ids),
    ).fetchall()
    return [dict(row) for row in rows]


def _fingerprint(rows: list[dict[str, Any]]) -> str:
    identity = [
        {
            "artifact_id": int(row["artifact_id"]),
            "chapter_id": int(row["chapter_id"]),
            "sha256": str(row["sha256"] or ""),
        }
        for row in rows
    ]
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _preview_from_connection(connection, artifact_ids: list[int]) -> dict[str, Any]:
    ids = _normalise_ids(artifact_ids)
    rows = _rows(connection, ids)
    found = {int(row["artifact_id"]) for row in rows}
    if found != set(ids):
        raise AudioLibraryRemovalError(
            "STALE_SCOPE",
            "Ít nhất một audio không còn là bản hiện tại. Hãy làm mới danh sách rồi chọn lại.",
        )
    chapter_ids = [int(row["chapter_id"]) for row in rows]
    chapter_placeholders = ",".join("?" for _ in chapter_ids)
    status_placeholders = ",".join("?" for _ in NON_TERMINAL_JOB_STATUSES)
    live = connection.execute(
        f"""SELECT jc.chapter_id,j.id AS job_id,j.status
            FROM job_chapters jc JOIN jobs j ON j.id=jc.job_id
            WHERE jc.chapter_id IN ({chapter_placeholders})
              AND j.status IN ({status_placeholders})
            ORDER BY j.id LIMIT 1""",
        (*chapter_ids, *NON_TERMINAL_JOB_STATUSES),
    ).fetchone()
    if live is not None:
        raise AudioLibraryRemovalError(
            "ACTIVE_JOB_CONFLICT",
            f"Chương đang có Công việc #{int(live['job_id'])} chưa kết thúc. Hãy xử lý Công việc trước khi xóa audio hiện tại.",
        )
    items = [
        {
            "artifact_id": int(row["artifact_id"]),
            "chapter_id": int(row["chapter_id"]),
            "book_id": int(row["book_id"]),
            "book_title": row["book_title"],
            "chapter_number": int(row["chapter_number"]),
            "chapter_title": row["chapter_title"],
            "sha256": row["sha256"],
            "size_bytes": int(row["size_bytes"] or 0),
        }
        for row in rows
    ]
    return {
        "items": items,
        "count": len(items),
        "total_size_bytes": sum(item["size_bytes"] for item in items),
        "fingerprint": _fingerprint(rows),
        "confirmation": f"XOA {len(items)} AUDIO",
        "effect": "REMOVE_CURRENT_OUTPUT_ONLY",
        "retained": ["artifact_file", "job", "human_qa_history", "text_revision", "casting_plan"],
    }


def preview_audio_library_removal(db: Database, artifact_ids: list[int]) -> dict[str, Any]:
    with db.connect() as connection:
        return _preview_from_connection(connection, artifact_ids)


def remove_audio_library_outputs(
    db: Database,
    *,
    artifact_ids: list[int],
    fingerprint: str,
    confirmation: str,
    idempotency_key: str,
) -> dict[str, Any]:
    requested_ids = _normalise_ids(artifact_ids)
    with db.transaction() as connection:
        prior = connection.execute(
            """SELECT details_json FROM audit_events
               WHERE event_code='audio_library_outputs_removed'
                 AND json_extract(details_json,'$.idempotency_key')=?
               ORDER BY id DESC LIMIT 1""",
            (idempotency_key,),
        ).fetchone()
        if prior is not None:
            try:
                details = json.loads(prior["details_json"] or "{}")
            except (TypeError, ValueError):
                details = {}
            if isinstance(details.get("result"), dict):
                prior_ids = sorted(int(value) for value in details["result"].get("artifact_ids", []))
                if prior_ids != requested_ids:
                    raise AudioLibraryRemovalError(
                        "IDEMPOTENCY_KEY_REUSED",
                        "Mã thao tác đã được dùng cho một phạm vi audio khác.",
                    )
                return {**details["result"], "reused": True}

        preview = _preview_from_connection(connection, requested_ids)
        if preview["fingerprint"] != fingerprint:
            raise AudioLibraryRemovalError(
                "STALE_FINGERPRINT",
                "Danh sách audio đã thay đổi sau khi xem trước. Chưa có audio nào bị xóa.",
            )
        if confirmation.strip() != preview["confirmation"]:
            raise AudioLibraryRemovalError(
                "CONFIRMATION_MISMATCH",
                f"Nhập chính xác {preview['confirmation']} để xác nhận.",
            )

        now = utcnow()
        for item in preview["items"]:
            cursor = connection.execute(
                """UPDATE chapters
                   SET active_audio_artifact_id=NULL,audio_status='not_created',updated_at=?
                   WHERE id=? AND active_audio_artifact_id=?""",
                (now, item["chapter_id"], item["artifact_id"]),
            )
            if cursor.rowcount != 1:
                raise AudioLibraryRemovalError(
                    "STALE_SCOPE",
                    "Audio hiện tại đã thay đổi. Toàn bộ thao tác đã được hủy.",
                )

        result = {
            "removed_count": preview["count"],
            "artifact_ids": [item["artifact_id"] for item in preview["items"]],
            "chapter_ids": [item["chapter_id"] for item in preview["items"]],
            "retained": preview["retained"],
            "reused": False,
        }
        connection.execute(
            "INSERT INTO audit_events(event_code,job_id,chapter_id,details_json,created_at) VALUES(?,?,?,?,?)",
            (
                "audio_library_outputs_removed",
                None,
                preview["items"][0]["chapter_id"] if preview["count"] == 1 else None,
                json.dumps(
                    {
                        "idempotency_key": idempotency_key,
                        "fingerprint": fingerprint,
                        "artifacts": [
                            {
                                "artifact_id": item["artifact_id"],
                                "chapter_id": item["chapter_id"],
                                "sha256": item["sha256"],
                            }
                            for item in preview["items"]
                        ],
                        "result": result,
                    },
                    ensure_ascii=False,
                ),
                now,
            ),
        )
    return result
