"""Tests for core/text_provider.py — uses mocks, no real API calls."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.text_provider import (
    GemmaProvider,
    GoogleProvider,
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


# ── GoogleProvider ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_google_provider_no_thinking_config_for_none_budget():
    """When thinking_budget is None, ThinkingConfig must NOT be passed."""
    fake_response = MagicMock()
    fake_response.text = "hello"

    mock_aio = AsyncMock(return_value=fake_response)
    with patch("core.text_provider.genai.Client") as mock_cls:
        mock_cls.return_value.aio.models.generate_content = mock_aio
        p = GoogleProvider(api_key="k", model="gemma-4-31b-it", thinking_budget=None)
        result = await p.chat("hi", temperature=0.5)

    assert result == "hello"
    call_kwargs = mock_aio.call_args.kwargs
    assert call_kwargs["config"].thinking_config is None


@pytest.mark.asyncio
async def test_google_provider_sets_thinking_budget_when_int():
    """When thinking_budget is 0, ThinkingConfig(thinking_budget=0) must be set."""
    fake_response = MagicMock()
    fake_response.text = "hello"

    mock_aio = AsyncMock(return_value=fake_response)
    with patch("core.text_provider.genai.Client") as mock_cls:
        mock_cls.return_value.aio.models.generate_content = mock_aio
        p = GoogleProvider(api_key="k", model="gemini-2.5-flash-lite", thinking_budget=0)
        await p.chat("hi")

    call_kwargs = mock_aio.call_args.kwargs
    assert call_kwargs["config"].thinking_config.thinking_budget == 0


@pytest.mark.asyncio
async def test_google_provider_strips_response_text():
    fake_response = MagicMock()
    fake_response.text = "  spaced  "

    mock_aio = AsyncMock(return_value=fake_response)
    with patch("core.text_provider.genai.Client") as mock_cls:
        mock_cls.return_value.aio.models.generate_content = mock_aio
        p = GoogleProvider(api_key="k", model="gemini-3.1-flash-lite", thinking_budget=512)
        result = await p.chat("q")

    assert result == "spaced"


def test_build_provider_google():
    config = {"model": "gemini-2.5-flash-lite", "thinking_budget": 0}
    with patch("core.text_provider.genai.Client"):
        p = build_provider("google", {"gemini_api_key": "k"}, provider_config=config)
    assert isinstance(p, GoogleProvider)


def test_build_provider_gemma_alias_still_works():
    """'gemma' name must still resolve to GoogleProvider for backwards compat."""
    with patch("core.text_provider.genai.Client"):
        p = build_provider("gemma", {"gemini_api_key": "k", "gemma_model": "gemma-4-31b-it"})
    assert isinstance(p, GoogleProvider)


def test_build_provider_openrouter_uses_provider_config_when_given():
    config = {"base_url": "http://x", "api_key": "k2", "model": "m2"}
    p = build_provider("openrouter", {}, provider_config=config)
    assert isinstance(p, OpenRouterProvider)
    assert p._base_url == "http://x"
    assert p._api_key == "k2"
    assert p._model == "m2"
