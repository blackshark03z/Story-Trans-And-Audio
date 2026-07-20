from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, TYPE_CHECKING

from .config import Settings
from .files import atomic_write_json, sha256_file, sha256_text

if TYPE_CHECKING:
    from .custom_voice import CustomVoiceRepository
    from .storage import ContentStore


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
    def __init__(
        self,
        tts: PreviewTts,
        config: Settings,
        *,
        custom_voice_repo: "CustomVoiceRepository | None" = None,
        store: "ContentStore | None" = None,
    ) -> None:
        self.tts = tts
        self.config = config
        self.custom_voice_repo = custom_voice_repo
        self.store = store
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

    def _custom_identity(
        self,
        custom_voice_id: int,
        custom_voice_revision_id: int,
        reference_audio_sha256: str,
        reference_transcript_sha256: str,
        preview_text: str,
    ) -> dict[str, Any]:
        text_sha256 = sha256_text(preview_text)
        settings_hash = sha256_text(
            json.dumps(self._settings(), sort_keys=True, separators=(",", ":"))
        )
        engine_version = f"vieneu:{self.config.tts_mode}"
        cache_key = sha256_text(
            json.dumps(
                {
                    "custom_voice_id": custom_voice_id,
                    "custom_voice_revision_id": custom_voice_revision_id,
                    "reference_audio_sha256": reference_audio_sha256,
                    "reference_transcript_sha256": reference_transcript_sha256,
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
            "custom_voice_id": custom_voice_id,
            "custom_voice_revision_id": custom_voice_revision_id,
            "reference_audio_sha256": reference_audio_sha256,
            "reference_transcript_sha256": reference_transcript_sha256,
            "preview_text_sha256": text_sha256,
            "preview_text": preview_text,
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
            # Preset preview uses fixed PREVIEW_TEXT designed for 10-20s range
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
        response = {
            "cache_key": manifest["cache_key"],
            "duration_ms": manifest["duration_ms"],
            "sample_rate": manifest["sample_rate"],
            "cache_hit": cache_hit,
            "preview_text": manifest.get("preview_text", PREVIEW_TEXT),
        }
        # Add voice_id for preset, custom_voice_revision_id for custom
        if "voice_id" in manifest:
            response["voice_id"] = manifest["voice_id"]
        if "custom_voice_revision_id" in manifest:
            response["custom_voice_revision_id"] = manifest["custom_voice_revision_id"]
        if "custom_voice_id" in manifest:
            response["custom_voice_id"] = manifest["custom_voice_id"]
        return response

    def create_custom(self, custom_voice_revision_id: int, preview_text: str | None = None) -> dict[str, Any]:
        """
        Create a preview for a custom voice revision.
        Requires custom_voice_repo and store to be injected at construction.

        Args:
            custom_voice_revision_id: The ID of the custom voice revision to preview
            preview_text: Optional text to synthesize. If None/empty/whitespace, uses PREVIEW_TEXT constant.
        """
        # Dependency validation
        if self.custom_voice_repo is None or self.store is None:
            raise RuntimeError(
                "Custom voice preview requires CustomVoiceRepository and ContentStore dependencies"
            )

        # Import here to avoid circular imports
        from .custom_voice import CustomVoiceRevisionNotFoundError
        from .synthesis_snapshot import StorageResolutionError

        # Validate revision ID
        if not isinstance(custom_voice_revision_id, int) or custom_voice_revision_id <= 0:
            raise ValueError("custom_voice_revision_id must be a positive integer")

        # Fetch the exact revision
        try:
            revision = self.custom_voice_repo.get_revision(custom_voice_revision_id)
        except CustomVoiceRevisionNotFoundError:
            raise

        # Validate required metadata
        if not revision.audio_storage_key or not revision.audio_storage_key.strip():
            raise ValueError("Revision has invalid audio_storage_key")
        if not revision.audio_sha256 or len(revision.audio_sha256) != 64:
            raise ValueError("Revision has invalid audio_sha256")
        if not revision.reference_transcript or not revision.reference_transcript.strip():
            raise ValueError("Revision has empty reference_transcript")
        if not revision.transcript_sha256 or len(revision.transcript_sha256) != 64:
            raise ValueError("Revision has invalid transcript_sha256")

        # Compute effective preview text (trim and use default if empty)
        effective_text = (preview_text or "").strip()
        if not effective_text:
            effective_text = PREVIEW_TEXT

        # Build identity with effective preview text
        identity = self._custom_identity(
            revision.custom_voice_id,
            revision.id,
            revision.audio_sha256,
            revision.transcript_sha256,
            effective_text,
        )

        wav_path, manifest_path = self._paths(identity["cache_key"])
        self.config.preview_cache_dir.mkdir(parents=True, exist_ok=True)

        with self._lock:
            self.cleanup()

            # Try cache hit
            cached = self._load_valid(identity)
            if cached:
                os.utime(wav_path, None)
                os.utime(manifest_path, None)
                return self._response(cached, cache_hit=True)

            # Cache miss - prepare for synthesis
            wav_path.unlink(missing_ok=True)
            manifest_path.unlink(missing_ok=True)

            # Resolve and verify source audio
            try:
                reference_audio_path = self.store.absolute(revision.audio_storage_key)
            except ValueError as exc:
                raise StorageResolutionError(f"Invalid storage key: {exc}") from exc

            if not reference_audio_path.exists():
                raise StorageResolutionError(
                    f"Reference audio does not exist: {revision.audio_storage_key}"
                )
            if not reference_audio_path.is_file():
                raise StorageResolutionError(
                    f"Reference audio is not a regular file: {revision.audio_storage_key}"
                )

            # Verify reference audio integrity
            audio_sha_computed = sha256_file(reference_audio_path)
            if audio_sha_computed != revision.audio_sha256:
                raise StorageResolutionError(
                    f"Reference audio SHA-256 mismatch: expected {revision.audio_sha256}, "
                    f"got {audio_sha_computed}"
                )

            # Verify transcript integrity
            transcript_sha_computed = sha256_text(revision.reference_transcript)
            if transcript_sha_computed != revision.transcript_sha256:
                raise ValueError(
                    f"Reference transcript SHA-256 mismatch: expected {revision.transcript_sha256}, "
                    f"got {transcript_sha_computed}"
                )

            # Call TTS with custom reference and effective preview text
            try:
                duration_ms, sample_rate = self.tts.synthesize(
                    text=effective_text,
                    reference_audio_path=reference_audio_path,
                    reference_transcript=revision.reference_transcript,
                    output_path=wav_path,
                    **self._settings(),
                )
            except Exception:
                # Clean up on synthesis failure
                wav_path.unlink(missing_ok=True)
                manifest_path.unlink(missing_ok=True)
                raise

            # Validate output
            if not wav_path.is_file() or wav_path.stat().st_size <= 0:
                wav_path.unlink(missing_ok=True)
                manifest_path.unlink(missing_ok=True)
                raise ValueError("TTS preview did not produce a valid WAV file")

            # Custom preview: allow valid short audio, enforce only maximum duration
            if duration_ms <= 0:
                wav_path.unlink(missing_ok=True)
                manifest_path.unlink(missing_ok=True)
                raise ValueError(
                    f"Voice preview duration must be greater than zero, got {duration_ms / 1000:.1f}"
                )

            if duration_ms > MAX_PREVIEW_DURATION_MS:
                wav_path.unlink(missing_ok=True)
                manifest_path.unlink(missing_ok=True)
                raise ValueError(
                    f"Voice preview duration must not exceed {MAX_PREVIEW_DURATION_MS / 1000:.1f} seconds, got {duration_ms / 1000:.1f}"
                )

            # Write manifest
            now = datetime.now(timezone.utc).isoformat()
            manifest: dict[str, Any] = {
                **identity,
                "audio_sha256": sha256_file(wav_path),
                "size_bytes": wav_path.stat().st_size,
                "duration_ms": duration_ms,
                "sample_rate": sample_rate,
                "created_at": now,
            }

            try:
                atomic_write_json(manifest_path, manifest)
            except Exception:
                wav_path.unlink(missing_ok=True)
                manifest_path.unlink(missing_ok=True)
                raise

            return self._response(manifest, cache_hit=False)

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
        if "custom_voice_revision_id" in manifest and "custom_voice_id" not in manifest:
            raise FileNotFoundError("Preview provenance is incomplete")
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
