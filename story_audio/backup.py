from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .config import Settings
from .db import Database
from .files import atomic_write_json, sha256_file
from .migrations import LATEST_SCHEMA_VERSION
from .batch_prepare_schema import PREPARE_SCHEMA_VERSION, prepare_migration_runner


MANIFEST_SCHEMA_VERSION = 1
ACTIVE_JOB_STATUSES = ("running", "repairing", "synthesizing", "assembling")


class BackupError(RuntimeError):
    pass


class BackupVerificationError(BackupError):
    pass


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_child(root: Path, relative: str) -> Path:
    candidate = (root / Path(relative)).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise BackupVerificationError(f"Manifest path escapes backup root: {relative}")
    return candidate


def _sqlite_quick_check(path: Path) -> str:
    connection = sqlite3.connect(path)
    try:
        row = connection.execute("PRAGMA quick_check").fetchone()
        return str(row[0]) if row else "no result"
    finally:
        connection.close()


def _sqlite_schema_version(path: Path) -> int:
    connection = sqlite3.connect(path)
    try:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if not table:
            return 0
        row = connection.execute(
            "SELECT COALESCE(MAX(version),0) FROM schema_migrations"
        ).fetchone()
        return int(row[0])
    finally:
        connection.close()


def _backup_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(source)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
        destination_connection.commit()
    finally:
        destination_connection.close()
        source_connection.close()
    if _sqlite_quick_check(destination) != "ok":
        raise BackupError("SQLite snapshot failed PRAGMA quick_check.")


def _iter_files(path: Path) -> Iterable[Path]:
    if not path.exists():
        return []
    return (
        item
        for item in sorted(path.rglob("*"))
        if item.is_file() and ".partial" not in item.name
    )


