"""Clone-only PREPARE schema rehearsal and rollback evidence.

This module deliberately bypasses the application Database class.  The latter
opens ordinary SQLite connections and enables WAL, which is not acceptable when
the canonical source must remain strictly read-only.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config import canonical_production_db_path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXTERNAL_ROOT = Path(r"D:\Youtube_AI_HANDOFFS\Story Audio\phase12_clone_rehearsal")
REQUIRED_SOURCE_SCHEMA = 12
TARGET_SCHEMA = 15
DORMANT_TABLES = (
    "batch_prepare_requests",
    "batch_prepare_job_links",
    "batch_prepare_execution_attempts",
)
CORE_COUNT_TABLES = (
    "speaker_assignment_drafts",
    "casting_plans",
    "jobs",
    "job_chapters",
    "segments",
    "artifacts",
)
MIGRATION_FILES = {
    13: ("batch_prepare_requests", "0013_batch_prepare_requests.sql"),
    14: ("batch_prepare_job_links", "0014_batch_prepare_job_links.sql"),
    15: ("batch_prepare_execution_attempts", "0015_batch_prepare_execution_attempts.sql"),
}
EXPECTED_INDEXES = {
    13: {
        "idx_batch_prepare_requests_client",
        "idx_batch_prepare_requests_identity",
        "idx_batch_prepare_requests_state_updated",
        "idx_batch_prepare_requests_stale_applying",
        "idx_batch_prepare_requests_job",
        "idx_batch_prepare_requests_scope",
        "ux_batch_prepare_requests_id_identity",
    },
    14: {
        "ux_batch_prepare_job_links_request",
        "ux_batch_prepare_job_links_identity",
        "ux_batch_prepare_job_links_job",
        "idx_batch_prepare_job_links_committed",
    },
    15: {
        "ux_batch_prepare_execution_attempts_live_owner",
        "idx_batch_prepare_execution_attempts_request_generation",
        "idx_batch_prepare_execution_attempts_lease",
        "idx_batch_prepare_execution_attempts_link",
    },
}
REQUIRED_CHECK_FRAGMENTS = {
    "batch_prepare_requests": ("state IN", "from_chapter <= to_chapter"),
    "batch_prepare_job_links": ("prepared_status = 'prepared'", "worker_woken = 0", "render_started = 0"),
    "batch_prepare_execution_attempts": ("state IN", "lease_expires_at > lease_acquired_at"),
}


class CloneRehearsalError(RuntimeError):
    """Base error for clone-only operations."""


class ClonePathRejected(CloneRehearsalError):
    """Raised when a source or destination violates the isolation guard."""


class CloneEvidenceError(CloneRehearsalError):
    """Raised when logical or byte-level evidence does not match."""


class CloneMigrationError(CloneRehearsalError):
    """Raised when an explicit dormant migration fails."""


@dataclass(frozen=True)
class DatabaseFacts:
    path_ref: str
    file_id: str
    sha256: str
    size: int
    mtime_utc: str
    schema_version: int
    quick_check: str
    foreign_key_check: str
    wal_present: bool
    shm_present: bool
    tables: tuple[str, ...]
    dormant_row_counts: Mapping[str, int]
    counts: Mapping[str, int]
    chapter_369: Mapping[str, Any]
    plan_369: Mapping[str, Any]


@dataclass(frozen=True)
class CloneCreationEvidence:
    mechanism: str
    destination_ref: str
    source_before: DatabaseFacts
    clone: DatabaseFacts
    source_after: DatabaseFacts
    source_unchanged: bool


@dataclass(frozen=True)
class CloneBackupEvidence:
    mechanism: str
    backup_ref: str
    clone_before: DatabaseFacts
    backup: DatabaseFacts
    exact_hash_match: bool


@dataclass(frozen=True)
class MigrationStageEvidence:
    version: int
    name: str
    sha256: str
    predecessor_schema: int
    resulting_schema: int
    quick_check: str
    applied: bool
    failure_code: str | None = None


@dataclass(frozen=True)
class MigrationRunEvidence:
    applied_versions: tuple[int, ...]
    stages: tuple[MigrationStageEvidence, ...]
    final_facts: DatabaseFacts
    postflight: Mapping[str, Any]


@dataclass(frozen=True)
class RollbackEvidence:
    mechanism: str
    backup_ref: str
    failed_clone_ref: str
    failed_clone_sha256: str | None
    restored_clone_sha256: str
    backup_sha256: str
    exact_backup_hash_restored: bool
    restored_schema: int
    restored_quick_check: str
    restored_foreign_key_check: str
    sidecars_archived: tuple[str, ...]
    already_restored: bool
    logical_baseline_restored: bool


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path_ref(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()


def _file_id(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_dev}:{stat.st_ino}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _readonly_uri(path: Path) -> str:
    return path.resolve().as_uri() + "?mode=ro&immutable=1"


def _connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise CloneEvidenceError("Database file is missing.")
    connection = sqlite3.connect(_readonly_uri(path), uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _connect_writable_clone(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA synchronous=FULL")
    return connection


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def validate_canonical_source(source: Path, *, canonical_path: Path | None = None) -> Path:
    expected = (canonical_path or canonical_production_db_path()).resolve(strict=True)
    candidate = source.resolve()
    if not candidate.is_file():
        raise ClonePathRejected("Canonical source file is missing.")
    if candidate != expected:
        raise ClonePathRejected("Source is not the explicitly verified canonical database.")
    try:
        if not os.path.samefile(candidate, expected):
            raise ClonePathRejected("Source file identity does not match canonical database.")
    except OSError as exc:
        raise ClonePathRejected("Source file identity cannot be verified.") from exc
    return candidate


def validate_external_destination(
    destination: Path,
    *,
    allowed_external_root: Path = DEFAULT_EXTERNAL_ROOT,
    canonical_path: Path | None = None,
) -> Path:
    if not destination.is_absolute():
        raise ClonePathRejected("External destination must be absolute.")
    root = allowed_external_root.resolve()
    candidate = destination.resolve()
    canonical = (canonical_path or canonical_production_db_path()).resolve()
    repo = REPOSITORY_ROOT.resolve()
    forbidden_roots = (repo, repo / "data", repo / "experiment_b_transcript", repo / "runs", canonical.parent)
    if any(_is_within(candidate, forbidden) for forbidden in forbidden_roots):
        raise ClonePathRejected("Destination is inside a protected repository or canonical path.")
    if not _is_within(candidate, root) or candidate == root:
        raise ClonePathRejected("Destination is outside the approved external rehearsal root.")
    if candidate.exists():
        raise ClonePathRejected("Destination must not already exist.")
    return candidate


def _schema_version(connection: sqlite3.Connection) -> int:
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if not table:
        return 0
    return int(connection.execute("SELECT COALESCE(MAX(version),0) FROM schema_migrations").fetchone()[0])


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _chapter_facts(connection: sqlite3.Connection) -> tuple[dict[str, Any], dict[str, Any]]:
    chapter = connection.execute(
        "SELECT active_text_revision_id,audio_status,active_audio_artifact_id FROM chapters WHERE id=369"
    ).fetchone()
    plan = connection.execute(
        "SELECT id,text_revision_id,plan_revision,status,approved_at FROM casting_plans "
        "WHERE chapter_id=369 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return (
        dict(chapter) if chapter else {"missing": True},
        dict(plan) if plan else {"missing": True},
    )


def _collect_facts_open(path: Path, connection: sqlite3.Connection) -> DatabaseFacts:
    tables = _table_names(connection)
    quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
    fk_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    foreign_key_check = "ok" if not fk_rows else f"{len(fk_rows)} violation(s)"
    counts = {
        table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in CORE_COUNT_TABLES
        if table in tables
    }
    dormant_counts = {
        table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in DORMANT_TABLES
        if table in tables
    }
    chapter, plan = _chapter_facts(connection)
    return DatabaseFacts(
        path_ref=_path_ref(path),
        file_id=_file_id(path),
        sha256="",
        size=path.stat().st_size,
        mtime_utc=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        schema_version=_schema_version(connection),
        quick_check=quick,
        foreign_key_check=foreign_key_check,
        wal_present=path.with_name(path.name + "-wal").exists(),
        shm_present=path.with_name(path.name + "-shm").exists(),
        tables=tuple(sorted(tables)),
        dormant_row_counts=dormant_counts,
        counts=counts,
        chapter_369=chapter,
        plan_369=plan,
    )


def collect_database_facts(path: Path, *, read_only: bool = True) -> DatabaseFacts:
    path = path.resolve(strict=True)
    connection = _connect_readonly(path) if read_only else _connect_writable_clone(path)
    try:
        facts = _collect_facts_open(path, connection)
    finally:
        connection.close()
    return DatabaseFacts(
        **{
            **asdict(facts),
            "sha256": _sha256(path),
            "size": path.stat().st_size,
            "wal_present": path.with_name(path.name + "-wal").exists(),
            "shm_present": path.with_name(path.name + "-shm").exists(),
        }
    )


def _assert_source_unchanged(before: DatabaseFacts, after: DatabaseFacts) -> None:
    if before != after:
        raise CloneEvidenceError("Canonical source evidence changed during clone creation.")


def create_external_clone(
    source: Path,
    destination: Path,
    *,
    canonical_path: Path | None = None,
    allowed_external_root: Path = DEFAULT_EXTERNAL_ROOT,
) -> CloneCreationEvidence:
    source = validate_canonical_source(source, canonical_path=canonical_path)
    destination = validate_external_destination(
        destination, allowed_external_root=allowed_external_root, canonical_path=canonical_path
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_before = collect_database_facts(source)
    if source_before.schema_version != REQUIRED_SOURCE_SCHEMA or source_before.quick_check != "ok":
        raise CloneEvidenceError("Canonical source is not a verified schema-12 quick-check database.")
    source_connection = _connect_readonly(source)
    destination_connection = sqlite3.connect(destination, timeout=10)
    try:
        source_connection.backup(destination_connection)
        destination_connection.commit()
    finally:
        destination_connection.close()
        source_connection.close()
    clone = collect_database_facts(destination)
    source_after = collect_database_facts(source)
    _assert_source_unchanged(source_before, source_after)
    if clone.schema_version != REQUIRED_SOURCE_SCHEMA or clone.quick_check != "ok":
        raise CloneEvidenceError("External clone did not preserve schema 12 and quick_check.")
    if clone.counts != source_before.counts or clone.chapter_369 != source_before.chapter_369 or clone.plan_369 != source_before.plan_369:
        raise CloneEvidenceError("External clone logical baseline differs from source.")
    return CloneCreationEvidence(
        mechanism="SQLITE_ONLINE_BACKUP_FROM_READONLY_SOURCE",
        destination_ref=_path_ref(destination),
        source_before=source_before,
        clone=clone,
        source_after=source_after,
        source_unchanged=True,
    )


def _validate_external_existing(path: Path, *, allowed_external_root: Path) -> Path:
    if not path.is_absolute() or not path.exists() or not _is_within(path.resolve(), allowed_external_root.resolve()):
        raise ClonePathRejected("Path is not an existing file inside the approved external root.")
    return path.resolve()


def create_clone_backup(
    clone: Path,
    backup: Path,
    *,
    allowed_external_root: Path = DEFAULT_EXTERNAL_ROOT,
) -> CloneBackupEvidence:
    clone = _validate_external_existing(clone, allowed_external_root=allowed_external_root)
    # The clone itself is external; do not treat its parent as a protected
    # canonical directory when validating another external rehearsal file.
    backup = validate_external_destination(backup, allowed_external_root=allowed_external_root)
    clone_before = collect_database_facts(clone)
    if clone_before.schema_version != REQUIRED_SOURCE_SCHEMA or clone_before.quick_check != "ok":
        raise CloneEvidenceError("Only a verified schema-12 clone may be backed up.")
    temporary = backup.with_name(f".{backup.name}.tmp")
    shutil.copyfile(clone, temporary)
    os.replace(temporary, backup)
    backup_facts = collect_database_facts(backup)
    if backup_facts.sha256 != clone_before.sha256 or backup_facts.schema_version != REQUIRED_SOURCE_SCHEMA:
        raise CloneEvidenceError("Clone backup did not preserve exact schema-12 bytes.")
    return CloneBackupEvidence(
        mechanism="CLOSED_CLONE_BYTE_COPY_ATOMIC_RENAME",
        backup_ref=_path_ref(backup),
        clone_before=clone_before,
        backup=backup_facts,
        exact_hash_match=True,
    )


def migration_hashes() -> dict[int, str]:
    result: dict[int, str] = {}
    dormant_root = Path(__file__).resolve().parent / "migrations" / "dormant"
    for version, (_, filename) in MIGRATION_FILES.items():
        path = dormant_root / filename
        if not path.is_file():
            raise CloneMigrationError(f"Required dormant migration is missing: {version}.")
        result[version] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _load_migration(version: int) -> tuple[str, str, str]:
    if version not in MIGRATION_FILES:
        raise CloneMigrationError("Migration version is not in the explicit 13-15 allowlist.")
    name, filename = MIGRATION_FILES[version]
    path = Path(__file__).resolve().parent / "migrations" / "dormant" / filename
    if not path.is_file():
        raise CloneMigrationError("Allowlisted migration file is missing.")
    sql = path.read_text(encoding="utf-8")
    return name, hashlib.sha256(sql.encode("utf-8")).hexdigest(), sql


def _statements(sql: str) -> list[str]:
    buffer = ""
    statements: list[str] = []
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            if buffer.strip():
                statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        raise CloneMigrationError("Migration contains an incomplete SQL statement.")
    return statements


def _apply_stage(path: Path, version: int, *, fail_after_statement: int | None = None) -> MigrationStageEvidence:
    name, checksum, sql = _load_migration(version)
    connection = _connect_writable_clone(path)
    predecessor = _schema_version(connection)
    expected = version - 1
    if predecessor != expected:
        connection.close()
        raise CloneMigrationError(f"Migration {version} expected schema {expected}, found {predecessor}.")
    try:
        connection.execute("BEGIN IMMEDIATE")
        for number, statement in enumerate(_statements(sql), start=1):
            connection.execute(statement)
            if fail_after_statement is not None and number >= fail_after_statement:
                raise CloneMigrationError(f"INJECTED_MIGRATION_FAILURE_{version}")
        connection.execute(
            "INSERT INTO schema_migrations(version,name,checksum,applied_at) VALUES(?,?,?,?)",
            (version, name, checksum, _utcnow()),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    facts = collect_database_facts(path)
    if facts.schema_version != version or facts.quick_check != "ok":
        raise CloneMigrationError(f"Migration {version} post-stage verification failed.")
    return MigrationStageEvidence(version, name, checksum, predecessor, version, facts.quick_check, True)


def apply_dormant_migration(path: Path, version: int, *, fail_after_statement: int | None = None) -> MigrationStageEvidence:
    path = _validate_external_existing(path, allowed_external_root=path.parent)
    return _apply_stage(path, version, fail_after_statement=fail_after_statement)


def _schema_object_errors(path: Path) -> list[str]:
    errors: list[str] = []
    connection = _connect_readonly(path)
    try:
        for version, expected_indexes in EXPECTED_INDEXES.items():
            table, _ = MIGRATION_FILES[version]
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?",
                (table,),
            ).fetchall()
            actual = {str(row[0]) for row in rows}
            missing = sorted(expected_indexes - actual)
            if missing:
                errors.append(f"MISSING_INDEXES_{version}:{','.join(missing)}")
            sql_row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            sql = str(sql_row[0] or "") if sql_row else ""
            for fragment in REQUIRED_CHECK_FRAGMENTS[table]:
                if fragment.lower() not in sql.lower():
                    errors.append(f"MISSING_CHECK_{table}:{fragment}")
            if not connection.execute(f"PRAGMA foreign_key_list({table})").fetchall():
                errors.append(f"MISSING_FOREIGN_KEYS_{table}")
    finally:
        connection.close()
    return errors


def validate_migrated_clone(
    baseline: DatabaseFacts,
    migrated: DatabaseFacts,
    *,
    migrated_path: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    expected_tables = set(DORMANT_TABLES)
    tables = set(migrated.tables)
    if migrated.schema_version != TARGET_SCHEMA:
        errors.append("FINAL_SCHEMA_NOT_15")
    if migrated.quick_check != "ok":
        errors.append("QUICK_CHECK_FAILED")
    if migrated.foreign_key_check != "ok":
        errors.append("FOREIGN_KEY_CHECK_FAILED")
    if not expected_tables.issubset(tables):
        errors.append("REQUIRED_DORMANT_TABLE_MISSING")
    if migrated.counts != baseline.counts:
        errors.append("LEGACY_COUNTS_CHANGED")
    if migrated.chapter_369 != baseline.chapter_369 or migrated.plan_369 != baseline.plan_369:
        errors.append("CHAPTER_369_CHANGED")
    if any(migrated.dormant_row_counts.get(table, 0) != 0 for table in DORMANT_TABLES):
        errors.append("DORMANT_ROWS_CREATED")
    if migrated_path is not None:
        errors.extend(_schema_object_errors(migrated_path.resolve(strict=True)))
    return {"valid": not errors, "errors": errors, "expected_schema": TARGET_SCHEMA}


def migrate_clone(path: Path, *, failure_version: int | None = None) -> MigrationRunEvidence:
    path = _validate_external_existing(path, allowed_external_root=path.parent)
    baseline = collect_database_facts(path)
    if baseline.schema_version != REQUIRED_SOURCE_SCHEMA:
        raise CloneMigrationError("Migration rehearsal must start at schema 12.")
    stages: list[MigrationStageEvidence] = []
    try:
        for version in (13, 14, 15):
            stages.append(_apply_stage(path, version, fail_after_statement=1 if failure_version == version else None))
    except Exception as exc:
        raise CloneMigrationError(f"MIGRATION_STAGE_FAILED_{getattr(exc, 'args', ['UNKNOWN'])[0]}") from exc
    final = collect_database_facts(path)
    postflight = validate_migrated_clone(baseline, final, migrated_path=path)
    if not postflight["valid"]:
        raise CloneEvidenceError(";".join(postflight["errors"]))
    return MigrationRunEvidence((13, 14, 15), tuple(stages), final, postflight)


def _archive_sidecar(path: Path, archive: Path) -> str | None:
    if not path.exists():
        return None
    suffix = "-wal" if path.name.endswith("-wal") else "-shm" if path.name.endswith("-shm") else path.suffix
    target = archive.with_name(archive.name + suffix)
    os.replace(path, target)
    return target.name


def restore_clone_backup(
    clone: Path,
    backup: Path,
    *,
    archive: Path | None = None,
    allowed_external_root: Path = DEFAULT_EXTERNAL_ROOT,
) -> RollbackEvidence:
    clone = _validate_external_existing(clone, allowed_external_root=allowed_external_root)
    backup = _validate_external_existing(backup, allowed_external_root=allowed_external_root)
    backup_facts = collect_database_facts(backup)
    if backup_facts.schema_version != REQUIRED_SOURCE_SCHEMA or backup_facts.quick_check != "ok":
        raise CloneEvidenceError("Rollback backup is not a verified schema-12 database.")
    current = collect_database_facts(clone)
    archive = archive or clone.with_name(clone.stem + ".failed.db")
    archive = validate_external_destination(archive, allowed_external_root=allowed_external_root)
    if current.sha256 == backup_facts.sha256 and current.schema_version == REQUIRED_SOURCE_SCHEMA:
        return RollbackEvidence(
            "ATOMIC_EXTERNAL_CLONE_RESTORE", _path_ref(backup), _path_ref(archive), current.sha256,
            current.sha256, backup_facts.sha256, True, current.schema_version, current.quick_check,
            current.foreign_key_check, (), True, current.counts == backup_facts.counts and current.chapter_369 == backup_facts.chapter_369,
        )
    os.replace(clone, archive)
    sidecars: list[str] = []
    for suffix in ("-wal", "-shm"):
        archived = _archive_sidecar(clone.with_name(clone.name + suffix), archive)
        if archived:
            sidecars.append(archived)
    temporary = clone.with_name(f".{clone.name}.restore.tmp")
    shutil.copyfile(backup, temporary)
    if _sha256(temporary) != backup_facts.sha256:
        temporary.unlink(missing_ok=True)
        raise CloneEvidenceError("Restore staging hash does not match verified backup.")
    os.replace(temporary, clone)
    restored = collect_database_facts(clone)
    exact = restored.sha256 == backup_facts.sha256
    logical = (
        restored.schema_version == REQUIRED_SOURCE_SCHEMA
        and restored.quick_check == "ok"
        and restored.foreign_key_check == "ok"
        and restored.counts == backup_facts.counts
        and restored.chapter_369 == backup_facts.chapter_369
        and restored.plan_369 == backup_facts.plan_369
        and not any(restored.dormant_row_counts.values())
    )
    if not exact or not logical:
        raise CloneEvidenceError("Restored clone failed exact backup or logical verification.")
    failed_hash = _sha256(archive) if archive.exists() else None
    return RollbackEvidence(
        "ATOMIC_EXTERNAL_CLONE_RESTORE", _path_ref(backup), _path_ref(archive), failed_hash,
        restored.sha256, backup_facts.sha256, exact, restored.schema_version, restored.quick_check,
        restored.foreign_key_check, tuple(sorted(sidecars)), False, logical,
    )


def write_bounded_evidence(root: Path, filename: str, payload: Mapping[str, Any]) -> Path:
    root = root.resolve()
    if root == REPOSITORY_ROOT or _is_within(root, REPOSITORY_ROOT):
        raise ClonePathRejected("Evidence root cannot be inside the repository.")
    if not filename.endswith(".json") and filename != "REHEARSAL_RESULT.txt":
        raise ClonePathRejected("Evidence filename is not allowlisted.")
    target = (root / filename).resolve()
    if not _is_within(target, root):
        raise ClonePathRejected("Evidence path escapes external root.")
    root.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) if not isinstance(payload, str) else payload
    if len(text.encode("utf-8")) > 64 * 1024:
        raise CloneEvidenceError("Evidence is too large.")
    lowered = text.lower()
    if any(token in lowered for token in ("owner_token", "password", "api_key", "secret", "full_text", "raw_sql")):
        raise CloneEvidenceError("Evidence contains forbidden sensitive fields.")
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, target)
    return target


def dataclass_payload(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: dataclass_payload(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): dataclass_payload(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [dataclass_payload(item) for item in value]
    return value


__all__ = [
    "CORE_COUNT_TABLES", "DEFAULT_EXTERNAL_ROOT", "DORMANT_TABLES", "EXPECTED_INDEXES",
    "CloneBackupEvidence", "CloneCreationEvidence", "CloneEvidenceError", "CloneMigrationError",
    "ClonePathRejected", "DatabaseFacts", "MigrationRunEvidence", "MigrationStageEvidence",
    "RollbackEvidence", "TARGET_SCHEMA", "REQUIRED_SOURCE_SCHEMA", "apply_dormant_migration",
    "collect_database_facts", "create_clone_backup", "create_external_clone", "dataclass_payload",
    "migration_hashes", "migrate_clone", "restore_clone_backup", "validate_canonical_source",
    "validate_external_destination", "validate_migrated_clone", "write_bounded_evidence",
]
