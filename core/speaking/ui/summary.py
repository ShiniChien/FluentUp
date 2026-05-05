from __future__ import annotations

import streamlit as st

from core.async_utils import run_async
from core.speaking.session import ExamSession
from core.store import FluentUpStore
from .eval import render_evaluation
from .sidebar import render_history_detail


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


def render_history(store: FluentUpStore) -> None:
    try:
        history = run_async(store.get_recent_sessions(limit=10))
    except Exception as e:
        st.error(f"Could not load history: {e}")
        return

    if not history:
        st.caption("No saved sessions yet.")
        return

    view_id: str | None = st.session_state.get("history_view_id")

    for h in history:
        sid = h["_id"]
        ts = h.get("created_at", "")
        if hasattr(ts, "strftime"):
            ts = ts.strftime("%Y-%m-%d %H:%M")

        info_col, load_col, del_col = st.columns([7, 1, 1])
        with info_col:
            st.markdown(
                f"<div style='border-left:4px solid #1565C0;padding:6px 12px;margin:2px 0'>"
                f"{ts}</div>",
                unsafe_allow_html=True,
            )
        with load_col:
            if st.button("Load", key=f"hist_load_{sid}", use_container_width=True):
                if view_id == sid:
                    st.session_state.pop("history_view_id", None)
                else:
                    st.session_state["history_view_id"] = sid
                st.rerun()
        with del_col:
            if st.button("Delete", key=f"hist_del_{sid}", use_container_width=True):
                try:
                    run_async(store.delete_session(sid))
                    if view_id == sid:
                        st.session_state.pop("history_view_id", None)
                    st.rerun()
                except Exception as e:
                    st.error(f"Delete failed: {e}")

        if view_id == sid:
            try:
                doc = run_async(store.get_session(sid))
                if doc:
                    render_history_detail(doc)
            except Exception as e:
                st.error(f"Could not load session: {e}")


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
    store: FluentUpStore | None = st.session_state.get("store")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button(
            "Save Report",
            data=report,
            file_name="fluentup_session.txt",
            mime="text/plain",
        )
    with col2:
        if store is not None:
            if st.button("Save to History", type="primary", use_container_width=True):
                with st.spinner("Saving to MongoDB..."):
                    try:
                        session_id = run_async(store.save_session(summary))
                        st.success(f"Saved! ID: {session_id[:8]}…")
                    except Exception as e:
                        st.error(f"Save failed: {e}")
        else:
            st.caption("MongoDB not configured — history unavailable")
    with col3:
        if st.button("Start New Session", use_container_width=True):
            st.session_state.session = ExamSession()
            st.rerun()

    if store is not None:
        st.markdown("---")
        with st.expander("Session History", expanded=False):
            render_history(store)
