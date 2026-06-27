"""core/practice/generator.py — Generate and cache practice items."""
from __future__ import annotations

import json
import logging

from google import genai
from google.genai import types

from core.live_session import pcm_to_wav
from core.config import GEMINI_API_VERSION

_logger = logging.getLogger(__name__)

_DICTATION_PROMPT = """Generate {count} short English sentences for a dictation exercise.
Difficulty: {difficulty} (easy=simple vocabulary, medium=natural speech, hard=idioms/complex grammar).
Topic: {topic}.

Return a JSON array of strings, nothing else. Example:
["The cat sat on the mat.", "She went to the store."]"""

_SHADOWING_PROMPT = """Generate {count} natural English sentences for a shadowing exercise.
Difficulty: {difficulty}. Topic: {topic}.
Sentences should have varied rhythm and natural stress patterns.

Return a JSON array of strings, nothing else."""


async def generate_sentences(
    provider,
    mode: str,
    topic: str,
    difficulty: str,
    count: int = 5,
) -> list[str]:
    """Generate sentences for dictation or shadowing via text provider."""
    template = _DICTATION_PROMPT if mode == "dictation" else _SHADOWING_PROMPT
    prompt = template.format(count=count, difficulty=difficulty, topic=topic)
    raw = await provider.chat(prompt, temperature=0.8)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        sentences = json.loads(raw)
        if isinstance(sentences, list):
            return [s for s in sentences if isinstance(s, str)]
    except Exception:
        _logger.warning("Failed to parse sentences JSON: %s", raw[:200])
    return [line.strip().strip('"') for line in raw.splitlines() if line.strip()]


async def tts_sentence(api_key: str, text: str, voice: str = "Kore") -> bytes:
    """Convert text to speech using Gemini TTS. Returns raw PCM bytes."""
    client = genai.Client(api_key=api_key, http_options={"api_version": GEMINI_API_VERSION})
    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash-preview-tts",
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        ),
    )
    return response.candidates[0].content.parts[0].inline_data.data
