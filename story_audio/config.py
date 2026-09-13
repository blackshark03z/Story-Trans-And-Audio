from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_GEMINI_KEY_LOCK = threading.RLock()
_GEMINI_KEY_CURSOR = 0
DEFAULT_GEMINI_MODEL_CHAIN = (
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
)

def canonical_production_db_path() -> Path:
    """Return the canonical production database path.
    
    This is the single source of truth for what constitutes the live production DB.
    Any code attempting to initialize or migrate this path must have explicit opt-in.
    """
    return ROOT / "data" / "app.db"


def _resolve_data_dir() -> Path:
    """Resolve data directory from environment or default.

    Respects STORY_AUDIO_DATA_DIR environment variable for isolated testing.
    When unset, uses the default repository data directory.
    When set, validates and resolves to absolute path.
    """
    override = os.getenv("STORY_AUDIO_DATA_DIR", "")

    # If environment variable is not set, use default
    if override is None or (not override and "STORY_AUDIO_DATA_DIR" not in os.environ):
        return ROOT / "data"

    # If set to empty or whitespace, reject
    override = override.strip()
    if not override:
        raise ValueError("STORY_AUDIO_DATA_DIR cannot be empty or whitespace")

    data_path = Path(override).resolve()
    return data_path


# Resolve data directory once at module load
_DATA_DIR = _resolve_data_dir()


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    data_dir: Path = _DATA_DIR
    db_path: Path = _DATA_DIR / "app.db"
    blobs_dir: Path = _DATA_DIR / "blobs"
    output_dir: Path = _DATA_DIR / "output"
    work_dir: Path = _DATA_DIR / "work"
    imports_dir: Path = _DATA_DIR / "imports"
    log_dir: Path = ROOT / "logs"
    gemini_model: str = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL_CHAIN[0])
    gemini_prompt_version: str = "punctuation-v1"
    speaker_assignment_prompt_version: str = "speaker-assignment-v2"
    speaker_assignment_batch_size: int = 20
    speaker_assignment_context_size: int = 3
    tts_mode: str = "v3turbo"
    tts_sample_rate: int = 48_000
    tts_max_chars: int = 256
    tts_target_chars: int = 230
    tts_temperature: float = 0.8
    tts_top_k: int = 25
    tts_silence_seconds: float = 0.15
    undo_seconds: int = 10
    worker_poll_seconds: float = 0.75
    minimum_free_gb: float = 2.0
    successful_segment_retention_hours: int = 24
    preview_cache_retention_days: int = 30
    preview_cache_max_entries: int = 100
    gemini_cache_retention_days: int = 180
    gemini_cache_max_entries: int = 10_000
    gemini_cache_max_bytes: int = 256 * 1024 * 1024

    @property
    def preview_cache_dir(self) -> Path:
        return self.data_dir / "cache" / "previews"

    @property
    def gemini_cache_dir(self) -> Path:
        return self.data_dir / "cache" / "gemini_repairs"

    @property
    def youtube_export_dir(self) -> Path:
        return self.data_dir / "exports" / "youtube_auto"

    def ensure_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.blobs_dir,
            self.output_dir,
            self.work_dir,
            self.imports_dir,
            self.preview_cache_dir,
            self.gemini_cache_dir,
            self.youtube_export_dir,
            self.log_dir,
            self.root / "secrets",
        ):
            path.mkdir(parents=True, exist_ok=True)

    def gemini_models(self) -> list[str]:
        """Return the ordered Gemini model chain without duplicates.

        The stable default is 3.8 Flash with descending Flash fallbacks.  An
        explicit GEMINI_MODEL outside that chain stays pinned unless
        GEMINI_FALLBACK_MODELS is also configured, preserving deterministic
        custom/test model behavior.
        """
        primary = str(self.gemini_model or "").strip()
        raw_fallbacks = os.getenv("GEMINI_FALLBACK_MODELS", "").strip()
        if raw_fallbacks:
            fallbacks = [
                item.strip()
                for item in raw_fallbacks.replace("\n", ",").split(",")
                if item.strip()
            ]
        elif primary in DEFAULT_GEMINI_MODEL_CHAIN:
            index = DEFAULT_GEMINI_MODEL_CHAIN.index(primary)
            fallbacks = list(DEFAULT_GEMINI_MODEL_CHAIN[index + 1 :])
        else:
            fallbacks = []
        result: list[str] = []
        for value in [primary, *fallbacks]:
            if value and value not in result:
                result.append(value)
        return result

    @property
    def gemini_key_file(self) -> Path:
        return self.root / "secrets" / "gemini_api_key.txt"

    def gemini_keys(self) -> list[str]:
        """Return all configured Gemini keys without exposing duplicates.

        Environment keys stay first for backward compatibility. File keys are
        read one-per-line from the canonical secrets file and the legacy root
        file. Blank lines and comments are ignored.
        """
        values: list[str] = []
        env_value = os.getenv("GEMINI_API_KEY", "").strip()
        if env_value:
            values.extend(line.strip() for line in env_value.splitlines())
        for path in (
            self.gemini_key_file,
            self.root / "gemini_api_key.txt",  # backward-compatible local file
        ):
            if not path.exists():
                continue
            values.extend(path.read_text(encoding="utf-8-sig").splitlines())
        result: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = str(raw).strip()
            if not value or value.startswith("#") or value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def append_gemini_keys(self, values: list[str]) -> dict[str, int]:
        """Append new keys to the canonical secret file without replacing old ones."""
        normalized = [str(value).strip() for value in values if str(value).strip()]
        with _GEMINI_KEY_LOCK:
            existing = self.gemini_keys()
            known = set(existing)
            additions: list[str] = []
            duplicate_count = 0
            for value in normalized:
                if value in known:
                    duplicate_count += 1
                    continue
                known.add(value)
                additions.append(value)
            if additions:
                self.gemini_key_file.parent.mkdir(parents=True, exist_ok=True)
                needs_newline = self.gemini_key_file.exists() and self.gemini_key_file.stat().st_size > 0
                if needs_newline:
                    with self.gemini_key_file.open("rb") as handle:
                        handle.seek(-1, os.SEEK_END)
                        needs_newline = handle.read(1) not in {b"\n", b"\r"}
                with self.gemini_key_file.open("a", encoding="utf-8", newline="\n") as handle:
                    if needs_newline:
                        handle.write("\n")
                    handle.write("\n".join(additions))
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            return {
                "submitted_count": len(normalized),
                "added_count": len(additions),
                "duplicate_count": duplicate_count,
                "total_count": len(self.gemini_keys()),
            }

    def gemini_key(self) -> str | None:
        """Return the next configured Gemini key using a process-local round robin."""
        global _GEMINI_KEY_CURSOR
        keys = self.gemini_keys()
        if not keys:
            return None
        with _GEMINI_KEY_LOCK:
            index = _GEMINI_KEY_CURSOR % len(keys)
            _GEMINI_KEY_CURSOR = (_GEMINI_KEY_CURSOR + 1) % len(keys)
            return keys[index]

settings = Settings()
