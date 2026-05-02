"""
fluentup/evaluator.py
---------------------
Evaluate IELTS speaking via Gemini Live (AUDIO mode).

Flow per criterion:
  user audio → Gemini Live (spoken examiner) → output_audio_transcription (feedback text)
                                             → audio PCM (feedback audio for playback)

eval_one() returns (CriterionFeedback, input_transcript) and is called from separate
threads so results stream to the UI as they arrive.
"""
from __future__ import annotations

import asyncio

from fluentup.config import LIVE_MODEL
from fluentup.live_session import gemini_live_once, pcm_to_wav, OUTPUT_RATE
from fluentup.models import CriterionFeedback
from fluentup.prompts import (
    FC_LIVE_SYSTEM,
    LR_LIVE_SYSTEM,
    GR_LIVE_SYSTEM,
    PRONUN_LIVE_SYSTEM,
)

CRITERIA = ["FC", "LR", "GR", "Pronunciation"]

_PROMPTS = {
    "FC":            FC_LIVE_SYSTEM,
    "LR":            LR_LIVE_SYSTEM,
    "GR":            GR_LIVE_SYSTEM,
    "Pronunciation": PRONUN_LIVE_SYSTEM,
}


class LiveEvaluationPipeline:
    def __init__(self, api_key: str, model: str = LIVE_MODEL, **_kwargs) -> None:
        self._api   = api_key
        self._model = model
        # **_kwargs absorbs legacy openrouter_* params so call sites need no update

    async def eval_one(
        self,
        criterion:   str,
        audio_bytes: bytes,
        question:    str,
        part:        int = 1,
    ) -> tuple[CriterionFeedback, str]:
        """
        Evaluate a single criterion via Gemini Live.
        Returns (CriterionFeedback, input_transcript).
        Call from separate threads (each with asyncio.run) for streaming UI.
        """
        system_prompt = _PROMPTS[criterion].format(question=question, part=part)
        try:
            input_tr, output_tr, audio_pcm = await asyncio.wait_for(
                gemini_live_once(
                    api_key=self._api,
                    system_prompt=system_prompt,
                    wav_bytes=audio_bytes,
                    model=self._model,
                ),
                timeout=60.0,
            )
            wav = pcm_to_wav(audio_pcm, OUTPUT_RATE) if audio_pcm else b""
            return CriterionFeedback(
                criterion=criterion,
                feedback=output_tr,
                audio=wav,
            ), input_tr
        except Exception as exc:
            return CriterionFeedback(
                criterion=criterion,
                feedback=f"Evaluation failed: {exc}",
                audio=b"",
            ), ""
