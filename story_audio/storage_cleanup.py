from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import sqlite3
import stat
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

CONFIRMATION = "DELETE_PROVEN_ORPHANED_STORAGE"
TERMINAL_JOB_STATUSES = {
    "cancelled",
    "completed",
    "completed_with_errors",
    "failed",
}
PROTECTED_JOB_IDS = {23, 24, 25, 26}
PROTECTED_ROOT_NAMES = {".git", "experiment_b_transcript", "runs", "secrets"}
EXPERIMENT_ROOT_NAMES = {
    "experiment_a_gain",
    "experiment_c_temperature",
    "experiment_d_longform",
    "experiment_e_prosody",
    "experiment_f_repeatability",
}
DELETE_CATEGORIES = {
    "DUPLICATE_EXPORT",
    "ORPHANED_SMOKE_TEST",
    "ORPHANED_TEMP_PARTIAL",
    "REBUILDABLE_CACHE",
    "REDUNDANT_CLONE_REHEARSAL",
}


class StorageCleanupError(RuntimeError):
    pass


@dataclass(frozen=True)
class InventoryItem:
    path: str
    bytes: int
    category: str
    reason: str


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_within(path: Path, root: Path) -> bool:
    resolved = path.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    return resolved == resolved_root or resolved_root in resolved.parents


def _relative(path: Path, root: Path) -> str:
    return path.resolve(strict=False).relative_to(root.resolve(strict=False)).as_posix()


def _tree_files(path: Path) -> list[Path]:
    if path.is_file():
        return [] if _is_reparse(path) else [path]
    return [
        item
        for item in _walk_entries(path)
        if not _is_reparse(item) and item.is_file()
    ]


def _walk_entries(path: Path) -> Iterable[Path]:
    stack = [path]
    while stack:
        current = stack.pop()
        if current != path:
            yield current
        if _is_reparse(current) or not current.is_dir():
            continue
        with os.scandir(current) as entries:
            children = [Path(entry.path) for entry in entries]
        stack.extend(reversed(children))


def _is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _tree_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in _tree_files(path))


def _has_reparse_point(path: Path) -> bool:
    for item in (path, *_walk_entries(path)):
        if _is_reparse(item):
            return True
    return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sqlite_uri(path: Path) -> str:
    return f"file:{path.resolve().as_posix()}?mode=ro&immutable=1"


def _sqlite_evidence(path: Path) -> tuple[int, str]:
    connection = sqlite3.connect(_sqlite_uri(path), uri=True)
    try:
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        has_migrations = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if not has_migrations:
            return 0, quick_check
        row = connection.execute(
            "SELECT COALESCE(MAX(version),0) FROM schema_migrations"
        ).fetchone()
        return int(row[0]), quick_check
    finally:
        connection.close()


def _tracked_paths(root: Path) -> set[Path]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        check=True,
    )
    return {
        (root / value.decode("utf-8")).resolve(strict=False)
        for value in result.stdout.split(b"\0")
        if value
    }


def _contains_tracked(path: Path, tracked: set[Path]) -> bool:
    resolved = path.resolve(strict=False)
    return any(item == resolved or resolved in item.parents for item in tracked)


def _contains_reference(path: Path, references: set[Path]) -> bool:
    resolved = path.resolve(strict=False)
    return any(item == resolved or resolved in item.parents for item in references)


