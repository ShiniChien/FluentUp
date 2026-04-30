"""
fluentup/evaluator.py
---------------------
Evaluate IELTS speaking using 4 parallel Gemini Live sessions — one per criterion.

Each session receives the user's audio directly, so Gemini can:
  - Hear pronunciation, stress, intonation, connected speech  (Pronunciation)
  - Detect hesitation patterns, rhythm, filler words          (FC)
  - Assess vocabulary range from natural speech               (LR)
  - Identify grammatical structures in context               (GR)

Semaphore(2) limits concurrent sessions to avoid rate limits.
"""
from __future__ import annotations

import asyncio
import json
import re

from fluentup.live_session import LIVE_MODEL, gemini_live_once
from fluentup.models import BandScore, EvaluationResult
from fluentup.prompts import (
    FC_LIVE_SYSTEM,
    LR_LIVE_SYSTEM,
    GR_LIVE_SYSTEM,
    PRONUN_LIVE_SYSTEM,
)

_CRITERIA = ["FC", "LR", "GR", "Pronunciation"]


def _parse_band_score(criterion: str, raw: str) -> BandScore:
    """Extract JSON from the model's text response; return a fallback on failure."""
    try:
        # Strip markdown fences if present
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        # Find the first {...} block
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
    Run 4 Gemini Live sessions in parallel to evaluate one spoken answer.
    Each session uses a criterion-specific system prompt and receives the
    same audio, giving the model direct access to the user's speech.
    """

    def __init__(self, api_key: str, model: str = LIVE_MODEL) -> None:
        self._api   = api_key
        self._model = model
        self._sem   = asyncio.Semaphore(2)  # max 2 concurrent Live sessions

    async def evaluate(
        self,
        audio_bytes: bytes,
        transcript:  str,
        question:    str,
        part:        int = 1,
    ) -> EvaluationResult:
        """
        Evaluate all 4 IELTS criteria for a single spoken answer.
        The transcript is injected into each system prompt as context.
        """
        systems = {
            "FC":            FC_LIVE_SYSTEM.format(question=question, part=part, transcript=transcript),
            "LR":            LR_LIVE_SYSTEM.format(question=question, part=part, transcript=transcript),
            "GR":            GR_LIVE_SYSTEM.format(question=question, part=part, transcript=transcript),
            "Pronunciation": PRONUN_LIVE_SYSTEM.format(question=question, part=part, transcript=transcript),
        }

        async def _eval_one(criterion: str, system_prompt: str) -> BandScore:
            async with self._sem:
                try:
                    _, ai_response = await asyncio.wait_for(
                        gemini_live_once(
                            api_key=self._api,
                            system_prompt=system_prompt,
                            wav_bytes=audio_bytes,
                            model=self._model,
                        ),
                        timeout=45.0,
                    )
                    return _parse_band_score(criterion, ai_response)
                except Exception as exc:
                    return BandScore(
                        criterion=criterion,
                        band=0.0,
                        feedback=f"Evaluation failed: {exc}",
                        examples=[],
                        tips=[],
                    )

        scores = await asyncio.gather(
            *[_eval_one(c, systems[c]) for c in _CRITERIA],
            return_exceptions=False,
        )

        return EvaluationResult(transcript=transcript, scores=list(scores))
