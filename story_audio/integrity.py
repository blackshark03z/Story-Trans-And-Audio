from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .db import Database
from .files import sha256_file
from .gemini_cache import GeminiRepairCache
from .migrations import LATEST_SCHEMA_VERSION, SchemaMigrationError
from .storage import ContentStore


@dataclass(frozen=True)
class Finding:
    level: str
    name: str
    detail: str


def check_data_integrity(config: Settings, *, deep: bool = False) -> list[Finding]:
    findings: list[Finding] = []
    if not config.db_path.exists():
        return [Finding("ERROR", "database", f"missing: {config.db_path}")]
    database = Database(config.db_path)
    quick = database.fetch_one("PRAGMA quick_check")
    quick_value = next(iter(dict(quick).values())) if quick else "no result"
    findings.append(
        Finding(
            "OK" if quick_value == "ok" else "ERROR",
            "sqlite_quick_check",
            str(quick_value),
        )
    )
    try:
        schema_version = database.schema_version()
        schema_level = "OK" if schema_version == LATEST_SCHEMA_VERSION else "ERROR"
        findings.append(
            Finding(
                schema_level,
                "schema_version",
                f"current={schema_version} supported={LATEST_SCHEMA_VERSION}",
            )
        )
    except SchemaMigrationError as exc:
        findings.append(Finding("ERROR", "schema_version", str(exc)))

    counts = {}
    for table in ("books", "chapters", "text_revisions", "jobs", "segments", "artifacts"):
        try:
            counts[table] = int(
                database.fetch_one(f"SELECT COUNT(*) AS count FROM {table}")["count"]
            )
        except Exception as exc:
            findings.append(Finding("ERROR", f"table_{table}", str(exc)))
    findings.append(
        Finding(
            "INFO",
            "counts",
            " ".join(f"{key}={value}" for key, value in counts.items()),
        )
    )

    cache_report = GeminiRepairCache(ContentStore(config), config).inspect(deep=deep)
    if cache_report.get("root_missing"):
        findings.append(Finding("WARN", "gemini_repair_cache", "cache root is missing; it will be recreated on startup"))
    elif cache_report.get("root_unreadable"):
        findings.append(Finding("WARN", "gemini_repair_cache", "cache root is not readable; entries cannot be reused"))
    else:
        invalid_count = len(cache_report["invalid"])
        partial_count = int(cache_report["partial_files"])
        level = "OK" if invalid_count == 0 and partial_count == 0 else "WARN"
        findings.append(
            Finding(
                level,
                "gemini_repair_cache",
                f"entries={cache_report['entries']} checked={cache_report['checked']} "
                f"invalid={invalid_count} partial={partial_count} bytes={cache_report['manifest_bytes']} "
                f"deep={deep}",
            )
        )
        for item in cache_report["invalid"][:5]:
            findings.append(
                Finding("WARN", "gemini_cache_invalid", f"entry={item['entry']} reason={item['reason']}")
            )

    missing_blobs = 0
    bad_blob_hashes = 0
    for row in database.fetch_all(
        "SELECT id,content_path,content_sha256 FROM text_revisions"
    ):
        path = config.blobs_dir / row["content_path"]
        if not path.exists():
            missing_blobs += 1
            if missing_blobs <= 5:
                findings.append(
                    Finding(
                        "ERROR",
                        "missing_text_blob",
                        f"revision={row['id']} path={row['content_path']}",
                    )
                )
        elif deep and sha256_file(path) != row["content_sha256"]:
            bad_blob_hashes += 1
            if bad_blob_hashes <= 5:
                findings.append(
                    Finding("ERROR", "text_blob_hash", f"revision={row['id']} mismatch")
                )
    findings.append(
        Finding(
            "OK" if missing_blobs == 0 and bad_blob_hashes == 0 else "ERROR",
            "text_blobs",
            f"missing={missing_blobs} bad_hash={bad_blob_hashes}",
        )
    )

    missing_artifacts = 0
    bad_artifact_hashes = 0
    active_rows = database.fetch_all(
        "SELECT id,path,sha256 FROM artifacts WHERE status='active' AND deleted_at IS NULL"
    )
    for row in active_rows:
        path = Path(row["path"])
        if not path.exists():
            missing_artifacts += 1
            findings.append(
                Finding(
                    "ERROR",
                    "missing_active_artifact",
                    f"artifact={row['id']} path={path}",
                )
            )
        elif deep and sha256_file(path) != row["sha256"]:
            bad_artifact_hashes += 1
            findings.append(
                Finding("ERROR", "artifact_hash", f"artifact={row['id']} mismatch")
            )
    findings.append(
        Finding(
            "OK" if missing_artifacts == 0 and bad_artifact_hashes == 0 else "ERROR",
            "active_artifacts",
            f"checked={len(active_rows)} missing={missing_artifacts} bad_hash={bad_artifact_hashes}",
        )
    )

    missing_segments = 0
    for row in database.fetch_all(
        "SELECT id,wav_path FROM segments WHERE status='verified' AND wav_path IS NOT NULL"
    ):
        if not Path(row["wav_path"]).exists():
            missing_segments += 1
            if missing_segments <= 5:
                findings.append(
                    Finding(
                        "ERROR",
                        "missing_verified_segment",
                        f"segment={row['id']} path={row['wav_path']}",
                    )
                )
    findings.append(
        Finding(
            "OK" if missing_segments == 0 else "ERROR",
            "verified_segments",
            f"missing={missing_segments}",
        )
    )

    active_jobs = int(
        database.fetch_one(
            "SELECT COUNT(*) AS count FROM jobs "
            "WHERE status IN ('running','repairing','synthesizing','assembling')"
        )["count"]
    )
    findings.append(Finding("INFO", "active_jobs", str(active_jobs)))
    return findings


def has_errors(findings: list[Finding]) -> bool:
    return any(finding.level == "ERROR" for finding in findings)
