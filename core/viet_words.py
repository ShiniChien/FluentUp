"""Shared utilities for Vietnamese word seeding and topic generation."""
from __future__ import annotations

import random
import re
from pathlib import Path

from core.openrouter import async_chat

_VIET11K_PATH = Path(__file__).parent / "Viet11K.txt"
_viet_words: list[str] | None = None

_TOPIC_PROMPT = (
    "Generate a single conversational dialogue topic suitable for an IELTS listening exercise. "
    "The topic must be a short, specific scenario or situation — maximum 10 words. "
    "Output ONLY the topic text, nothing else.\n"
    "For inspiration, use 1–3 of these Vietnamese concept words as a thematic seed "
    "(translate / interpret them freely): {seeds}"
)


def load_viet_words() -> list[str]:
    global _viet_words
    if _viet_words is None:
        try:
            lines = _VIET11K_PATH.read_text(encoding="utf-8").splitlines()
            _viet_words = [ln.strip() for ln in lines if ln.strip()]
        except Exception:
            _viet_words = []
    return _viet_words


def seed_words(n: int = 2) -> list[str]:
    words = load_viet_words()
    if not words:
        return []
    return random.sample(words, min(n, len(words)))


async def generate_topic(
    openrouter_base_url: str,
    openrouter_api_key: str,
    openrouter_model: str,
    n_seeds: int = 2,
) -> str:
    seeds = seed_words(n_seeds)
    prompt = _TOPIC_PROMPT.format(seeds=", ".join(seeds) if seeds else "everyday life")
    topic = await async_chat(
        base_url=openrouter_base_url,
        api_key=openrouter_api_key,
        model=openrouter_model,
        prompt=prompt,
        temperature=0.9,
    )
    topic = re.sub(r'^["\']|["\']$', "", topic)
    words = topic.split()
    return " ".join(words[:10])
