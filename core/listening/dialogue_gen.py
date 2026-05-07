"""
core/listening/dialogue_gen.py
-------------------------------
Generate dialogue turns using Gemini Live only — no OpenRouter.
Each turn is generated as audio; output_audio_transcription is the ground-truth text.
"""
from __future__ import annotations

from core.config import LIVE_MODEL
from core.listening.prompts import SPEAKER_PERSONA
from core.live_session import GeminiLiveSession


async def generate_turn(
    topic: str,
    speaker: str,
    voice: str,
    history: list[dict],
    api_key: str,
    model: str = LIVE_MODEL,
    accent_instruction: str = "",
) -> dict:
    """
    Generate a single dialogue turn for `speaker` ("A" or "B").
    Returns {"speaker": str, "text": str, "audio": bytes}.
    """
    system_instruction = SPEAKER_PERSONA.format(
        speaker=speaker,
        topic=topic,
        accent_instruction=accent_instruction,
    )

    if history:
        history_text = "\n".join(
            f"Speaker {t['speaker']}: {t['text']}" for t in history
        )
        user_message = (
            f"Conversation so far:\n{history_text}\n\n"
            f"Now say your next line as Speaker {speaker}."
        )
    else:
        user_message = (
            f"Start a casual conversation about '{topic}' as Speaker {speaker}. "
            "Say your opening line."
        )

    live = GeminiLiveSession(api_key, model)
    result = await live.run(
        text=user_message,
        voice=voice,
        system_instruction=system_instruction,
    )
    return {"speaker": speaker, "text": result.output_transcript, "audio": result.audio_wav}
