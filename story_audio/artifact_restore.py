from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .db import Database, utcnow
from .files import sha256_file


FINAL_AUDIO_ARTIFACT_TYPES = {
    "chapter_m4a",
    "chapter_mp3",
    "chapter_final_m4a",
    "chapter_final_mp3",
}
ACTIVE_RENDER_STATUSES = {
    "scheduled",
    "queued",
    "running",
    "repairing",
    "synthesizing",
    "assembling",
}


class AcceptedArtifactRestoreError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _json_object(raw: Any) -> dict[str, Any]:
    try:
        payload = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _restore_snapshot(connection, chapter_id: int, artifact_id: int) -> dict[str, Any]:
    chapter = connection.execute(
        "SELECT id,active_audio_artifact_id FROM chapters WHERE id=?",
        (chapter_id,),
    ).fetchone()
    if not chapter:
        raise AcceptedArtifactRestoreError("CHAPTER_NOT_FOUND", "Không tìm thấy chương cần khôi phục.")

    artifact = connection.execute(
        """
        SELECT a.*,jc.job_id,jc.status AS job_chapter_status,j.status AS job_status
        FROM artifacts a
        LEFT JOIN job_chapters jc ON jc.id=a.job_chapter_id
        LEFT JOIN jobs j ON j.id=jc.job_id
        WHERE a.id=? AND a.chapter_id=?
        """,
        (artifact_id, chapter_id),
    ).fetchone()
    if not artifact or artifact["deleted_at"]:
        raise AcceptedArtifactRestoreError(
            "ARTIFACT_NOT_FOUND", "Bản audio lịch sử không còn tồn tại."
        )
    if str(artifact["artifact_type"]) not in FINAL_AUDIO_ARTIFACT_TYPES:
        raise AcceptedArtifactRestoreError(
            "ARTIFACT_NOT_FINAL_AUDIO", "Artifact đã chọn không phải bản audio chương hoàn chỉnh."
        )
    if not artifact["job_id"] or str(artifact["job_chapter_status"]) != "completed":
        raise AcceptedArtifactRestoreError(
            "ARTIFACT_BINDING_INVALID", "Bản audio không có liên kết Job hoàn tất đáng tin cậy."
        )
    if not artifact["verified_at"]:
        raise AcceptedArtifactRestoreError(
            "ARTIFACT_NOT_VERIFIED", "Bản audio chưa có bằng chứng kiểm tra file."
        )

    qa_rows = connection.execute(
        """
        SELECT id,job_id,details_json,created_at
        FROM audit_events
        WHERE chapter_id=? AND event_code='human_qa_recorded'
        ORDER BY id DESC
        """,
        (chapter_id,),
    ).fetchall()
    approval_row = None
    approval: dict[str, Any] = {}
    for row in qa_rows:
        details = _json_object(row["details_json"])
        if int(details.get("artifact_id") or 0) != artifact_id:
            continue
        approval_row = row
        approval = details
        break
    if not approval_row or str(approval.get("status") or "").lower() != "approved":
        raise AcceptedArtifactRestoreError(
            "ACCEPTED_APPROVAL_REQUIRED",
            "Chỉ có thể khôi phục bản audio có kết quả Human QA 'Đã chấp nhận' mới nhất.",
        )
    if (
        str(approval.get("sha256") or "") != str(artifact["sha256"])
        or int(approval.get("duration_ms") or -1) != int(artifact["duration_ms"] or -2)
        or int(approval.get("job_id") or approval_row["job_id"] or 0)
        != int(artifact["job_id"])
    ):
        raise AcceptedArtifactRestoreError(
            "APPROVAL_EVIDENCE_MISMATCH",
            "Bằng chứng Human QA không còn khớp chính xác với bản audio lịch sử.",
        )

    active_job = connection.execute(
        f"""
        SELECT j.id,j.status
        FROM jobs j JOIN job_chapters jc ON jc.job_id=j.id
        WHERE jc.chapter_id=? AND j.status IN ({','.join('?' for _ in ACTIVE_RENDER_STATUSES)})
        ORDER BY j.id DESC LIMIT 1
        """,
        (chapter_id, *sorted(ACTIVE_RENDER_STATUSES)),
    ).fetchone()
    if active_job:
        raise AcceptedArtifactRestoreError(
            "CHAPTER_RENDER_ACTIVE",
            f"Chương đang có Job #{int(active_job['id'])} ở trạng thái {active_job['status']}; chưa thể đổi bản hiện tại.",
        )
    if str(artifact["job_status"]) not in {"completed", "completed_with_errors"}:
        raise AcceptedArtifactRestoreError(
            "ARTIFACT_JOB_NOT_TERMINAL", "Job tạo bản audio này chưa kết thúc an toàn."
        )

    return {
        "chapter": chapter,
        "artifact": artifact,
        "approval": approval,
        "approval_event_id": int(approval_row["id"]),
        "approval_recorded_at": approval_row["created_at"],
    }


def _verify_artifact_file(artifact: Any) -> None:
    path = Path(str(artifact["path"]))
    if not path.is_file():
        raise AcceptedArtifactRestoreError(
            "ARTIFACT_FILE_MISSING", "File audio lịch sử không còn tồn tại trên ổ đĩa."
        )
    if path.stat().st_size != int(artifact["size_bytes"]):
        raise AcceptedArtifactRestoreError(
            "ARTIFACT_FILE_CHANGED", "Kích thước file audio lịch sử đã thay đổi."
        )
    if sha256_file(path) != str(artifact["sha256"]):
        raise AcceptedArtifactRestoreError(
            "ARTIFACT_FILE_CHANGED", "Nội dung file audio lịch sử không còn khớp bằng chứng."
        )


