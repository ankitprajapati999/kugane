"""Low-resource live microphone transcription for Kugane."""

from __future__ import annotations

import argparse
import queue
import re
import sys


def _word_key(word: str) -> str:
    return re.sub(r"\W+", "", word.casefold())


def _new_words(previous: list[str], current: list[str], max_overlap: int = 20) -> list[str]:
    """Remove text repeated where two overlapping audio windows meet."""
    limit = min(len(previous), len(current), max_overlap)
    for count in range(limit, 0, -1):
        if [_word_key(w) for w in previous[-count:]] == [_word_key(w) for w in current[:count]]:
            return current[count:]
    return current


def main() -> int:
    parser = argparse.ArgumentParser(description="Transcribe your microphone locally in near real time")
    parser.add_argument("--model", default="base", help="base is a good CPU/accuracy balance; tiny is lighter")
    parser.add_argument("--device", choices=("cpu", "auto", "cuda"), default="cpu")
    parser.add_argument("--language", help="language code, e.g. en or hi; auto-detect by default")
    parser.add_argument("--cpu-threads", type=int, default=2)
    parser.add_argument("--window-seconds", type=float, default=3.2)
    parser.add_argument("--update-seconds", type=float, default=1.6)
    parser.add_argument("--rms-threshold", type=float, default=0.008, help="skip quiet windows; lower for a quiet mic")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--input-device", type=int, help="microphone device number from --list-devices")
    args = parser.parse_args()

    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exc:
        print("Live mic support is optional. Install it with: uv sync --extra live", file=sys.stderr)
        print(f"Missing dependency: {exc}", file=sys.stderr)
        return 2

    if args.list_devices:
        print(sd.query_devices())
        return 0
    if args.window_seconds <= 0 or args.update_seconds <= 0 or args.update_seconds > args.window_seconds:
        parser.error("use positive window/update durations, with update no longer than the window")

    # Bounded queue prevents memory growth if inference ever falls behind capture.
    audio_queue: queue.Queue = queue.Queue(maxsize=40)  # 10 seconds at 0.25-second blocks
    dropped_blocks = 0

    def on_audio(indata, frames, time_info, status):
        nonlocal dropped_blocks
        if status:
            # PortAudio callbacks must stay short; report device status in the main loop.
            pass
        block = indata[:, 0].copy()
        try:
            audio_queue.put_nowait(block)
        except queue.Full:
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                pass
            dropped_blocks += 1
            try:
                audio_queue.put_nowait(block)
            except queue.Full:
                pass

    from model import LocalTranscriber

    recognizer = LocalTranscriber(
        model_size=args.model,
        device=args.device,
        language=args.language,
        cpu_threads=args.cpu_threads,
        beam_size=1,
        vad_filter=False,
    )
    rate = 16_000
    window_size = round(args.window_seconds * rate)
    step_size = round(args.update_seconds * rate)
    buffer = np.empty(0, dtype=np.float32)
    samples_since_update = 0
    previous_words: list[str] = []
    last_drop_report = 0

    print("Listening. Speak naturally; press Ctrl+C to stop.")
    print("The first result may take longer while the model loads. Audio stays on this computer.")
    try:
        with sd.InputStream(
            device=args.input_device,
            samplerate=rate,
            channels=1,
            dtype="float32",
            blocksize=round(rate * 0.25),
            callback=on_audio,
        ):
            while True:
                try:
                    block = audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                buffer = np.concatenate((buffer, block))
                samples_since_update += len(block)
                if len(buffer) > window_size:
                    buffer = buffer[-window_size:]
                if len(buffer) < window_size or samples_since_update < step_size:
                    continue
                samples_since_update = 0
                rms = float(np.sqrt(np.mean(np.square(buffer))))
                if rms < args.rms_threshold:
                    buffer = np.empty(0, dtype=np.float32)
                    samples_since_update = 0
                    previous_words = []
                    continue
                try:
                    result = recognizer.transcribe_audio(buffer, sample_rate=rate)
                except Exception as exc:
                    print(f"Transcription error: {exc}", file=sys.stderr)
                    continue
                words = result.text.split()
                delta = _new_words(previous_words, words)
                if delta:
                    print(" ".join(delta), flush=True)
                previous_words = words
                if dropped_blocks != last_drop_report:
                    print("[Audio backlog; dropped old mic blocks to stay current.]", file=sys.stderr)
                    last_drop_report = dropped_blocks
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as exc:
        print(f"Could not open the microphone: {exc}", file=sys.stderr)
        print("Try --list-devices, then pass --input-device N.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
