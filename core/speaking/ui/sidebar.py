from __future__ import annotations

import streamlit as st

from core.speaking.config import ACCENT_LABELS, DEFAULT_ACCENT, DEFAULT_FEEDBACK_LANGUAGE, FEEDBACK_LANGUAGE_LABELS
from core.speaking.session import ExamSession
from core.speaking.ui.helpers import clear_streaming_state


def render_sidebar(secrets: dict) -> None:
    with st.sidebar:
        st.markdown("## Speaking")

        st.markdown("**Examiner Accent**")
        accent_options = list(ACCENT_LABELS.keys())
        current = st.session_state.get("examiner_accent", DEFAULT_ACCENT)
        selected_idx = accent_options.index(current) if current in accent_options else 0
        chosen = st.selectbox(
            "Voice accent",
            options=accent_options,
            format_func=lambda a: ACCENT_LABELS[a],
            index=selected_idx,
            key="accent_select",
            label_visibility="collapsed",
        )
        st.session_state["examiner_accent"] = chosen

        st.markdown("**Ngôn ngữ nhận xét**")
        lang_options = list(FEEDBACK_LANGUAGE_LABELS.keys())
        current_lang = st.session_state.get("feedback_language", DEFAULT_FEEDBACK_LANGUAGE)
        lang_idx = lang_options.index(current_lang) if current_lang in lang_options else 0
        chosen_lang = st.selectbox(
            "Feedback language",
            options=lang_options,
            format_func=lambda l: FEEDBACK_LANGUAGE_LABELS[l],
            index=lang_idx,
            key="lang_select",
            label_visibility="collapsed",
        )
        st.session_state["feedback_language"] = chosen_lang

        st.divider()

        st.markdown("**Listening Mode**")
        st.toggle(
            "Hide question text, auto-play audio",
            value=st.session_state.get("listening_mode", True),
            key="listening_mode",
        )

        st.divider()

        sess: ExamSession = st.session_state.session
        if sess.phase != "home":
            if st.button("New Session", use_container_width=True):
                st.session_state.session = ExamSession()
                clear_streaming_state()
                st.rerun()