def inspect_accepted_artifact_restore(
    db: Database,
    *,
    chapter_id: int,
    artifact_id: int,
) -> dict[str, Any]:
    try:
        with db.connect() as connection:
            snapshot = _restore_snapshot(connection, chapter_id, artifact_id)
            active_id = int(snapshot["chapter"]["active_audio_artifact_id"] or 0)
            if active_id == artifact_id:
                raise AcceptedArtifactRestoreError(
                    "ARTIFACT_ALREADY_ACTIVE", "Bản audio này đã là bản hiện tại."
                )
            artifact = snapshot["artifact"]
            path = Path(str(artifact["path"]))
            if not path.is_file() or path.stat().st_size != int(artifact["size_bytes"]):
                raise AcceptedArtifactRestoreError(
                    "ARTIFACT_FILE_UNAVAILABLE", "File audio lịch sử không sẵn sàng để khôi phục."
                )
            return {
                "eligible": True,
                "code": "READY",
                "message": "Bản đã duyệt có thể được khôi phục làm bản hiện tại.",
                "active_artifact_id": active_id,
                "artifact_id": artifact_id,
                "approval_event_id": snapshot["approval_event_id"],
            }
    except AcceptedArtifactRestoreError as exc:
        return {
            "eligible": False,
            "code": exc.code,
            "message": str(exc),
            "artifact_id": artifact_id,
        }


def restore_accepted_artifact(
    db: Database,
    *,
    chapter_id: int,
    artifact_id: int,
    expected_active_artifact_id: int,
) -> dict[str, Any]:
    with db.transaction() as connection:
        current = connection.execute(
            "SELECT active_audio_artifact_id FROM chapters WHERE id=?",
            (chapter_id,),
        ).fetchone()
        if not current:
            raise AcceptedArtifactRestoreError("CHAPTER_NOT_FOUND", "Không tìm thấy chương cần khôi phục.")
        current_id = int(current["active_audio_artifact_id"] or 0)
        if current_id == artifact_id:
            prior_rows = connection.execute(
                """
                SELECT details_json FROM audit_events
                WHERE chapter_id=? AND event_code='accepted_audio_artifact_restored'
                ORDER BY id DESC
                """,
                (chapter_id,),
            ).fetchall()
            for row in prior_rows:
                details = _json_object(row["details_json"])
                if (
                    int(details.get("artifact_id") or 0) == artifact_id
                    and int(details.get("previous_artifact_id") or 0)
                    == expected_active_artifact_id
                ):
                    return {
                        "chapter_id": chapter_id,
                        "artifact_id": artifact_id,
                        "previous_artifact_id": expected_active_artifact_id,
                        "approval_event_id": details.get("approval_event_id"),
                        "idempotent_reused": True,
                    }
        if current_id != expected_active_artifact_id:
            raise AcceptedArtifactRestoreError(
                "ACTIVE_ARTIFACT_CHANGED",
                "Bản audio hiện tại đã thay đổi. Hãy tải lại trước khi khôi phục.",
            )

        snapshot = _restore_snapshot(connection, chapter_id, artifact_id)
        artifact = snapshot["artifact"]
        _verify_artifact_file(artifact)
        approval = snapshot["approval"]
        restored_at = utcnow()
        restored_approval = {
            "status": "approved",
            "recorded_at": snapshot["approval_recorded_at"],
            "approved_at": snapshot["approval_recorded_at"],
            "notes": str(approval.get("notes") or ""),
            "artifact_id": artifact_id,
            "job_id": int(artifact["job_id"]),
            "output_path": artifact["path"],
            "sha256": artifact["sha256"],
            "duration_ms": int(artifact["duration_ms"]),
            "qa_feedback": approval.get("qa_feedback") or {},
            "restored_at": restored_at,
            "restore_evidence_id": snapshot["approval_event_id"],
        }
        connection.execute(
            """
            UPDATE artifacts SET status='stale'
            WHERE chapter_id=? AND artifact_type IN ('chapter_m4a','chapter_mp3','chapter_final_m4a','chapter_final_mp3')
              AND status='active' AND id<>?
            """,
            (chapter_id, artifact_id),
        )
        connection.execute("UPDATE artifacts SET status='active' WHERE id=?", (artifact_id,))
        connection.execute(
            """
            UPDATE chapters
            SET active_audio_artifact_id=?,audio_status='completed',human_approval_json=?,updated_at=?
            WHERE id=? AND active_audio_artifact_id=?
            """,
            (
                artifact_id,
                json.dumps(restored_approval, ensure_ascii=False),
                restored_at,
                chapter_id,
                expected_active_artifact_id,
            ),
        )
        if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
            raise AcceptedArtifactRestoreError(
                "ACTIVE_ARTIFACT_CHANGED",
                "Bản audio hiện tại đã thay đổi. Hãy tải lại trước khi khôi phục.",
            )
        details = {
            "artifact_id": artifact_id,
            "previous_artifact_id": expected_active_artifact_id,
            "approval_event_id": snapshot["approval_event_id"],
            "sha256": artifact["sha256"],
            "duration_ms": int(artifact["duration_ms"]),
        }
        connection.execute(
            """
            INSERT INTO audit_events(event_code,job_id,chapter_id,details_json,created_at)
            VALUES('accepted_audio_artifact_restored',?,?,?,?)
            """,
            (
                int(artifact["job_id"]),
                chapter_id,
                json.dumps(details, ensure_ascii=False),
                restored_at,
            ),
        )
    return {
        "chapter_id": chapter_id,
        "artifact_id": artifact_id,
        "previous_artifact_id": expected_active_artifact_id,
        "approval_event_id": snapshot["approval_event_id"],
        "idempotent_reused": False,
    }


__all__ = [
    "AcceptedArtifactRestoreError",
    "inspect_accepted_artifact_restore",
    "restore_accepted_artifact",
]
