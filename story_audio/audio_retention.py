"""Keep one current audio bundle per chapter and remove superseded media."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .db import Database


FINAL_AUDIO_TYPES = {
    "chapter_m4a",
    "chapter_mp3",
    "chapter_final_m4a",
    "chapter_final_mp3",
}


class AudioRetentionError(RuntimeError):
    pass


def _ids(values: Iterable[int]) -> list[int]:
    return sorted({int(value) for value in values})


def _placeholders(values: list[int]) -> str:
    return ",".join("?" for _ in values)


def _inside(path: Path, roots: tuple[Path, ...]) -> bool:
    resolved = path.resolve(strict=False)
    return any(resolved == root or root in resolved.parents for root in roots)


def _validated_paths(
    paths: Iterable[str],
    *,
    allowed_roots: Iterable[Path],
    protected_paths: Iterable[str] = (),
) -> list[str]:
    roots = tuple(Path(root).resolve(strict=False) for root in allowed_roots)
    protected = {
        Path(raw).resolve(strict=False)
        for raw in protected_paths
        if raw
    }
    validated: list[str] = []
    for raw in sorted({str(value) for value in paths if value}):
        path = Path(raw).resolve(strict=False)
        if not _inside(path, roots):
            raise AudioRetentionError(f"Refusing audio cleanup outside configured roots: {path}")
        if path not in protected:
            validated.append(str(path))
    return validated


def _delete_exact_files(paths: Iterable[str], *, allowed_roots: Iterable[Path]) -> dict[str, Any]:
    roots = tuple(Path(root).resolve(strict=False) for root in allowed_roots)
    deleted = 0
    bytes_freed = 0
    parents: set[Path] = set()
    failures: list[str] = []
    for raw in sorted({str(value) for value in paths if value}):
        path = Path(raw).resolve(strict=False)
        try:
            if path.is_file():
                size = path.stat().st_size
                path.unlink()
                deleted += 1
                bytes_freed += size
                parents.add(path.parent)
        except OSError as exc:
            failures.append(f"{path}: {exc}")
    for parent in sorted(parents, key=lambda value: len(value.parts), reverse=True):
        current = parent
        while _inside(current, roots) and current not in roots:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent
    return {
        "deleted_files": deleted,
        "bytes_freed": bytes_freed,
        "file_cleanup_failures": failures,
    }


def _event_artifact_id(row: Any) -> int:
    try:
        details = json.loads(row["details_json"] or "{}")
    except (TypeError, ValueError):
        return 0
    return int(details.get("artifact_id") or 0) if isinstance(details, dict) else 0


def purge_audio_history(
    db: Database,
    *,
    output_root: Path,
    work_root: Path,
    chapter_ids: Iterable[int] | None = None,
) -> dict[str, Any]:
    """Delete every audio bundle except the chapter's current artifact family.

    Jobs, text revisions, casting snapshots and custom voices remain. Segment rows
    remain useful operational evidence, but their superseded WAV files are removed.
    """

    requested_chapters = _ids(chapter_ids or [])
    if chapter_ids is not None and not requested_chapters:
        return {
            "deleted_artifacts": 0,
            "deleted_artifact_ids": [],
            "deleted_files": 0,
            "bytes_freed": 0,
            "cleared_approvals": 0,
            "cleared_segment_files": 0,
            "deleted_qa_events": 0,
            "deleted_operation_events": 0,
            "file_cleanup_failures": [],
        }
    chapter_clause = ""
    chapter_params: tuple[Any, ...] = ()
    if requested_chapters:
        chapter_clause = f" WHERE id IN ({_placeholders(requested_chapters)})"
        chapter_params = tuple(requested_chapters)

    with db.transaction() as connection:
        chapters = connection.execute(
            f"SELECT id,active_audio_artifact_id,human_approval_json FROM chapters{chapter_clause}",
            chapter_params,
        ).fetchall()
        scope_ids = [int(row["id"]) for row in chapters]
        if not scope_ids:
            return {
                "deleted_artifacts": 0,
                "deleted_artifact_ids": [],
                "deleted_files": 0,
                "bytes_freed": 0,
                "cleared_approvals": 0,
                "cleared_segment_files": 0,
                "deleted_qa_events": 0,
                "deleted_operation_events": 0,
                "file_cleanup_failures": [],
            }

        artifact_rows = connection.execute(
            f"SELECT id,chapter_id,job_chapter_id,artifact_type,path,size_bytes FROM artifacts WHERE chapter_id IN ({_placeholders(scope_ids)})",
            tuple(scope_ids),
        ).fetchall()
        current_final_ids = {
            int(row["active_audio_artifact_id"])
            for row in chapters
            if row["active_audio_artifact_id"]
        }
        keep_ids = set(current_final_ids)
        if current_final_ids:
            keep_params = _ids(current_final_ids)
            parents = connection.execute(
                f"SELECT parent_artifact_id FROM artifact_dependencies WHERE child_artifact_id IN ({_placeholders(keep_params)})",
                tuple(keep_params),
            ).fetchall()
            keep_ids.update(int(row["parent_artifact_id"]) for row in parents)

        delete_rows = [row for row in artifact_rows if int(row["id"]) not in keep_ids]
        delete_ids = _ids(int(row["id"]) for row in delete_rows)
        deleted_final_ids = {
            int(row["id"])
            for row in delete_rows
            if str(row["artifact_type"]) in FINAL_AUDIO_TYPES
        }
        old_job_chapter_ids = _ids(
            int(row["job_chapter_id"])
            for row in delete_rows
            if row["job_chapter_id"]
            and not any(
                int(kept["job_chapter_id"] or 0) == int(row["job_chapter_id"])
                for kept in artifact_rows
                if int(kept["id"]) in keep_ids
            )
        )

        segment_rows: list[Any] = []
        if old_job_chapter_ids:
            segment_rows = connection.execute(
                f"SELECT id,wav_path FROM segments WHERE job_chapter_id IN ({_placeholders(old_job_chapter_ids)}) AND wav_path IS NOT NULL",
                tuple(old_job_chapter_ids),
            ).fetchall()
        kept_artifact_paths = [
            row["path"] for row in artifact_rows if int(row["id"]) in keep_ids
        ]
        file_paths = _validated_paths(
            [row["path"] for row in delete_rows]
            + [row["wav_path"] for row in segment_rows],
            allowed_roots=(output_root, work_root),
            protected_paths=kept_artifact_paths,
        )

        if old_job_chapter_ids:
            connection.execute(
                f"UPDATE segments SET wav_path=NULL WHERE job_chapter_id IN ({_placeholders(old_job_chapter_ids)})",
                tuple(old_job_chapter_ids),
            )

        cleared_approvals = 0
        for row in chapters:
            raw = row["human_approval_json"]
            if not raw:
                continue
            try:
                approval = json.loads(raw)
            except (TypeError, ValueError):
                approval = {}
            current_id = int(row["active_audio_artifact_id"] or 0)
            if int(approval.get("artifact_id") or 0) != current_id:
                connection.execute(
                    "UPDATE chapters SET human_approval_json=NULL WHERE id=?",
                    (int(row["id"]),),
                )
                cleared_approvals += 1

        event_rows = connection.execute(
            f"SELECT id,event_code,details_json FROM audit_events WHERE chapter_id IN ({_placeholders(scope_ids)}) AND event_code IN ('human_qa_recorded','accepted_audio_artifact_restored','chapter_completed')",
            tuple(scope_ids),
        ).fetchall()
        delete_event_ids = []
        for row in event_rows:
            artifact_id = _event_artifact_id(row)
            if row["event_code"] == "accepted_audio_artifact_restored" or artifact_id in deleted_final_ids:
                delete_event_ids.append(int(row["id"]))
        if delete_event_ids:
            connection.execute(
                f"DELETE FROM audit_events WHERE id IN ({_placeholders(delete_event_ids)})",
                tuple(delete_event_ids),
            )

        deleted_operation_events = 0
        if chapter_ids is None:
            cursor = connection.execute(
                "DELETE FROM audit_events WHERE event_code='audio_library_outputs_removed'"
            )
            deleted_operation_events = int(cursor.rowcount)

        if delete_ids:
            connection.execute(
                f"UPDATE job_chapters SET artifact_id=NULL WHERE artifact_id IN ({_placeholders(delete_ids)})",
                tuple(delete_ids),
            )
            connection.execute(
                f"DELETE FROM artifact_dependencies WHERE parent_artifact_id IN ({_placeholders(delete_ids)}) OR child_artifact_id IN ({_placeholders(delete_ids)})",
                (*delete_ids, *delete_ids),
            )
            connection.execute(
                f"DELETE FROM artifacts WHERE id IN ({_placeholders(delete_ids)})",
                tuple(delete_ids),
            )

    cleanup = _delete_exact_files(
        file_paths,
        allowed_roots=(output_root, work_root),
    )
    return {
        "deleted_artifacts": len(delete_ids),
        "deleted_artifact_ids": delete_ids,
        "deleted_files": cleanup["deleted_files"],
        "bytes_freed": cleanup["bytes_freed"],
        "cleared_approvals": cleared_approvals,
        "cleared_segment_files": len(segment_rows),
        "deleted_qa_events": len(delete_event_ids),
        "deleted_operation_events": deleted_operation_events,
        "file_cleanup_failures": cleanup["file_cleanup_failures"],
    }
