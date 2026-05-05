from __future__ import annotations

import streamlit as st

from core.speaking.session import ExamSession


def _build_report(sess: ExamSession) -> str:
    summary = sess.build_summary()
    lines = [
        "FluentUp — IELTS Speaking Practice Session Report",
        "=" * 50,
        "",
    ]
    for t in summary.turns:
        lines.append(f"Part {t.part} — {t.question}")
        if t.result:
            if t.result.transcript:
                lines.append(f"  Transcript: {t.result.transcript}")
            for fb in t.result.feedbacks:
                lines.append(f"  [{fb.criterion}] {fb.feedback}")
        lines.append("")
    return "\n".join(lines)


def render_session_summary() -> None:
    sess: ExamSession = st.session_state.session
    summary = sess.build_summary()

    st.header("Session Summary")

    if not summary.turns:
        st.info("No answers recorded this session.")
        if st.button("Start New Session", use_container_width=True):
            st.session_state.session = ExamSession()
            st.rerun()
        return

    parts_done = []
    if sess.part_turns(1):
        parts_done.append(f"Part 1 ({len(sess.part_turns(1))} answers)")
    if sess.part_turns(2):
        parts_done.append(f"Part 2 ({len(sess.part_turns(2))} speech)")
    if sess.part_turns(3):
        parts_done.append(f"Part 3 ({len(sess.part_turns(3))} answers)")
    if parts_done:
        st.markdown("**Parts completed:** " + " | ".join(parts_done))

    st.markdown("---")

    report = _build_report(sess)
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "Save Report",
            data=report,
            file_name="fluentup_session.txt",
            mime="text/plain",
        )
    with col2:
        if st.button("Start New Session", use_container_width=True):
            st.session_state.session = ExamSession()
            st.rerun()
