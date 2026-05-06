from __future__ import annotations

import streamlit as st

from core.shared import load_secrets, get_store
from core.listening.ui.state import init_state
from core.listening.ui.sidebar import render_sidebar_dict
from core.listening.ui.render import render_idle, render_generating, render_submitted


def main() -> None:
    init_state()
    secrets = load_secrets()
    store   = get_store(secrets)

    render_sidebar_dict(store)

    phase = st.session_state["echo_phase"]

    if phase == "idle":
        render_idle(secrets)
    elif phase == "generating":
        render_generating(secrets)
    elif phase == "submitted":
        render_submitted()
    else:
        st.session_state["echo_phase"] = "idle"
        st.rerun()
