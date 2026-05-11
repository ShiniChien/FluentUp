from __future__ import annotations

import json

from core.reading.prompts import QUESTION_GEN_PROMPT, QUESTION_GEN_RETRY_PROMPT
from core.reading.rss_fetcher import ArticleData
from core.text_provider import TextProvider


async def generate_questions(article: ArticleData, provider: TextProvider) -> dict:
    """Call LLM and return parsed question dict. Retries once on JSON parse failure."""
    prompt = QUESTION_GEN_PROMPT.format(title=article.title, body=article.body)
    raw = await provider.chat(prompt, temperature=0.3)
    questions = _parse_json(raw)
    if questions is None:
        retry_prompt = QUESTION_GEN_RETRY_PROMPT.format(title=article.title, body=article.body)
        raw = await provider.chat(retry_prompt, temperature=0.1)
        questions = _parse_json(raw)
    if questions is None:
        raise ValueError("LLM did not return valid JSON after retry.")
    _validate(questions)
    return questions


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None


def _validate(q: dict) -> None:
    for key in ("tfng", "headings", "fill_blank", "mcq"):
        if key not in q or not isinstance(q[key], list):
            raise ValueError(f"Missing or invalid key in LLM response: {key!r}")
