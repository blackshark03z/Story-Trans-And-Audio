from __future__ import annotations

import threading
from pathlib import Path
from typing import Any


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
        text: str,
        voice: str,
        temperature: float,
        top_k: int,
        max_chars: int,
        silence_seconds: float,
        output_path: Path,
    ) -> tuple[int, int]:
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
        sf.write(str(partial), audio, engine.sample_rate, subtype="PCM_16", format="WAV")
        info = sf.info(str(partial))
        if info.frames <= 0 or info.duration <= 0:
            partial.unlink(missing_ok=True)
            raise ValueError("WAV segment không hợp lệ.")
        partial.replace(output_path)
        return int(round(info.duration * 1000)), int(engine.sample_rate)


tts_service = TtsService()
