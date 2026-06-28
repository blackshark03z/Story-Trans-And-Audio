from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from .synthesis_snapshot import SegmentSynthesisInput


class TtsService:
    def __init__(self) -> None:
        self._engine: Any = None
        self._lock = threading.RLock()
        self.status = "not_loaded"
        self.error: str | None = None

    def ensure_loaded(self) -> Any:
        with self._lock:
            if self._engine is not None:
                return self._engine
            self.status = "loading"
            self.error = None
            try:
                from vieneu import Vieneu

                self._engine = Vieneu(mode="v3turbo")
                self.status = "ready"
                return self._engine
            except Exception as exc:
                self.status = "error"
                self.error = str(exc)
                raise

    def voices(self) -> list[dict[str, str]]:
        engine = self.ensure_loaded()
        with self._lock:
            values = engine.list_preset_voices()
        return [{"label": str(label), "id": str(voice_id)} for label, voice_id in values]

    def synthesize(
        self,
        *,
        synth_input: SegmentSynthesisInput | None = None,
        output_path: Path,
        # Legacy parameters (temporary, Phase 3B3-D will remove)
        text: str | None = None,
        voice: str | None = None,
        reference_audio_path: Path | None = None,
        reference_transcript: str | None = None,
        temperature: float | None = None,
        top_k: int | None = None,
        max_chars: int | None = None,
        silence_seconds: float | None = None,
    ) -> tuple[int, int]:
        """
        Synthesize audio from snapshot or legacy parameters.

        Snapshot path (Phase 3B3-C):
            synth_input: SegmentSynthesisInput with validated fields
            output_path: Final WAV destination

        Legacy preset path (temporary, Phase 3B3-D will remove):
            text, voice, temperature, top_k, max_chars, silence_seconds
            output_path: Final WAV destination

        Legacy custom-reference path (temporary, Phase 4B custom preview):
            text, reference_audio_path, reference_transcript, temperature, top_k, max_chars, silence_seconds
            output_path: Final WAV destination

        Returns:
            (duration_ms, sample_rate)

        Raises:
            ValueError: Mixed arguments, incomplete arguments, validation failures
        """
        import numpy as np
        import soundfile as sf

        # Argument routing validation
        snapshot_provided = synth_input is not None
        legacy_provided = any(
            arg is not None
            for arg in [text, voice, reference_audio_path, reference_transcript,
                       temperature, top_k, max_chars, silence_seconds]
        )

        if snapshot_provided and legacy_provided:
            raise ValueError("Cannot mix synth_input with legacy parameters")

        if not snapshot_provided and not legacy_provided:
            raise ValueError("Must provide either synth_input or complete legacy parameters")

        # Route to appropriate path
        if snapshot_provided:
            return self._synthesize_from_snapshot(synth_input, output_path)
        else:
            # Legacy path subdivides into preset vs custom-reference
            preset_provided = voice is not None
            custom_provided = reference_audio_path is not None or reference_transcript is not None

            if preset_provided and custom_provided:
                raise ValueError("Cannot mix preset voice with custom reference parameters")

            if not preset_provided and not custom_provided:
                raise ValueError("Must provide either voice (preset) or reference_audio_path+reference_transcript (custom)")

            # Validate complete parameter sets
            if preset_provided:
                if any(
                    arg is None
                    for arg in [text, voice, temperature, top_k, max_chars, silence_seconds]
                ):
                    raise ValueError("Incomplete preset legacy parameters")
                return self._synthesize_legacy(
                    text=text,
                    voice=voice,
                    temperature=temperature,
                    top_k=top_k,
                    max_chars=max_chars,
                    silence_seconds=silence_seconds,
                    output_path=output_path,
                )
            else:
                # Custom-reference path
                if reference_audio_path is None or reference_transcript is None:
                    raise ValueError("Custom reference requires both reference_audio_path and reference_transcript")
                if any(
                    arg is None
                    for arg in [text, temperature, top_k, max_chars, silence_seconds]
                ):
                    raise ValueError("Incomplete custom reference legacy parameters")
                return self._synthesize_legacy_custom_reference(
                    text=text,
                    reference_audio_path=reference_audio_path,
                    reference_transcript=reference_transcript,
                    temperature=temperature,
                    top_k=top_k,
                    max_chars=max_chars,
                    silence_seconds=silence_seconds,
                    output_path=output_path,
                )

    def _synthesize_from_snapshot(
        self,
        synth_input: SegmentSynthesisInput,
        output_path: Path,
    ) -> tuple[int, int]:
        """
        Snapshot-aware synthesis (Phase 3B3-C).
        Single source of truth for deterministic synthesis.
        """
        import numpy as np
        import soundfile as sf

        # Validate provider/model against service configuration
        if synth_input.voice_provider != "vieneu":
            raise ValueError(f"Unsupported provider: {synth_input.voice_provider}")
        if synth_input.voice_model != "v3turbo":
            raise ValueError(f"Unsupported model: {synth_input.voice_model}")

        # Validate dataclass consistency
        if synth_input.voice_source_type == "preset":
            if synth_input.preset_voice_id is None:
                raise ValueError("Preset snapshot missing preset_voice_id")
            if synth_input.custom_voice_revision_id is not None:
                raise ValueError("Preset snapshot has custom_voice_revision_id populated")
        elif synth_input.voice_source_type == "custom_reference":
            if synth_input.reference_audio_path is None:
                raise ValueError("Custom snapshot missing reference_audio_path")
            if synth_input.reference_transcript is None:
                raise ValueError("Custom snapshot missing reference_transcript")
            if synth_input.preset_voice_id is not None:
                raise ValueError("Custom snapshot has preset_voice_id populated")
        else:
            raise ValueError(f"Invalid voice_source_type: {synth_input.voice_source_type}")

        engine = self.ensure_loaded()

        # Engine inference under lock
        with self._lock:
            if synth_input.voice_source_type == "preset":
                audio = engine.infer(
                    synth_input.text,
                    voice=synth_input.preset_voice_id,
                    temperature=synth_input.settings.temperature,
                    top_k=synth_input.settings.top_k,
                    max_chars=synth_input.settings.max_chars,
                    silence_p=0.0,
                    crossfade_p=0.0,
                )
            else:  # custom_reference
                audio = engine.infer(
                    synth_input.text,
                    ref_audio=str(synth_input.reference_audio_path),
                    ref_text=synth_input.reference_transcript,
                    temperature=synth_input.settings.temperature,
                    top_k=synth_input.settings.top_k,
                    max_chars=synth_input.settings.max_chars,
                    silence_p=0.0,
                    crossfade_p=0.0,
                )

        # Output validation
        audio = np.asarray(audio, dtype=np.float32)
        if audio.size == 0 or not np.isfinite(audio).all():
            raise ValueError("VieNeu trả audio rỗng hoặc không hợp lệ.")

        # Append effective silence (deterministic segment position rule)
        effective_silence = synth_input.effective_silence_seconds()
        if effective_silence > 0:
            audio = np.concatenate(
                [audio, np.zeros(int(engine.sample_rate * effective_silence), dtype=np.float32)]
            )

        # Atomic write with partial file cleanup
        output_path.parent.mkdir(parents=True, exist_ok=True)
        partial = output_path.with_suffix(output_path.suffix + ".partial")
        try:
            sf.write(str(partial), audio, engine.sample_rate, subtype="PCM_16", format="WAV")
            info = sf.info(str(partial))
            if info.frames <= 0 or info.duration <= 0:
                raise ValueError("WAV segment không hợp lệ.")
            partial.replace(output_path)
        except Exception:
            partial.unlink(missing_ok=True)
            raise

        return int(round(info.duration * 1000)), int(engine.sample_rate)

    def _synthesize_legacy(
        self,
        *,
        text: str,
        voice: str,
        temperature: float,
        top_k: int,
        max_chars: int,
        silence_seconds: float,
        output_path: Path,
    ) -> tuple[int, int]:
        """
        Legacy synthesis path (temporary, Phase 3B3-D will remove).
        Preserved for backward compatibility during migration.
        """
        import numpy as np
        import soundfile as sf

        engine = self.ensure_loaded()
        with self._lock:
            audio = engine.infer(
                text,
                voice=voice,
                temperature=temperature,
                top_k=top_k,
                max_chars=max_chars,
                silence_p=0.0,
                crossfade_p=0.0,
            )
        audio = np.asarray(audio, dtype=np.float32)
        if audio.size == 0 or not np.isfinite(audio).all():
            raise ValueError("VieNeu trả audio rỗng hoặc không hợp lệ.")
        if silence_seconds > 0:
            audio = np.concatenate(
                [audio, np.zeros(int(engine.sample_rate * silence_seconds), dtype=np.float32)]
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        partial = output_path.with_suffix(output_path.suffix + ".partial")
        try:
            sf.write(str(partial), audio, engine.sample_rate, subtype="PCM_16", format="WAV")
            info = sf.info(str(partial))
            if info.frames <= 0 or info.duration <= 0:
                raise ValueError("WAV segment không hợp lệ.")
            partial.replace(output_path)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        return int(round(info.duration * 1000)), int(engine.sample_rate)

    def _synthesize_legacy_custom_reference(
        self,
        *,
        text: str,
        reference_audio_path: Path,
        reference_transcript: str,
        temperature: float,
        top_k: int,
        max_chars: int,
        silence_seconds: float,
        output_path: Path,
    ) -> tuple[int, int]:
        """
        Legacy custom-reference synthesis path (temporary, Phase 4B custom preview).
        Reuses Phase 3B snapshot custom-reference engine inference behavior.
        """
        import numpy as np
        import soundfile as sf

        engine = self.ensure_loaded()
        with self._lock:
            audio = engine.infer(
                text,
                ref_audio=str(reference_audio_path),
                ref_text=reference_transcript,
                temperature=temperature,
                top_k=top_k,
                max_chars=max_chars,
                silence_p=0.0,
                crossfade_p=0.0,
            )
        audio = np.asarray(audio, dtype=np.float32)
        if audio.size == 0 or not np.isfinite(audio).all():
            raise ValueError("VieNeu trả audio rỗng hoặc không hợp lệ.")
        if silence_seconds > 0:
            audio = np.concatenate(
                [audio, np.zeros(int(engine.sample_rate * silence_seconds), dtype=np.float32)]
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        partial = output_path.with_suffix(output_path.suffix + ".partial")
        try:
            sf.write(str(partial), audio, engine.sample_rate, subtype="PCM_16", format="WAV")
            info = sf.info(str(partial))
            if info.frames <= 0 or info.duration <= 0:
                raise ValueError("WAV segment không hợp lệ.")
            partial.replace(output_path)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        return int(round(info.duration * 1000)), int(engine.sample_rate)


tts_service = TtsService()
