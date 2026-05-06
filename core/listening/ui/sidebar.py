from __future__ import annotations

import streamlit as st

from core.config import ACCENT_LABELS


def render_sidebar_dict() -> None:
    # ── Speaker accent config ─────────────────────────────────────────────────
    st.sidebar.markdown("### 🗣 Speaker Accents")
    accent_options = list(ACCENT_LABELS.keys())

    col_a, col_b = st.sidebar.columns(2)
    with col_a:
        idx_a = accent_options.index(st.session_state.get("echo_accent_a", "us"))
        chosen_a = st.selectbox(
            "Speaker A", options=accent_options,
            format_func=lambda k: ACCENT_LABELS[k],
            index=idx_a, key="sidebar_accent_a",
        )
        st.session_state["echo_accent_a"] = chosen_a
    with col_b:
        idx_b = accent_options.index(st.session_state.get("echo_accent_b", "us"))
        chosen_b = st.selectbox(
            "Speaker B", options=accent_options,
            format_func=lambda k: ACCENT_LABELS[k],
            index=idx_b, key="sidebar_accent_b",
        )
        st.session_state["echo_accent_b"] = chosen_b

