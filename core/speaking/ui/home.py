from __future__ import annotations

import streamlit as st

from core.speaking.session import ExamSession


def render_home() -> None:
    st.title("Speaking Practice")
    sess: ExamSession = st.session_state.session

    st.markdown("Choose a part to start practicing:")

    has_part2 = bool(sess.part2_topic)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            "<div style='border:2px solid #1565C0;border-radius:10px;padding:20px;text-align:center'>"
            "<h3 style='color:#1565C0'>Part 1</h3>"
            "<p>Introduction &amp; Interview</p>"
            "<p style='font-size:0.9em'>10 questions on familiar topics</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button("Start Part 1", key="start_p1", use_container_width=True):
            sess.phase = "part1_loading"
            st.rerun()

    with col2:
        p2_color = "#6A1B9A" if not has_part2 else "#9E9E9E"
        st.markdown(
            f"<div style='border:2px solid {p2_color};border-radius:10px;padding:20px;text-align:center;opacity:{'1' if not has_part2 else '0.5'}'>"
            f"<h3 style='color:{p2_color}'>Part 2</h3>"
            "<p>Individual Long Turn</p>"
            "<p style='font-size:0.9em'>Cue card, 1 min prep, 2 min speech</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.button(
            "Complete Part 1 first",
            key="start_p2",
            use_container_width=True,
            disabled=True,
        )

    with col3:
        p3_color = "#E65100" if has_part2 else "#9E9E9E"
        p3_hint = "5-6 abstract discussion questions" if has_part2 else "Complete Part 2 first to unlock"
        st.markdown(
            f"<div style='border:2px solid {p3_color};border-radius:10px;padding:20px;text-align:center;opacity:{'1' if has_part2 else '0.5'}'>"
            f"<h3 style='color:{p3_color}'>Part 3</h3>"
            "<p>Two-way Discussion</p>"
            f"<p style='font-size:0.9em'>{p3_hint}</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button(
            "Start Part 3" if has_part2 else "Locked",
            key="start_p3",
            use_container_width=True,
            disabled=not has_part2,
        ):
            sess.phase = "part3_loading"
            st.rerun()
