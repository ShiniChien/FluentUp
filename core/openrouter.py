"""Shared OpenRouter helper — one place to create client and call chat."""
from __future__ import annotations

import openai


async def async_chat(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    temperature: float = 0.7,
) -> str:
    client = openai.AsyncOpenAI(base_url=base_url, api_key=api_key)
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return (resp.choices[0].message.content or "").strip()
