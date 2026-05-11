from __future__ import annotations

import streamlit as st


def init_state() -> None:
    defaults: dict = {
        "reading_phase":     "idle",
        "reading_article":   None,
        "reading_questions": None,
        "reading_answers":   {},
        "reading_score":     None,
        "reading_category":  "World News",
        "reading_doc_id":    None,
        "reading_error":     None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_state() -> None:
    st.session_state["reading_phase"]     = "idle"
    st.session_state["reading_article"]   = None
    st.session_state["reading_questions"] = None
    st.session_state["reading_answers"]   = {}
    st.session_state["reading_score"]     = None
    st.session_state["reading_doc_id"]    = None
    st.session_state["reading_error"]     = None
