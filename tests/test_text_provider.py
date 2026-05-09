"""Tests for core/text_provider.py — uses mocks, no real API calls."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.text_provider import (
    GemmaProvider,
    OpenRouterProvider,
    TextProvider,
    build_provider,
)


# ── OpenRouterProvider ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_openrouter_provider_delegates_to_async_chat():
    with patch("core.text_provider.async_chat", new=AsyncMock(return_value="hello")) as mock_chat:
        p = OpenRouterProvider(base_url="http://x", api_key="k", model="m")
        result = await p.chat("hi", temperature=0.5)

    assert result == "hello"
    mock_chat.assert_awaited_once_with(
        base_url="http://x", api_key="k", model="m", prompt="hi", temperature=0.5
    )


@pytest.mark.asyncio
async def test_openrouter_provider_default_temperature():
    with patch("core.text_provider.async_chat", new=AsyncMock(return_value="ok")) as mock_chat:
        p = OpenRouterProvider(base_url="http://x", api_key="k", model="m")
        await p.chat("hi")

    _, kwargs = mock_chat.call_args
    assert kwargs["temperature"] == 0.7


# ── GemmaProvider ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gemma_provider_returns_stripped_text():
    fake_response = MagicMock()
    fake_response.text = "  answer  "

    mock_aio = AsyncMock(return_value=fake_response)

    with patch("core.text_provider.genai.Client") as mock_client_cls:
        instance = mock_client_cls.return_value
        instance.aio.models.generate_content = mock_aio

        p = GemmaProvider(api_key="k", model="gemma-4-31b-it")
        result = await p.chat("question", temperature=0.3)

    assert result == "answer"
    mock_aio.assert_awaited_once()
    call_kwargs = mock_aio.call_args.kwargs
    assert call_kwargs["model"] == "gemma-4-31b-it"
    assert call_kwargs["contents"] == "question"
    assert call_kwargs["config"].temperature == 0.3


# ── build_provider ────────────────────────────────────────────────────────────

def test_build_provider_openrouter():
    secrets = {
        "openrouter_base_url": "http://or",
        "openrouter_api_key": "k",
        "openrouter_model": "m",
        "gemini_api_key": "g",
    }
    with patch("core.text_provider.genai.Client"):
        p = build_provider("openrouter", secrets)
    assert isinstance(p, OpenRouterProvider)


def test_build_provider_gemma():
    secrets = {
        "gemini_api_key": "g",
        "gemma_model": "gemma-4-31b-it",
        "openrouter_base_url": "",
        "openrouter_api_key": "",
        "openrouter_model": "",
    }
    with patch("core.text_provider.genai.Client"):
        p = build_provider("gemma", secrets)
    assert isinstance(p, GemmaProvider)


def test_build_provider_unknown_defaults_to_openrouter():
    secrets = {
        "openrouter_base_url": "http://or",
        "openrouter_api_key": "k",
        "openrouter_model": "m",
        "gemini_api_key": "g",
    }
    with patch("core.text_provider.genai.Client"):
        p = build_provider("unknown_provider", secrets)
    assert isinstance(p, OpenRouterProvider)


def test_text_provider_is_abstract():
    with pytest.raises(TypeError):
        TextProvider()  # type: ignore[abstract]
