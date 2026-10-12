# Kugane local STT

The file CLI transcribes recordings. Live mode listens to the selected microphone and prints new words as you speak. It keeps one faster-whisper model loaded, uses CPU/int8 and two CPU threads by default, and skips quiet audio windows. There is no listener until you launch the live command; stop it with Ctrl+C.

Install optional microphone support from the repository root:

```powershell
uv sync --extra live
```

Start live transcription:

```powershell
uv run python Voice/stt_module/live_cli.py
```

The default multilingual `base` model updates from a 3.2-second rolling window every 1.6 seconds. It overlaps windows to preserve words near boundaries and removes repeated words at the overlap. `tiny` is lighter; `small` may improve accuracy with additional compute. For Blender coexistence, keep the CPU default. `--device auto` tries CUDA/int8, which can be faster but shares GPU memory with Blender.

Useful options: `--language en`, `--input-device N`, `--list-devices`, `--window-seconds 3.2`, `--update-seconds 1.6`, `--rms-threshold 0.008`, and `--cpu-threads 2`.

To transcribe a file:

```powershell
uv run python Voice/stt_module/CLI_test.py Voice/stt_module/audio.mp3
```

Voice activity filtering is off by default because it dropped sung and quiet words in the existing sample. The live mode uses a simple RMS silence gate to avoid decoding quiet windows while retaining the captured audio for recognition.
