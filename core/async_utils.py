# Streamlit's main thread is synchronous; each browser session gets a single
# persistent asyncio event loop in a daemon thread (st.session_state["_bg_loop"]).
from __future__ import annotations

import asyncio
import concurrent.futures
import threading

import streamlit as st


def get_bg_loop() -> asyncio.AbstractEventLoop:
    """
    Return the session-scoped background event loop, creating one if needed.
    Stores the loop in st.session_state["_bg_loop"] so it survives reruns.
    When a new loop must be created, any cached Motor client (store / echo_store)
    is invalidated so it can rebind to the fresh loop.
    """
    persisted = st.session_state.get("_bg_loop")
    if persisted is not None and persisted.is_running():
        return persisted

    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    st.session_state["_bg_loop"] = loop
    # Invalidate Motor-backed store objects bound to the old (dead) loop
    st.session_state.pop("store", None)
    st.session_state.pop("echo_store", None)
    return loop


def run_async(coro):
    loop = get_bg_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()
