from __future__ import annotations

import json

import httpx

from core.text_provider import TextProvider
from core.reading.prompts import (
    CONTENT_REWRITE_PROMPT,
    QUESTION_GEN_PROMPT,
    QUESTION_GEN_RETRY_PROMPT,
)

_JINA_BASE = "https://r.jina.ai/"
_TIMEOUT   = 30


async def fetch_markdown(url: str) -> str:
    """Fetch article content as markdown via r.jina.ai."""
    jina_url = _JINA_BASE + url
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            jina_url, timeout=_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/markdown"},
            follow_redirects=True,
        )
        resp.raise_for_status()
    return resp.text


async def rewrite_content(markdown: str, provider: TextProvider) -> str:
    """LLM Phase 1: rewrite raw markdown into clean reading passage."""
    prompt = CONTENT_REWRITE_PROMPT.format(markdown=markdown[:8000])
    return await provider.chat(prompt, temperature=0.3)


async def generate_questions(content: str, provider: TextProvider) -> dict:
    """LLM Phase 2: generate fill-blank questions from rewritten passage.

    Returns dict with keys: requirement (str), questions (list[dict]).
    Retries once on JSON parse failure.
    """
    prompt = QUESTION_GEN_PROMPT.format(content=content)
    raw = await provider.chat(prompt, temperature=0.3)
    result = _parse_json(raw)
    if result is None:
        retry = QUESTION_GEN_RETRY_PROMPT.format(content=content)
        raw = await provider.chat(retry, temperature=0.1)
        result = _parse_json(raw)
    if result is None:
        raise ValueError("LLM did not return valid JSON after retry.")
    _validate(result)
    return result


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


def _validate(data: dict) -> None:
    if "requirement" not in data or not isinstance(data.get("questions"), list):
        raise ValueError("Missing 'requirement' or 'questions' in LLM response.")
    for q in data["questions"]:
        if "sentence" not in q or "answer" not in q:
            raise ValueError(f"Question missing 'sentence' or 'answer': {q}")
