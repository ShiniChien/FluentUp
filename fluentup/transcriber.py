from __future__ import annotations

from google import genai
from google.genai import types


TRANSCRIBE_PROMPT = (
    "Transcribe the following speech exactly as spoken. "
    "Preserve hesitations like 'um', 'uh', 'er', 'like', 'you know'. "
    "The speaker may have a Vietnamese accent — transcribe what is actually said. "
    "Return only the transcript text, no commentary, no timestamps."
)


class GeminiTranscriber:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def transcribe(self, audio_bytes: bytes, mime_type: str = "audio/wav") -> str:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=[
                TRANSCRIBE_PROMPT,
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            ],
        )
        return (response.text or "").strip()
