"""
fluentup/evaluator.py
---------------------
Evaluate IELTS speaking using 4 parallel Gemini Live sessions — one per criterion.

Flow per criterion:
  user audio → Gemini Live (AUDIO mode, native) → output_audio_transcription (model's spoken eval)
             → OpenRouter LLM → parse into BandScore JSON

Using AUDIO response modality avoids the 1011 WebSocket errors caused by forcing TEXT mode.
The model's spoken evaluation is captured via output_audio_transcription, then a lightweight
OpenRouter call turns the free-form text into the required JSON structure.
"""
from __future__ import annotations

import asyncio
import json
import re

import openai

from fluentup.config import LIVE_MODEL
from fluentup.live_session import gemini_live_once, pcm_to_wav, OUTPUT_RATE
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

_PARSE_PROMPT = """\
You are a JSON formatter. The text below is a spoken IELTS evaluation for the criterion "{criterion}".
Extract the assessment and return ONLY valid JSON with this exact schema:
{{"band": <float 1.0-9.0 step 0.5>, "feedback": "<2-3 sentence assessment>", "examples": ["<quoted phrase>"], "tips": ["<actionable tip>"]}}

Spoken evaluation:
{text}"""


def _parse_band_score(criterion: str, raw: str) -> BandScore:
    """Try to extract JSON directly from raw text (fallback before OpenRouter call)."""
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
    except Exception:
        return BandScore(criterion=criterion, band=0.0, feedback=raw[:300], examples=[], tips=[])


class LiveEvaluationPipeline:
    """
    Run 4 Gemini Live sessions in parallel (AUDIO mode) to evaluate one spoken answer.
    Each session's spoken output is transcribed then parsed by OpenRouter into BandScore JSON.
    """

    def __init__(
        self,
        api_key:             str,
        model:               str = LIVE_MODEL,
        openrouter_base_url: str = "",
        openrouter_api_key:  str = "",
        openrouter_model:    str = "",
    ) -> None:
        self._api   = api_key
        self._model = model
        self._sem   = asyncio.Semaphore(4)

        self._or_client = openai.AsyncOpenAI(
            base_url=openrouter_base_url,
            api_key=openrouter_api_key,
        ) if openrouter_base_url and openrouter_api_key else None
        self._or_model = openrouter_model

    async def _parse_with_llm(self, criterion: str, text: str) -> BandScore:
        """Use OpenRouter to parse free-form spoken evaluation into BandScore JSON."""
        if not self._or_client or not text.strip():
            return _parse_band_score(criterion, text)
        try:
            resp = await self._or_client.chat.completions.create(
                model=self._or_model,
                messages=[{"role": "user", "content": _PARSE_PROMPT.format(
                    criterion=criterion, text=text
                )}],
                temperature=0.0,
            )
            raw = (resp.choices[0].message.content or "").strip()
            return _parse_band_score(criterion, raw)
        except Exception:
            return _parse_band_score(criterion, text)

    async def evaluate(
        self,
        audio_bytes: bytes,
        question:    str,
        part:        int = 1,
    ) -> EvaluationResult:
        """
        Evaluate all 4 IELTS criteria in parallel.
        Returns EvaluationResult with transcript + optional WAV bytes per criterion.
        """

        async def _eval_one(criterion: str) -> tuple[BandScore, str, bytes]:
            system_prompt = _PROMPTS[criterion].format(question=question, part=part)
            async with self._sem:
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
                    score = await self._parse_with_llm(criterion, output_tr)
                    return score, input_tr, audio_pcm
                except Exception as exc:
                    return BandScore(
                        criterion=criterion,
                        band=0.0,
                        feedback=f"Evaluation failed: {exc}",
                        examples=[],
                        tips=[],
                    ), "", b""

        results = await asyncio.gather(
            *[_eval_one(c) for c in _CRITERIA],
            return_exceptions=False,
        )

        scores = [score for score, _, _ in results]
        transcript = next((t for _, t, _ in results if t.strip()), "")

        # Collect per-criterion audio WAV (wrap PCM → WAV for browser playback)
        criterion_audio: dict[str, bytes] = {}
        for (criterion, (_, _, pcm)) in zip(_CRITERIA, results):
            if pcm:
                criterion_audio[criterion] = pcm_to_wav(pcm, OUTPUT_RATE)

        return EvaluationResult(
            transcript=transcript,
            scores=scores,
            criterion_audio=criterion_audio,
        )
