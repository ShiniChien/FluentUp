from __future__ import annotations

import json
import math
import random
from datetime import datetime, timezone

from core.text_provider import TextProvider

_TARGET = 1000

_TASK1_SYSTEM = """You are an IELTS Task 1 question generator.
Return ONLY valid JSON with these fields based on the chart type you choose.

Choose ONE chart type from: bar, line, pie, scatter, table, map, process, mixed

Common schema:
{
  "prompt": "<one sentence IELTS exam-style description>",
  "chart_spec": {
    "type": "<chosen type>",
    "title": "<chart title>",
    "labels": [...],
    "datasets": [...],
    "x_label": "<or empty string>",
    "y_label": "<or empty string>"
  }
}

Type-specific rules:
- bar/line/scatter: labels=x-axis categories, datasets=[{label, values:[numbers]}]
- pie: labels=slice names, datasets=[{label, values:[numbers]}] (one dataset)
- table: labels=column headers, datasets=[{label=row name, values=[cell values]}]
- map: labels=location names, datasets=[{label=time period, values=[what is at each location (string)]}]
- process: labels=step descriptions (e.g. "Cut trees"), datasets=[{label="Process", values=[labels repeated or empty]}]
- mixed: labels=x-axis, datasets=[{label, values:[numbers], chart_subtype:"bar"}, {label, values:[numbers], chart_subtype:"line"}]

Make data realistic and varied. Use 3-6 data points. Vary chart types across calls."""

_TASK2_SYSTEM = """You are an IELTS Task 2 question generator.
Return ONLY valid JSON with this field:
{
  "prompt": "<full IELTS Task 2 question, including instruction such as 'Discuss both views and give your own opinion.'>"
}
Cover a variety of topics: environment, technology, education, health, society."""


def _compute_p_generate(count: int) -> float:
    return max(0.0, 1.0 - count / _TARGET)


def _round_band(value: float) -> float:
    """Round to nearest 0.5 per IELTS convention (arithmetic, not banker's)."""
    return math.floor(value * 2 + 0.5) / 2


async def _generate_task1(provider: TextProvider) -> dict:
    raw = await provider.chat(_TASK1_SYSTEM, temperature=0.9)
    data = json.loads(raw)
    return {
        "task_type":  "task1",
        "prompt":     data["prompt"],
        "chart_data": data["chart_spec"],
        "created_at": datetime.now(timezone.utc),
    }


async def _generate_task2(provider: TextProvider) -> dict:
    raw = await provider.chat(_TASK2_SYSTEM, temperature=0.9)
    data = json.loads(raw)
    return {
        "task_type":  "task2",
        "prompt":     data["prompt"],
        "chart_data": None,
        "created_at": datetime.now(timezone.utc),
    }


async def get_topic(store, task_type: str, provider: TextProvider) -> dict:
    """Return a topic dict, generating a new one or sampling from the pool."""
    col   = store._client["fluentup"]["writing_topics"]
    count = await col.count_documents({"task_type": task_type})
    p     = _compute_p_generate(count)

    if random.random() < p:
        topic = await (_generate_task1(provider) if task_type == "task1" else _generate_task2(provider))
        await col.insert_one(topic)
        topic.pop("_id", None)
        return topic

    pipeline = [{"$match": {"task_type": task_type}}, {"$sample": {"size": 1}}]
    async for doc in col.aggregate(pipeline):
        doc.pop("_id", None)
        return doc

    topic = await (_generate_task1(provider) if task_type == "task1" else _generate_task2(provider))
    await col.insert_one(topic)
    topic.pop("_id", None)
    return topic
