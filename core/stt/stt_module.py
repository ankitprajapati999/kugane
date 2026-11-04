# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║            KUGANE — Continuous Real-Time STT Engine (stt_module.py)         ║
║         faster-whisper · CUDA/int8 · sounddevice · VAD · colorama           ║
╚══════════════════════════════════════════════════════════════════════════════╝

Architecture:
  ┌─────────────────────────────────────────────────────────────────────────┐
  │  Microphone (sounddevice InputStream)                                   │
  │        ↓  (callback — non-blocking, PortAudio thread)                   │
  │  Thread-safe audio_queue (queue.Queue, bounded 80 blocks)               │
  │        ↓  (main consumer thread)                                        │
  │  VAD Gate  →  RMS energy check  →  accumulate phrase buffer             │
  │        ↓  (silence window ≥ 1.2 s detected)                             │
  │  faster-whisper CUDA/int8 inference on accumulated phrase chunk         │
  │        ↓                                                                │
  │  colorama stdout  →  "[Kugane STT Log]: <text>"                         │
  │        ↓  (future integration)                                          │
  │  Callback / WebSocket  →  LLM server  →  edge-tts speaker output        │
  └─────────────────────────────────────────────────────────────────────────┘

Target hardware:
  CPU : AMD Ryzen 5 7235HS (4 Cores / 8 Threads)
  GPU : NVIDIA RTX 3050A — 4 GB VRAM  (VRAM target < 300 MB for base model)
  RAM : 24 GB DDR5

Usage (standalone):
    uv run python Voice/stt_module/stt_module.py

    # Optional flags
    --device      cuda | cpu | auto   (default: cuda)
    --language    en | hi | ...       (default: auto-detect)
    --threshold   0.01                (RMS silence gate, lower = more sensitive)
    --silence     1.2                 (seconds of silence that closes a phrase)
    --input-device N                  (sounddevice device index)
    --list-devices                    (print device list and exit)

Designed to be imported and driven programmatically:
    from stt_module import KuganeSTTEngine
    engine = KuganeSTTEngine(on_transcript=my_callback)
    engine.start()
    ...
    engine.stop()
