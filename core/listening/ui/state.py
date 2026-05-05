from __future__ import annotations

import streamlit as st

from .constants import TOPICS


def init_state() -> None:
    defaults = {
        "echo_phase":     "idle",
        "echo_dialogue":  [],
        "echo_masked":    [],
        "echo_mode":      "fill_blank",
        "echo_topic":     TOPICS[0],
        "echo_voice_a":   "Kore",
        "echo_voice_b":   "Fenrir",
        "echo_accent_a":  "us",
        "echo_accent_b":  "us",
        "echo_n_turns":   10,
        "echo_answers":   {},
        "echo_scores":    [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
