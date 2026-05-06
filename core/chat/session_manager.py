"""
core/chat/session_manager.py
----------------------------
Persistent bidirectional Gemini Live session for real-time audio chat.

Threading model:
  - Streamlit main thread : calls send_turn_wav(), wait_turn_complete(), stop()
  - Internal daemon thread: runs its own asyncio loop with _send_loop + _recv_loop
    running concurrently via asyncio.gather()

Push-to-talk flow:
  1. main thread  → send_turn_wav(wav_bytes)   : enqueue ActivityStart + PCM + ActivityEnd
  2. daemon thread → _send_loop sends to socket ; _recv_loop accumulates response
  3. main thread  → wait_turn_complete()        : block until turn_complete, return result
"""
from __future__ import annotations

import asyncio
import queue
import threading
from dataclasses import dataclass

import numpy as np
import google.genai as genai
from google.genai import types

from core.config import LIVE_MODEL, INPUT_RATE, OUTPUT_RATE, CHUNK_MS
from core.live_session import wav_to_pcm16k, pcm_to_wav

_CHUNK_BYTES = INPUT_RATE * 2 * CHUNK_MS // 1000  # 3200 bytes = 100 ms at 16 kHz

_ACTIVITY_START = b"__START__"
_ACTIVITY_END   = b"__END__"


@dataclass
class ChatMessage:
    role: str   # "user" | "assistant"
    text: str


class GeminiLiveSession:
    """
    Persistent Gemini Live WebSocket session.

    One socket stays open for the whole conversation — Gemini maintains
    internal state across turns without needing history injection.
    """

    def __init__(self, api_key: str, model: str, system_prompt: str) -> None:
        self._api_key       = api_key
        self._model         = model
        self._system_prompt = system_prompt

        # asyncio input queue (created inside loop thread before signalling ready)
        self._input_q: asyncio.Queue[bytes] | None = None

        # Conversation log
        self._messages: list[ChatMessage] = []
        self._msg_lock = threading.Lock()

        # Per-turn result state (written by _recv_loop, read by wait_turn_complete)
        self._turn_lock          = threading.Lock()
        self._turn_complete      = threading.Event()
        self._turn_user_text     = ""
        self._turn_asst_text     = ""
        self._turn_audio_chunks: list[bytes] = []

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

    def send_turn_wav(self, wav_bytes: bytes) -> None:
        """
        Convert WAV to PCM 16 kHz and enqueue as a complete turn on the
        persistent socket (ActivityStart → PCM chunks → ActivityEnd).
        """
        if not self.is_ready or self._input_q is None:
            raise RuntimeError("Session not ready")

        pcm = wav_to_pcm16k(wav_bytes)

        # Reset turn state BEFORE enqueuing so recv_loop can't race ahead
        with self._turn_lock:
            self._turn_complete.clear()
            self._turn_user_text    = ""
            self._turn_asst_text    = ""
            self._turn_audio_chunks = []

        self._enqueue(_ACTIVITY_START)
        for offset in range(0, len(pcm), _CHUNK_BYTES):
            self._enqueue(pcm[offset : offset + _CHUNK_BYTES])
        self._enqueue(_ACTIVITY_END)

    def wait_turn_complete(self, timeout: float = 30.0) -> tuple[str, str, bytes]:
        """
        Block until Gemini signals turn_complete.
        Returns (user_transcript, assistant_transcript, response_wav_bytes).
        Raises TimeoutError if no response within *timeout* seconds.
        """
        if not self._turn_complete.wait(timeout=timeout):
            raise TimeoutError("No response from Gemini within timeout")

        with self._turn_lock:
            user_tr  = self._turn_user_text
            asst_tr  = self._turn_asst_text
            wav = pcm_to_wav(b"".join(self._turn_audio_chunks), OUTPUT_RATE) \
                  if self._turn_audio_chunks else b""

        return user_tr.strip(), asst_tr.strip(), wav

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

        async with client.aio.live.connect(
            model=self._model, config=types.LiveConnectConfig(**cfg_kwargs)
        ) as session:
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
                with self._turn_lock:
                    self._turn_user_text += it.text

            ot = getattr(sc, "output_transcription", None)
            if ot and getattr(ot, "text", None):
                with self._turn_lock:
                    self._turn_asst_text += ot.text

            mt = getattr(sc, "model_turn", None)
            if mt:
                for part in getattr(mt, "parts", []) or []:
                    inline = getattr(part, "inline_data", None)
                    if inline and getattr(inline, "data", None):
                        with self._turn_lock:
                            self._turn_audio_chunks.append(inline.data)

            if getattr(sc, "turn_complete", False):
                with self._turn_lock:
                    user_tr = self._turn_user_text.strip()
                    asst_tr = self._turn_asst_text.strip()
                with self._msg_lock:
                    if user_tr:
                        self._messages.append(ChatMessage("user", user_tr))
                    if asst_tr:
                        self._messages.append(ChatMessage("assistant", asst_tr))
                self._turn_complete.set()
