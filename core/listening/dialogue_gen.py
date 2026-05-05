"""
core/listening/dialogue_gen.py
-------------------------------
Generate dialogue turns using Gemini Live only — no OpenRouter.
Each turn is generated as audio; output_audio_transcription is the ground-truth text.
"""
from __future__ import annotations

from core.config import LIVE_MODEL, SPEAKER_PERSONA
from core.live_session import gemini_live_dialogue_turn


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

    transcript, wav = await gemini_live_dialogue_turn(
        api_key=api_key,
        user_message=user_message,
        voice=voice,
        model=model,
        system_instruction=system_instruction,
    )

    return {"speaker": speaker, "text": transcript, "audio": wav}
