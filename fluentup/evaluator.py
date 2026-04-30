"""
fluentup/evaluator.py
---------------------
Evaluate IELTS speaking via Gemini Live (AUDIO mode) + OpenRouter JSON parsing.

Flow per criterion:
  user audio → Gemini Live (AUDIO native) → output_audio_transcription (spoken eval)
             → OpenRouter LLM → BandScore JSON

eval_one() is exposed publicly so app.py can run each criterion in its own thread
and stream results to the UI as they complete.
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

CRITERIA = ["FC", "LR", "GR", "Pronunciation"]

_PROMPTS = {
    "FC":            FC_LIVE_SYSTEM,
    "LR":            LR_LIVE_SYSTEM,
    "GR":            GR_LIVE_SYSTEM,
    "Pronunciation": PRONUN_LIVE_SYSTEM,
}

_PARSE_PROMPT = """\
You are a JSON formatter. The text below is a spoken IELTS evaluation for the criterion "{criterion}".
Extract the assessment and return ONLY valid JSON with this exact schema — no markdown, no extra text:
{{"band": <float 1.0-9.0 step 0.5>, "weak_points": ["<issue>"], "improvements": ["<actionable tip>"]}}

Spoken evaluation:
{text}"""


def _parse_band_score(criterion: str, raw: str) -> BandScore:
    try:
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        data = json.loads(match.group() if match else cleaned)
        return BandScore(
            criterion=criterion,
            band=float(data.get("band", 0.0)),
            feedback="",
            examples=[],
            tips=list(data.get("improvements", data.get("tips", []))),
            weak_points=list(data.get("weak_points", [])),
        )
    except Exception:
        return BandScore(criterion=criterion, band=0.0, feedback=raw[:300],
                         examples=[], tips=[], weak_points=[])


class LiveEvaluationPipeline:
    def __init__(
        self,
        api_key:             str,
        model:               str = LIVE_MODEL,
        openrouter_base_url: str = "",
        openrouter_api_key:  str = "",
        openrouter_model:    str = "",
    ) -> None:
        self._api      = api_key
        self._model    = model
        self._or_client = openai.AsyncOpenAI(
            base_url=openrouter_base_url,
            api_key=openrouter_api_key,
        ) if openrouter_base_url and openrouter_api_key else None
        self._or_model = openrouter_model

    async def _parse_with_llm(self, criterion: str, text: str) -> BandScore:
        if not self._or_client or not text.strip():
            return _parse_band_score(criterion, text)
        try:
            resp = await self._or_client.chat.completions.create(
                model=self._or_model,
                messages=[{"role": "user", "content": _PARSE_PROMPT.format(
                    criterion=criterion, text=text,
                )}],
                temperature=0.0,
            )
            raw = (resp.choices[0].message.content or "").strip()
            return _parse_band_score(criterion, raw)
        except Exception:
            return _parse_band_score(criterion, text)

    async def eval_one(
        self,
        criterion:   str,
        audio_bytes: bytes,
        question:    str,
        part:        int = 1,
    ) -> tuple[BandScore, str, bytes]:
        """
        Evaluate a single criterion.
        Returns (score, input_transcript, audio_wav_bytes).
        Call this from separate threads (each with asyncio.run) for streaming UI.
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
            score = await self._parse_with_llm(criterion, output_tr)
            wav = pcm_to_wav(audio_pcm, OUTPUT_RATE) if audio_pcm else b""
            return score, input_tr, wav
        except Exception as exc:
            return BandScore(
                criterion=criterion, band=0.0,
                feedback=f"Evaluation failed: {exc}",
                examples=[], tips=[], weak_points=[],
            ), "", b""

    async def evaluate(
        self,
        audio_bytes: bytes,
        question:    str,
        part:        int = 1,
    ) -> EvaluationResult:
        """Evaluate all 4 criteria in parallel (for non-streaming callers)."""
        results = await asyncio.gather(
            *[self.eval_one(c, audio_bytes, question, part) for c in CRITERIA],
            return_exceptions=False,
        )
        scores     = [score for score, _, _ in results]
        transcript = next((t for _, t, _ in results if t.strip()), "")
        criterion_audio = {
            CRITERIA[i]: wav
            for i, (_, _, wav) in enumerate(results)
            if wav
        }
        return EvaluationResult(transcript=transcript, scores=scores,
                                criterion_audio=criterion_audio)
