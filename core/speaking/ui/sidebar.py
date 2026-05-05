from __future__ import annotations

import streamlit as st

from core.auth import current_user
from core.config import ACCENT_LABELS, DEFAULT_ACCENT, DEFAULT_FEEDBACK_LANGUAGE, FEEDBACK_LANGUAGE_LABELS
from core.speaking.session import ExamSession
from .helpers import clear_streaming_state



def render_sidebar(secrets: dict) -> None:
    with st.sidebar:
        st.markdown("## Speaking")
        st.caption("IELTS Speaking Practice")

        # User info
        user = current_user()
        if user:
            name = user.get("name") or user.get("username", "")
            st.markdown(
                f"<div style='background:#E3F2FD;border-left:3px solid #1565C0;"
                f"padding:6px 10px;border-radius:4px;font-size:0.85em;color:#1a1a1a'>"
                f"👤 <b>{name}</b></div>",
                unsafe_allow_html=True,
            )

        st.divider()
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

        st.divider()
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

        sess: ExamSession = st.session_state.session
        phase = sess.phase

        st.markdown("**Session Progress**")
        p1_done = len(sess.part_turns(1))
        p2_done = len(sess.part_turns(2))
        p3_done = len(sess.part_turns(3))

        if p1_done > 0:
            st.caption(f"Part 1: {p1_done} answer(s)")
        if p2_done > 0:
            st.caption(f"Part 2: {p2_done} speech(es)")
        if p3_done > 0:
            st.caption(f"Part 3: {p3_done} answer(s)")

        if not any([p1_done, p2_done, p3_done]):
            st.caption("No answers yet.")

        st.divider()

        if phase != "home":
            if st.button("New Session", use_container_width=True):
                st.session_state.session = ExamSession()
                clear_streaming_state()
                st.rerun()

        if "part1" in phase:
            st.markdown("**Part 1 Tips**")
            st.caption("- Answer in 2–3 sentences\n- Add a reason or example\n- Use present tenses for habits")
        elif "part2" in phase:
            st.markdown("**Part 2 Tips**")
            st.caption("- Cover all bullet points\n- Use past tense for stories\n- Start with a clear topic sentence")
        elif "part3" in phase:
            st.markdown("**Part 3 Tips**")
            st.caption("- Give your opinion clearly\n- Use phrases like 'I believe...' / 'It seems to me...'\n- Compare and contrast ideas")
