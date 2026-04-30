"""
fluentup/evaluator.py
---------------------
Evaluate IELTS speaking using 4 parallel Gemini Live sessions — one per criterion.

Each session receives the user's audio directly, so Gemini can:
  - Hear pronunciation, stress, intonation, connected speech  (Pronunciation)
  - Detect hesitation patterns, rhythm, filler words          (FC)
  - Assess vocabulary range from natural speech               (LR)
  - Identify grammatical structures in context               (GR)

The FC session also captures the input transcript (via input_audio_transcription)
so no separate transcription step is needed.
"""
from __future__ import annotations

import asyncio
import json
import re

from fluentup.config import LIVE_MODEL
from fluentup.live_session import gemini_live_once
from fluentup.models import BandScore, EvaluationResult
from fluentup.prompts import (
    FC_LIVE_SYSTEM,
    LR_LIVE_SYSTEM,
    GR_LIVE_SYSTEM,
    PRONUN_LIVE_SYSTEM,
)

_CRITERIA = ["FC", "LR", "GR", "Pronunciation"]
_PROMPTS  = {
    "FC":            FC_LIVE_SYSTEM,
    "LR":            LR_LIVE_SYSTEM,
    "GR":            GR_LIVE_SYSTEM,
    "Pronunciation": PRONUN_LIVE_SYSTEM,
}


def _parse_band_score(criterion: str, raw: str) -> BandScore:
    try:
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        data = json.loads(match.group() if match else cleaned)
        return BandScore(
            criterion=criterion,
            band=float(data.get("band", 0.0)),
            feedback=str(data.get("feedback", "")),
            examples=list(data.get("examples", [])),
            tips=list(data.get("tips", data.get("improvement_tips", []))),
        )
    except Exception as exc:
        return BandScore(
            criterion=criterion,
            band=0.0,
            feedback=f"Could not parse evaluation: {exc}",
            examples=[],
            tips=[],
        )


class LiveEvaluationPipeline:
    """
    Run 4 Gemini Live sessions in parallel — one per IELTS criterion.
    Audio is sent directly; no separate transcription step required.
    The transcript is captured from the FC session's input_audio_transcription.
    """

    def __init__(self, api_key: str, model: str = LIVE_MODEL) -> None:
        self._api   = api_key
        self._model = model
        # 4 criteria → 4 concurrent sessions; semaphore prevents overload
        self._sem   = asyncio.Semaphore(4)

    async def evaluate(
        self,
        audio_bytes: bytes,
        question:    str,
        part:        int = 1,
    ) -> EvaluationResult:
        """
        Evaluate all 4 IELTS criteria for a single spoken answer in parallel.
        Returns EvaluationResult with transcript captured from the FC session.
        """

        async def _eval_one(criterion: str) -> tuple[BandScore, str]:
            system_prompt = _PROMPTS[criterion].format(question=question, part=part)
            async with self._sem:
                try:
                    input_transcript, ai_response = await asyncio.wait_for(
                        gemini_live_once(
                            api_key=self._api,
                            system_prompt=system_prompt,
                            wav_bytes=audio_bytes,
                            model=self._model,
                        ),
                        timeout=60.0,
                    )
                    return _parse_band_score(criterion, ai_response), input_transcript
                except Exception as exc:
                    return BandScore(
                        criterion=criterion,
                        band=0.0,
                        feedback=f"Evaluation failed: {exc}",
                        examples=[],
                        tips=[],
                    ), ""

        results = await asyncio.gather(
            *[_eval_one(c) for c in _CRITERIA],
            return_exceptions=False,
        )

        scores = [score for score, _ in results]
        # Use the first non-empty transcript across all sessions
        transcript = next((t for _, t in results if t.strip()), "")

        return EvaluationResult(transcript=transcript, scores=scores)
