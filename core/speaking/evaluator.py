"""
core/evaluator.py
---------------------
Evaluate IELTS speaking via a single Gemini Live session with thinking enabled.

Flow:
  user audio → Gemini Live (thinking=True, single examiner)
             → spoken feedback covering FC / LR / GR / Pronunciation
             → output_audio_transcription shown directly in UI
"""
from __future__ import annotations

import asyncio

from core.config import LIVE_MODEL
from core.live_session import gemini_live_once, pcm_to_wav, OUTPUT_RATE
from core.models import CriterionFeedback, EvaluationResult
from core.speaking.prompts import get_examiner_prompt

_EVAL_TIMEOUT = 90.0  # seconds — longer than before because thinking adds latency


class LiveEvaluationPipeline:
    def __init__(self, api_key: str, model: str = LIVE_MODEL, **_kwargs) -> None:
        self._api   = api_key
        self._model = model

    async def evaluate(
        self,
        audio_bytes: bytes,
        question:    str,
        part:        int = 1,
        language:    str = "vi",
    ) -> tuple[EvaluationResult, str]:
        system_prompt = get_examiner_prompt(question=question, part=part, language=language)
        try:
            input_tr, output_tr, audio_pcm = await asyncio.wait_for(
                gemini_live_once(
                    api_key=self._api,
                    system_prompt=system_prompt,
                    wav_bytes=audio_bytes,
                    model=self._model,
                    thinking=True,
                ),
                timeout=_EVAL_TIMEOUT,
            )
            wav = pcm_to_wav(audio_pcm, OUTPUT_RATE) if audio_pcm else b""
            feedback = CriterionFeedback(
                criterion="Examiner",
                feedback=output_tr,
                audio=wav,
            )
            return EvaluationResult(transcript=input_tr, feedbacks=[feedback]), input_tr
        except Exception as exc:
            feedback = CriterionFeedback(
                criterion="Examiner",
                feedback=f"Evaluation failed: {exc}",
                audio=b"",
            )
            return EvaluationResult(transcript="", feedbacks=[feedback]), ""
