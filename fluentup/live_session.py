"""
fluentup/live_session.py
------------------------
One-shot Gemini Live utility for push-to-talk audio processing and TTS.

Flow (transcription/evaluation):
  WAV bytes  →  PCM 16 kHz mono
             →  Gemini Live session (activity_start + chunks + activity_end)
             →  (input_transcript, ai_text_response)

Flow (TTS):
  text  →  Gemini Live session (send_client_content, AUDIO modality)
        →  PCM 24 kHz mono  →  WAV bytes
"""
from __future__ import annotations

import asyncio
import random
import struct

import numpy as np
import google.genai as genai
from google.genai import types

from fluentup.config import LIVE_MODEL, INPUT_RATE, OUTPUT_RATE, CHUNK_MS

CHUNK_BYTES = INPUT_RATE * 2 * CHUNK_MS // 1000

_MAX_RETRIES    = 4
_RETRY_BASE_SEC = 1.5
_RETRYABLE      = ("1011", "1012", "1013", "empty", "timeout", "connection", "internal")  # e.g. 100 ms of 16-bit PCM = 3200 bytes


# ── WAV → PCM 16 kHz mono ─────────────────────────────────────────────────────

def wav_to_pcm16k(wav_bytes: bytes) -> bytes:
    """
    Parse a WAV file and return raw 16-bit little-endian PCM resampled to 16 kHz mono.
    Falls back to returning the raw bytes if the header cannot be parsed.
    """
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

        # Decode samples to float32
        if bits_per_sample == 32:
            arr = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2_147_483_648.0
        else:
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32_768.0

        # Mix to mono
        if channels > 1:
            arr = arr.reshape(-1, channels).mean(axis=1)

        # Resample to 16 kHz
        if sample_rate != INPUT_RATE:
            n_out = max(1, round(len(arr) * INPUT_RATE / sample_rate))
            arr = np.interp(
                np.linspace(0, len(arr) - 1, n_out),
                np.arange(len(arr)),
                arr,
            )

        return (np.clip(arr, -1.0, 1.0) * 32_767).astype(np.int16).tobytes()

    except Exception:
        return wav_bytes


# ── PCM → WAV ─────────────────────────────────────────────────────────────────

def pcm_to_wav(pcm: bytes, sample_rate: int = OUTPUT_RATE) -> bytes:
    """Wrap raw 16-bit mono PCM bytes in a minimal WAV header."""
    num_channels  = 1
    bits_per_sample = 16
    byte_rate     = sample_rate * num_channels * bits_per_sample // 8
    block_align   = num_channels * bits_per_sample // 8
    data_size     = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, num_channels,
        sample_rate, byte_rate, block_align, bits_per_sample,
        b"data", data_size,
    )
    return header + pcm


# ── Core one-shot helper ──────────────────────────────────────────────────────

async def gemini_live_once(
    api_key:       str,
    system_prompt: str,
    wav_bytes:     bytes,
    model:         str = LIVE_MODEL,
) -> tuple[str, str, bytes]:
    """
    Send pre-recorded WAV to Gemini Live (AUDIO modality — its native mode).
    Returns (input_transcript, output_transcript, audio_pcm_bytes).

    - input_transcript : what the user said (input_audio_transcription)
    - output_transcript: model's spoken reply as text (output_audio_transcription)
    - audio_pcm_bytes  : raw PCM of the model's audio response (for optional playback)

    Retries up to _MAX_RETRIES times on transient 1011/connection errors.
    """
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return await _gemini_live_once_attempt(api_key, system_prompt, wav_bytes, model)
        except Exception as exc:
            last_exc = exc
            msg = str(exc).lower()
            if not any(tag in msg for tag in _RETRYABLE) or attempt == _MAX_RETRIES:
                raise
            delay = _RETRY_BASE_SEC * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


