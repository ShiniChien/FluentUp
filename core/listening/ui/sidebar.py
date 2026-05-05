from __future__ import annotations

import streamlit as st

from core.async_utils import run_async
from core.config import ACCENT_LABELS


def render_sidebar_dict(store) -> None:
    # ── Speaker accent config ─────────────────────────────────────────────────
    st.sidebar.markdown("### 🗣 Speaker Accents")
    accent_options = list(ACCENT_LABELS.keys())
    accent_labels  = [ACCENT_LABELS[k] for k in accent_options]

    col_a, col_b = st.sidebar.columns(2)
    with col_a:
        idx_a = accent_options.index(st.session_state.get("echo_accent_a", "us"))
        chosen_a = st.selectbox(
            "Speaker A", options=accent_options,
            format_func=lambda k: ACCENT_LABELS[k],
            index=idx_a, key="sidebar_accent_a",
        )
        st.session_state["echo_accent_a"] = chosen_a
    with col_b:
        idx_b = accent_options.index(st.session_state.get("echo_accent_b", "us"))
        chosen_b = st.selectbox(
            "Speaker B", options=accent_options,
            format_func=lambda k: ACCENT_LABELS[k],
            index=idx_b, key="sidebar_accent_b",
        )
        st.session_state["echo_accent_b"] = chosen_b

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📖 Personal Dictionary")

    if store is None:
        st.sidebar.caption("Connect MongoDB to enable the personal dictionary.")
        return

    with st.sidebar.form("add_vocab_form", clear_on_submit=True):
        word  = st.text_input("Word / phrase", placeholder="e.g. ameliorate")
        notes = st.text_input("Notes (optional)", placeholder="meaning, example…")
        if st.form_submit_button("Save", use_container_width=True):
            if word.strip():
                try:
                    run_async(store.save_vocab(word.strip(), notes.strip()))
                    st.session_state.pop("echo_vocab_cache", None)
                    st.sidebar.success(f'"{word.strip()}" saved!')
                except Exception as exc:
                    st.sidebar.error(f"Save failed: {exc}")

    if "echo_vocab_cache" not in st.session_state:
        try:
            st.session_state["echo_vocab_cache"] = run_async(store.get_vocab())
        except Exception:
            st.session_state["echo_vocab_cache"] = []

    entries: list[dict] = st.session_state.get("echo_vocab_cache", [])
    if not entries:
        st.sidebar.caption("No words saved yet.")
        return

    st.sidebar.markdown(f"**{len(entries)} word(s):**")
    for entry in entries:
        col1, col2 = st.sidebar.columns([5, 1])
        with col1:
            w = entry.get("word", "")
            n = entry.get("notes", "")
            if n:
                st.markdown(f"**{w}** — _{n}_")
            else:
                st.markdown(f"**{w}**")
        with col2:
            if st.button("×", key=f"del_vocab_{entry['_id']}", help="Delete"):
                try:
                    run_async(store.delete_vocab(entry["_id"]))
                    st.session_state.pop("echo_vocab_cache", None)
                    st.rerun()
                except Exception as exc:
                    st.sidebar.error(f"Delete failed: {exc}")
