from __future__ import annotations

import asyncio
import json
import re
import threading

import streamlit as st

from core.openrouter import async_chat
from core.writing.topic_pool import _round_band

_EVAL_PROMPT = """You are an IELTS examiner. Evaluate the essay below strictly.
Return ONLY valid JSON:
{{
  "task_achievement": {{"band": <0-9 in 0.5 steps>, "comment": "<2-3 sentences>"}},
  "coherence_cohesion": {{"band": <0-9>, "comment": "<2-3 sentences>"}},
  "lexical_resource": {{"band": <0-9>, "comment": "<2-3 sentences>"}},
  "grammatical_range": {{"band": <0-9>, "comment": "<2-3 sentences>"}},
  "overall_band": <mean of four bands rounded to nearest 0.5>,
  "summary": "<3-4 sentences overall feedback>"
}}

Task type: {task_type}
First criterion name: {first_criterion}

Prompt:
{prompt}

Essay:
{essay}"""


def _first_criterion_name(task_type: str) -> str:
    return "Task Achievement" if task_type == "task1" else "Task Response"


def _parse_response(raw: str) -> dict:
    text = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    return json.loads(text)


def _overall_band(bands: list[float]) -> float:
    return _round_band(sum(bands) / len(bands))


def _build_prompt(task_type: str, topic: dict, essay: str) -> str:
    prompt_text = topic["prompt"]
    if task_type == "task1" and topic.get("chart_data"):
        cd = topic["chart_data"]
        prompt_text += f"\nChart: {cd.get('title','')} ({cd.get('type','')})"
    return _EVAL_PROMPT.format(
        task_type=task_type,
        first_criterion=_first_criterion_name(task_type),
        prompt=prompt_text,
        essay=essay,
    )


async def _evaluate_async(secrets: dict, task_type: str, topic: dict, essay: str) -> dict:
    prompt = _build_prompt(task_type, topic, essay)
    raw = await async_chat(
        base_url=secrets["openrouter_base_url"],
        api_key=secrets["openrouter_api_key"],
        model=secrets["openrouter_model"],
        prompt=prompt,
        temperature=0.3,
    )
    result = _parse_response(raw)
    bands = [
        result["task_achievement"]["band"],
        result["coherence_cohesion"]["band"],
        result["lexical_resource"]["band"],
        result["grammatical_range"]["band"],
    ]
    result["overall_band"] = _overall_band(bands)
    return result


def start_evaluation(secrets: dict, task_type: str, topic: dict, essay: str) -> None:
    """Launch evaluation in a daemon thread; writes result to session_state."""
    import time
    st.session_state["writing_eval_result"] = None
    st.session_state["writing_eval_started_at"] = time.time()

    def _run():
        try:
            result = asyncio.run(_evaluate_async(secrets, task_type, topic, essay))
        except Exception as exc:
            result = {"error": str(exc)}
        st.session_state["writing_eval_result"] = result

    t = threading.Thread(target=_run, daemon=True)
    t.start()
