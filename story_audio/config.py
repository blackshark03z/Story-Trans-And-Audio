from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def canonical_production_db_path() -> Path:
    """Return the canonical production database path.
    
    This is the single source of truth for what constitutes the live production DB.
    Any code attempting to initialize or migrate this path must have explicit opt-in.
    """
    return ROOT / "data" / "app.db"

@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    data_dir: Path = ROOT / "data"
    db_path: Path = ROOT / "data" / "app.db"
    blobs_dir: Path = ROOT / "data" / "blobs"
    output_dir: Path = ROOT / "data" / "output"
    work_dir: Path = ROOT / "data" / "work"
    log_dir: Path = ROOT / "logs"
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
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
            self.preview_cache_dir,
            self.gemini_cache_dir,
            self.youtube_export_dir,
            self.log_dir,
            self.root / "secrets",
        ):
            path.mkdir(parents=True, exist_ok=True)

    def gemini_key(self) -> str | None:
        value = os.getenv("GEMINI_API_KEY", "").strip()
        if value:
            return value
        candidates = (
            self.root / "secrets" / "gemini_api_key.txt",
            self.root / "gemini_api_key.txt",  # backward-compatible local file
        )
        for path in candidates:
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                value = line.strip()
                if value and not value.startswith("#"):
                    return value
        return None

settings = Settings()
