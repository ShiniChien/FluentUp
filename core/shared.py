from __future__ import annotations

import streamlit as st

from core.async_utils import get_bg_loop
from core.config import LIVE_MODEL
from core.store import FluentUpStore
from core.text_provider import TextProvider, build_provider


def load_secrets() -> dict:
    """Read all required secrets from .streamlit/secrets.toml."""
    return {
        "gemini_api_key":      st.secrets.get("GEMINI_API_KEY", ""),
        "live_model":          st.secrets.get("GEMINI_LIVE_MODEL", LIVE_MODEL),
        "mongodb_uri":         st.secrets.get("MONGODB_URI", ""),
        "mongodb_username":    st.secrets.get("MONGODB_USERNAME", ""),
        "mongodb_password":    st.secrets.get("MONGODB_PASSWORD", ""),
        "openrouter_base_url": st.secrets.get("OPENROUTER_BASE_URL", ""),
        "openrouter_api_key":  st.secrets.get("OPENROUTER_API_KEY", ""),
        "openrouter_model":    st.secrets.get("OPENROUTER_MODEL", ""),
        "text_provider":       st.secrets.get("TEXT_PROVIDER", "openrouter"),
        "gemma_model":         st.secrets.get("GEMMA_MODEL", "gemma-4-31b-it"),
    }


def get_store(secrets: dict | None = None) -> FluentUpStore | None:
    # Reuse across reruns; value may be None when MongoDB credentials are missing.
    if "store" in st.session_state:
        return st.session_state["store"]

    if secrets is None:
        secrets = load_secrets()

    if secrets["mongodb_uri"]:
        get_bg_loop()  # Motor client must bind to an already-running loop
        store = FluentUpStore(
            uri=secrets["mongodb_uri"],
            username=secrets["mongodb_username"],
            password=secrets["mongodb_password"],
        )
        st.session_state["store"] = store
        return store

    st.session_state["store"] = None
    return None


_PROVIDER_KEY = "text_provider"          # session_state string key (name)
_PROVIDER_OBJ_KEY = "_text_provider"     # session_state cached instance


def get_text_provider(secrets: dict) -> TextProvider:
    """Return the active TextProvider, building and caching if needed."""
    if _PROVIDER_OBJ_KEY in st.session_state:
        return st.session_state[_PROVIDER_OBJ_KEY]

    name = st.session_state.get(_PROVIDER_KEY)

    if name is None:
        # Try MongoDB settings collection
        store = get_store(secrets)
        if store is not None:
            try:
                from core.async_utils import run_async as _run_async
                doc = _run_async(
                    store._client["fluentup"]["settings"].find_one({"_id": "config"})
                )
                if doc:
                    name = doc.get(_PROVIDER_KEY)
            except Exception:
                pass

    if name is None:
        name = secrets.get("text_provider", "openrouter")

    provider = build_provider(name, secrets)
    st.session_state[_PROVIDER_OBJ_KEY] = provider
    st.session_state[_PROVIDER_KEY] = name
    return provider


def set_text_provider(name: str, secrets: dict) -> None:
    """Switch active provider; clears cached instance so next call rebuilds."""
    st.session_state[_PROVIDER_KEY] = name
    st.session_state.pop(_PROVIDER_OBJ_KEY, None)
