# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

Python runs inside the **conda environment `tmchien`**. Always activate it before running any command:

```bash
conda activate tmchien
```

## Commands

```bash
pip install -r requirements.txt   # install dependencies
streamlit run app.py              # start the app

# Syntax-check modified files before reporting done
conda run -n tmchien python -m py_compile <file.py>

# Import sanity check
conda run -n tmchien python -c "import app"

# Smoke test (headless)
conda run -n tmchien streamlit run app.py --server.headless true &
sleep 6 && curl -s http://localhost:8501/_stcore/health
```

Secrets are loaded from `.streamlit/secrets.toml` via `st.secrets`. Required keys:

| Key | Purpose |
|-----|---------|
| `GEMINI_API_KEY` | Gemini Live API key |
| `GEMINI_LIVE_MODEL` | Gemini Live model ID |
| `OPENROUTER_BASE_URL` | OpenRouter base URL |
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `OPENROUTER_MODEL` | Model ID passed to OpenRouter |
| `TEXT_PROVIDER` | `"openrouter"` or `"gemma"` (default: `"openrouter"`) |
| `GEMMA_MODEL` | Gemma model ID (default: `"gemma-4-31b-it"`) |
| `MONGODB_URI` | MongoDB connection string |
| `MONGODB_USERNAME` / `MONGODB_PASSWORD` | MongoDB credentials |

## Architecture

Multi-page Streamlit app (`st.navigation` ≥ 1.36) for IELTS English practice. `app.py` is the thin hub — it registers pages, loads secrets once, ensures MongoDB indexes, and renders the shared vocabulary sidebar. Each page file is a thin entry point that calls into the `core/` subpackage.

```
app.py  ──► pages/0_Home.py        (login + admin, sidebar hidden)
        ├──► pages/1_Speaking.py   → core/speaking/ui/app.py:main()
        ├──► pages/2_Listening.py  → core/listening/ui/app.py:main()
        └──► pages/3_Chat.py       (push-to-talk Live Chat, standalone)
```

### Auth

`core/auth.py` — pure session helpers (`is_logged_in`, `current_user`, `logout`). No middleware. Auth state lives in `st.session_state["current_user"]`. There is a hardcoded root account (`username=root / password=root`) that bypasses MongoDB and can manage other accounts. Regular users are stored in MongoDB `users` collection.

### Async / threading model

Streamlit's main thread is synchronous. A single persistent `asyncio` loop runs in a daemon thread per browser session, stored in `st.session_state["_bg_loop"]` — managed by `core/async_utils.py`. All async coroutines are dispatched via `run_async(coro)`.

**Critical constraint:** MongoDB's Motor client must be created *after* the background loop is already running. `get_store()` in `core/shared.py` calls `get_bg_loop()` first for exactly this reason. If the loop dies and is recreated, the store is invalidated — `get_bg_loop()` pops `"store"` from session_state to force rebind.

Speaking evaluation and question generation use separate daemon threads calling `asyncio.run()` independently (never the shared loop) and write results into plain dicts in `st.session_state`. They must never write directly to `st.session_state` from off-thread — use a `threading.Lock` (`_RESULT_LOCK` in `core/speaking/ui/helpers.py`).

### Store (`core/store.py`)

`FluentUpStore` wraps Motor (async MongoDB). Singleton stored in `st.session_state["store"]` — `get_store()` returns `None` when MongoDB URI is not configured (app degrades gracefully). Database: `fluentup`, collections: `vocabulary`, `users`, `speaking_part2`.

### Vendors

| Vendor | Usage |
|--------|-------|
| **Google Gemini Live** (`google-genai`, `aio.live`) | Speaking: audio transcription + evaluation (TTS+STT); Listening: dialogue generation; Chat: persistent socket conversation |
| **OpenRouter** (`openai.AsyncOpenAI` with custom `base_url`) | Speaking only: parse evaluation → structured feedback, generate Part 1/2/3 questions |
| **Motor** (`motor.motor_asyncio`) | Async MongoDB — vocabulary, users, part 2 attempts |

