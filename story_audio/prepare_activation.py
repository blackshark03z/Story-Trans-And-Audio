"""Explicit canonical activation tooling for production PREPARE."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from .batch_prepare_clone_rehearsal import (
    DORMANT_TABLES,
    CloneEvidenceError,
    ClonePathRejected,
    collect_database_facts,
    create_external_clone,
    validate_canonical_source,
    validate_external_destination,
    validate_migrated_clone,
)
from .batch_prepare_runtime_integration import DISABLED, read_runtime_integration_config
from .batch_prepare_schema import (
    PREPARE_SCHEMA_VERSION,
    prepare_migration_runner,
    verified_prepare_migration_hashes,
)
from .config import canonical_production_db_path
from .db import utcnow


ACTIVATION_CONFIRMATION = "ACTIVATE_CANONICAL_SCHEMA_15"
ROLLBACK_CONFIRMATION = "RESTORE_CANONICAL_SCHEMA_12"
EVIDENCE_FILENAME = "prepare-activation-preflight.json"
DEFAULT_ACTIVATION_ROOT = Path(r"D:\Youtube_AI_HANDOFFS\Story Audio\prepare_activation")
ACTIVE_JOB_STATUSES = (
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


class PrepareActivationError(RuntimeError):
    pass


def _flags_are_disabled() -> dict[str, Any]:
    config = read_runtime_integration_config()
    disabled = (
        config.config_valid
        and config.mode == DISABLED
        and not config.flags.feature_available
        and not config.flags.mutation_enabled
        and not config.flags.operator_window_open
        and not config.flags.canonical_schema_ready
        and config.flags.kill_switch_active
    )
    return {
        "valid": disabled,
        "runtime_mode": config.mode,
        "feature_available": config.flags.feature_available,
        "mutation_enabled": config.flags.mutation_enabled,
        "operator_window_open": config.flags.operator_window_open,
        "canonical_schema_ready": config.flags.canonical_schema_ready,
        "kill_switch_active": config.flags.kill_switch_active,
        "authentication_state": (
            "CONFIGURED" if config.auth.enabled and config.auth.config_valid else "DISABLED"
        ),
        "errors": list(config.errors),
    }


def _readonly_active_job_count(path: Path) -> int:
    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro&immutable=1",
        uri=True,
        timeout=5,
    )
    try:
        placeholders = ",".join("?" for _ in ACTIVE_JOB_STATUSES)
        row = connection.execute(
            f"SELECT COUNT(*) FROM jobs WHERE status IN ({placeholders})",
            ACTIVE_JOB_STATUSES,
        ).fetchone()
        return int(row[0])
    finally:
        connection.close()


def _require_stopped_database(path: Path) -> None:
    sidecars = [
        candidate
        for candidate in (
            path.with_name(path.name + "-wal"),
            path.with_name(path.name + "-shm"),
        )
        if candidate.exists()
    ]
    if sidecars:
        raise PrepareActivationError(
            "Canonical WAL/SHM sidecars are present; stop the runtime before activation preflight."
        )


def _require_disabled_flags() -> dict[str, Any]:
    flags = _flags_are_disabled()
    if not flags["valid"]:
        raise PrepareActivationError(
            "PREPARE flags must remain hard-disabled with the kill switch active."
        )
    return flags


def _write_evidence(path: Path, payload: Mapping[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    if len(text.encode("utf-8")) > 128 * 1024:
        raise PrepareActivationError("Activation evidence exceeded the bounded size.")
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _command(script: Path, backup: Path, switch: str, confirmation: str) -> str:
    return (
        "$env:STORY_AUDIO_ALLOW_LIVE_DB='1'; "
        f"& 'D:\\Youtube\\VieNeu-TTS\\.venv\\Scripts\\python.exe' "
        f"'{script}' --backup '{backup}' {switch} --confirm '{confirmation}'"
    )


def run_preflight(
    backup: Path,
    *,
    canonical_path: Path | None = None,
    external_root: Path = DEFAULT_ACTIVATION_ROOT,
    script_path: Path | None = None,
) -> dict[str, Any]:
    canonical = validate_canonical_source(
        canonical_path or canonical_production_db_path(),
        canonical_path=canonical_path or canonical_production_db_path(),
    )
    _require_stopped_database(canonical)
    flags = _require_disabled_flags()
    before = collect_database_facts(canonical)
    if before.schema_version != 12 or before.quick_check != "ok":
        raise PrepareActivationError("Canonical database must be verified schema 12.")
    active_jobs = _readonly_active_job_count(canonical)
    if active_jobs:
        raise PrepareActivationError("Canonical database has active or prepared jobs.")

    backup = backup.resolve()
    clone_evidence = create_external_clone(
        canonical,
        backup,
        canonical_path=canonical,
        allowed_external_root=external_root,
    )
    after = collect_database_facts(canonical)
    if before != after:
        changed = [
            field
            for field in before.__dataclass_fields__
            if getattr(before, field) != getattr(after, field)
        ]
        raise PrepareActivationError(
            f"Canonical database changed during preflight: {','.join(changed)} "
            f"({before.wal_present}/{before.shm_present} -> "
            f"{after.wal_present}/{after.shm_present})."
        )

    hashes = verified_prepare_migration_hashes()
    script = (script_path or Path(__file__).resolve().parents[1] / "scripts" / "prepare_activation.py").resolve()
    evidence_path = backup.parent / EVIDENCE_FILENAME
    payload = {
        "status": "GO_FOR_EXPLICIT_ACTIVATION_APPROVAL",
        "canonical_path": str(canonical),
        "backup_path": str(backup),
        "canonical": asdict(before),
        "backup": asdict(clone_evidence.clone),
        "source_unchanged": clone_evidence.source_unchanged,
        "active_job_count": active_jobs,
        "flags": flags,
        "migration_hashes": {str(key): value for key, value in hashes.items()},
        "migration_command": _command(
            script, backup, "--execute-migration", ACTIVATION_CONFIRMATION
        ),
        "rollback_command": _command(
            script, backup, "--rollback", ROLLBACK_CONFIRMATION
        ),
        "canary_rules": {
            "book_count": 1,
            "chapter_count_min": 1,
            "chapter_count_max": 3,
            "contiguous_range": True,
            "required_target_phase": "PREPARE",
            "all_rows_must_be_included": True,
            "approved_casting_required": True,
            "existing_or_live_jobs_forbidden": True,
            "chapter_369_forbidden": True,
            "start_render_forbidden": True,
        },
    }
    _write_evidence(evidence_path, payload)
    payload["evidence_path"] = str(evidence_path)
    return payload


def _load_preflight(backup: Path) -> dict[str, Any]:
    evidence_path = backup.resolve().parent / EVIDENCE_FILENAME
    if not evidence_path.is_file():
        raise PrepareActivationError("Verified preflight evidence is missing.")
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    if payload.get("backup_path") != str(backup.resolve()):
        raise PrepareActivationError("Preflight evidence does not match the requested backup.")
    return payload


def _require_live_execution_authority(confirmation: str, expected: str) -> None:
    if confirmation != expected:
        raise PrepareActivationError("Exact activation confirmation is required.")
    if os.getenv("STORY_AUDIO_TESTING", "").strip() == "1":
        raise PrepareActivationError("Canonical activation is forbidden in test mode.")
    if os.getenv("STORY_AUDIO_ALLOW_LIVE_DB", "").strip() != "1":
        raise PrepareActivationError("STORY_AUDIO_ALLOW_LIVE_DB=1 is required.")


def execute_migration(
    backup: Path,
    *,
    confirmation: str,
    canonical_path: Path | None = None,
) -> dict[str, Any]:
    _require_live_execution_authority(confirmation, ACTIVATION_CONFIRMATION)
    canonical = validate_canonical_source(
        canonical_path or canonical_production_db_path(),
        canonical_path=canonical_path or canonical_production_db_path(),
    )
    _require_stopped_database(canonical)
    _require_disabled_flags()
    evidence = _load_preflight(backup)
    baseline = collect_database_facts(canonical)
    if baseline.schema_version != 12 or baseline.quick_check != "ok":
        raise PrepareActivationError("Migration requires the verified schema-12 canonical state.")
    if baseline.sha256 != evidence["canonical"]["sha256"]:
        raise PrepareActivationError("Canonical hash changed after preflight; run preflight again.")
    backup_facts = collect_database_facts(backup.resolve())
    if backup_facts.schema_version != 12 or backup_facts.quick_check != "ok":
        raise PrepareActivationError("Rollback backup verification failed.")
    if _readonly_active_job_count(canonical):
        raise PrepareActivationError("Active jobs block schema activation.")

    connection = sqlite3.connect(canonical, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        version = prepare_migration_runner().apply(connection, utcnow())
    finally:
        connection.close()
    migrated = collect_database_facts(canonical)
    postflight = validate_migrated_clone(baseline, migrated, migrated_path=canonical)
    if version != PREPARE_SCHEMA_VERSION or not postflight["valid"]:
        raise PrepareActivationError("Schema activation postflight failed; rollback is required.")
    result = {
        "status": "CANONICAL_SCHEMA_READY_BUT_DISABLED",
        "schema_version": migrated.schema_version,
        "quick_check": migrated.quick_check,
        "flags": _require_disabled_flags(),
        "canonical": asdict(migrated),
        "postflight": postflight,
    }
    _write_evidence(backup.resolve().parent / "prepare-activation-result.json", result)
    return result


def rollback_migration(
    backup: Path,
    *,
    confirmation: str,
    canonical_path: Path | None = None,
    external_root: Path = DEFAULT_ACTIVATION_ROOT,
) -> dict[str, Any]:
    _require_live_execution_authority(confirmation, ROLLBACK_CONFIRMATION)
    canonical = validate_canonical_source(
        canonical_path or canonical_production_db_path(),
        canonical_path=canonical_path or canonical_production_db_path(),
    )
    _require_stopped_database(canonical)
    _require_disabled_flags()
    evidence = _load_preflight(backup)
    current = collect_database_facts(canonical)
    backup_facts = collect_database_facts(backup.resolve())
    if current.schema_version != PREPARE_SCHEMA_VERSION:
        raise PrepareActivationError("Rollback requires canonical schema 15.")
    if any(current.dormant_row_counts.get(table, 0) for table in DORMANT_TABLES):
        raise PrepareActivationError(
            "PREPARE state exists; pre-activation full-file rollback is no longer allowed."
        )
    if current.counts != backup_facts.counts:
        raise PrepareActivationError("Legacy counts changed; automatic rollback is blocked.")
    if current.chapter_369 != backup_facts.chapter_369 or current.plan_369 != backup_facts.plan_369:
        raise PrepareActivationError("Chapter 369 changed; automatic rollback is blocked.")

    archive = validate_external_destination(
        backup.resolve().parent / "canonical-schema15-failed.db",
        allowed_external_root=external_root,
        canonical_path=canonical,
    )
    shutil.copyfile(canonical, archive)
    temporary = canonical.with_name(f".{canonical.name}.restore.tmp")
    shutil.copyfile(backup.resolve(), temporary)
    if collect_database_facts(temporary).sha256 != backup_facts.sha256:
        temporary.unlink(missing_ok=True)
        raise CloneEvidenceError("Rollback staging hash does not match the verified backup.")
    os.replace(temporary, canonical)
    restored = collect_database_facts(canonical)
    if restored.sha256 != backup_facts.sha256 or restored.schema_version != 12:
        raise PrepareActivationError("Rollback verification failed.")
    return {
        "status": "CANONICAL_SCHEMA_12_RESTORED_PREPARE_DISABLED",
        "canonical": asdict(restored),
        "backup_path": evidence["backup_path"],
        "archive_path": str(archive),
    }


__all__ = [
    "ACTIVATION_CONFIRMATION",
    "DEFAULT_ACTIVATION_ROOT",
    "EVIDENCE_FILENAME",
    "PrepareActivationError",
    "ROLLBACK_CONFIRMATION",
    "execute_migration",
    "rollback_migration",
    "run_preflight",
]
