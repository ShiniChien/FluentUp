from __future__ import annotations

import streamlit as st

from core.async_utils import get_bg_loop
from core.config import LIVE_MODEL
from core.store import FluentUpStore


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
