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


import json as _json

_PROVIDER_OBJ_KEY  = "_text_provider"
_PROVIDER_HASH_KEY = "_provider_config_hash"


def _config_hash(cfg: dict) -> str:
    return _json.dumps(cfg, sort_keys=True, default=str)


def _load_provider_config_from_db(secrets: dict) -> dict | None:
    store = get_store(secrets)
    if store is None:
        return None
    try:
        from core.async_utils import run_async as _run_async
        return _run_async(store.get_provider_config())
    except Exception:
        return None


def _build_config_from_secrets(secrets: dict) -> dict:
    name = secrets.get("text_provider", "openrouter")
    if name == "gemma":
        name = "google"
    return {
        "active_provider": name,
        "providers": {
            "openrouter": {
                "base_url": secrets.get("openrouter_base_url", ""),
                "api_key":  secrets.get("openrouter_api_key", ""),
                "model":    secrets.get("openrouter_model", ""),
            },
            "google": {
                "model":           secrets.get("gemma_model", "gemma-4-31b-it"),
                "thinking_budget": None,
            },
        },
    }


def get_text_provider(secrets: dict) -> TextProvider:
    """Return the active TextProvider, building and caching if needed."""
    if _PROVIDER_OBJ_KEY in st.session_state and _PROVIDER_HASH_KEY in st.session_state:
        return st.session_state[_PROVIDER_OBJ_KEY]

    db_cfg = _load_provider_config_from_db(secrets)
    cfg    = db_cfg or _build_config_from_secrets(secrets)

    if "active_provider" not in cfg:
        cfg = _build_config_from_secrets(secrets)

    h = _config_hash(cfg)

    active       = cfg.get("active_provider", "openrouter")
    provider_cfg = cfg.get("providers", {}).get(active, {})
    provider     = build_provider(active, secrets, provider_config=provider_cfg)

    st.session_state[_PROVIDER_OBJ_KEY]  = provider
    st.session_state[_PROVIDER_HASH_KEY] = h
    return provider


def set_text_provider_name(name: str) -> None:
    """Invalidate provider cache so next get_text_provider() call rebuilds."""
    st.session_state.pop(_PROVIDER_OBJ_KEY, None)
    st.session_state.pop(_PROVIDER_HASH_KEY, None)
    st.session_state.pop("question_gen", None)
