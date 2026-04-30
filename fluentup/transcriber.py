"""
fluentup/transcriber.py
-----------------------
Transcribe user's spoken audio via a Gemini Live session.
Input transcript is captured from input_audio_transcription (not the model's reply).
"""
from __future__ import annotations

from fluentup.live_session import LIVE_MODEL, gemini_live_once

_SYSTEM = (
    "The user is an English language learner practising IELTS speaking. "
    "Listen to their answer and acknowledge it briefly (one sentence). "
    "Preserve all hesitations (um, uh, er, like, you know) — "
    "these are captured via transcription and must not be cleaned up."
)


class GeminiLiveTranscriber:
    def __init__(self, api_key: str, model: str = LIVE_MODEL) -> None:
        self._api   = api_key
        self._model = model

    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Return the input_audio_transcription captured from Gemini Live.
        Falls back to the model's text reply if no transcription is available.
        """
        input_transcript, fallback = await gemini_live_once(
            api_key=self._api,
            system_prompt=_SYSTEM,
            wav_bytes=audio_bytes,
            model=self._model,
        )
        return input_transcript or fallback

