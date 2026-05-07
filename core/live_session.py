"""
core/live_session.py
────────────────────
Single entry point for all one-shot Gemini Live interactions.

    session = GeminiLiveSession(api_key, model)

    # TTS / dialogue
    result = await session.run(text="...", voice="Kore")

    # Evaluation / next-question (audio in, audio+transcript out)
    result = await session.run(audio_wav=wav_bytes, thinking=True, with_input_transcript=True)

    result.audio_wav          → WAV bytes
    result.output_transcript  → model's spoken reply as text
    result.input_transcript   → user's audio as text (only when with_input_transcript=True)
"""
from __future__ import annotations

import asyncio
import dataclasses
import random
import struct

import numpy as np
import google.genai as genai
from google.genai import types

from core.config import LIVE_MODEL, INPUT_RATE, OUTPUT_RATE, CHUNK_MS

CHUNK_BYTES = INPUT_RATE * 2 * CHUNK_MS // 1000  # e.g. 100 ms → 3200 bytes

_MAX_RETRIES    = 4
_RETRY_BASE_SEC = 1.5
_RETRYABLE = ("1011", "1012", "1013", "empty", "timeout", "connection", "internal")


# ── WAV ↔ PCM ─────────────────────────────────────────────────────────────────

def wav_to_pcm16k(wav_bytes: bytes) -> bytes:
    """Parse WAV and return 16-bit LE PCM resampled to 16 kHz mono."""
    try:
        fmt_idx = wav_bytes.find(b"fmt ")
        if fmt_idx == -1:
            return wav_bytes
        _, channels, sample_rate, _, _, bits_per_sample = struct.unpack_from(
            "<HHIIHH", wav_bytes, fmt_idx + 8
        )
        data_idx = wav_bytes.find(b"data")
        if data_idx == -1:
            return wav_bytes
        data_size = struct.unpack_from("<I", wav_bytes, data_idx + 4)[0]
        raw = wav_bytes[data_idx + 8 : data_idx + 8 + data_size]

        if bits_per_sample == 32:
            arr = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2_147_483_648.0
        else:
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32_768.0

        if channels > 1:
            arr = arr.reshape(-1, channels).mean(axis=1)

        if sample_rate != INPUT_RATE:
            n_out = max(1, round(len(arr) * INPUT_RATE / sample_rate))
            arr = np.interp(np.linspace(0, len(arr) - 1, n_out), np.arange(len(arr)), arr)

        return (np.clip(arr, -1.0, 1.0) * 32_767).astype(np.int16).tobytes()
    except Exception:
        return wav_bytes


def pcm_to_wav(pcm: bytes, sample_rate: int = OUTPUT_RATE) -> bytes:
    """Wrap raw 16-bit mono PCM in a minimal WAV header."""
    num_channels    = 1
    bits_per_sample = 16
    byte_rate       = sample_rate * num_channels * bits_per_sample // 8
    block_align     = num_channels * bits_per_sample // 8
    data_size       = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, num_channels,
        sample_rate, byte_rate, block_align, bits_per_sample,
        b"data", data_size,
    )
    return header + pcm


# ── Result ────────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class LiveResult:
    audio_wav:         bytes  # model response as WAV
    output_transcript: str    # model response as text
    input_transcript:  str = ""  # user audio as text (only when requested)


# ── Session ───────────────────────────────────────────────────────────────────

class GeminiLiveSession:
    """Manages one-shot Gemini Live calls. Create once per component, reuse."""

    def __init__(self, api_key: str, model: str = LIVE_MODEL) -> None:
        self._api_key = api_key
        self._model   = model

    async def run(
        self,
        *,
        text:                  str | None = None,
        audio_wav:             bytes | None = None,
        system_instruction:    str = "",
        voice:                 str | None = None,
        thinking:              bool = False,
        with_input_transcript: bool = False,
    ) -> LiveResult:
        """Run a single Gemini Live turn and return the result.

        Exactly one of `text` or `audio_wav` must be provided:
          - text      → send_realtime_input(text=...) — Live model's native text input
          - audio_wav → send_realtime_input with manual ActivityStart/End

        Retries on transient 1011/connection errors.
        """
        if (text is None) == (audio_wav is None):
            raise ValueError("Provide exactly one of `text` or `audio_wav`")

        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return await self._attempt(
                    text=text,
                    audio_wav=audio_wav,
                    system_instruction=system_instruction,
                    voice=voice,
                    thinking=thinking,
                    with_input_transcript=with_input_transcript,
                )
            except Exception as exc:
                last_exc = exc
                msg = str(exc).lower()
                if not any(tag in msg for tag in _RETRYABLE) or attempt == _MAX_RETRIES:
                    raise
                delay = _RETRY_BASE_SEC * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
        raise last_exc  # type: ignore[misc]

    async def _attempt(
        self,
        *,
        text:                  str | None,
        audio_wav:             bytes | None,
        system_instruction:    str,
        voice:                 str | None,
        thinking:              bool,
        with_input_transcript: bool,
    ) -> LiveResult:
        client = genai.Client(
            api_key=self._api_key,
            http_options={"api_version": "v1beta"},
        )

        cfg: dict = dict(
            response_modalities=[types.Modality.AUDIO],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            thinking_config=types.ThinkingConfig(include_thoughts=thinking),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(disabled=True),
            ),
        )
        if voice:
            cfg["speech_config"] = types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            )
        if with_input_transcript:
            cfg["input_audio_transcription"] = types.AudioTranscriptionConfig()
        if system_instruction.strip():
            cfg["system_instruction"] = types.Content(
                parts=[types.Part.from_text(text=system_instruction)]
            )

        async with client.aio.live.connect(
            model=self._model, config=types.LiveConnectConfig(**cfg)
        ) as session:
            if text is not None:
                await session.send_realtime_input(text=text)
            else:
                pcm = wav_to_pcm16k(audio_wav)  # type: ignore[arg-type]
                await session.send_realtime_input(activity_start=types.ActivityStart())
                for offset in range(0, len(pcm), CHUNK_BYTES):
                    await session.send_realtime_input(
                        audio=types.Blob(
                            data=pcm[offset : offset + CHUNK_BYTES],
                            mime_type=f"audio/pcm;rate={INPUT_RATE}",
                        )
                    )
                await session.send_realtime_input(activity_end=types.ActivityEnd())

            input_tr, output_tr, raw_pcm = await self._collect(session)

        if not raw_pcm:
            raise RuntimeError("Empty audio received from Gemini Live")

        return LiveResult(
            audio_wav=pcm_to_wav(raw_pcm, OUTPUT_RATE),
            output_transcript=output_tr,
            input_transcript=input_tr,
        )

    @staticmethod
    async def _collect(session: genai.live.AsyncSession) -> tuple[str, str, bytes]:
        """Drain session.receive() → (input_tr, output_tr, raw_pcm).

        session.receive() already breaks after turn_complete.
        go_away signals imminent server disconnect — stop early.
        """
        input_tr  = ""
        output_tr = ""
        pcm_chunks: list[bytes] = []

        async for msg in session.receive():
            if msg.go_away is not None:
                break
            sc = msg.server_content
            if sc is None:
                continue
            if sc.input_transcription and sc.input_transcription.text:
                input_tr += sc.input_transcription.text
            if sc.output_transcription and sc.output_transcription.text:
                output_tr += sc.output_transcription.text
            if sc.model_turn:
                for part in sc.model_turn.parts or []:
                    if part.inline_data and part.inline_data.data:
                        pcm_chunks.append(part.inline_data.data)

        return input_tr.strip(), output_tr.strip(), b"".join(pcm_chunks)
