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

import struct

import numpy as np
import google.genai as genai
from google.genai import types

LIVE_MODEL    = "models/gemini-3.1-flash-live-preview"
INPUT_RATE    = 16000   # Gemini Live expects 16 kHz PCM input
OUTPUT_RATE   = 24000   # Gemini Live audio output is 24 kHz PCM
CHUNK_BYTES   = INPUT_RATE * 2 * 100 // 1000   # 100 ms of 16-bit PCM = 3 200 bytes


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
) -> tuple[str, str]:
    """
    Open a Gemini Live session, send pre-recorded WAV audio as a single push-to-talk
    turn, and collect (input_transcript, ai_text_response).

    The session is closed after the model's first turn_complete.
    """
    pcm = wav_to_pcm16k(wav_bytes)

    client = genai.Client(
        api_key=api_key,
        http_options={"api_version": "v1beta"},
    )

    cfg_kwargs: dict = dict(
        response_modalities=[types.Modality.TEXT],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True),
        ),
    )
    if system_prompt.strip():
        cfg_kwargs["system_instruction"] = types.Content(
            parts=[types.Part.from_text(text=system_prompt)]
        )

    input_transcript = ""
    ai_response      = ""

    async with client.aio.live.connect(
        model=model, config=types.LiveConnectConfig(**cfg_kwargs)
    ) as session:
        # ── Push audio as a complete turn ─────────────────────────────────────
        await session.send_realtime_input(activity_start=types.ActivityStart())

        for offset in range(0, len(pcm), CHUNK_BYTES):
            await session.send_realtime_input(
                audio=types.Blob(
                    data=pcm[offset : offset + CHUNK_BYTES],
                    mime_type=f"audio/pcm;rate={INPUT_RATE}",
                )
            )

        await session.send_realtime_input(activity_end=types.ActivityEnd())

        # ── Collect response ──────────────────────────────────────────────────
        async for response in session.receive():
            if getattr(response, "go_away", None) is not None:
                break

            sc = getattr(response, "server_content", None)
            if sc is None:
                continue

            # Input transcript (what the user said)
            it = getattr(sc, "input_transcription", None)
            if it:
                text = getattr(it, "text", None)
                if text:
                    input_transcript += text

            # Model text output (evaluation JSON or response text)
            mt = getattr(sc, "model_turn", None)
            if mt:
                for part in getattr(mt, "parts", []) or []:
                    text = getattr(part, "text", None)
                    if text:
                        ai_response += text

            if getattr(sc, "turn_complete", False):
                break

    return input_transcript.strip(), ai_response.strip()


# ── TTS via Gemini Live AUDIO output ─────────────────────────────────────────

async def gemini_live_speak(
    api_key: str,
    text:    str,
    voice:   str = "Kore",
    model:   str = LIVE_MODEL,
) -> bytes:
    """
    Use Gemini Live with AUDIO response modality to synthesize speech.
    Returns WAV bytes (24 kHz mono PCM wrapped in a WAV header).
    """
    client = genai.Client(
        api_key=api_key,
        http_options={"api_version": "v1beta"},
    )

    cfg = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        ),
    )

    pcm_chunks: list[bytes] = []

    async with client.aio.live.connect(model=model, config=cfg) as session:
        await session.send_client_content(
            turns=types.Content(
                parts=[types.Part.from_text(text=text)],
                role="user",
            ),
            turn_complete=True,
        )

        async for response in session.receive():
            if getattr(response, "go_away", None) is not None:
                break

            sc = getattr(response, "server_content", None)
            if sc is None:
                continue

            mt = getattr(sc, "model_turn", None)
            if mt:
                for part in getattr(mt, "parts", []) or []:
                    inline = getattr(part, "inline_data", None)
                    if inline and getattr(inline, "data", None):
                        pcm_chunks.append(inline.data)

            if getattr(sc, "turn_complete", False):
                break

    return pcm_to_wav(b"".join(pcm_chunks), OUTPUT_RATE)