"""

from __future__ import annotations

import argparse
import queue
import sys
import threading
from typing import Callable, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Optional import guard — give a clean error before anything else runs
# ─────────────────────────────────────────────────────────────────────────────
try:
    import numpy as np
except ImportError:
    sys.exit("[Kugane FATAL] numpy is required: uv add numpy")

try:
    import sounddevice as sd
except ImportError:
    sys.exit("[Kugane FATAL] sounddevice is required: uv add sounddevice")

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    _HAS_COLORAMA = True
except ImportError:
    _HAS_COLORAMA = False


# ─────────────────────────────────────────────────────────────────────────────
# Internal logging helpers
# ─────────────────────────────────────────────────────────────────────────────

def _clr(color_code: str, text: str) -> str:
    """Wrap text in a colorama color if available, else return plain text."""
    if _HAS_COLORAMA:
        return f"{color_code}{text}{Style.RESET_ALL}"
    return text


def _log_info(msg: str) -> None:
    tag = _clr(Fore.CYAN, "[Kugane INFO ]") if _HAS_COLORAMA else "[Kugane INFO ]"
    print(f"{tag} {msg}", flush=True)


def _log_warn(msg: str) -> None:
    tag = _clr(Fore.YELLOW, "[Kugane WARN ]") if _HAS_COLORAMA else "[Kugane WARN ]"
    print(f"{tag} {msg}", file=sys.stderr, flush=True)


def _log_error(msg: str) -> None:
    tag = _clr(Fore.RED, "[Kugane ERROR]") if _HAS_COLORAMA else "[Kugane ERROR]"
    print(f"{tag} {msg}", file=sys.stderr, flush=True)


def _log_transcript(text: str) -> None:
    """
    Primary output surface — called once per recognised phrase.
    Format contract: "[Kugane STT Log]: <text>"
    Future: replace/augment with WebSocket push to LLM server.
    """
    if _HAS_COLORAMA:
        prefix = Fore.GREEN + Style.BRIGHT + "[Kugane STT Log]:" + Style.RESET_ALL
        body = Fore.WHITE + Style.BRIGHT + f" {text}" + Style.RESET_ALL
    else:
        prefix = "[Kugane STT Log]:"
        body = f" {text}"
    print(f"{prefix}{body}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_RATE: int = 16_000
CHANNELS: int = 1
DTYPE: str = "float32"
BLOCK_DURATION: float = 0.10          # seconds per PortAudio callback block
BLOCK_SAMPLES: int = int(SAMPLE_RATE * BLOCK_DURATION)  # 1 600 samples/block

QUEUE_MAX: int = 80   # 8 seconds of audio before oldest block is dropped

DEFAULT_RMS_THRESHOLD: float = 0.01   # Energy gate for voice vs silence
DEFAULT_SILENCE_SECONDS: float = 1.2  # Consecutive silence → phrase boundary

MIN_PHRASE_SECONDS: float = 0.4       # Discard shorter phrases (clicks/coughs)
MIN_PHRASE_SAMPLES: int = int(SAMPLE_RATE * MIN_PHRASE_SECONDS)


# ─────────────────────────────────────────────────────────────────────────────
# KuganeSTTEngine
# ─────────────────────────────────────────────────────────────────────────────

class KuganeSTTEngine:
    """
    Continuous, real-time speech-to-text engine for the Kugane assistant.

    Parameters
    ----------
    device : str
        Inference backend — "cuda" (RTX 3050A), "cpu", or "auto".
    compute_type : str
        Quantisation — "int8" keeps VRAM under 300 MB on the base model.
    model_size : str
        faster-whisper model tier — "base" recommended for RTX 3050A balance.
    language : str | None
        ISO-639-1 language code ("en", "hi", ...). None = auto-detect.
    rms_threshold : float
        RMS energy below which a block is considered silence.
    silence_seconds : float
        Continuous silence (seconds) that closes and transcribes a phrase.
    input_device : int | None
        sounddevice device index. None = system default microphone.
    on_transcript : Callable[[str], None] | None
        Optional callback invoked with every recognised phrase string.
        Defaults to printing with the "[Kugane STT Log]:" format.
    """

    def __init__(
        self,
        device: str = "auto",          # "auto" → try CUDA, fall back to CPU
        compute_type: str = "int8",
        model_size: str = "base",
        language: Optional[str] = None,
        rms_threshold: float = DEFAULT_RMS_THRESHOLD,
        silence_seconds: float = DEFAULT_SILENCE_SECONDS,
        input_device: Optional[int] = None,
        on_transcript: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.device = device
        self.compute_type = compute_type
        self.model_size = model_size
        self.language = language
        self.rms_threshold = rms_threshold
        self.silence_samples: int = int(SAMPLE_RATE * silence_seconds)
        self.input_device = input_device
        self.on_transcript = on_transcript or _log_transcript

        # Tracks which device the model is actually running on after load/fallback
        self._active_device: str = "cpu"

        # Thread-safe bounded audio queue
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=QUEUE_MAX)

        # Phrase accumulation state
        self._phrase_buffer: list[np.ndarray] = []
        self._silent_samples: int = 0
        self._is_speaking: bool = False
        self._dropped_blocks: int = 0

        # Lifecycle control
        self._stop_event = threading.Event()
        self._model = None  # Lazy-loaded on first transcription call

        # Dedicated background inference thread
        self._inference_thread: Optional[threading.Thread] = None
        self._inference_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=8)

    # ──────────────────────────────────────────────────────────────────────────
    # Model initialisation (lazy, called from inference worker thread)
    # ──────────────────────────────────────────────────────────────────────────

    # DLL / driver error substrings that indicate CUDA runtime is broken
    _CUDA_DLL_ERRORS = (
        "cublas64_12.dll",
        "cublasLt64_12.dll",
        "cudart64_12.dll",
        "cudnn",
        "cannot be loaded",
        "not found",
        "CUDA error",
    )

    def _load_model(self, force_cpu: bool = False) -> None:
        """
        Load faster-whisper WhisperModel.

        Strategy:
          "cuda"  → try CUDA; if CUDA DLL missing, warn and fall back to CPU.
          "auto"  → try CUDA first, then CPU (same as above).
          "cpu"   → CPU only, no fallback attempt.

        Tracks the actually-used device in self._active_device.
        """
        if self._model is not None and not force_cpu:
            return

        _log_info(
            f"Loading faster-whisper [{self.model_size}] "
            f"device={self.device} compute={self.compute_type} ..."
        )

        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError:
            sys.exit(
                "[Kugane FATAL] faster-whisper not installed. "
                "Run: uv add faster-whisper"
            )

        # Build candidate list: always put CPU as the final safety net
        if self.device == "cpu" or force_cpu:
            candidates = [("cpu", "int8")]
        else:
            # "cuda" or "auto" — probe CUDA first, CPU as fallback
            candidates = [("cuda", "int8"), ("cpu", "int8")]

        last_exc: Optional[Exception] = None
        for dev, ctype in candidates:
            try:
                model = WhisperModel(
                    self.model_size,
                    device=dev,
                    compute_type=ctype,
                    num_workers=1,
                    cpu_threads=4 if dev == "cpu" else 0,
                )
                self._model = model
                self._active_device = dev
                _log_info(_clr(Fore.GREEN if _HAS_COLORAMA else "",
                               f"Model ready — {dev.upper()}/{ctype}"))
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                _log_warn(f"{dev}/{ctype} failed: {exc}")

        raise RuntimeError(
            f"Could not initialise faster-whisper. Last error: {last_exc}"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # PortAudio callback (runs in C-level PortAudio thread — must be fast)
    # ──────────────────────────────────────────────────────────────────────────

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: "sd.CallbackFlags",
    ) -> None:
        """
        Non-blocking PortAudio callback. Copies the audio block and enqueues it.
        Never calls inference, I/O, or blocking primitives here.
        """
        # Extract mono channel; indata is read-only view from PortAudio
        block: np.ndarray = indata[:, 0].copy()

        try:
            self._audio_queue.put_nowait(block)
        except queue.Full:
            # Queue saturated — drop the oldest block to preserve real-time capture
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                pass
            self._dropped_blocks += 1
            try:
                self._audio_queue.put_nowait(block)
            except queue.Full:
                pass  # Discard if still full (extremely rare)

    # ──────────────────────────────────────────────────────────────────────────
    # VAD — vectorised RMS energy gate
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _rms(block: np.ndarray) -> float:
        """
        Root-Mean-Square energy of a float32 audio block.
        Fully vectorised NumPy op — avoids Python-level loops.
        """
        return float(np.sqrt(np.mean(np.square(block))))

    # ──────────────────────────────────────────────────────────────────────────
    # Background inference worker thread
    # ──────────────────────────────────────────────────────────────────────────

    def _inference_worker(self) -> None:
        """
        Daemon thread that consumes phrase audio chunks from _inference_queue
        and runs faster-whisper GPU inference without blocking the audio loop.
        """
        while not self._stop_event.is_set():
            try:
                phrase_audio = self._inference_queue.get(timeout=0.3)
            except queue.Empty:
                continue

            try:
                self._transcribe_and_emit(phrase_audio)
            except Exception as exc:  # noqa: BLE001
                _log_error(f"Inference error: {exc}")
            finally:
                self._inference_queue.task_done()

    def _transcribe_and_emit(self, audio: np.ndarray) -> None:
        """
        Run faster-whisper on a single phrase chunk and emit the transcript.

        If the CUDA runtime DLLs are missing (cublas64_12.dll etc.), the model
        can load successfully but fail during the first inference call.  We
        detect that pattern here, tear down the broken CUDA model, and
        transparently reload on CPU so the session continues without user
        intervention.
        """
        self._load_model()

        try:
            segments, _info = self._model.transcribe(
                audio,
                language=self.language,
                beam_size=1,
                best_of=1,
                vad_filter=False,
                condition_on_previous_text=False,
                without_timestamps=True,
            )
            text_parts: list[str] = []
            for seg in segments:
                part = seg.text.strip()
                if part:
                    text_parts.append(part)

        except Exception as exc:
            exc_msg = str(exc)
            # Check if this is a CUDA DLL / runtime error that we can recover from
            is_cuda_dll_err = any(hint in exc_msg for hint in self._CUDA_DLL_ERRORS)

            if is_cuda_dll_err and self._active_device == "cuda":
                _log_warn(
                    "CUDA runtime DLL missing at inference time — "
                    f"({exc_msg.strip()})"
                )
                _log_warn(
                    "Tip: Install CUDA Toolkit 12 from https://developer.nvidia.com/cuda-downloads"
                )
                _log_info("Falling back to CPU inference for this session ...")
                # Destroy broken CUDA model to free VRAM reference
                self._model = None
                self._active_device = "cpu"
                # Force-reload on CPU
                self._load_model(force_cpu=True)
                # Retry the phrase on CPU
                segments, _info = self._model.transcribe(
                    audio,
                    language=self.language,
                    beam_size=1,
                    best_of=1,
                    vad_filter=False,
                    condition_on_previous_text=False,
                    without_timestamps=True,
                )
                text_parts = [seg.text.strip() for seg in segments if seg.text.strip()]
            else:
                raise  # Re-raise non-CUDA errors to the worker's except handler

        full_text = " ".join(text_parts).strip()
        if full_text:
            self.on_transcript(full_text)

    # ──────────────────────────────────────────────────────────────────────────
    # Main VAD / phrase accumulation loop (runs in the calling thread)
    # ──────────────────────────────────────────────────────────────────────────

    def _process_loop(self) -> None:
        """
        Reads audio blocks from _audio_queue, applies the VAD energy gate,
        accumulates phrase buffers, and dispatches complete phrases to
        _inference_queue when the silence window is exceeded.
        """
        _log_info("VAD processor active. Listening for speech ...")
        last_drop_report = 0

        while not self._stop_event.is_set():
            # ── Consume block ──────────────────────────────────────────────
            try:
                block: np.ndarray = self._audio_queue.get(timeout=0.3)
            except queue.Empty:
                continue

            # ── Report audio backlog ───────────────────────────────────────
            if self._dropped_blocks != last_drop_report:
                _log_warn(
                    f"Audio backlog: dropped "
                    f"{self._dropped_blocks - last_drop_report} block(s). "
                    "Reduce system CPU load."
                )
                last_drop_report = self._dropped_blocks

            # ── VAD: RMS energy gate ───────────────────────────────────────
            is_voice = self._rms(block) >= self.rms_threshold

            if is_voice:
                self._phrase_buffer.append(block)
                self._silent_samples = 0
                self._is_speaking = True
            else:
                if self._is_speaking:
                    # Include trailing silence as phrase context
                    self._phrase_buffer.append(block)
                    self._silent_samples += len(block)

                    if self._silent_samples >= self.silence_samples:
                        self._flush_phrase()

    def _flush_phrase(self) -> None:
        """
        Phrase boundary reached.
        Concatenates buffer → validates length → submits to inference queue.
        Buffer is cleared IMMEDIATELY after concatenation to free RAM.
        """
        if not self._phrase_buffer:
            self._reset_phrase_state()
            return

        phrase_audio: np.ndarray = np.concatenate(self._phrase_buffer, axis=0)
        self._reset_phrase_state()  # Free buffer memory before inference

        if phrase_audio.size < MIN_PHRASE_SAMPLES:
            return  # Too short to be meaningful speech

        try:
            self._inference_queue.put_nowait(phrase_audio)
        except queue.Full:
            _log_warn("Inference queue full — phrase dropped. GPU may be overloaded.")

    def _reset_phrase_state(self) -> None:
        """Zero out all phrase accumulation state."""
        self._phrase_buffer = []   # Dereference numpy arrays → GC reclaims
        self._silent_samples = 0
        self._is_speaking = False

    # ──────────────────────────────────────────────────────────────────────────
    # Public control API
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """
        Open the microphone stream and begin continuous transcription.
        Blocks the calling thread in the VAD processing loop until stop()
        is called or a KeyboardInterrupt is received.
        """
        _log_info(
            _clr(Fore.MAGENTA if _HAS_COLORAMA else "",
                 "Kugane STT Engine starting ...")
        )
        _log_info(
            f"model={self.model_size} | device={self.device} | "
            f"compute={self.compute_type} | "
            f"rms_threshold={self.rms_threshold:.4f} | "
            f"silence_window={self.silence_samples / SAMPLE_RATE:.2f}s"
        )

        self._stop_event.clear()

        # Launch inference worker as a daemon thread
        self._inference_thread = threading.Thread(
            target=self._inference_worker,
            name="kugane-inference",
            daemon=True,
        )
        self._inference_thread.start()

        try:
            with sd.InputStream(
                device=self.input_device,
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                blocksize=BLOCK_SAMPLES,
                callback=self._audio_callback,
            ):
                _log_info(
                    _clr(Fore.GREEN if _HAS_COLORAMA else "",
                         "Microphone stream OPEN — speak naturally.")
                )
                _log_info("Press Ctrl+C to stop.\n")
                self._process_loop()

        except sd.PortAudioError as exc:
            _log_error(f"PortAudio error — microphone unavailable: {exc}")
            _log_error("Try: python stt_module.py --list-devices")
        except OSError as exc:
            _log_error(f"OS audio error (device changed/disconnected?): {exc}")
        finally:
            self.stop()

    def stop(self) -> None:
        """Signal all threads to terminate and wait for clean shutdown."""
        self._stop_event.set()
        if self._inference_thread and self._inference_thread.is_alive():
            self._inference_thread.join(timeout=5.0)
        _log_info("Kugane STT Engine stopped.")


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry-point
# ─────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stt_module",
        description=(
            "Kugane Continuous STT — real-time mic transcription "
            "via faster-whisper on CUDA/int8."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--model",
        default="base",
        choices=["tiny", "base", "small", "medium", "large-v3"],
        help="faster-whisper model tier.",
    )
    p.add_argument(
        "--device",
        default="auto",
        choices=["cuda", "cpu", "auto"],
        help="Inference device. 'auto' tries CUDA then falls back to CPU.",
    )
    p.add_argument(
        "--language",
        default=None,
        metavar="CODE",
        help="ISO-639-1 language code, e.g. 'en' or 'hi'. None = auto-detect.",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_RMS_THRESHOLD,
        metavar="FLOAT",
        help="RMS energy silence gate. Lower value = more sensitive.",
    )
    p.add_argument(
        "--silence",
        type=float,
        default=DEFAULT_SILENCE_SECONDS,
        metavar="SECONDS",
        help="Seconds of silence that closes and transcribes a phrase.",
    )
    p.add_argument(
        "--input-device",
        type=int,
        default=None,
        metavar="N",
        help="sounddevice device index (see --list-devices).",
    )
    p.add_argument(
        "--list-devices",
        action="store_true",
        help="Print available audio input devices and exit.",
    )
    return p


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.list_devices:
        try:
            print(sd.query_devices())
        except Exception as exc:  # noqa: BLE001
            _log_error(f"Cannot query audio devices: {exc}")
            return 2
        return 0

    if _HAS_COLORAMA:
        banner = (
            "\n"
            + Fore.MAGENTA + Style.BRIGHT
            + "  ╔══════════════════════════════════════╗\n"
            + "  ║   K U G A N E   S T T   E N G I N E  ║\n"
            + "  ╚══════════════════════════════════════╝\n"
            + Style.RESET_ALL
        )
    else:
        banner = "\n  [ KUGANE STT ENGINE ]\n"
    print(banner, flush=True)

    engine = KuganeSTTEngine(
        device=args.device,
        model_size=args.model,
        language=args.language,
        rms_threshold=args.threshold,
        silence_seconds=args.silence,
        input_device=args.input_device,
    )

    try:
        engine.start()
    except KeyboardInterrupt:
        print()
        engine.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
