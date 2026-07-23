from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .db import Database
from .files import sha256_file, sha256_text
from .gemini_cache import GeminiRepairCache
from .migrations import LATEST_SCHEMA_VERSION, SchemaMigrationError
from .batch_prepare_schema import PREPARE_SCHEMA_VERSION, prepare_migration_runner
from .storage import ContentStore
from .youtube_handoff import HandoffError, verify_handoff


@dataclass(frozen=True)
class Finding:
    level: str
    name: str
    detail: str


def check_data_integrity(config: Settings, *, deep: bool = False) -> list[Finding]:
    findings: list[Finding] = []
    if not config.db_path.exists():
        return [Finding("ERROR", "database", f"missing: {config.db_path}")]
    database = Database(config.db_path, migration_runner=prepare_migration_runner())
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
        schema_level = (
            "OK"
            if schema_version in {LATEST_SCHEMA_VERSION, PREPARE_SCHEMA_VERSION}
            else "ERROR"
        )
        findings.append(
            Finding(
                schema_level,
                "schema_version",
                f"current={schema_version} supported={LATEST_SCHEMA_VERSION},{PREPARE_SCHEMA_VERSION}",
            )
        )
    except SchemaMigrationError as exc:
        findings.append(Finding("ERROR", "schema_version", str(exc)))

    counts = {}
    for table in (
        "books", "chapters", "text_revisions", "book_voice_profiles", "characters",
        "character_aliases", "character_bible_imports", "casting_plans",
        "speaker_assignment_drafts", "jobs", "segments", "artifacts",
    ):
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

    duplicate_external = database.fetch_all(
        """SELECT book_id,external_key_normalized,COUNT(*) AS count FROM characters
           WHERE external_key_normalized IS NOT NULL
           GROUP BY book_id,external_key_normalized HAVING COUNT(*)>1"""
    )
    orphan_aliases = int(database.fetch_one(
        """SELECT COUNT(*) AS count FROM character_aliases a
           LEFT JOIN characters c ON c.id=a.character_id WHERE c.id IS NULL"""
    )["count"])
    alias_book_mismatch = int(database.fetch_one(
        """SELECT COUNT(*) AS count FROM character_aliases a
           JOIN characters c ON c.id=a.character_id WHERE a.book_id<>c.book_id"""
    )["count"])
    invalid_character_enums = int(database.fetch_one(
        """SELECT COUNT(*) AS count FROM characters
           WHERE (gender IS NOT NULL AND gender NOT IN ('male','female','unknown'))
              OR role NOT IN ('main','supporting','minor','unknown')
              OR (age_group IS NOT NULL AND age_group NOT IN
                 ('child','teen','young_adult','adult','elder','unknown'))"""
    )["count"])
    identity_errors = len(duplicate_external) + orphan_aliases + alias_book_mismatch + invalid_character_enums
    findings.append(Finding(
        "OK" if identity_errors == 0 else "ERROR",
        "character_bible_integrity",
        f"duplicate_external_keys={len(duplicate_external)} orphan_aliases={orphan_aliases} "
        f"alias_book_mismatch={alias_book_mismatch} invalid_enums={invalid_character_enums}",
    ))

    invalid_drafts = 0
    draft_rows = database.fetch_all(
        """SELECT d.*,c.book_id AS chapter_book_id,tr.chapter_id AS revision_chapter_id
           FROM speaker_assignment_drafts d
           LEFT JOIN chapters c ON c.id=d.chapter_id
           LEFT JOIN text_revisions tr ON tr.id=d.text_revision_id"""
    )
    content_store = ContentStore(config)
    for row in draft_rows:
        try:
            if row["chapter_book_id"] is None or row["revision_chapter_id"] is None:
                raise ValueError("orphan_owner")
            if int(row["book_id"]) != int(row["chapter_book_id"]):
                raise ValueError("book_owner_mismatch")
            if int(row["chapter_id"]) != int(row["revision_chapter_id"]):
                raise ValueError("revision_owner_mismatch")
            payload = content_store.read_json(str(row["content_path"]))
            canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if sha256_text(canonical) != row["content_sha256"]:
                raise ValueError("content_hash_mismatch")
            if payload.get("schema") != row["response_schema"]:
                raise ValueError("response_schema_mismatch")
            if payload.get("input_fingerprint") != row["input_fingerprint"]:
                raise ValueError("input_fingerprint_mismatch")
            referenced = {
                int(item["character_id"])
                for item in payload.get("assignments", [])
                if item.get("speaker_type") == "character" and item.get("character_id") is not None
            }
            indexed = {
                int(item["character_id"])
                for item in database.fetch_all(
                    "SELECT character_id FROM speaker_assignment_draft_characters WHERE draft_id=?",
                    (row["id"],),
                )
            }
            if not referenced <= indexed:
                raise ValueError("invalid_character_reference")
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            invalid_drafts += 1
    findings.append(Finding(
        "OK" if invalid_drafts == 0 else "WARN",
        "speaker_assignment_drafts",
        f"drafts={len(draft_rows)} invalid={invalid_drafts}",
    ))

    review_plans = 0
    invalid_review_links = 0
    idempotency_identities: dict[str, tuple[object, object, object]] = {}
    for row in database.fetch_all("SELECT id,chapter_id,content_path,plan_sha256 FROM casting_plans"):
        try:
            payload = content_store.read_json(str(row["content_path"]))
            canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if sha256_text(canonical) != row["plan_sha256"]:
                raise ValueError("content_hash_mismatch")
            metadata = payload.get("source_metadata") or {}
            if metadata.get("source") != "gemini_speaker_review":
                continue
            review_plans += 1
            review = metadata.get("review")
            if not isinstance(review, dict):
                raise ValueError("missing_review_metadata")
            draft = database.fetch_one(
                "SELECT chapter_id,input_fingerprint FROM speaker_assignment_drafts WHERE id=?",
                (review.get("draft_id"),),
            )
            if not draft or int(draft["chapter_id"]) != int(row["chapter_id"]):
                raise ValueError("invalid_review_draft_link")
            if review.get("draft_fingerprint") != draft["input_fingerprint"]:
                raise ValueError("review_draft_fingerprint_mismatch")
            base_id = review.get("base_casting_plan_id")
            if base_id is not None:
                base = database.fetch_one("SELECT chapter_id FROM casting_plans WHERE id=?", (base_id,))
                if not base or int(base["chapter_id"]) != int(row["chapter_id"]):
                    raise ValueError("invalid_review_base_link")
            decision_fingerprint = review.get("decision_fingerprint")
            if (
                not isinstance(decision_fingerprint, str)
                or len(decision_fingerprint) != 64
                or any(character not in "0123456789abcdef" for character in decision_fingerprint)
            ):
                raise ValueError("invalid_decision_fingerprint")
            idempotency_key = review.get("idempotency_key")
            if not isinstance(idempotency_key, str) or not idempotency_key.strip():
                raise ValueError("invalid_idempotency_key")
            reviewed_ids = review.get("reviewed_utterance_ids")
            if not isinstance(reviewed_ids, list) or len(reviewed_ids) != len(set(reviewed_ids)):
                raise ValueError("invalid_reviewed_utterance_ids")
            identity = (review.get("draft_id"), base_id, decision_fingerprint)
            previous = idempotency_identities.setdefault(idempotency_key, identity)
            if previous != identity:
                raise ValueError("idempotency_key_conflict")
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            invalid_review_links += 1
    findings.append(Finding(
        "OK" if invalid_review_links == 0 else "WARN",
        "speaker_review_links",
        f"plans={review_plans} invalid={invalid_review_links}",
    ))

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
    export_manifests = list(config.youtube_export_dir.glob("*/handoff.json")) if config.youtube_export_dir.exists() else []
    invalid_exports = 0
    for manifest in export_manifests:
        try:
            verify_handoff(manifest.parent)
        except HandoffError:
            invalid_exports += 1
    findings.append(
        Finding(
            "OK" if invalid_exports == 0 else "WARN",
            "youtube_handoff_exports",
            f"bundles={len(export_manifests)} invalid={invalid_exports}",
        )
    )
    return findings


def has_errors(findings: list[Finding]) -> bool:
    return any(finding.level == "ERROR" for finding in findings)