async def _gemini_live_once_attempt(
    api_key:       str,
    system_prompt: str,
    wav_bytes:     bytes,
    model:         str,
) -> tuple[str, str, bytes]:
    pcm = wav_to_pcm16k(wav_bytes)

    client = genai.Client(
        api_key=api_key,
        http_options={"api_version": "v1beta"},
    )

    cfg_kwargs: dict = dict(
        # AUDIO is the native Live modality — avoids 1011 errors from TEXT forcing
        response_modalities=[types.Modality.AUDIO],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True),
        ),
        thinking_config=types.ThinkingConfig(include_thoughts=False),
    )
    if system_prompt.strip():
        cfg_kwargs["system_instruction"] = types.Content(
            parts=[types.Part.from_text(text=system_prompt)]
        )

    input_transcript  = ""
    output_transcript = ""
    audio_chunks:  list[bytes] = []

    async with client.aio.live.connect(
        model=model, config=types.LiveConnectConfig(**cfg_kwargs)
    ) as session:
        await session.send_realtime_input(activity_start=types.ActivityStart())

        for offset in range(0, len(pcm), CHUNK_BYTES):
            await session.send_realtime_input(
                audio=types.Blob(
                    data=pcm[offset : offset + CHUNK_BYTES],
                    mime_type=f"audio/pcm;rate={INPUT_RATE}",
                )
            )

        await session.send_realtime_input(activity_end=types.ActivityEnd())

        async for response in session.receive():
            if getattr(response, "go_away", None) is not None:
                break

            sc = getattr(response, "server_content", None)
            if sc is None:
                continue

            # User's speech → input_audio_transcription
            it = getattr(sc, "input_transcription", None)
            if it:
                t = getattr(it, "text", None)
                if t:
                    input_transcript += t

            # Model's spoken reply → output_audio_transcription + audio PCM
            ot = getattr(sc, "output_transcription", None)
            if ot:
                t = getattr(ot, "text", None)
                if t:
                    output_transcript += t

            mt = getattr(sc, "model_turn", None)
            if mt:
                for part in getattr(mt, "parts", []) or []:
                    inline = getattr(part, "inline_data", None)
                    if inline and getattr(inline, "data", None):
                        audio_chunks.append(inline.data)

            if getattr(sc, "turn_complete", False):
                break

    return (
        input_transcript.strip(),
        output_transcript.strip(),
        b"".join(audio_chunks),
    )


# ── Next question generation via Gemini Live ─────────────────────────────────

async def gemini_live_next_question(
    api_key: str,
    prev_question: str,
    answer_wav: bytes,
    model: str = LIVE_MODEL,
    accent_instruction: str = "",
    profile_ctx: str = "",
) -> tuple[str, bytes]:
    """
    Generate the next IELTS Part 1 question by sending the previous question (as
    system context) and the candidate's audio answer to Gemini Live.

    Returns (question_text, question_wav) where question_wav is a WAV file.
    """
    context = ""
    if accent_instruction.strip():
        context += accent_instruction + "\n\n"
    if profile_ctx.strip():
        context += profile_ctx
    system_prompt = (
        context
        + f'The previous IELTS Part 1 question you asked was: "{prev_question}"\n'
        "Listen to the candidate\'s answer, then ask ONE natural follow-up IELTS Part 1 "
        "question on a related or new everyday topic. "
        "Speak ONLY the question itself — no greetings, no commentary, just the question."
    )

    _input_tr, output_tr, pcm = await gemini_live_once(
        api_key=api_key,
        system_prompt=system_prompt,
        wav_bytes=answer_wav,
        model=model,
    )
    wav = pcm_to_wav(pcm, OUTPUT_RATE) if pcm else b""
    return output_tr.strip(), wav


# ── TTS via Gemini Live AUDIO output ─────────────────────────────────────────

async def gemini_live_speak(
    api_key:            str,
    text:               str,
    voice:              str = "Kore",
    model:              str = LIVE_MODEL,
    system_instruction: str = "",
) -> bytes:
    """
    Use Gemini Live with AUDIO response modality to synthesize speech.
    Returns WAV bytes (24 kHz mono PCM wrapped in a WAV header).

    Pass system_instruction to shape accent/persona (e.g. EXAMINER_ACCENTS["uk"]).
    """
    client = genai.Client(
        api_key=api_key,
        http_options={"api_version": "v1beta"},
    )

    cfg_kwargs: dict = dict(
        response_modalities=[types.Modality.AUDIO],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        ),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True),
        ),
        thinking_config=types.ThinkingConfig(include_thoughts=False),
    )
    if system_instruction.strip():
        cfg_kwargs["system_instruction"] = types.Content(
            parts=[types.Part.from_text(text=system_instruction)]
        )

    cfg = types.LiveConnectConfig(**cfg_kwargs)

    pcm_chunks: list[bytes] = []

    async with client.aio.live.connect(model=model, config=cfg) as session:
        # Explicit read instruction prevents the model from paraphrasing
        await session.send_realtime_input(
            text=f"Read the following text exactly as written, do not add or change anything:\n{text}"
        )

        async for response in session.receive():
            if getattr(response, "go_away", None) is not None:
                break

            sc = getattr(response, "server_content", None)
            if sc is not None:
                mt = getattr(sc, "model_turn", None)
                if mt:
                    for part in getattr(mt, "parts", []) or []:
                        inline = getattr(part, "inline_data", None)
                        if inline and getattr(inline, "data", None):
                            pcm_chunks.append(inline.data)

                if getattr(sc, "turn_complete", False):
                    break

            if getattr(response, "turn_complete", False):
                break

    if not pcm_chunks:
        raise RuntimeError("Empty audio received from Live session")

    return pcm_to_wav(b"".join(pcm_chunks), OUTPUT_RATE)
