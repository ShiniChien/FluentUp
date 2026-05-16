from __future__ import annotations

import asyncio
import json
import math
import re
import threading
import time

from core.log import get_logger

_logger = get_logger(__name__)

import streamlit as st

_RESULT_LOCK = threading.Lock()

from core.text_provider import TextProvider
from core.writing.topic_pool import _round_band

_EVAL_PROMPT = """You are an IELTS examiner. Evaluate the writing below strictly.
Return ONLY valid JSON:
{{
  "task_achievement": {{"band": <1-9 in 0.5 steps>, "comment": "<2-3 sentences>"}},
  "coherence_cohesion": {{"band": <1-9>, "comment": "<2-3 sentences>"}},
  "lexical_resource": {{"band": <1-9>, "comment": "<2-3 sentences>"}},
  "grammatical_range": {{"band": <1-9>, "comment": "<2-3 sentences>"}},
  "overall_band": <mean of four bands rounded to nearest 0.5>,
  "summary": "<3-4 sentences overall feedback>"
}}

Task type: {task_type}
First criterion name: {first_criterion}

{task_structure_note}

Prompt:
{prompt}

Essay:
{essay}"""

_TASK1_STRUCTURE_NOTE = """For Task 1, the ideal response has 4 parts:
- Intro (~1 sentence): paraphrase the prompt
- Overview (~2 sentences): highlight key trends/features WITHOUT specific data
- Body paragraph 1: describe and compare key data groups with specific figures
- Body paragraph 2: describe remaining data with comparisons
For Map/Process: describe ALL steps or changes systematically.
Minimum 150 words."""

_TASK2_STRUCTURE_NOTE = """For Task 2, the ideal response has:
- Introduction: background + clear thesis/position
- Body paragraphs (2-3): each with clear topic sentence, evidence, explanation
- Conclusion: summarise position without adding new ideas
Minimum 250 words."""


def _first_criterion_name(task_type: str) -> str:
    return "Task Achievement" if task_type == "task1" else "Task Response"


def _parse_response(raw: str) -> dict:
    text = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    try:
        start = text.index('{')
        end   = text.rindex('}') + 1
        text  = text[start:end]
    except ValueError:
        pass
    return json.loads(text)


def _overall_band(bands: list[float]) -> float:
    return _round_band(sum(bands) / len(bands))


def _build_prompt(task_type: str, topic: dict, essay: str) -> str:
    prompt_text = topic["prompt"]
    if task_type == "task1" and topic.get("chart_data"):
        cd = topic["chart_data"]
        prompt_text += f"\nChart: {cd.get('title','')} ({cd.get('type','')})"
    structure_note = _TASK1_STRUCTURE_NOTE if task_type == "task1" else _TASK2_STRUCTURE_NOTE
    return _EVAL_PROMPT.format(
        task_type=task_type,
        first_criterion=_first_criterion_name(task_type),
        task_structure_note=structure_note,
        prompt=prompt_text,
        essay=essay,
    )


async def _evaluate_async(provider: TextProvider, task_type: str, topic: dict, essay: str) -> dict:
    prompt = _build_prompt(task_type, topic, essay)
    raw = await provider.chat(prompt, temperature=0.3)
    result = _parse_response(raw)
    bands = [
        result["task_achievement"]["band"],
        result["coherence_cohesion"]["band"],
        result["lexical_resource"]["band"],
        result["grammatical_range"]["band"],
    ]
    result["overall_band"] = _overall_band(bands)
    return result


def start_evaluation(provider: TextProvider, task_type: str, topic: dict, essay: str) -> None:
    """Launch evaluation in a daemon thread; writes result to session_state."""
    st.session_state["writing_eval_result"] = None
    st.session_state["writing_eval_started_at"] = time.time()

    def _run():
        try:
            result = asyncio.run(asyncio.wait_for(
                _evaluate_async(provider, task_type, topic, essay), timeout=115.0
            ))
        except asyncio.TimeoutError:
            _logger.error("writing evaluation timed out after 115s")
            result = {"error": "Evaluation timed out — please try again."}
        except Exception as exc:
            _logger.exception("writing evaluation failed (task_type=%s)", task_type)
            result = {"error": str(exc)}
        with _RESULT_LOCK:
            st.session_state["writing_eval_result"] = result

    t = threading.Thread(target=_run, daemon=True)
    t.start()
