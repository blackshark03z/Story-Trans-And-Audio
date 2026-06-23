from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .config import Settings
from .files import atomic_write_json, sha256_file, sha256_text


PREVIEW_TEXT = (
    "Ngoài hiên, mưa rơi rất khẽ. Người lữ khách dừng chân bên cửa sổ, "
    "nhìn ánh đèn trải dài trên con phố vắng. Anh hít một hơi chậm rãi rồi kể tiếp: "
    "mọi hành trình đều bắt đầu từ một lựa chọn nhỏ, nhưng đủ can đảm để đổi thay cả ngày mai."
)
MIN_PREVIEW_DURATION_MS = 10_000
MAX_PREVIEW_DURATION_MS = 20_000


class PreviewTts(Protocol):
    def synthesize(self, **kwargs: Any) -> tuple[int, int]: ...


class VoicePreviewService:
    def __init__(self, tts: PreviewTts, config: Settings):
        self.tts = tts
        self.config = config
        self._lock = threading.RLock()

    def _settings(self) -> dict[str, Any]:
        return {
            "temperature": self.config.tts_temperature,
            "top_k": self.config.tts_top_k,
            "max_chars": self.config.tts_max_chars,
            "silence_seconds": 0.0,
        }

    def _identity(self, voice_id: str) -> dict[str, str]:
        text_sha256 = sha256_text(PREVIEW_TEXT)
        settings_hash = sha256_text(
            json.dumps(self._settings(), sort_keys=True, separators=(",", ":"))
        )
        engine_version = f"vieneu:{self.config.tts_mode}"
        cache_key = sha256_text(
            json.dumps(
                {
                    "voice_id": voice_id,
                    "preview_text_sha256": text_sha256,
                    "settings_hash": settings_hash,
                    "engine_version": engine_version,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
        )
        return {
            "cache_key": cache_key,
            "voice_id": voice_id,
            "preview_text_sha256": text_sha256,
            "settings_hash": settings_hash,
            "engine_version": engine_version,
        }

    def _paths(self, cache_key: str) -> tuple[Path, Path]:
        root = self.config.preview_cache_dir
        return root / f"{cache_key}.wav", root / f"{cache_key}.json"

    def _load_valid(self, identity: dict[str, str]) -> dict[str, Any] | None:
        wav_path, manifest_path = self._paths(identity["cache_key"])
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        if any(manifest.get(key) != value for key, value in identity.items()):
            return None
        if not wav_path.is_file() or wav_path.stat().st_size <= 0:
            return None
        if manifest.get("audio_sha256") != sha256_file(wav_path):
            return None
        return manifest

    def create(self, voice_id: str) -> dict[str, Any]:
        voice_id = voice_id.strip()
        if not voice_id:
            raise ValueError("Voice ID is required")
        identity = self._identity(voice_id)
        wav_path, manifest_path = self._paths(identity["cache_key"])
        self.config.preview_cache_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.cleanup()
            cached = self._load_valid(identity)
            if cached:
                os.utime(wav_path, None)
                os.utime(manifest_path, None)
                return self._response(cached, cache_hit=True)

            wav_path.unlink(missing_ok=True)
            manifest_path.unlink(missing_ok=True)
            duration_ms, sample_rate = self.tts.synthesize(
                text=PREVIEW_TEXT,
                voice=voice_id,
                output_path=wav_path,
                **self._settings(),
            )
            if not wav_path.is_file() or wav_path.stat().st_size <= 0:
                raise ValueError("TTS preview did not produce a valid WAV file")
            if not MIN_PREVIEW_DURATION_MS <= duration_ms <= MAX_PREVIEW_DURATION_MS:
                wav_path.unlink(missing_ok=True)
                raise ValueError(
                    f"Voice preview duration must be 10–20 seconds, got {duration_ms / 1000:.1f}"
                )
            now = datetime.now(timezone.utc).isoformat()
            manifest: dict[str, Any] = {
                **identity,
                "audio_sha256": sha256_file(wav_path),
                "size_bytes": wav_path.stat().st_size,
                "duration_ms": duration_ms,
                "sample_rate": sample_rate,
                "created_at": now,
            }
            atomic_write_json(manifest_path, manifest)
            return self._response(manifest, cache_hit=False)

    def _response(self, manifest: dict[str, Any], *, cache_hit: bool) -> dict[str, Any]:
        return {
            "cache_key": manifest["cache_key"],
            "voice_id": manifest["voice_id"],
            "duration_ms": manifest["duration_ms"],
            "sample_rate": manifest["sample_rate"],
            "cache_hit": cache_hit,
            "preview_text": PREVIEW_TEXT,
        }

    def audio_path(self, cache_key: str) -> Path:
        if len(cache_key) != 64 or any(char not in "0123456789abcdef" for char in cache_key):
            raise ValueError("Invalid preview cache key")
        wav_path, manifest_path = self._paths(cache_key)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise FileNotFoundError("Preview not found") from exc
        if manifest.get("cache_key") != cache_key or not wav_path.is_file():
            raise FileNotFoundError("Preview not found")
        if manifest.get("audio_sha256") != sha256_file(wav_path):
            raise FileNotFoundError("Preview cache is corrupted")
        os.utime(wav_path, None)
        os.utime(manifest_path, None)
        return wav_path

    def cleanup(self) -> dict[str, int]:
        root = self.config.preview_cache_dir
        root.mkdir(parents=True, exist_ok=True)
        cutoff = datetime.now(timezone.utc).timestamp() - (
            self.config.preview_cache_retention_days * 86400
        )
        manifests = sorted(root.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        removed = 0
        for index, manifest_path in enumerate(manifests):
            expired = manifest_path.stat().st_mtime < cutoff
            over_limit = index >= self.config.preview_cache_max_entries
            if expired or over_limit:
                manifest_path.with_suffix(".wav").unlink(missing_ok=True)
                manifest_path.unlink(missing_ok=True)
                removed += 1
        known = {path.with_suffix(".wav") for path in root.glob("*.json")}
        for wav_path in root.glob("*.wav"):
            if wav_path not in known and wav_path.stat().st_mtime < cutoff:
                wav_path.unlink(missing_ok=True)
                removed += 1
        return {"removed": removed, "remaining": len(list(root.glob("*.json")))}
