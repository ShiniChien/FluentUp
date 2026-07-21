"""core/vocab/sidebar.py — Sidebar vocab button + stay-open dialog."""
from __future__ import annotations

import re

import streamlit as st

from core.async_utils import run_async
from core.auth import current_user, is_logged_in
from core.vocab.shared import (
    render_add_new_word,
    render_entry_list,
    render_search_input,
    render_sense_manager,
    search_on_query_change,
)


def _on_dismiss() -> None:
    """Clear the open flag when the user dismisses (X / ESC / click-outside)."""
    st.session_state["_vocab_dialog_open"] = False


@st.dialog("📖 Từ điển cá nhân", width="large", on_dismiss=_on_dismiss)
def _vocab_dialog(store, user_id: str) -> None:
    # ── Expand button to full page ──────────────────────────────────────────
    col_title, col_expand = st.columns([6, 2])
    with col_title:
        st.markdown("##### Từ điển của bạn")
    with col_expand:
        if st.button("↗ Xem tất cả", use_container_width=True, help="Mở trang từ điển đầy đủ"):
            st.switch_page("pages/7_Vocabulary.py")

    st.divider()

    # ── Search ──────────────────────────────────────────────────────────────
    query = render_search_input(lambda: search_on_query_change(store, user_id))

    # ── Fetch ───────────────────────────────────────────────────────────────
    q = query.strip()
    if q:
        if not _is_valid_regex(q):
            st.caption("Regex không hợp lệ.")
            entries = []
        else:
            try:
                entries = run_async(store.search_vocab(user_id=user_id, query=q))
            except Exception:
                entries = []
    else:
        try:
            entries = run_async(store.get_vocab(user_id=user_id))
        except Exception:
            entries = []

    # ── Entry list ──────────────────────────────────────────────────────────
    if not q:
        if entries:
            st.markdown("<small style='color:gray'>20 từ gần nhất</small>", unsafe_allow_html=True)
            render_entry_list(entries, store)
        else:
            st.caption("Chưa có từ nào. Hãy thêm từ đầu tiên!")
    else:
        if entries:
            st.markdown(f"<small style='color:gray'>{len(entries)} kết quả</small>", unsafe_allow_html=True)
            render_entry_list(entries, store)
        elif _is_valid_regex(q):
            st.caption("Không tìm thấy từ nào khớp.")

    # ── Add / edit section ──────────────────────────────────────────────────
    if q:
        st.divider()
        dup_entry = next((e for e in entries if e.get("word", "").lower() == q.lower()), None)
        if dup_entry:
            render_sense_manager(dup_entry, store)
        else:
            render_add_new_word(q, store, user_id)


def _is_valid_regex(pattern: str) -> bool:
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False


def render_vocab_sidebar(store) -> None:
    if not is_logged_in():
        return
    if store is None:
        return
    user_id = (current_user() or {}).get("_id", "default")
    st.sidebar.markdown("---")
    if st.sidebar.button("📖 Từ điển cá nhân", use_container_width=True, shortcut="Alt+V"):
        st.session_state["_vocab_dialog_open"] = True
    if st.session_state.get("_vocab_dialog_open"):
        # Do NOT clear the flag here — it must stay True so in-dialog
        # st.rerun() calls reopen the dialog. The flag is cleared only
        # by the on_dismiss callback (X / ESC / click-outside).
        _vocab_dialog(store, user_id)
