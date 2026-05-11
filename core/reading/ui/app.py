from __future__ import annotations

import streamlit as st

from core.shared import load_secrets, get_store
from core.reading.ui.state import init_state
from core.reading.ui.render import (
    render_idle,
    render_generating,
    render_reading,
    render_result,
)


def main() -> None:
    init_state()
    secrets = load_secrets()
    store   = get_store(secrets)

    phase = st.session_state["reading_phase"]

    if phase == "idle":
        render_idle(secrets, store)

    elif phase == "generating":
        render_generating(secrets, store)

    elif phase == "reading":
        render_reading()

    elif phase == "scoring":
        st.session_state["reading_phase"] = "result"
        st.rerun()

    elif phase == "result":
        render_result(secrets, store)

    else:
        st.session_state["reading_phase"] = "idle"
        st.rerun()
