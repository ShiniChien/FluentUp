from __future__ import annotations

import json
import random
from datetime import datetime, timezone

from core.openrouter import async_chat

_TARGET = 1000

_TASK1_SYSTEM = """You are an IELTS Task 1 question generator.
Return ONLY valid JSON with these fields:
{
  "prompt": "<one sentence exam-style description, e.g. 'The bar chart below shows...'>",
  "chart_spec": {
    "type": "<bar|line|pie|scatter>",
    "title": "<chart title>",
    "labels": ["<label1>", "<label2>", ...],
    "datasets": [{"label": "<series name>", "values": [<number>, ...]}, ...],
    "x_label": "<axis label or empty string>",
    "y_label": "<axis label or empty string>"
  }
}
Make the data realistic and varied. Use 3-6 data points."""

_TASK2_SYSTEM = """You are an IELTS Task 2 question generator.
Return ONLY valid JSON with this field:
{
  "prompt": "<full IELTS Task 2 question, including instruction such as 'Discuss both views and give your own opinion.'>"
}
Cover a variety of topics: environment, technology, education, health, society."""


def _compute_p_generate(count: int) -> float:
    return max(0.0, 1.0 - count / _TARGET)


def _round_band(value: float) -> float:
    """Round to nearest 0.5 per IELTS convention."""
    return round(value * 2) / 2


async def _generate_task1(secrets: dict) -> dict:
    raw = await async_chat(
        base_url=secrets["openrouter_base_url"],
        api_key=secrets["openrouter_api_key"],
        model=secrets["openrouter_model"],
        prompt=_TASK1_SYSTEM,
        temperature=0.9,
    )
    data = json.loads(raw)
    return {
        "task_type":  "task1",
        "prompt":     data["prompt"],
        "chart_data": data["chart_spec"],
        "created_at": datetime.now(timezone.utc),
    }


async def _generate_task2(secrets: dict) -> dict:
    raw = await async_chat(
        base_url=secrets["openrouter_base_url"],
        api_key=secrets["openrouter_api_key"],
        model=secrets["openrouter_model"],
        prompt=_TASK2_SYSTEM,
        temperature=0.9,
    )
    data = json.loads(raw)
    return {
        "task_type":  "task2",
        "prompt":     data["prompt"],
        "chart_data": None,
        "created_at": datetime.now(timezone.utc),
    }


async def get_topic(store, task_type: str, secrets: dict) -> dict:
    """Return a topic dict, generating a new one or sampling from the pool."""
    col   = store.db.writing_topics
    count = await col.count_documents({"task_type": task_type})
    p     = _compute_p_generate(count)

    if random.random() < p:
        if task_type == "task1":
            topic = await _generate_task1(secrets)
        else:
            topic = await _generate_task2(secrets)
        await col.insert_one(topic)
        topic.pop("_id", None)
        return topic

    pipeline = [{"$match": {"task_type": task_type}}, {"$sample": {"size": 1}}]
    async for doc in col.aggregate(pipeline):
        doc.pop("_id", None)
        return doc

    # Fallback: pool was empty despite count > 0 (race condition)
    if task_type == "task1":
        topic = await _generate_task1(secrets)
    else:
        topic = await _generate_task2(secrets)
    await col.insert_one(topic)
    topic.pop("_id", None)
    return topic