def _runtime_listening(host: str = "127.0.0.1", port: int = 8772) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def _load_canonical_state(root: Path) -> dict[str, Any]:
    db_path = (root / "data" / "app.db").resolve()
    connection = sqlite3.connect(_sqlite_uri(db_path), uri=True)
    connection.row_factory = sqlite3.Row
    try:
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        schema = int(
            connection.execute(
                "SELECT COALESCE(MAX(version),0) FROM schema_migrations"
            ).fetchone()[0]
        )
        jobs = {
            int(row["id"]): str(row["status"])
            for row in connection.execute("SELECT id,status FROM jobs")
        }
        nonterminal = sorted(
            job_id
            for job_id, status in jobs.items()
            if status not in TERMINAL_JOB_STATUSES
        )
        artifact_rows = list(
            connection.execute(
                "SELECT id,path,sha256,status FROM artifacts WHERE path IS NOT NULL"
            )
        )
        artifact_paths = {Path(row["path"]).resolve(strict=False) for row in artifact_rows}
        artifact_hashes = {str(row["sha256"]) for row in artifact_rows if row["sha256"]}
        active_ids = {
            int(row[0])
            for row in connection.execute(
                "SELECT active_audio_artifact_id FROM chapters "
                "WHERE active_audio_artifact_id IS NOT NULL"
            )
        }
        references = set(artifact_paths)
        for table, column in (
            ("segments", "wav_path"),
            ("segment_attempts", "wav_path"),
            ("audio_repair_blocks", "candidate_wav_path"),
        ):
            references.update(
                Path(row[0]).resolve(strict=False)
                for row in connection.execute(
                    f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL"
                )
            )
    finally:
        connection.close()

    escaped = sorted(str(path) for path in references if not _is_within(path, root))
    missing_artifacts = sorted(
        _relative(path, root)
        for path in artifact_paths
        if _is_within(path, root) and not path.is_file()
    )
    return {
        "db_path": db_path,
        "schema": schema,
        "quick_check": quick_check,
        "foreign_key_violations": foreign_keys,
        "jobs": jobs,
        "nonterminal_job_ids": nonterminal,
        "artifact_paths": artifact_paths,
        "artifact_hashes": artifact_hashes,
        "active_artifact_ids": active_ids,
        "references": references,
        "escaped_references": escaped,
        "missing_artifacts": missing_artifacts,
    }


def _inspect_backup(path: Path, *, verify_hashes: bool = False) -> dict[str, Any]:
    if path.is_dir() and (path / "manifest.json").is_file():
        try:
            manifest = json.loads(
                (path / "manifest.json").read_text(encoding="utf-8")
            )
            files = manifest.get("files")
            if (
                manifest.get("manifest_schema_version") != 1
                or not isinstance(files, list)
                or not files
                or int(manifest.get("file_count", -1)) != len(files)
                or int(manifest.get("total_size", -1))
                != sum(int(item.get("size", -1)) for item in files)
            ):
                raise StorageCleanupError("invalid backup manifest structure")
            listed_targets: set[Path] = set()
            for entry in files:
                relative = str(entry.get("path") or "")
                target = (path / relative).resolve(strict=False)
                if (
                    not relative
                    or not _is_within(target, path)
                    or not target.is_file()
                    or target.stat().st_size != int(entry.get("size", -1))
                ):
                    raise StorageCleanupError(
                        f"invalid backup manifest entry: {relative}"
                    )
                listed_targets.add(target)
                if verify_hashes and _sha256(target) != entry.get("sha256"):
                    raise StorageCleanupError(
                        f"backup hash mismatch: {relative}"
                    )
            extras = [
                item
                for item in _tree_files(path)
                if item not in listed_targets and item.name != "manifest.json"
            ]
            if extras:
                raise StorageCleanupError(
                    "backup contains files not declared by manifest"
                )
            database = path / "files" / "app.db"
            schema, quick_check = _sqlite_evidence(database)
            database_entry = next(
                (
                    entry
                    for entry in files
                    if str(entry.get("path")) == "files/app.db"
                ),
                None,
            )
            if (
                quick_check != "ok"
                or schema != int(manifest.get("schema_version", -1))
                or database_entry is None
                or _sha256(database) != database_entry.get("sha256")
            ):
                raise StorageCleanupError(
                    "backup database integrity does not match manifest"
                )
        except (
            json.JSONDecodeError,
            OSError,
            StorageCleanupError,
        ) as exc:
            return {"valid": False, "reason": f"backup verification failed: {exc}"}
        return {
            "valid": True,
            "kind": "full_backup",
            "schema": int(manifest["schema_version"]),
            "created_at": str(manifest["created_at"]),
        }

    database: Path | None = None
    if path.is_file():
        try:
            with path.open("rb") as handle:
                if handle.read(16) == b"SQLite format 3\0":
                    database = path
        except OSError:
            database = None
    elif path.is_dir():
        databases = [
            item
            for item in _tree_files(path)
            if item.is_file()
            and (
                item.name == "app.db"
                or item.suffix.lower() in {".bak", ".db", ".sqlite3"}
            )
        ]
        if len(databases) == 1:
            database = databases[0]
    if database is None:
        return {"valid": False, "reason": "not a verified backup or isolated clone"}
    try:
        schema, quick_check = _sqlite_evidence(database)
    except (OSError, sqlite3.Error) as exc:
        return {"valid": False, "reason": f"SQLite verification failed: {exc}"}
    if quick_check != "ok":
        return {"valid": False, "reason": f"SQLite quick_check={quick_check}"}
    return {
        "valid": True,
        "kind": "sqlite_clone",
        "schema": schema,
        "created_at": datetime.fromtimestamp(
            path.stat().st_mtime, timezone.utc
        ).isoformat(),
    }