def create_backup(
    config: Settings,
    destination: Path,
    *,
    include_work: bool = True,
    allow_active: bool = False,
) -> dict[str, Any]:
    destination = destination.resolve()
    if destination.exists():
        raise BackupError(f"Backup destination already exists: {destination}")
    if not config.db_path.exists():
        raise BackupError(f"Database does not exist: {config.db_path}")

    database = Database(config.db_path, migration_runner=prepare_migration_runner())
    schema_version = database.schema_version()
    supported = schema_version <= LATEST_SCHEMA_VERSION or schema_version == PREPARE_SCHEMA_VERSION
    if schema_version < 1 or not supported:
        raise BackupError(
            f"Database schema {schema_version} is not supported by this backup version "
            f"(supported: 1-{LATEST_SCHEMA_VERSION} or {PREPARE_SCHEMA_VERSION})."
        )
    placeholders = ",".join("?" for _ in ACTIVE_JOB_STATUSES)
    active_count = int(
        database.fetch_one(
            f"SELECT COUNT(*) AS count FROM jobs WHERE status IN ({placeholders})",
            ACTIVE_JOB_STATUSES,
        )["count"]
    )
    if active_count and not allow_active:
        raise BackupError(
            f"Refusing backup while {active_count} job(s) are active. Pause them or use --allow-active."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f".{destination.name}.staging-{uuid.uuid4().hex}"
    files_root = staging / "files"
    try:
        files_root.mkdir(parents=True)
        _backup_sqlite(config.db_path, files_root / "app.db")
        roots = [config.blobs_dir, config.output_dir, config.youtube_export_dir]
        if include_work:
            roots.append(config.work_dir)
        for source_root in roots:
            if not source_root.exists():
                continue
            relative_root = source_root.resolve().relative_to(config.data_dir.resolve())
            for source in _iter_files(source_root):
                relative = relative_root / source.relative_to(source_root)
                target = files_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

        file_entries: list[dict[str, Any]] = []
        total_size = 0
        for path in sorted(item for item in files_root.rglob("*") if item.is_file()):
            size = path.stat().st_size
            total_size += size
            file_entries.append(
                {
                    "path": path.relative_to(staging).as_posix(),
                    "size": size,
                    "sha256": sha256_file(path),
                }
            )
        manifest = {
            "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
            "created_at": _utcnow(),
            "app_version": __version__,
            "schema_version": schema_version,
            "source_data_dir": str(config.data_dir.resolve()),
            "includes": {
                "database": True,
                "blobs": True,
                "output": True,
                "youtube_exports": True,
                "work": include_work,
            },
            "file_count": len(file_entries),
            "total_size": total_size,
            "files": file_entries,
        }
        atomic_write_json(staging / "manifest.json", manifest)
        verify_backup(staging)
        staging.rename(destination)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_backup(backup_dir: Path) -> dict[str, Any]:
    backup_dir = backup_dir.resolve()
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        raise BackupVerificationError("Backup is missing manifest.json.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupVerificationError(f"Invalid manifest.json: {exc}") from exc
    if manifest.get("manifest_schema_version") != MANIFEST_SCHEMA_VERSION:
        raise BackupVerificationError("Unsupported backup manifest schema version.")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise BackupVerificationError("Manifest has no files.")
    if int(manifest.get("file_count", -1)) != len(files):
        raise BackupVerificationError("Manifest file_count mismatch.")

    total_size = 0
    listed: set[str] = set()
    for entry in files:
        relative = str(entry.get("path") or "")
        if not relative or relative in listed:
            raise BackupVerificationError(f"Invalid/duplicate manifest path: {relative}")
        listed.add(relative)
        path = _safe_child(backup_dir, relative)
        if not path.is_file():
            raise BackupVerificationError(f"Backup file is missing: {relative}")
        size = path.stat().st_size
        if size != int(entry.get("size", -1)):
            raise BackupVerificationError(f"Size mismatch: {relative}")
        if sha256_file(path) != entry.get("sha256"):
            raise BackupVerificationError(f"SHA-256 mismatch: {relative}")
        total_size += size
    if total_size != int(manifest.get("total_size", -1)):
        raise BackupVerificationError("Manifest total_size mismatch.")

    database_path = backup_dir / "files" / "app.db"
    if not database_path.exists():
        raise BackupVerificationError("Backup is missing files/app.db.")
    if _sqlite_quick_check(database_path) != "ok":
        raise BackupVerificationError("Backup database failed PRAGMA quick_check.")
    database_version = _sqlite_schema_version(database_path)
    if database_version != int(manifest.get("schema_version", -1)):
        raise BackupVerificationError(
            f"Database schema version {database_version} does not match manifest."
        )
    return manifest


def _remap_path(value: str | None, source_root: Path, destination_root: Path) -> str | None:
    if not value:
        return value
    path = Path(value)
    if not path.is_absolute():
        return value
    try:
        relative = path.resolve().relative_to(source_root.resolve())
    except ValueError:
        return value
    return str((destination_root / relative).resolve())


def _rewrite_restored_paths(
    database_path: Path, source_data_dir: Path, destination_data_dir: Path
) -> int:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    changed = 0
    try:
        connection.execute("BEGIN IMMEDIATE")
        for table, column in (("artifacts", "path"), ("segments", "wav_path")):
            rows = connection.execute(
                f"SELECT id,{column} FROM {table} WHERE {column} IS NOT NULL"
            ).fetchall()
            for row in rows:
                mapped = _remap_path(
                    row[column], source_data_dir, destination_data_dir
                )
                if mapped != row[column]:
                    connection.execute(
                        f"UPDATE {table} SET {column}=? WHERE id=?",
                        (mapped, row["id"]),
                    )
                    changed += 1
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return changed


def restore_backup(
    backup_dir: Path,
    destination_data_dir: Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    manifest = verify_backup(backup_dir)
    backup_dir = backup_dir.resolve()
    destination_data_dir = destination_data_dir.resolve()
    if destination_data_dir.exists() and not overwrite:
        raise BackupError(
            f"Restore destination already exists: {destination_data_dir}. Use --overwrite explicitly."
        )
    destination_data_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = destination_data_dir.parent / (
        f".{destination_data_dir.name}.restore-{uuid.uuid4().hex}"
    )
    previous: Path | None = None
    try:
        shutil.copytree(backup_dir / "files", staging)
        database_path = staging / "app.db"
        rewritten = _rewrite_restored_paths(
            database_path,
            Path(manifest["source_data_dir"]),
            destination_data_dir,
        )
        if _sqlite_quick_check(database_path) != "ok":
            raise BackupError("Restored database failed PRAGMA quick_check.")
        restored_schema = _sqlite_schema_version(database_path)
        if restored_schema > LATEST_SCHEMA_VERSION and restored_schema != PREPARE_SCHEMA_VERSION:
            raise BackupError("Restored database is newer than this application.")

        if destination_data_dir.exists():
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            previous = destination_data_dir.parent / (
                f"{destination_data_dir.name}.pre-restore-{timestamp}-{uuid.uuid4().hex[:8]}"
            )
            destination_data_dir.rename(previous)
        try:
            staging.rename(destination_data_dir)
        except Exception:
            if previous and previous.exists() and not destination_data_dir.exists():
                previous.rename(destination_data_dir)
            raise
        restore_record = {
            "restored_at": _utcnow(),
            "source_backup": str(backup_dir),
            "source_created_at": manifest["created_at"],
            "schema_version": manifest["schema_version"],
            "rewritten_paths": rewritten,
            "previous_data_dir": str(previous) if previous else None,
        }
        atomic_write_json(destination_data_dir / "restore_manifest.json", restore_record)
        return restore_record
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
