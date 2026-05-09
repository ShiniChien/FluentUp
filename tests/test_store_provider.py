"""Tests for FluentUpStore provider config methods."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def store():
    with patch("core.store.AsyncIOMotorClient"):
        from core.store import FluentUpStore
        return FluentUpStore(uri="mongodb://localhost", username="", password="")


@pytest.mark.asyncio
async def test_get_provider_config_returns_doc(store):
    doc = {
        "_id": "config",
        "active_provider": "google",
        "providers": {"google": {"model": "gemini-2.5-flash-lite", "thinking_budget": 0}},
    }
    store._settings.find_one = AsyncMock(return_value=doc)
    result = await store.get_provider_config()
    assert result["active_provider"] == "google"
    store._settings.find_one.assert_awaited_once_with({"_id": "config"})


@pytest.mark.asyncio
async def test_get_provider_config_returns_none_when_missing(store):
    store._settings.find_one = AsyncMock(return_value=None)
    result = await store.get_provider_config()
    assert result is None


@pytest.mark.asyncio
async def test_save_provider_config_upserts(store):
    store._settings.update_one = AsyncMock()
    providers = {
        "openrouter": {"base_url": "http://x", "api_key": "k", "model": "m"},
        "google": {"model": "gemini-3.1-flash-lite", "thinking_budget": 512},
    }
    await store.save_provider_config(active="google", providers=providers)
    store._settings.update_one.assert_awaited_once_with(
        {"_id": "config"},
        {"$set": {"active_provider": "google", "providers": providers}},
        upsert=True,
    )