def _largest_paths(root: Path, limit: int = 25) -> list[dict[str, Any]]:
    files = _tree_files(root)
    directory_sizes: dict[Path, int] = {}
    for file_path in files:
        file_size = file_path.stat().st_size
        parent = file_path.parent
        while True:
            directory_sizes[parent] = directory_sizes.get(parent, 0) + file_size
            if parent == root:
                break
            parent = parent.parent
    combined = [
        {"path": _relative(path, root), "bytes": size, "kind": "directory"}
        for path, size in directory_sizes.items()
        if path != root
    ]
    combined.extend(
        {
            "path": _relative(path, root),
            "bytes": path.stat().st_size,
            "kind": "file",
        }
        for path in files
    )
    return sorted(combined, key=lambda item: item["bytes"], reverse=True)[:limit]


def _candidate(
    path: Path,
    root: Path,
    category: str,
    reason: str,
    tracked: set[Path],
    references: set[Path],
) -> InventoryItem | None:
    if not path.exists() or category not in DELETE_CATEGORIES:
        return None
    if not _is_within(path, root):
        return None
    if any(_is_within(path, root / name) for name in PROTECTED_ROOT_NAMES):
        return None
    if _contains_tracked(path, tracked) or _contains_reference(path, references):
        return None
    if _has_reparse_point(path):
        return None
    return InventoryItem(_relative(path, root), _tree_size(path), category, reason)


def _is_known_data_clone(path: Path) -> bool:
    name = path.name
    return (
        (name.startswith("app-before-") and name.endswith(".db"))
        or (
            name.startswith("app.db.pre-migration-")
            and name.endswith(".bak")
        )
        or (
            name.startswith("app.db.backup_phase")
            and name.endswith("_temp")
        )
    )


def _deduplicate_candidates(items: Iterable[InventoryItem]) -> list[InventoryItem]:
    ordered = sorted(items, key=lambda item: (item.path.count("/"), item.path))
    kept: list[InventoryItem] = []
    for item in ordered:
        if any(item.path == parent.path or item.path.startswith(parent.path + "/") for parent in kept):
            continue
        kept.append(item)
    return kept


