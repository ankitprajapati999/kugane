import argparse
import logging
import sys
import time
from pathlib import Path
from model import LocalTranscriber


def main():
    parser = argparse.ArgumentParser(description="Local speech-to-text using faster-whisper")
    parser.add_argument("audio", type=Path)
    parser.add_argument("--model", default="base")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="cpu")
    parser.add_argument("--language", help="language code such as en or hi; auto-detect by default")
    parser.add_argument("--cpu-threads", type=int, default=2)
    parser.add_argument("--beam-size", type=int, default=1)
    parser.add_argument("--vad", action="store_true", help="filter silence; may discard singing or quiet words")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    stt = LocalTranscriber(args.model, args.device, args.language, args.cpu_threads,
                           args.beam_size, vad_filter=args.vad)
    started = time.perf_counter()
    try:
        result = stt.transcribe_file(args.audio)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"STT error: {exc}", file=sys.stderr)
        return 2
    print(f"Language: {result.language} ({result.language_probability:.0%})")
    for segment in result.segments:
        print(f"[{segment.start:7.2f}–{segment.end:7.2f}] {segment.text.strip()}")
    print(f"\nElapsed: {time.perf_counter()-started:.2f}s | backend: {stt.device}/{stt.compute_type}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
