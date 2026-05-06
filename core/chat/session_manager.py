"""
core/chat/session_manager.py
----------------------------
Persistent bidirectional Gemini Live session for real-time audio chat.

Threading model:
  - WebRTC callback thread  : calls push_audio() and pop_output()
  - Streamlit main thread   : calls get_messages(), is_ready, stop()
  - Internal daemon thread  : runs its own asyncio loop with _send_loop + _recv_loop
    running concurrently via asyncio.gather()

VAD is energy-based: consecutive silent chunks trigger ActivityEnd; voice
above threshold triggers ActivityStart.
"""
from __future__ import annotations

import asyncio
import queue
import threading
from dataclasses import dataclass, field

import numpy as np
import google.genai as genai
from google.genai import types

from core.config import LIVE_MODEL, INPUT_RATE, OUTPUT_RATE, CHUNK_MS

_CHUNK_BYTES = INPUT_RATE * 2 * CHUNK_MS // 1000  # 3200 bytes = 100 ms at 16 kHz

_ACTIVITY_START = b"__START__"
_ACTIVITY_END   = b"__END__"

# VAD tuning
_ENERGY_THRESHOLD = 300   # RMS amplitude (0–32767)
_SILENCE_FRAMES   = 8     # consecutive silent 100 ms chunks before ActivityEnd


@dataclass
class ChatMessage:
    role: str   # "user" | "assistant"
    text: str


class GeminiLiveSession:
    """Persistent Gemini Live session with bidirectional PCM streaming."""

    def __init__(self, api_key: str, model: str, system_prompt: str) -> None:
        self._api_key      = api_key
        self._model        = model
        self._system_prompt = system_prompt

        # asyncio queue (created inside the loop thread before signalling ready)
        self._input_q: asyncio.Queue[bytes] | None = None

        # Output PCM chunks (24 kHz mono int16); thread-safe
        self._output_q: queue.Queue[bytes] = queue.Queue(maxsize=2000)

        # Conversation transcript
        self._messages: list[ChatMessage] = []
        self._msg_lock = threading.Lock()

        # VAD state — only touched from push_audio (WebRTC callback thread)
        self._speaking       = False
        self._silence_count  = 0

        # Lifecycle
        self._ready      = threading.Event()
        self._stop_event = threading.Event()
        self._error: str | None = None

        self._loop   = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # ── Public API (thread-safe) ──────────────────────────────────────────────

    def wait_ready(self, timeout: float = 10.0) -> bool:
        return self._ready.wait(timeout=timeout)

    @property
    def is_alive(self) -> bool:
        return self._thread.is_alive()

    @property
    def is_ready(self) -> bool:
        return (
            self._ready.is_set()
            and not self._stop_event.is_set()
            and self._thread.is_alive()
        )

    @property
    def error(self) -> str | None:
        return self._error

    def push_audio(self, pcm_16k_mono: bytes) -> None:
        """
        Accept a PCM chunk (16 kHz, 16-bit mono).  Runs VAD internally and
        enqueues ActivityStart / PCM / ActivityEnd signals as needed.
        """
        if not self.is_ready or self._input_q is None:
            return

        arr = np.frombuffer(pcm_16k_mono, dtype=np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(arr ** 2))) if len(arr) else 0.0

        if rms > _ENERGY_THRESHOLD:
            if not self._speaking:
                self._speaking      = True
                self._silence_count = 0
                self._enqueue(_ACTIVITY_START)
            self._silence_count = 0
            self._enqueue(pcm_16k_mono)
        else:
            if self._speaking:
                self._silence_count += 1
                # Still send audio during leading silence (natural speech gaps)
                self._enqueue(pcm_16k_mono)
                if self._silence_count >= _SILENCE_FRAMES:
                    self._speaking      = False
                    self._silence_count = 0
                    self._enqueue(_ACTIVITY_END)

    def pop_output(self) -> bytes | None:
        """Return one PCM chunk (24 kHz mono int16) or None if nothing ready."""
        try:
            return self._output_q.get_nowait()
        except queue.Empty:
            return None

    def get_messages(self) -> list[ChatMessage]:
        with self._msg_lock:
            return list(self._messages)

    def stop(self) -> None:
        self._stop_event.set()
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            pass

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _enqueue(self, item: bytes) -> None:
        try:
            self._loop.call_soon_threadsafe(self._input_q.put_nowait, item)
        except Exception:
            pass

    # ── Asyncio loop (runs in daemon thread) ──────────────────────────────────

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._session_loop())
        except Exception as exc:
            self._error = str(exc)

    async def _session_loop(self) -> None:
        self._input_q = asyncio.Queue(maxsize=500)

        client = genai.Client(
            api_key=self._api_key,
            http_options={"api_version": "v1beta"},
        )

        cfg_kwargs: dict = dict(
            response_modalities=[types.Modality.AUDIO],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=True
                ),
            ),
            thinking_config=types.ThinkingConfig(include_thoughts=False),
        )
        if self._system_prompt.strip():
            cfg_kwargs["system_instruction"] = types.Content(
                parts=[types.Part.from_text(text=self._system_prompt)]
            )

        cfg = types.LiveConnectConfig(**cfg_kwargs)

        async with client.aio.live.connect(model=self._model, config=cfg) as session:
            self._ready.set()
            await asyncio.gather(
                self._send_loop(session),
                self._recv_loop(session),
            )

    async def _send_loop(self, session) -> None:
        while not self._stop_event.is_set():
            try:
                item = await asyncio.wait_for(self._input_q.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            if item is _ACTIVITY_START:
                await session.send_realtime_input(activity_start=types.ActivityStart())
            elif item is _ACTIVITY_END:
                await session.send_realtime_input(activity_end=types.ActivityEnd())
            else:
                await session.send_realtime_input(
                    audio=types.Blob(
                        data=item,
                        mime_type=f"audio/pcm;rate={INPUT_RATE}",
                    )
                )

    async def _recv_loop(self, session) -> None:
        user_buf       = ""
        assistant_buf  = ""

        async for response in session.receive():
            if self._stop_event.is_set():
                break

            if getattr(response, "go_away", None) is not None:
                break

            sc = getattr(response, "server_content", None)
            if sc is None:
                continue

            it = getattr(sc, "input_transcription", None)
            if it and getattr(it, "text", None):
                user_buf += it.text

            ot = getattr(sc, "output_transcription", None)
            if ot and getattr(ot, "text", None):
                assistant_buf += ot.text

            mt = getattr(sc, "model_turn", None)
            if mt:
                for part in getattr(mt, "parts", []) or []:
                    inline = getattr(part, "inline_data", None)
                    if inline and getattr(inline, "data", None):
                        try:
                            self._output_q.put_nowait(inline.data)
                        except queue.Full:
                            pass

            if getattr(sc, "turn_complete", False):
                with self._msg_lock:
                    if user_buf.strip():
                        self._messages.append(ChatMessage("user", user_buf.strip()))
                    if assistant_buf.strip():
                        self._messages.append(
                            ChatMessage("assistant", assistant_buf.strip())
                        )
                user_buf      = ""
                assistant_buf = ""
