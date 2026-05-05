from __future__ import annotations

import streamlit as st


def init_state() -> None:
    defaults = {
        "echo_phase":     "idle",
        "echo_dialogue":  [],
        "echo_masked":    [],
        "echo_mode":      "fill_blank",
        "echo_topic":     "",
        "echo_voice_a":   "Kore",
        "echo_voice_b":   "Fenrir",
        "echo_accent_a":  "us",
        "echo_accent_b":  "us",
        "echo_n_turns":   10,
        "echo_answers":   {},
        "echo_scores":    [],
        "echo_q_type":    "ONE WORD ONLY",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
