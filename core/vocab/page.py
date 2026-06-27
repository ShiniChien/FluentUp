"""core/vocab/page.py — Full-page vocabulary management."""
from __future__ import annotations

import streamlit as st

from core.async_utils import run_async
from core.auth import current_user
from core.vocab.quiz import render_mini_quiz
from core.vocab.shared import (
    render_bulk_insert,
    render_search_input,
    render_sense_manager,
    search_on_query_change,
)


def render_vocab_page(store) -> None:
    user = current_user()
    user_id = str(user.get("_id", "default")) if user else "default"

    if store is None:
        st.warning("Không có kết nối MongoDB.")
        return

    # ── Header ──────────────────────────────────────────────────────────────
    col_title, col_count = st.columns([5, 1])
    with col_title:
        st.markdown("# 📖 Từ điển cá nhân")
    with col_count:
        try:
            total = run_async(store.count_vocab(user_id))
        except Exception:
            total = 0
        st.markdown(
            f"<div style='text-align:right;font-size:1.1em;margin-top:8px'>📊 {total} từ</div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Bulk insert ─────────────────────────────────────────────────────────
    with st.expander("📥 Nhập hàng loạt"):
        render_bulk_insert(store, user_id)

    st.divider()

    # ── Mini test ───────────────────────────────────────────────────────────
    render_mini_quiz(store, user_id)

    st.divider()

    # ── Search ──────────────────────────────────────────────────────────────
    query = render_search_input(lambda: search_on_query_change(store, user_id))

    # ── Fetch with pagination ───────────────────────────────────────────────
    q = query.strip()
    page_size = st.session_state.get("vocab_page_size", 50)

    try:
        if q:
            entries = run_async(store.search_vocab(user_id=user_id, query=q, limit=9999))
        else:
            entries = run_async(store.get_vocab(user_id=user_id, limit=page_size))
            total_count = run_async(store.count_vocab(user_id))
    except Exception as exc:
        st.error(f"Lỗi tải dữ liệu: {exc}")
        return

    # ── Results info ────────────────────────────────────────────────────────
    if not q:
        shown = min(len(entries), page_size)
        st.markdown(
            f"<small style='color:gray'>Hiển thị {shown}/{total_count} từ</small>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(f"<small style='color:gray'>{len(entries)} kết quả</small>", unsafe_allow_html=True)

    if not entries:
        st.caption("Chưa có từ nào.")
        return

    # ── Render entries with inline sense manager ────────────────────────────
    for entry in entries:
        with st.expander(f"**{entry['word']}**", expanded=False):
            render_sense_manager(entry, store)

    # ── Load more ───────────────────────────────────────────────────────────
    if not q and total_count > page_size:
        if st.button("Xem thêm…", use_container_width=True):
            st.session_state["vocab_page_size"] = page_size + 50
            st.rerun()