def build_report(root: Path, *, include_largest: bool = True) -> dict[str, Any]:
    root = root.resolve(strict=True)
    state = _load_canonical_state(root)
    tracked = _tracked_paths(root)
    references: set[Path] = state["references"]
    candidates: list[InventoryItem] = []
    retained: list[InventoryItem] = []
    backup_evidence: dict[Path, dict[str, Any]] = {}

    backup_root = root / "backups"
    if backup_root.is_dir():
        for item in backup_root.iterdir():
            if item.name.endswith(("-wal", "-shm")):
                continue
            if _is_reparse(item):
                retained.append(
                    InventoryItem(
                        _relative(item, root),
                        0,
                        "UNKNOWN_KEEP",
                        "backup entry is a reparse point",
                    )
                )
                continue
            backup_evidence[item] = _inspect_backup(item)
        full_backups = [
            (path, evidence)
            for path, evidence in backup_evidence.items()
            if evidence.get("valid") and evidence.get("kind") == "full_backup"
        ]
        pre_backups = [
            pair for pair in full_backups if int(pair[1]["schema"]) < state["schema"]
        ]
        current_backups = [
            pair for pair in full_backups if int(pair[1]["schema"]) == state["schema"]
        ]
        keep_backups: set[Path] = set()
        for pool in (pre_backups, current_backups):
            for path, _evidence in sorted(
                pool, key=lambda pair: pair[0].stat().st_mtime, reverse=True
            ):
                verified = _inspect_backup(path, verify_hashes=True)
                if verified.get("valid"):
                    backup_evidence[path] = verified
                    keep_backups.add(path)
                    break
                backup_evidence[path] = verified

        for item, evidence in backup_evidence.items():
            if not evidence.get("valid"):
                retained.append(
                    InventoryItem(
                        _relative(item, root),
                        _tree_size(item),
                        "UNKNOWN_KEEP",
                        str(evidence["reason"]),
                    )
                )
                continue
            if item in keep_backups:
                retained.append(
                    InventoryItem(
                        _relative(item, root),
                        _tree_size(item),
                        "VERIFIED_BACKUP_KEEP",
                        f"retained schema-{evidence['schema']} {evidence['kind']}",
                    )
                )
                continue
            category = "REDUNDANT_CLONE_REHEARSAL"
            reason = (
                f"verified schema-{evidence['schema']} {evidence['kind']} superseded "
                "by retained rollback backups"
            )
            candidate = _candidate(
                item, root, category, reason, tracked, references
            )
            if candidate:
                candidates.append(candidate)

        for sidecar in backup_root.iterdir():
            if not sidecar.name.endswith(("-wal", "-shm")):
                continue
            base = Path(str(sidecar).removesuffix("-wal").removesuffix("-shm"))
            if base in backup_evidence and base not in keep_backups:
                candidate = _candidate(
                    sidecar,
                    root,
                    "REDUNDANT_CLONE_REHEARSAL",
                    "sidecar of a redundant verified SQLite snapshot",
                    tracked,
                    references,
                )
                if candidate:
                    candidates.append(candidate)

    data_root = root / "data"
    for clone in data_root.glob("app*"):
        if clone.name in {"app.db", "app.db-wal", "app.db-shm"}:
            continue
        if not clone.is_file() or clone.suffix.lower() not in {".bak", ".db", ".sqlite3", ".backup_phase1_temp"}:
            continue
        if not _is_known_data_clone(clone):
            retained.append(
                InventoryItem(
                    _relative(clone, root),
                    _tree_size(clone),
                    "UNKNOWN_KEEP",
                    "SQLite-like data file has no recognized rehearsal provenance",
                )
            )
            continue
        evidence = _inspect_backup(clone)
        if evidence.get("valid"):
            candidate = _candidate(
                clone,
                root,
                "REDUNDANT_CLONE_REHEARSAL",
                f"verified isolated schema-{evidence['schema']} database clone",
                tracked,
                references,
            )
            if candidate:
                candidates.append(candidate)
        else:
            retained.append(
                InventoryItem(
                    _relative(clone, root),
                    _tree_size(clone),
                    "UNKNOWN_KEEP",
                    str(evidence["reason"]),
                )
            )

    work_root = data_root / "work"
    if work_root.is_dir():
        for item in work_root.iterdir():
            if _is_reparse(item) or not item.is_dir():
                continue
            if item.name == "smoke":
                candidate = _candidate(
                    item,
                    root,
                    "ORPHANED_SMOKE_TEST",
                    "unreferenced smoke work tree",
                    tracked,
                    references,
                )
                if candidate:
                    candidates.append(candidate)
                continue
            if not item.name.startswith("job_"):
                retained.append(
                    InventoryItem(
                        _relative(item, root),
                        _tree_size(item),
                        "UNKNOWN_KEEP",
                        "work directory has no canonical job identity",
                    )
                )
                continue
            try:
                job_id = int(item.name[4:])
            except ValueError:
                job_id = -1
            status = state["jobs"].get(job_id)
            if (
                job_id in PROTECTED_JOB_IDS
                or status not in TERMINAL_JOB_STATUSES
                or _contains_reference(item, references)
            ):
                retained.append(
                    InventoryItem(
                        _relative(item, root),
                        _tree_size(item),
                        "HISTORICAL_KEEP",
                        f"protected/referenced canonical Job {job_id}",
                    )
                )
                continue
            candidate = _candidate(
                item,
                root,
                "ORPHANED_TEMP_PARTIAL",
                f"terminal Job {job_id} has no persisted file reference",
                tracked,
                references,
            )
            if candidate:
                candidates.append(candidate)

    for name in EXPERIMENT_ROOT_NAMES:
        item = root / name
        if not item.is_dir():
            continue
        files = _tree_files(item)
        if files and all(file.suffix.lower() == ".wav" for file in files):
            candidate = _candidate(
                item,
                root,
                "ORPHANED_SMOKE_TEST",
                "untracked WAV-only experiment output with no canonical reference",
                tracked,
                references,
            )
            if candidate:
                candidates.append(candidate)

    for item in _walk_entries(root):
        if _is_reparse(item) or not item.is_dir() or item.name not in {
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
        }:
            continue
        candidate = _candidate(
            item,
            root,
            "REBUILDABLE_CACHE",
            "generated local tool cache",
            tracked,
            references,
        )
        if candidate:
            candidates.append(candidate)

    export_root = data_root / "exports" / "youtube_auto"
    if export_root.is_dir():
        for package in export_root.iterdir():
            if _is_reparse(package) or not package.is_dir():
                continue
            audio_files = [
                item
                for item in _tree_files(package)
                if item.suffix.lower() in {".m4a", ".mp3", ".wav"}
            ]
            if audio_files and all(
                _sha256(item) in state["artifact_hashes"] for item in audio_files
            ):
                candidate = _candidate(
                    package,
                    root,
                    "DUPLICATE_EXPORT",
                    "all exported audio hashes match preserved canonical Artifacts",
                    tracked,
                    references,
                )
                if candidate:
                    candidates.append(candidate)

    output_root = data_root / "output"
    if output_root.is_dir():
        for item in _walk_entries(output_root):
            if (
                _is_reparse(item)
                or not item.is_dir()
                or any(child.is_dir() for child in item.iterdir())
            ):
                continue
            files = _tree_files(item)
            if (
                files
                and not _contains_reference(item, references)
                and all(
                    file.suffix.lower()
                    in {".json", ".m4a", ".mp3", ".partial", ".tmp", ".txt", ".wav"}
                    for file in files
                )
            ):
                candidate = _candidate(
                    item,
                    root,
                    "ORPHANED_TEMP_PARTIAL",
                    "output leaf has no canonical Artifact or intermediate reference",
                    tracked,
                    references,
                )
                if candidate:
                    candidates.append(candidate)

    logs_root = root / "logs"
    if logs_root.is_dir() and all(
        item.suffix.lower() == ".log" for item in _tree_files(logs_root)
    ):
        candidate = _candidate(
            logs_root,
            root,
            "ORPHANED_TEMP_PARTIAL",
            "stopped-runtime disposable logs",
            tracked,
            references,
        )
        if candidate:
            candidates.append(candidate)
    for parent in (root, data_root):
        for log_path in parent.glob("*.log"):
            candidate = _candidate(
                log_path,
                root,
                "ORPHANED_TEMP_PARTIAL",
                "stopped-runtime disposable log",
                tracked,
                references,
            )
            if candidate:
                candidates.append(candidate)

    smoke_reports = data_root / "smoke_reports"
    if smoke_reports.is_dir():
        candidate = _candidate(
            smoke_reports,
            root,
            "ORPHANED_SMOKE_TEST",
            "unreferenced historical smoke report output",
            tracked,
            references,
        )
        if candidate:
            candidates.append(candidate)

    nonzero_wal_paths: list[str] = []
    for sidecar in _tree_files(root):
        if not sidecar.name.endswith(("-wal", "-shm")):
            continue
        base = Path(str(sidecar).removesuffix("-wal").removesuffix("-shm"))
        if not base.is_file():
            continue
        try:
            with base.open("rb") as handle:
                is_sqlite = handle.read(16) == b"SQLite format 3\0"
        except OSError:
            is_sqlite = False
        if not is_sqlite:
            continue
        wal = Path(str(base) + "-wal")
        if wal.is_file() and wal.stat().st_size > 0:
            nonzero_wal_paths.append(_relative(wal, root))
            continue
        candidate = _candidate(
            sidecar,
            root,
            "ORPHANED_TEMP_PARTIAL",
            "runtime is stopped and SQLite WAL is absent or zero-byte",
            tracked,
            references,
        )
        if candidate:
            candidates.append(candidate)

    candidates = _deduplicate_candidates(candidates)
    candidate_bytes = sum(item.bytes for item in candidates)
    total_bytes = _tree_size(root)
    output_bytes = _tree_size(output_root) if output_root.exists() else 0
    category_bytes: dict[str, int] = {}
    for item in candidates:
        category_bytes[item.category] = category_bytes.get(item.category, 0) + item.bytes

    blockers: list[str] = []
    if state["quick_check"] != "ok":
        blockers.append(f"canonical quick_check={state['quick_check']}")
    if state["foreign_key_violations"]:
        blockers.append(
            f"canonical foreign key violations={state['foreign_key_violations']}"
        )
    if state["nonterminal_job_ids"]:
        blockers.append(f"nonterminal Jobs={state['nonterminal_job_ids']}")
    if state["escaped_references"]:
        blockers.append("canonical file references escape repository root")
    if state["missing_artifacts"]:
        blockers.append(f"missing canonical Artifacts={state['missing_artifacts']}")
    if nonzero_wal_paths:
        blockers.append(f"non-empty SQLite WAL files={sorted(set(nonzero_wal_paths))}")
    current_backups = [
        item
        for item in retained
        if item.category == "VERIFIED_BACKUP_KEEP"
        and f"schema-{state['schema']} " in item.reason
    ]
    pre_backups = [
        item
        for item in retained
        if item.category == "VERIFIED_BACKUP_KEEP"
        and f"schema-{state['schema']} " not in item.reason
    ]
    if not current_backups:
        blockers.append(f"no verified schema-{state['schema']} backup retained")
    if not pre_backups:
        blockers.append("no verified pre-current-schema backup retained")

    return {
        "schema": "story-audio-storage-cleanup/v1",
        "generated_at": _utcnow(),
        "mode": "report",
        "canonical": {
            "schema_version": state["schema"],
            "quick_check": state["quick_check"],
            "foreign_key_violations": state["foreign_key_violations"],
            "artifact_path_count": len(state["artifact_paths"]),
            "active_artifact_ids": sorted(state["active_artifact_ids"]),
            "nonterminal_job_ids": state["nonterminal_job_ids"],
            "missing_artifacts": state["missing_artifacts"],
            "escaped_reference_count": len(state["escaped_references"]),
        },
        "storage": {
            "repository_bytes": total_bytes,
            "output_bytes": output_bytes,
            "reclaimable_bytes": candidate_bytes,
            "category_bytes": dict(sorted(category_bytes.items())),
        },
        "largest_paths": _largest_paths(root) if include_largest else [],
        "candidates": [asdict(item) for item in candidates],
        "retained": [asdict(item) for item in sorted(retained, key=lambda item: item.path)],
        "blockers": blockers,
    }


