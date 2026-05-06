from __future__ import annotations

import datetime

import streamlit as st

from core.async_utils import run_async
from core.auth import current_user
from core.models import CueCard
from core.shared import get_store
from core.speaking.session import ExamSession


def _load_part2_attempts() -> list[dict]:
    u = current_user()
    user_id = str(u.get("_id", "default")) if u else "default"
    try:
        return run_async(get_store().get_part2_attempts(user_id=user_id, limit=20))
    except Exception:
        return []


def render_home() -> None:
    st.title("Speaking Practice")
    sess: ExamSession = st.session_state.session

    st.markdown("Choose a part to start practicing:")

    attempts = _load_part2_attempts()
    has_attempts = len(attempts) > 0

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
        st.markdown(
            "<div style='border:2px solid #6A1B9A;border-radius:10px;padding:20px;text-align:center'>"
            "<h3 style='color:#6A1B9A'>Part 2</h3>"
            "<p>Individual Long Turn</p>"
            "<p style='font-size:0.9em'>Cue card, 1 min prep, 2 min speech</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button("Start Part 2", key="start_p2", use_container_width=True):
            sess.phase = "part2_idle"
            st.rerun()

    with col3:
        p3_color = "#E65100" if has_attempts else "#9E9E9E"
        p3_hint = "5-6 abstract discussion questions" if has_attempts else "Complete Part 2 first to unlock"
        st.markdown(
            f"<div style='border:2px solid {p3_color};border-radius:10px;padding:20px;text-align:center;opacity:{'1' if has_attempts else '0.5'}'>"
            f"<h3 style='color:{p3_color}'>Part 3</h3>"
            "<p>Two-way Discussion</p>"
            f"<p style='font-size:0.9em'>{p3_hint}</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        if has_attempts:
            def _fmt(a: dict) -> str:
                dt = a.get("created_at")
                if isinstance(dt, datetime.datetime):
                    label_date = dt.strftime("%d/%m %H:%M")
                else:
                    label_date = ""
                return f"{a.get('topic', '?')} — {label_date}"

            selected = st.selectbox(
                "Chọn buổi Part 2",
                options=attempts,
                format_func=_fmt,
                key="p3_attempt_select",
                label_visibility="collapsed",
            )
            if st.button("Start Part 3", key="start_p3", use_container_width=True, type="primary"):
                if selected:
                    sess.part2_topic = selected.get("topic", "")
                    sess.part2_cue_card = CueCard(
                        topic=selected.get("topic", ""),
                        points=selected.get("cue_points", []),
                        explain=selected.get("cue_explain", ""),
                    )
                    st.session_state["p3_context_transcript"] = selected.get("transcript", "")
                sess.phase = "part3_loading"
                st.rerun()
        else:
            st.button("Locked", key="start_p3", use_container_width=True, disabled=True)
