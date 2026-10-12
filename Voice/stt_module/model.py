from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    language: str
    language_probability: float
    segments: tuple


class LocalTranscriber:
    """Lazy faster-whisper recognizer; CPU/int8 is the shared-work default."""

    def __init__(self, model_size="base", device="cpu", language=None, cpu_threads=2,
                 beam_size=1, vad_filter=False):
        if device not in ("auto", "cpu", "cuda"):
            raise ValueError("device must be auto, cpu, or cuda")
        if cpu_threads < 1 or beam_size < 1:
            raise ValueError("cpu_threads and beam_size must be positive")
        self.model_size, self.requested_device = model_size, device
        self.language, self.cpu_threads, self.beam_size = language, cpu_threads, beam_size
        self.vad_filter = vad_filter
        self._model = None
        self.device = self.compute_type = None

    def _load(self):
        if self._model is not None:
            return
        from faster_whisper import WhisperModel
        choices = [("cuda", "int8"), ("cpu", "int8")] if self.requested_device == "auto" else [
            (self.requested_device, "int8")]
        errors = []
        for device, precision in choices:
            try:
                self._model = WhisperModel(
                    self.model_size, device=device, compute_type=precision,
                    cpu_threads=self.cpu_threads if device == "cpu" else 0, num_workers=1,
                )
                self.device, self.compute_type = device, precision
                return
            except Exception as exc:
                errors.append(f"{device}/{precision}: {exc}")
                if self.requested_device != "auto":
                    raise RuntimeError(errors[-1]) from exc
                log.warning("%s backend unavailable; trying fallback", device)
        raise RuntimeError("Unable to initialize faster-whisper: " + "; ".join(errors))

    def _decode(self, audio):
        self._load()
        pieces, info = self._model.transcribe(
            audio, language=self.language, beam_size=self.beam_size,
            vad_filter=self.vad_filter, condition_on_previous_text=False,
        )
        segments = tuple(pieces)
        return Transcript(" ".join(s.text.strip() for s in segments).strip(),
                          info.language, info.language_probability, segments)

    def transcribe_file(self, path):
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(path)
        return self._decode(str(path))

    def transcribe_audio(self, audio: np.ndarray, sample_rate=16000):
        import numpy as np
        if sample_rate != 16000:
            raise ValueError("audio must be mono float32 PCM at 16 kHz")
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        if not samples.size:
            raise ValueError("audio is empty")
        return self._decode(samples)

    def transcribe_stream(self, chunks: Iterable[np.ndarray], sample_rate=16000,
                          chunk_seconds=4.0) -> Iterator[Transcript]:
        """Decode sequential windows from mono 16 kHz audio chunks."""
        import numpy as np
        if sample_rate != 16000 or chunk_seconds <= 0:
            raise ValueError("use 16 kHz audio and positive chunk_seconds")
        window = np.empty(0, dtype=np.float32)
        width = int(sample_rate * chunk_seconds)
        for chunk in chunks:
            data = np.asarray(chunk, dtype=np.float32).reshape(-1)
            if data.size:
                window = np.concatenate((window, data))
            while window.size >= width:
                current, window = window[:width], window[width:]
                yield self.transcribe_audio(current)
        if window.size:
            yield self.transcribe_audio(window)
