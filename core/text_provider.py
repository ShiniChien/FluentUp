"""Text-generation provider abstraction.

Two implementations:
  OpenRouterProvider — wraps core/openrouter.async_chat (OpenAI-compatible API)
  GemmaProvider      — uses google-genai async client
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from google import genai
from google.genai.types import GenerateContentConfig

from core.openrouter import async_chat


class TextProvider(ABC):
    @abstractmethod
    async def chat(self, prompt: str, temperature: float = 0.7) -> str: ...


class OpenRouterProvider(TextProvider):
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self._base_url = base_url
        self._api_key  = api_key
        self._model    = model

    async def chat(self, prompt: str, temperature: float = 0.7) -> str:
        return await async_chat(
            base_url=self._base_url,
            api_key=self._api_key,
            model=self._model,
            prompt=prompt,
            temperature=temperature,
        )


class GemmaProvider(TextProvider):
    def __init__(self, api_key: str, model: str = "gemma-4-31b-it") -> None:
        self._client = genai.Client(api_key=api_key)
        self._model  = model

    async def chat(self, prompt: str, temperature: float = 0.7) -> str:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=GenerateContentConfig(temperature=temperature),
        )
        return response.text.strip()


def build_provider(name: str, secrets: dict) -> TextProvider:
    """Instantiate the correct provider from its name string and secrets dict."""
    if name == "gemma":
        return GemmaProvider(
            api_key=secrets["gemini_api_key"],
            model=secrets.get("gemma_model", "gemma-4-31b-it"),
        )
    return OpenRouterProvider(
        base_url=secrets["openrouter_base_url"],
        api_key=secrets["openrouter_api_key"],
        model=secrets["openrouter_model"],
    )
