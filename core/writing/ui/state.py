from __future__ import annotations
import streamlit as st


def init_state() -> None:
    defaults: dict = {
        "writing_phase":       "idle",
        "writing_task_type":   None,
        "writing_topic":       None,
        "writing_essay":       "",
        "writing_eval_result": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_state() -> None:
    st.session_state["writing_phase"]       = "idle"
    st.session_state["writing_task_type"]   = None
    st.session_state["writing_topic"]       = None
    st.session_state["writing_essay"]       = ""
    st.session_state["writing_eval_result"] = None
