# Kugane

A personal AI desktop assistant for Windows. Floats as a sleek, compact Dynamic Island capsule on your screen with fluid physics. Click to expand into a full conversation panel powered by Gemini.

---

## Features

- **Floating Dynamic Island UI** — compact pill capsule near top center; click to smoothly expand into full assistant panel.
- **Pure Text Interaction** — lightweight, fast, with zero audio driver or microphone overhead.
- **Gemini Intelligence** — conversational reasoning powered by official Google GenAI SDK.
- **Fluid Animations** — symmetrical physics-based geometry transitions (`OutCubic`), hover states, pulsing indicators, and animated thinking waveforms.
- **Smart Message Composer** — dynamic send button illumination, input focus styling, and auto-scroll tracking.
- **Draggable Window** — click and drag anywhere on the capsule or header to reposition across monitors.
- **In-Memory Context** — retains conversation history during the application session.
- **Graceful Error Handling** — clear status indicators for missing API keys or network errors without crashes.

---

## Requirements

- Windows 10/11
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey)

---

## Installation

```powershell
# 1. Clone or navigate to the repository
cd d:\Kugane

# 2. Install dependencies via uv
uv sync
```

---

## Configuration

Copy `.env.example` to `.env`:

```powershell
copy .env.example .env
```

Edit `.env` and set your Gemini API key:

```env
GEMINI_API_KEY=your_actual_key_here
GEMINI_MODEL=gemini-3.8-flash
```

> ⚠️ **Never commit `.env` to version control.** It is excluded via `.gitignore`.

---

## Running Kugane

```powershell
uv run python main.py
```

A compact pill appears at the top center of your primary display.

---

## How to use

1. **Expand**: Click the compact capsule to expand into the assistant panel.
2. **Type**: Enter your question or prompt in the composer field.
3. **Send**: Press **Enter** or click the circular **↑** send button.
4. **Thinking**: Kugane displays a smooth thinking indicator with animated waveform bars while Gemini generates the response.
5. **Read**: The assistant reply appears in the conversation area.
6. **Collapse**: Click the **—** / **✕** buttons in the header, or press **Esc**, or click the compact pill.

---

## Project Structure

```
Kugane/
├── main.py                    # Application entry point & pipeline composition
├── pyproject.toml             # Dependencies (PyQt6, google-genai, python-dotenv)
├── .env                       # Local secrets (never committed)
├── .env.example               # Template for environment variables
├── config/
│   └── settings.py            # Environment loader & typed constants
├── core/
│   └── llm/
│       ├── gemini_service.py  # Stateful Gemini client & session history
│       └── gemini_worker.py   # QThread worker for non-blocking API calls
└── ui/
    └── island_window.py       # Dynamic Island window & animations
```
