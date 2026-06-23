from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .files import atomic_write_json, atomic_write_text, sha256_file, sha256_text
from .gemini import GENERATION_SETTINGS, REPAIR_CONTRACT_VERSION
from .storage import ContentStore
from .text import (
    LEXICAL_VALIDATOR_VERSION,
    REPAIR_BLOCK_STRATEGY_VERSION,
    validate_lexical_identity,
)


CACHE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CacheLookup:
    status: str
    cache_key: str
    repaired_text: str | None = None
    repaired_blob_path: str | None = None
    reason: str | None = None
    lookup_ms: float = 0.0
    validation_ms: float = 0.0


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class GeminiRepairCache:
    def __init__(self, store: ContentStore, config: Settings):
        self.store = store
        self.config = config

    def identity(self, *, source_hash: str, model: str, prompt_version: str) -> dict[str, Any]:
        return {
            "source_hash": source_hash,
            "model": model.strip(),
            "prompt_version": prompt_version.strip(),
            "repair_contract_version": REPAIR_CONTRACT_VERSION,
            "block_strategy_version": REPAIR_BLOCK_STRATEGY_VERSION,
            "lexical_validator_version": LEXICAL_VALIDATOR_VERSION,
            "settings": GENERATION_SETTINGS,
        }

    def cache_key(self, identity: dict[str, Any]) -> str:
        return sha256_text(canonical_json(identity))

    def contract_fingerprint(self, *, model: str, prompt_version: str) -> str:
        identity = self.identity(
            source_hash="0" * 64, model=model, prompt_version=prompt_version
        )
        return self.cache_key(identity)

    def legacy_checkpoint_is_compatible(self) -> bool:
        """Allow adoption of checkpoints made by the pre-cache implementation.

        This must become false when any legacy repair behavior changes.
        """
        return (
            REPAIR_CONTRACT_VERSION == "punctuation-only-v1"
            and REPAIR_BLOCK_STRATEGY_VERSION == "repair-block-v1-target1900-max2500"
            and LEXICAL_VALIDATOR_VERSION == "lexical-token-v1"
            and GENERATION_SETTINGS
            == {"temperature": 0, "response_mime_type": "application/json"}
        )

    def _manifest_path(self, cache_key: str) -> Path:
        root = self.config.gemini_cache_dir.resolve()
        path = (root / cache_key[:2] / f"{cache_key}.json").resolve()
        if root not in path.parents:
            raise ValueError("Gemini cache path escapes cache root")
        return path

    def _safe_blob_path(self, relative_path: str) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe_blob_path")
        raw = self.config.blobs_dir / relative
        cursor = self.config.blobs_dir
        for part in relative.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError("symlink_blob_path")
        return self.store.absolute(relative_path)

    def lookup(self, *, source: str, model: str, prompt_version: str) -> CacheLookup:
        started = time.perf_counter()
        source_hash = sha256_text(source)
        identity = self.identity(
            source_hash=source_hash, model=model, prompt_version=prompt_version
        )
        cache_key = self.cache_key(identity)
        manifest_path = self._manifest_path(cache_key)
        if not manifest_path.is_file() or manifest_path.is_symlink():
            return CacheLookup(
                "miss", cache_key, lookup_ms=(time.perf_counter() - started) * 1000
            )
        validation_started = time.perf_counter()
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            required = {
                "schema_version",
                "cache_key",
                "identity",
                "source_blob_path",
                "repaired_blob_path",
                "repaired_hash",
                "source_char_count",
                "repaired_char_count",
                "lexical_validated",
                "created_at",
            }
            if not required <= manifest.keys():
                raise ValueError("required manifest metadata is missing")
            if manifest["schema_version"] != CACHE_SCHEMA_VERSION:
                raise ValueError("unsupported cache schema")
            if manifest["cache_key"] != cache_key:
                raise ValueError("manifest cache key mismatch")
            if manifest["identity"] != identity or self.cache_key(manifest["identity"]) != cache_key:
                raise ValueError("canonical identity hash mismatch")
            if manifest["lexical_validated"] is not True:
                raise ValueError("lexical_validation_metadata_missing")
            source_path = self._safe_blob_path(str(manifest["source_blob_path"]))
            repaired_path = self._safe_blob_path(str(manifest["repaired_blob_path"]))
            if not source_path.is_file() or not repaired_path.is_file():
                raise ValueError("payload_blob_missing")
            if sha256_file(source_path) != identity["source_hash"]:
                raise ValueError("source_blob_hash_mismatch")
            repaired = repaired_path.read_text(encoding="utf-8")
            if sha256_text(repaired) != manifest["repaired_hash"]:
                raise ValueError("repaired_blob_hash_mismatch")
            if len(source) != manifest["source_char_count"] or len(repaired) != manifest["repaired_char_count"]:
                raise ValueError("character_count_mismatch")
            valid, reason = validate_lexical_identity(source, repaired)
            if not valid:
                raise ValueError("lexical_validation_failed")
            os.utime(manifest_path, None)
            elapsed = (time.perf_counter() - started) * 1000
            validation_ms = (time.perf_counter() - validation_started) * 1000
            return CacheLookup(
                "hit",
                cache_key,
                repaired,
                str(manifest["repaired_blob_path"]),
                lookup_ms=elapsed,
                validation_ms=validation_ms,
            )
        except json.JSONDecodeError:
            reason = "json_parse_error"
        except UnicodeError:
            reason = "encoding_error"
        except OSError:
            reason = "filesystem_error"
        except TypeError:
            reason = "metadata_type_error"
        except ValueError as exc:
            reason = str(exc)
        if 'reason' in locals():
            return CacheLookup(
                "invalid",
                cache_key,
                reason=reason,
                lookup_ms=(time.perf_counter() - started) * 1000,
                validation_ms=(time.perf_counter() - validation_started) * 1000,
            )

    def store_result(
        self, *, source: str, repaired: str, model: str, prompt_version: str
    ) -> dict[str, Any]:
        valid, reason = validate_lexical_identity(source, repaired)
        if not valid:
            raise ValueError(f"Cannot cache lexically invalid repair: {reason}")
        source_blob_path, source_hash = self.store.put_text(source)
        repaired_blob_path, repaired_hash = self.store.put_text(repaired)
        # Content-addressed blobs are immutable. If a prior cache payload was
        # damaged on disk, restore the bytes matching the canonical hash.
        source_absolute = self.store.absolute(source_blob_path)
        if not source_absolute.is_file() or sha256_file(source_absolute) != source_hash:
            atomic_write_text(source_absolute, source)
        repaired_absolute = self.store.absolute(repaired_blob_path)
        if not repaired_absolute.is_file() or sha256_file(repaired_absolute) != repaired_hash:
            atomic_write_text(repaired_absolute, repaired)
        identity = self.identity(
            source_hash=source_hash, model=model, prompt_version=prompt_version
        )
        cache_key = self.cache_key(identity)
        manifest = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "cache_key": cache_key,
            "identity": identity,
            "source_blob_path": source_blob_path,
            "repaired_blob_path": repaired_blob_path,
            "repaired_hash": repaired_hash,
            "source_char_count": len(source),
            "repaired_char_count": len(repaired),
            "lexical_validated": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        path = self._manifest_path(cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, manifest)
        return manifest

    def cleanup(self, *, dry_run: bool = True) -> dict[str, int]:
        root = self.config.gemini_cache_dir
        root.mkdir(parents=True, exist_ok=True)
        cutoff = time.time() - self.config.gemini_cache_retention_days * 86_400
        entries = [path for path in root.rglob("*.json") if path.is_file() and not path.is_symlink()]
        entries.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        total_bytes = sum(path.stat().st_size for path in entries)
        removed = removed_bytes = 0
        kept_bytes = 0
        for index, path in enumerate(entries):
            size = path.stat().st_size
            expired = path.stat().st_mtime < cutoff
            over_entries = index >= self.config.gemini_cache_max_entries
            over_bytes = kept_bytes + size > self.config.gemini_cache_max_bytes
            if expired or over_entries or over_bytes:
                removed += 1
                removed_bytes += size
                if not dry_run:
                    path.unlink(missing_ok=True)
            else:
                kept_bytes += size
        if not dry_run:
            for directory in sorted(root.rglob("*"), reverse=True):
                if directory.is_dir():
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
        return {
            "entries": len(entries),
            "bytes": total_bytes,
            "removed": removed,
            "removed_bytes": removed_bytes,
            "remaining": len(entries) - removed,
        }

    def clear_manifests(self) -> None:
        root = self.config.gemini_cache_dir
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True, exist_ok=True)

    def inspect(self, *, deep: bool = False) -> dict[str, Any]:
        root = self.config.gemini_cache_dir
        if not root.is_dir():
            return {
                "entries": 0, "checked": 0, "invalid": [], "partial_files": 0,
                "manifest_bytes": 0, "deep": deep, "root_missing": True,
            }
        if not os.access(root, os.R_OK):
            return {
                "entries": 0, "checked": 0, "invalid": [], "partial_files": 0,
                "manifest_bytes": 0, "deep": deep, "root_unreadable": True,
            }
        manifests = [path for path in root.rglob("*.json") if path.is_file()]
        partials = [path for path in root.rglob("*.partial") if path.is_file()]
        invalid: list[dict[str, str]] = []
        total_bytes = 0
        checked = 0
        for path in manifests:
            try:
                total_bytes += path.stat().st_size
                if path.is_symlink():
                    raise ValueError("symlink_manifest")
                manifest = json.loads(path.read_text(encoding="utf-8"))
                identity = manifest["identity"]
                cache_key = str(manifest["cache_key"])
                if manifest["schema_version"] != CACHE_SCHEMA_VERSION:
                    raise ValueError("unsupported_cache_schema")
                if path.stem != cache_key or self.cache_key(identity) != cache_key:
                    raise ValueError("cache_key_mismatch")
                for field in (
                    "source_blob_path", "repaired_blob_path", "repaired_hash",
                    "source_char_count", "repaired_char_count", "lexical_validated", "created_at",
                ):
                    if field not in manifest:
                        raise ValueError("required_manifest_metadata_missing")
                if deep:
                    source_path = self._safe_blob_path(str(manifest["source_blob_path"]))
                    source = source_path.read_text(encoding="utf-8")
                    repaired_path = self._safe_blob_path(str(manifest["repaired_blob_path"]))
                    repaired = repaired_path.read_text(encoding="utf-8")
                    if sha256_text(source) != identity["source_hash"]:
                        raise ValueError("source_blob_hash_mismatch")
                    if sha256_text(repaired) != manifest["repaired_hash"]:
                        raise ValueError("repaired_blob_hash_mismatch")
                    if len(source) != manifest["source_char_count"] or len(repaired) != manifest["repaired_char_count"]:
                        raise ValueError("character_count_mismatch")
                    valid, _reason = validate_lexical_identity(source, repaired)
                    if not valid:
                        raise ValueError("lexical_validation_failed")
                checked += 1
            except (KeyError, OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
                invalid.append({"entry": path.name, "reason": type(exc).__name__ if not str(exc) else str(exc)})
        return {
            "entries": len(manifests),
            "checked": checked,
            "invalid": invalid,
            "partial_files": len(partials),
            "manifest_bytes": total_bytes,
            "deep": deep,
        }
