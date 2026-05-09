"""Text-generation provider abstraction."""
from __future__ import annotations

from abc import ABC, abstractmethod

from google import genai
from google.genai.types import GenerateContentConfig, ThinkingConfig

from core.openrouter import async_chat

GEMINI_MODELS = ["gemini-2.5-flash-lite", "gemini-3.1-flash-lite"]
GEMMA_MODELS  = ["gemma-4-31b-it", "gemma-4-26b-a4b-it"]
GOOGLE_MODELS = GEMINI_MODELS + GEMMA_MODELS

THINKING_LEVELS = {
    "Off":  0,
    "Low":  512,
    "High": 24576,
}


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


class GoogleProvider(TextProvider):
    def __init__(self, api_key: str, model: str, thinking_budget: int | None = None) -> None:
        self._client          = genai.Client(api_key=api_key)
        self._model           = model
        self._thinking_budget = thinking_budget

    async def chat(self, prompt: str, temperature: float = 0.7) -> str:
        thinking_config = (
            ThinkingConfig(thinking_budget=self._thinking_budget)
            if self._thinking_budget is not None
            else None
        )
        config = GenerateContentConfig(
            temperature=temperature,
            thinking_config=thinking_config,
        )
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=config,
        )
        return (response.text or "").strip()


# Backwards-compatible alias — remove after all callers migrated
GemmaProvider = GoogleProvider


def build_provider(
    name: str,
    secrets: dict,
    provider_config: dict | None = None,
) -> TextProvider:
    """Instantiate provider from name + secrets (fallback) or provider_config (DB)."""
    if name in ("google", "gemma"):
        cfg = provider_config or {}
        model           = cfg.get("model") or secrets.get("gemma_model", "gemma-4-31b-it")
        thinking_budget = cfg.get("thinking_budget")  # None for Gemma models
        return GoogleProvider(
            api_key=secrets["gemini_api_key"],
            model=model,
            thinking_budget=thinking_budget,
        )
    # openrouter (default)
    cfg = provider_config or {}
    return OpenRouterProvider(
        base_url=cfg.get("base_url") or secrets.get("openrouter_base_url", ""),
        api_key=cfg.get("api_key")   or secrets.get("openrouter_api_key", ""),
        model=cfg.get("model")       or secrets.get("openrouter_model", ""),
    )