def _write_report(path: Path, payload: dict[str, Any], root: Path) -> None:
    path = path.resolve(strict=False)
    tracked = _tracked_paths(root)
    if path in tracked:
        raise StorageCleanupError("Refusing to overwrite a Git-tracked report path.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def execute_cleanup(
    root: Path,
    *,
    confirmation: str,
    json_report: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve(strict=True)
    if confirmation != CONFIRMATION:
        raise StorageCleanupError(f"--confirm must equal {CONFIRMATION}")
    if _runtime_listening():
        raise StorageCleanupError("Refusing cleanup while runtime is listening on port 8772.")
    report = build_report(root, include_largest=False)
    if report["blockers"]:
        raise StorageCleanupError(
            "Refusing cleanup because safety blockers remain: "
            + "; ".join(report["blockers"])
        )
    tracked = _tracked_paths(root)
    state = _load_canonical_state(root)
    approved_roots = {
        (root / "backups").resolve(strict=False),
        (root / "data").resolve(strict=False),
        (root / "logs").resolve(strict=False),
    }
    approved_roots.update(
        (root / name).resolve(strict=False) for name in EXPERIMENT_ROOT_NAMES
    )
    candidates = [
        (root / item["path"]).resolve(strict=False) for item in report["candidates"]
    ]
    if json_report is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        json_report = root / "data" / "cleanup_reports" / f"storage-cleanup-{stamp}.json"
    report_path = json_report.resolve(strict=False)
    if any(report_path == item or item in report_path.parents for item in candidates):
        raise StorageCleanupError("Deletion manifest path is inside a cleanup candidate.")

    for candidate in candidates:
        is_generated_cache = candidate.name in {
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
        }
        is_root_log = candidate.parent == root and candidate.suffix.lower() == ".log"
        if not (
            any(_is_within(candidate, approved) for approved in approved_roots)
            or is_generated_cache
            or is_root_log
        ):
            raise StorageCleanupError(f"Candidate escaped approved roots: {_relative(candidate, root)}")
        if _contains_tracked(candidate, tracked):
            raise StorageCleanupError(f"Candidate contains tracked files: {_relative(candidate, root)}")
        if _contains_reference(candidate, state["references"]):
            raise StorageCleanupError(f"Candidate contains canonical references: {_relative(candidate, root)}")
        if _has_reparse_point(candidate):
            raise StorageCleanupError(f"Candidate contains a reparse point: {_relative(candidate, root)}")

    # The worker is an in-process API thread, so recheck its owning runtime
    # immediately before the first destructive operation.
    if _runtime_listening():
        raise StorageCleanupError(
            "Refusing cleanup because runtime started during verification."
        )

    reclaimed = 0
    deleted: list[dict[str, Any]] = []
    for item, candidate in zip(report["candidates"], candidates, strict=True):
        current_size = _tree_size(candidate)
        if current_size != int(item["bytes"]):
            raise StorageCleanupError(
                f"Candidate changed after verification: {item['path']}"
            )
        if candidate.is_dir():
            shutil.rmtree(candidate)
        else:
            candidate.unlink()
        reclaimed += current_size
        deleted.append(item)

    report["mode"] = "execute"
    report["executed_at"] = _utcnow()
    report["deleted"] = deleted
    report["reclaimed_bytes"] = reclaimed
    report["storage_after_bytes"] = _tree_size(root)
    _write_report(report_path, report, root)
    report["deletion_manifest"] = _relative(report_path, root) if _is_within(report_path, root) else report_path.name
    return report
