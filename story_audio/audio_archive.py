from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .db import Database


class AudioArchiveError(RuntimeError):
    def __init__(self, code: str, message: str, *, issues: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.code = code
        self.issues = issues or []


@dataclass(frozen=True)
class ArchiveEntry:
    chapter_id: int
    chapter_number: int
    artifact_id: int
    source_path: Path
    archive_name: str
    size_bytes: int
    sha256: str

    def public_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("source_path")
        return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _safe_download_stem(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-")
    return normalized[:80] or "story-audio"


def build_archive_plan(
    db: Database,
    *,
    output_root: Path,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
) -> dict[str, Any]:
    if from_chapter < 0 or to_chapter < 0:
        raise AudioArchiveError("INVALID_RANGE", "Chapter numbers must be non-negative.")
    if from_chapter > to_chapter:
        raise AudioArchiveError("INVALID_RANGE", "The first chapter must not exceed the last chapter.")

    book = db.fetch_one("SELECT id,title FROM books WHERE id=?", (book_id,))
    if not book:
        raise AudioArchiveError("BOOK_NOT_FOUND", "The selected book no longer exists.")

    rows = db.fetch_all(
        """
        SELECT c.id AS chapter_id,
               c.chapter_number,
               c.title AS chapter_title,
               c.active_audio_artifact_id,
               a.id AS artifact_id,
               a.path,
               a.sha256,
               a.size_bytes,
               a.deleted_at,
               jc.job_id,
               jc.status AS job_chapter_status
        FROM chapters c
        LEFT JOIN artifacts a ON a.id=c.active_audio_artifact_id
        LEFT JOIN job_chapters jc ON jc.id=a.job_chapter_id
        WHERE c.book_id=? AND c.chapter_number BETWEEN ? AND ?
        ORDER BY c.chapter_number,c.id
        """,
        (book_id, from_chapter, to_chapter),
    )
    by_number: dict[int, list[Any]] = {}
    for row in rows:
        by_number.setdefault(int(row["chapter_number"]), []).append(row)

    issues: list[dict[str, Any]] = []
    entries: list[ArchiveEntry] = []
    seen_artifacts: set[int] = set()
    seen_paths: set[Path] = set()
    output_root = output_root.resolve(strict=False)

    for chapter_number in range(from_chapter, to_chapter + 1):
        matches = by_number.get(chapter_number, [])
        if not matches:
            issues.append(
                {
                    "chapter_number": chapter_number,
                    "code": "CHAPTER_MISSING",
                    "message": "Chapter is missing from the selected book.",
                }
            )
            continue
        if len(matches) != 1:
            issues.append(
                {
                    "chapter_number": chapter_number,
                    "code": "CHAPTER_NUMBER_DUPLICATE",
                    "message": "Chapter number is not unique in the selected book.",
                }
            )
            continue
        row = matches[0]
        artifact_id = row["artifact_id"]
        if not artifact_id or row["deleted_at"] is not None:
            issues.append(
                {
                    "chapter_number": chapter_number,
                    "chapter_id": int(row["chapter_id"]),
                    "code": "ACTIVE_ARTIFACT_MISSING",
                    "message": "No valid active audio artifact is available.",
                }
            )
            continue
        if not row["job_id"] or row["job_chapter_status"] != "completed":
            issues.append(
                {
                    "chapter_number": chapter_number,
                    "chapter_id": int(row["chapter_id"]),
                    "artifact_id": int(artifact_id),
                    "code": "ACTIVE_BINDING_INVALID",
                    "message": "The active artifact is not bound to a completed JobChapter.",
                }
            )
            continue

        source = Path(str(row["path"])).resolve(strict=False)
        if not _is_within(source, output_root):
            issues.append(
                {
                    "chapter_number": chapter_number,
                    "chapter_id": int(row["chapter_id"]),
                    "artifact_id": int(artifact_id),
                    "code": "OUTPUT_PATH_UNSAFE",
                    "message": "The active artifact is outside managed output storage.",
                }
            )
            continue
        if not source.is_file():
            issues.append(
                {
                    "chapter_number": chapter_number,
                    "chapter_id": int(row["chapter_id"]),
                    "artifact_id": int(artifact_id),
                    "code": "OUTPUT_MISSING",
                    "message": "The active audio file is missing.",
                }
            )
            continue
        actual_size = source.stat().st_size
        actual_hash = _sha256(source)
        if row["size_bytes"] is not None and actual_size != int(row["size_bytes"]):
            issues.append(
                {
                    "chapter_number": chapter_number,
                    "chapter_id": int(row["chapter_id"]),
                    "artifact_id": int(artifact_id),
                    "code": "OUTPUT_SIZE_MISMATCH",
                    "message": "The active audio size no longer matches canonical metadata.",
                }
            )
            continue
        if not row["sha256"] or actual_hash != str(row["sha256"]):
            issues.append(
                {
                    "chapter_number": chapter_number,
                    "chapter_id": int(row["chapter_id"]),
                    "artifact_id": int(artifact_id),
                    "code": "OUTPUT_HASH_MISMATCH",
                    "message": "The active audio hash no longer matches canonical metadata.",
                }
            )
            continue
        if int(artifact_id) in seen_artifacts or source in seen_paths:
            issues.append(
                {
                    "chapter_number": chapter_number,
                    "chapter_id": int(row["chapter_id"]),
                    "artifact_id": int(artifact_id),
                    "code": "DUPLICATE_OUTPUT",
                    "message": "The selected range resolves to a duplicate active output.",
                }
            )
            continue
        seen_artifacts.add(int(artifact_id))
        seen_paths.add(source)
        extension = source.suffix.lower() if source.suffix else ".m4a"
        entries.append(
            ArchiveEntry(
                chapter_id=int(row["chapter_id"]),
                chapter_number=chapter_number,
                artifact_id=int(artifact_id),
                source_path=source,
                archive_name=f"chapter_{chapter_number:04d}{extension}",
                size_bytes=actual_size,
                sha256=actual_hash,
            )
        )

    expected_count = to_chapter - from_chapter + 1
    return {
        "ready": not issues and len(entries) == expected_count,
        "book_id": int(book["id"]),
        "book_title": str(book["title"]),
        "from_chapter": from_chapter,
        "to_chapter": to_chapter,
        "expected_chapter_count": expected_count,
        "chapter_count": len(entries),
        "estimated_size_bytes": sum(entry.size_bytes for entry in entries),
        "archive_name": (
            f"{_safe_download_stem(str(book['title']))}-chapters-"
            f"{from_chapter:04d}-{to_chapter:04d}.zip"
        ),
        "entries": entries,
        "items": [entry.public_dict() for entry in entries],
        "issues": issues,
    }


def create_archive(plan: dict[str, Any], destination: Path) -> dict[str, Any]:
    if not plan.get("ready"):
        raise AudioArchiveError(
            "ARCHIVE_RANGE_INCOMPLETE",
            "The selected range is incomplete and cannot be downloaded.",
            issues=list(plan.get("issues") or []),
        )
    destination = destination.resolve(strict=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise AudioArchiveError("ARCHIVE_PATH_CONFLICT", "The temporary archive path already exists.")

    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        for entry in plan["entries"]:
            info = zipfile.ZipInfo(entry.archive_name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o600 << 16
            info.create_system = 3
            archive.writestr(info, entry.source_path.read_bytes())

    return {
        "path": destination,
        "size_bytes": destination.stat().st_size,
        "sha256": _sha256(destination),
        "chapter_count": int(plan["chapter_count"]),
        "archive_name": str(plan["archive_name"]),
    }