### Speaking subpackage (`core/speaking/`)

State machine in `ExamSession.phase` (defined in `core/speaking/session.py`). The dispatcher lives in `core/speaking/ui/app.py:main()` — it maps 13+ phase strings to render functions in `part1.py`, `part2.py`, `part3.py`, `home.py`, `summary.py`.

Evaluation flow per answer:
1. User records WAV → `st.audio_input`
2. `start_bg_turn_eval()` (in `eval.py`) launches a daemon thread calling `asyncio.run(evaluator.evaluate(...))`
3. `SpeakingEvaluator` (in `evaluator.py`) sends audio to a single Gemini Live session with `thinking=True`; returns `EvaluationResult` with spoken feedback audio
4. Thread writes into `st.session_state["turn_evals"][turn_idx]` behind `_RESULT_LOCK`
5. On subsequent reruns, `assemble_bg_evals()` checks the dict and materializes results onto `Turn.result`

For Part 2/3 live evaluation (`render_streaming_eval`), a dedicated streaming path polls `st.session_state["eval_result"]` with `time.sleep(_POLL_INTERVAL)` + `st.rerun()`. Timeout constants are in `core/speaking/ui/eval.py`: `_EVAL_TIMEOUT_SECS = 120`, `_EVAL_PROGRESS_DENOMINATOR = 90`.

### Listening subpackage (`core/listening/`)

State lives in `st.session_state` keys prefixed `echo_*` (initialized by `core/listening/ui/state.py:init_state()`). Phase string `echo_phase`: `idle → generating → (ready via rerun) → submitted`.

Dialogue generation is sequential: `render_generating()` calls `generate_turn()` (in `dialogue_gen.py`) turn-by-turn inside a single synchronous loop, updating progress in-place using `st.empty()` placeholders. Each turn returns audio PCM + `output_audio_transcription` as ground truth.

Scoring: fill-blank uses exact match (normalized); transcription uses `difflib.SequenceMatcher`. Both in `core/listening/ui/scoring.py`.

### Chat page (`pages/3_Chat.py`)

Persistent Gemini Live socket managed by `GeminiLiveSession` (`core/chat/session_manager.py`). Push-to-talk: user records → `send_turn_wav()` → `wait_turn_complete()` → rerun to display transcript + play response audio. The session can be pre-loaded with a custom system prompt from the Speaking page's "Ask examiner" deep-dive feature (`core/speaking/ui/eval.py:_launch_deepdive`).

### Gemini Live protocol

- API version: `v1beta`
- Modality: `AUDIO` (avoids 1011 errors from TEXT forcing)
- Audio input: 16 kHz mono 16-bit PCM, 100 ms chunks
- Activity detection: disabled; explicit `ActivityStart`/`ActivityEnd` sent
- Retry logic: exponential backoff, up to 4 attempts, on errors 1011/1012/1013
- 30 configurable voices in `core/config.py:VOICES`

### Key session_state keys

| Key | Owner | Purpose |
|-----|-------|---------|
| `store` | `core/shared.py` | `FluentUpStore` singleton (may be `None`) |
| `_bg_loop` | `core/async_utils.py` | Persistent asyncio event loop |
| `current_user` | `core/auth.py` | Logged-in user dict |
| `session` | Speaking `app.py` | `ExamSession` dataclass |
| `evaluator` | Speaking `app.py` | `SpeakingEvaluator` instance |
| `question_gen` | Speaking `app.py` | `QuestionGenerator` instance |
| `turn_evals` | `eval.py` | Background eval results keyed by turn index |
| `eval_result` | `eval.py` | Streaming eval state dict |
| `echo_*` | Listening `state.py` | All listening page state |
| `chat_session` | `3_Chat.py` | `GeminiLiveSession` |
| `chat_system_prompt` | `3_Chat.py` / `eval.py` | System prompt (set by deep-dive to inject examiner context) |
| `text_provider` | `core/shared.py` | Active provider name: `"openrouter"` or `"gemma"` |
| `_text_provider` | `core/shared.py` | Cached `TextProvider` instance |
