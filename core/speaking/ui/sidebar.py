from __future__ import annotations

import streamlit as st

from core.async_utils import run_async
from core.config import ACCENT_LABELS, DEFAULT_ACCENT
from core.models import UserProfile
from core.speaking.session import ExamSession
from core.store import FluentUpStore
from .helpers import clear_streaming_state


def render_history_detail(doc: dict) -> None:
    with st.container():
        st.markdown("---")
        for turn in doc.get("turns", []):
            part     = turn.get("part", "?")
            question = turn.get("question", "")
            transcript = turn.get("transcript", "")
            with st.expander(f"Part {part} — {question[:60]}"):
                if transcript:
                    st.markdown(f"**Transcript:** {transcript}")
                for fb in turn.get("feedbacks", []):
                    crit = fb.get("criterion", "")
                    text = fb.get("feedback", "")
                    st.markdown(f"**{crit}:** {text}")
        st.markdown("---")


def _render_sidebar_history(store: FluentUpStore) -> None:
    try:
        history = run_async(store.get_recent_sessions(limit=10))
    except Exception as e:
        st.caption(f"Could not load: {e}")
        return

    if not history:
        st.caption("No saved sessions yet.")
        return

    view_id: str | None = st.session_state.get("history_view_id")

    for h in history:
        sid = h["_id"]
        ts = h.get("created_at", "")
        if hasattr(ts, "strftime"):
            ts = ts.strftime("%m-%d %H:%M")

        r1, r2 = st.columns([5, 2])
        with r1:
            st.markdown(
                f"<div style='border-left:3px solid #1565C0;padding:3px 8px;"
                f"font-size:0.85em'>{ts}</div>",
                unsafe_allow_html=True,
            )
        with r2:
            c1, c2 = st.columns(2)
            with c1:
                if st.button("📂", key=f"sb_load_{sid}", help="Load"):
                    st.session_state["history_view_id"] = None if view_id == sid else sid
                    st.rerun()
            with c2:
                if st.button("🗑", key=f"sb_del_{sid}", help="Delete"):
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
                st.caption(f"Load failed: {e}")


def _render_sidebar_profile() -> None:
    st.markdown("**Your Profile**")
    store: FluentUpStore | None = st.session_state.get("store")
    current: UserProfile | None = st.session_state.get("user_profile")
    sess: ExamSession = st.session_state.session

    if current:
        gender_label = {"male": "M", "female": "F", "other": "—"}.get(current.gender, "")
        st.markdown(
            f"<div style='background:#E3F2FD;border-left:3px solid #1565C0;"
            f"padding:6px 10px;border-radius:4px;font-size:0.85em;color:#1a1a1a'>"
            f"<b>{current.name}</b>, {current.age} ({gender_label})<br>"
            f"<span style='color:#444'>{current.occupation_detail[:45]}</span></div>",
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Edit", key="sb_edit_profile", use_container_width=True):
                sess.phase = "profile_q1"
                st.rerun()
        with c2:
            if st.button("Clear", key="sb_clear_profile", use_container_width=True):
                st.session_state.pop("user_profile", None)
                st.rerun()
    else:
        if st.button("Set up profile", key="sb_create_profile", use_container_width=True):
            sess.phase = "profile_q1"
            st.rerun()

    if store:
        if "sidebar_profiles_cache" not in st.session_state:
            try:
                st.session_state["sidebar_profiles_cache"] = run_async(store.get_profiles())
            except Exception:
                st.session_state["sidebar_profiles_cache"] = []

        profiles: list[dict] = st.session_state.get("sidebar_profiles_cache", [])
        if profiles:
            options_ids = [""] + [p["_id"] for p in profiles]
            current_id = current.profile_id if current else ""
            try:
                sel_index = options_ids.index(current_id)
            except ValueError:
                sel_index = 0

            def _fmt(pid: str) -> str:
                if not pid:
                    return "— select saved profile —"
                p = next((x for x in profiles if x["_id"] == pid), None)
                return f"{p['name']}, {p['age']} — {p.get('occupation_detail','')[:30]}" if p else pid

            selected = st.selectbox(
                "Saved profiles",
                options=options_ids,
                format_func=_fmt,
                index=sel_index,
                key="sb_profile_select",
                label_visibility="collapsed",
            )
            if selected and selected != current_id:
                p = next((x for x in profiles if x["_id"] == selected), None)
                if p:
                    st.session_state["user_profile"] = UserProfile(
                        name=p["name"],
                        age=p["age"],
                        occupation=p.get("occupation", "other"),
                        occupation_detail=p.get("occupation_detail", ""),
                        profile_id=p["_id"],
                        gender=p.get("gender", "male"),
                    )
                    st.rerun()

            if selected:
                if st.button("Delete this profile", key="sb_del_profile", use_container_width=True):
                    try:
                        run_async(store.delete_profile(selected))
                        if current and current.profile_id == selected:
                            st.session_state.pop("user_profile", None)
                        st.session_state.pop("sidebar_profiles_cache", None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete failed: {e}")


def render_sidebar(secrets: dict) -> None:
    with st.sidebar:
        st.markdown("## FluentUp")
        st.caption("IELTS Speaking Practice")

        st.divider()
        _render_sidebar_profile()

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

        store: FluentUpStore | None = st.session_state.get("store")
        if store is not None:
            st.markdown("**Session History**")
            with st.expander("View / manage", expanded=False):
                _render_sidebar_history(store)
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
