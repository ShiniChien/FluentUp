from __future__ import annotations

import asyncio
import json

from openai import AsyncOpenAI

from fluentup.models import BandScore, EvaluationResult
from fluentup.prompts import (
    FC_SYSTEM, FC_PROMPT,
    LR_SYSTEM, LR_PROMPT,
    GR_SYSTEM, GR_PROMPT,
    PRON_SYSTEM, PRON_PROMPT,
)

_CRITERIA = ["FC", "LR", "GR", "Pronunciation"]


class EvaluationPipeline:
    def __init__(self, base_url: str, api_key: str, model: str):
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._sem = asyncio.Semaphore(2)

    async def evaluate(
        self, transcript: str, question: str, part: int = 1
    ) -> EvaluationResult:
        fc, lr, gr, pr = await asyncio.gather(
            self._evaluate_fc(transcript, question, part),
            self._evaluate_lr(transcript, question, part),
            self._evaluate_gr(transcript, question, part),
            self._evaluate_pronunciation(transcript),
        )
        return EvaluationResult(transcript=transcript, scores=[fc, lr, gr, pr])

    async def _evaluate_fc(self, transcript: str, question: str, part: int) -> BandScore:
        return await self._call_metric(
            "FC",
            FC_SYSTEM,
            FC_PROMPT.format(transcript=transcript, question=question, part=part),
        )

    async def _evaluate_lr(self, transcript: str, question: str, part: int) -> BandScore:
        return await self._call_metric(
            "LR",
            LR_SYSTEM,
            LR_PROMPT.format(transcript=transcript, question=question, part=part),
        )

    async def _evaluate_gr(self, transcript: str, question: str, part: int) -> BandScore:
        return await self._call_metric(
            "GR",
            GR_SYSTEM,
            GR_PROMPT.format(transcript=transcript, question=question, part=part),
        )

    async def _evaluate_pronunciation(self, transcript: str) -> BandScore:
        return await self._call_metric(
            "Pronunciation",
            PRON_SYSTEM,
            PRON_PROMPT.format(transcript=transcript),
        )

    async def _call_metric(self, criterion: str, system: str, user: str) -> BandScore:
        async with self._sem:
            try:
                resp = await asyncio.wait_for(
                    self._client.chat.completions.create(
                        model=self._model,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        temperature=0.3,
                        response_format={"type": "json_object"},
                    ),
                    timeout=30.0,
                )
                raw = resp.choices[0].message.content or "{}"
                data = json.loads(raw)
                return BandScore(
                    criterion=criterion,
                    band=float(data.get("band", 0.0)),
                    feedback=data.get("feedback", ""),
                    examples=data.get("examples", []),
                    tips=data.get("improvement_tips", []),
                )
            except Exception as e:
                return BandScore(
                    criterion=criterion,
                    band=0.0,
                    feedback=f"Evaluation failed: {e}",
                    examples=[],
                    tips=[],
                )
