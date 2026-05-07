from __future__ import annotations

import asyncio

from core.config import ENGLISH_ACCENTS, LIVE_MODEL
from core.live_session import GeminiLiveSession
from core.models import CriterionFeedback, EvaluationResult
from core.speaking.prompts import get_examiner_prompt

_EVAL_TIMEOUT = 90.0  # seconds — longer than before because thinking adds latency


class SpeakingEvaluator:
    def __init__(self, api_key: str, model: str = LIVE_MODEL, **_kwargs) -> None:
        self._live = GeminiLiveSession(api_key, model)

    async def evaluate(
        self,
        audio_bytes: bytes,
        question:    str,
        part:        int = 1,
        language:    str = "vi",
        accent:      str = "us",
    ) -> tuple[EvaluationResult, str]:
        accent_instruction = ENGLISH_ACCENTS.get(accent, ENGLISH_ACCENTS["us"])
        system_prompt = get_examiner_prompt(
            question=question,
            part=part,
            language=language,
            accent_instruction=accent_instruction,
        )
        try:
            result = await asyncio.wait_for(
                self._live.run(
                    audio_wav=audio_bytes,
                    system_instruction=system_prompt,
                    thinking=True,
                    with_input_transcript=True,
                ),
                timeout=_EVAL_TIMEOUT,
            )
            feedback = CriterionFeedback(
                criterion="Examiner",
                feedback=result.output_transcript,
                audio=result.audio_wav,
            )
            return EvaluationResult(transcript=result.input_transcript, feedbacks=[feedback]), result.input_transcript
        except Exception as exc:
            feedback = CriterionFeedback(
                criterion="Examiner",
                feedback=f"Evaluation failed: {exc}",
                audio=b"",
            )
            return EvaluationResult(transcript="", feedbacks=[feedback]), ""
