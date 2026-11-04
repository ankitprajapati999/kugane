# Kugane STT Module

> **Part of the Kugane AI Assistant** — a student-built multi-modal, multi-agent automation assistant inspired by Gemini Live and GPT-4o Astra. Kugane combines voice input, camera vision, LLM reasoning, and tool-use to become a real-time AI companion running entirely on local hardware.

---

## Table of Contents

1. [What this module does](#what-this-module-does)
2. [Architecture deep-dive](#architecture-deep-dive)
3. [File inventory](#file-inventory)
4. [Hardware target & VRAM budget](#hardware-target--vram-budget)
5. [Dependencies](#dependencies)
6. [Installation](#installation)
7. [Running the STT engine](#running-the-stt-engine)
8. [CLI reference](#cli-reference)
9. [Programmatic API](#programmatic-api)
10. [Voice Activity Detection explained](#voice-activity-detection-explained)
11. [Thread model](#thread-model)
12. [Output format & future integration points](#output-format--future-integration-points)
13. [Tuning guide](#tuning-guide)
14. [Known limitations & roadmap](#known-limitations--roadmap)
15. [Project-wide context](#project-wide-context)

---

## What this module does

`stt_module.py` is the **continuous real-time speech-to-text (STT) engine** for Kugane. It:

- Captures audio **continuously** from the system microphone (no push-to-talk).
- Applies a lightweight **Voice Activity Detection (VAD)** gate based on RMS energy to distinguish speech from silence without a heavyweight ML VAD model.
- Waits for **1.2 seconds of consecutive silence** before treating the accumulated audio as a complete spoken phrase.
- Runs **faster-whisper** inference (`base` model, `int8` quantisation, CUDA device) on the phrase chunk in a **dedicated background thread** — completely decoupled from audio capture.
- Prints the transcription to terminal using the exact format: `[Kugane STT Log]: <text>` with full colorama colouring.
- Exposes a **clean Python API** (`KuganeSTTEngine`) so the main application pipeline can receive transcripts via a callback and feed them to the LLM server over WebSocket.

---

## Architecture deep-dive

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        KUGANE STT DATA FLOW                              │
│                                                                          │
│  ┌──────────────────┐   PortAudio C thread (non-blocking)                │
│  │  Windows Default │──► _audio_callback()                               │
│  │  Microphone      │     copies block → audio_queue.put_nowait()        │
│  └──────────────────┘                  │                                 │
│                                        │ queue.Queue(maxsize=80)         │
│                                        ▼                                 │
│                            _process_loop()  [main/calling thread]        │
│                            ┌───────────────────────────────────────┐     │
│                            │  audio_queue.get(timeout=0.3)         │     │
│                            │       ↓                               │     │
│                            │  _rms(block)  ← NumPy vectorised      │     │
│                            │       ↓                               │     │
│                            │  is_voice?  ──No──► silence counter   │     │
│                            │       │               ↓               │     │
│                            │      Yes         silence ≥ 1.2 s?     │     │
│                            │       ↓               ↓               │     │
│                            │  append to     _flush_phrase()         │     │
│                            │  phrase_buffer       ↓               │     │
│                            └──────────────  inference_queue ───────┘     │
│                                                    │                     │
│                            _inference_worker()  [daemon thread]          │
│                            ┌───────────────────────────────────────┐     │
│                            │  inference_queue.get(timeout=0.3)     │     │
│                            │       ↓                               │     │
│                            │  faster-whisper.transcribe()          │     │
│                            │  (CUDA, int8, beam_size=1)            │     │
│                            │       ↓                               │     │
│                            │  on_transcript(text)                  │     │
│                            │  "[Kugane STT Log]: <text>"           │     │
│                            └───────────────────────────────────────┘     │
│                                                                          │
│  Future:  on_transcript → WebSocket → LLM Server → edge-tts speaker     │
└──────────────────────────────────────────────────────────────────────────┘
```

### Why this design?

| Design choice | Rationale |
|---|---|
| `sounddevice.InputStream` callback | Non-blocking PortAudio C-level callback; zero GIL contention with Python threads |
| Bounded `queue.Queue(maxsize=80)` | 8 seconds of audio buffer; oldest block dropped on overflow to stay real-time |
| RMS energy VAD | No ONNX/ML VAD model overhead; vectorised NumPy sqrt+mean op takes < 0.1 ms per block |
| 1.2 s silence window | Empirically tuned for natural speech cadence without cutting off sentence-final pauses |
| Dedicated inference daemon thread | Keeps audio capture loop free even when CUDA is busy; inference latency is ~150–400 ms for base model |
| `beam_size=1, best_of=1` | Minimum compute path through Whisper decoder; maximises throughput on 4 GB VRAM |
| `condition_on_previous_text=False` | Prevents Whisper from hallucinating text continuations between unrelated phrases |
| Immediate buffer flush before inference | `phrase_buffer = []` is set *before* dispatching to inference queue → RAM freed in < 1 ms |

---

## File inventory

```
Voice/
└── stt_module/
    ├── stt_module.py      ← THE ENGINE (this module — the one you run)
    ├── live_cli.py        ← Original rolling-window live CLI (do not modify)
    ├── modelT4.py         ← LocalTranscriber + Transcript dataclass (do not modify)
    ├── audio.mp3          ← Test audio file for CLI_test.py
    └── README.md          ← This file
```

> **`live_cli.py` and `modelT4.py` are intentionally untouched.** They use a rolling sliding-window approach and CPU/int8. `stt_module.py` uses a **phrase-boundary VAD approach** on CUDA/int8, which is architecturally different and better suited for the LLM pipeline.

---

## Hardware target & VRAM budget

| Component | Spec | Budget |
|---|---|---|
| CPU | AMD Ryzen 5 7235HS — 4C/8T | ≤ 2 threads for CPU inference fallback |
| GPU | NVIDIA RTX 3050A — 4 GB GDDR6 | **< 300 MB VRAM** for faster-whisper base/int8 |
| RAM | 24 GB DDR5 | Phrase buffers are flushed immediately; negligible overhead |

**Measured VRAM usage (approximate):**

| Model | compute_type | VRAM |
|---|---|---|
| `tiny` | int8 | ~90 MB |
| `base` | int8 | ~180 MB ✅ |
| `small` | int8 | ~460 MB (exceeds budget) |

The RTX 3050A can simultaneously serve Kugane STT + the future edge-tts synthesis + any Blender/Unity GPU workload because the base/int8 footprint leaves ~3.8 GB of VRAM headroom.

---

## Dependencies

| Package | Purpose | Install |
|---|---|---|
| `faster-whisper` | CUDA-accelerated Whisper inference | `uv add faster-whisper` |
| `sounddevice` | PortAudio microphone input | `uv add sounddevice` |
| `numpy` | Audio buffer ops, RMS energy gate | `uv add numpy` |
| `colorama` | Cross-platform terminal colouring | `uv add colorama` |
| CUDA Toolkit + cuDNN | GPU acceleration (system-level) | NVIDIA driver + CUDA 12.x |
| CTranslate2 (CUDA build) | faster-whisper GPU backend | Installed automatically with `faster-whisper[cuda]` |

> **Note:** On Windows, `sounddevice` requires the Microsoft Visual C++ Redistributable to be installed for PortAudio to work.

---

## Installation

From the repository root:

```powershell
# Install all required packages
uv add faster-whisper sounddevice numpy colorama

# Verify sounddevice sees your microphone
uv run python Voice/stt_module/stt_module.py --list-devices
```

If you need the CUDA build of CTranslate2 (faster-whisper backend):

```powershell
# Force CUDA wheel (CUDA 12.x)
uv add "ctranslate2[cuda]"
```

---

## Running the STT engine

```powershell
# Run with defaults (CUDA, base model, auto language detection)
uv run python Voice/stt_module/stt_module.py

# Run in CPU-only mode (for Blender coexistence — keeps GPU free)
uv run python Voice/stt_module/stt_module.py --device cpu

# Lock to English for faster decode (skips language detection overhead)
uv run python Voice/stt_module/stt_module.py --language en

# Use a specific microphone
uv run python Voice/stt_module/stt_module.py --input-device 2

# Tune VAD sensitivity (lower threshold = pick up quieter voices)
uv run python Voice/stt_module/stt_module.py --threshold 0.005

# Extend silence window (useful for speakers who pause mid-sentence)
uv run python Voice/stt_module/stt_module.py --silence 2.0
```

**Expected terminal output:**

```
  ╔══════════════════════════════════════╗
  ║   K U G A N E   S T T   E N G I N E  ║
  ╚══════════════════════════════════════╝

[Kugane INFO ] Kugane STT Engine starting ...
[Kugane INFO ] model=base | device=cuda | compute=int8 | rms_threshold=0.0100 | silence_window=1.20s
[Kugane INFO ] Loading faster-whisper [base] device=cuda compute=int8 ...
[Kugane INFO ] Model ready — CUDA/int8
[Kugane INFO ] Microphone stream OPEN — speak naturally.
[Kugane INFO ] Press Ctrl+C to stop.

[Kugane STT Log]: What is the weather like today?
[Kugane STT Log]: Open Blender and create a new cube mesh.
```

---

## CLI reference

```
usage: stt_module [--model {tiny,base,small,medium,large-v3}]
                  [--device {cuda,cpu,auto}]
                  [--language CODE]
                  [--threshold FLOAT]
                  [--silence SECONDS]
                  [--input-device N]
                  [--list-devices]

options:
  --model      faster-whisper model tier. 'base' optimal for RTX 3050A. (default: base)
  --device     Inference device. (default: cuda)
  --language   ISO-639-1 code, e.g. 'en' or 'hi'. None = auto-detect. (default: None)
  --threshold  RMS energy silence gate. Lower = more sensitive. (default: 0.01)
  --silence    Seconds of silence that closes and transcribes a phrase. (default: 1.2)
  --input-device N   sounddevice device index. (default: system default)
  --list-devices     Print available audio input devices and exit.
```

---

## Programmatic API

`stt_module.py` is designed to be imported into the Kugane main application pipeline:

```python
from Voice.stt_module.stt_module import KuganeSTTEngine

def handle_transcript(text: str) -> None:
    """
    Called by the STT engine on every completed phrase.
    Plug in: WebSocket send to LLM server, queue push, etc.
    """
    # Future: asyncio.run(websocket.send(text))
    # Future: llm_request_queue.put(text)
    print(f"[Kugane STT Log]: {text}")

engine = KuganeSTTEngine(
    device="cuda",
    model_size="base",
    language="en",
    rms_threshold=0.01,
    silence_seconds=1.2,
    on_transcript=handle_transcript,  # ← your callback here
)

# engine.start() blocks the calling thread.
# Call engine.stop() from another thread to terminate.
import threading
t = threading.Thread(target=engine.start, daemon=True)
t.start()

# ... your LLM / TTS / UI code runs here ...

engine.stop()
t.join()
```

### `KuganeSTTEngine` constructor parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `device` | `str` | `"cuda"` | `"cuda"` / `"cpu"` / `"auto"` |
| `compute_type` | `str` | `"int8"` | Quantisation precision |
| `model_size` | `str` | `"base"` | faster-whisper model tier |
| `language` | `str\|None` | `None` | ISO-639-1 code or None for auto-detect |
| `rms_threshold` | `float` | `0.01` | RMS energy below this = silence |
| `silence_seconds` | `float` | `1.2` | Silence duration that closes a phrase |
| `input_device` | `int\|None` | `None` | sounddevice device index |
| `on_transcript` | `Callable[[str], None]\|None` | `None` | Phrase callback; defaults to stdout print |

---

## Voice Activity Detection explained

Kugane STT uses a **mathematical energy gate** rather than an ML-based VAD model (like Silero VAD). This keeps the CPU free for the rest of the application stack.

**How it works:**

1. Each 100 ms audio block (1 600 float32 samples at 16 kHz) comes in from the PortAudio callback.
2. The **RMS (Root Mean Square)** energy of the block is computed:

   ```
   RMS = sqrt( mean( block² ) )
   ```

3. If `RMS ≥ rms_threshold` → block is classified as **voice** → appended to phrase buffer.
4. If `RMS < rms_threshold` → block is classified as **silence**.
   - If we were previously speaking, silence blocks are still appended (as trailing context) and the silence counter increments.
   - Once `silence_counter ≥ silence_samples` (1.2 s × 16 000 = 19 200 samples), the phrase is finalised.
5. Phrases shorter than 0.4 seconds are discarded (protect against decoded mouse clicks and cough bursts).

**Tuning tips:**

| Room condition | Suggested `--threshold` |
|---|---|
| Quiet room, close mic | `0.005` – `0.01` |
| Normal office | `0.01` – `0.02` |
| Noisy environment | `0.03` – `0.05` |
| Headset / boom mic | `0.005` |

---

## Thread model

```
Main thread (calling thread)
├── Opens sd.InputStream context manager
├── Runs _process_loop() — VAD gate, phrase accumulation, queue dispatch
│
├── [PortAudio C thread — NOT a Python thread]
│   └── _audio_callback() — copy block, put_nowait()
│
└── kugane-inference [Python daemon thread]
    └── _inference_worker() — faster-whisper GPU, on_transcript()
```

The GIL is not a bottleneck here because:
- PortAudio callback runs in a C-level OS thread (bypasses GIL).
- NumPy RMS ops release the GIL during vectorised computation.
- CTranslate2 CUDA inference releases the GIL during GPU execution.

---

## Output format & future integration points

### Current (terminal print)

```
[Kugane STT Log]: <transcribed text>
```

### Future pipeline (planned)

```
on_transcript(text)
    → asyncio WebSocket client
    → Kugane LLM Server (local or API)
    → LLM response
    → edge-tts synthesis
    → Windows audio output (laptop speaker)
```

The `on_transcript` callback is the **sole integration seam** between the STT module and the rest of Kugane. Replace the default stdout print with a WebSocket send, an asyncio queue push, or a direct LLM API call — without changing any audio capture code.

### Camera query integration (future)

When the LLM detects visual queries ("what is in front of me?", "describe this"), the Kugane orchestrator will:

1. Receive the transcript via `on_transcript`.
2. Parse intent using the LLM.
3. If visual intent detected → grab frame from the `cam_module` (OpenCV, future).
4. Send frame + query to vision-capable LLM endpoint.
5. Speak the response via `tts_module` (edge-tts, future).

---

## Tuning guide

### My mic is too sensitive (picks up background noise)

```powershell
uv run python Voice/stt_module/stt_module.py --threshold 0.03
```

### Kugane cuts me off mid-sentence

```powershell
uv run python Voice/stt_module/stt_module.py --silence 2.0
```

### I want the fastest possible transcription (minimal latency)

```powershell
uv run python Voice/stt_module/stt_module.py --model tiny --language en
```

### Blender is running and I need to leave GPU memory for it

```powershell
uv run python Voice/stt_module/stt_module.py --device cpu
```
CPU inference with the `base` model takes ~800 ms–1.5 s per phrase on the Ryzen 5 7235HS — acceptable for voice assistant response latency.

### Running on a different microphone

```powershell
# List all devices first
uv run python Voice/stt_module/stt_module.py --list-devices
# Run on device index 3
uv run python Voice/stt_module/stt_module.py --input-device 3
```

---

## Known limitations & roadmap

| Limitation | Status | Planned fix |
|---|---|---|
| Transcripts go to stdout only | Current | WebSocket integration to LLM server |
| No wake-word detection | Pending | Integrate openWakeWord or custom wakeword ("Kugane") |
| No speaker diarization | Out of scope | pyannote.audio (future, high VRAM cost) |
| Hindi/English code-switching | Partial | faster-whisper handles mixed-language reasonably; tune `--language` |
| Edge-TTS response playback | Pending | `tts_module` to be built next |
| LLM integration | Pending | WebSocket client to LLM server |
| Camera vision queries | Pending | `cam_module` (OpenCV) — future |
| Dynamic Island UI | Pending | PyQt6 capsule widget — future |
| Wakeword-gated listening | Pending | Module will idle until "Kugane" is detected |

---

## Project-wide context

### What is Kugane?

Kugane is a **student-built**, local-first AI assistant that aims to combine:

- 🎤 **Voice input** (this module) — continuous STT via faster-whisper
- 📷 **Camera vision** (future `cam_module`) — OpenCV frame capture + vision LLM
- 🧠 **LLM reasoning** (future) — local or API model via WebSocket
- 🔊 **Voice output** (future `tts_module`) — edge-tts synthesis to speaker
- 🖥️ **Dynamic Island UI** (future) — PyQt6 Apple-style capsule widget
- 🔧 **Tool use / agents** (future) — Blender scripting, Unity, VS Code, browser

### Tech stack summary

| Layer | Technology |
|---|---|
| STT | faster-whisper (base, CUDA int8) |
| Voice capture | sounddevice (PortAudio) |
| VAD | RMS energy gate (NumPy) |
| TTS | edge-tts (planned) |
| LLM | Local/API via WebSocket (planned) |
| Camera | OpenCV (planned) |
| UI | PyQt6 Dynamic Island capsule (planned) |
| Package manager | uv |
| Python | 3.12+ |
| GPU | NVIDIA RTX 3050A (CUDA 12) |

---

*Kugane STT Module — built for the Ryzen 5 7235HS + RTX 3050A platform.*  
*Inspired by Gemini Live and GPT-4o Astra. Student project.*
