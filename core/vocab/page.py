"""core/vocab/page.py — Full-page vocabulary management."""
from __future__ import annotations

import html

import streamlit as st

from core.async_utils import run_async
from core.auth import current_user
from core.vocab.quiz import render_mini_quiz
from core.vocab.shared import (
    bust_review_cache,
    render_bulk_insert,
    render_quick_add_bar,
    render_sense_manager,
)


def _render_card(entry: dict, store) -> None:
    """Render a single word card with inline edit on demand."""
    word_id = entry["_id"]
    word = entry.get("word", "")
    senses = entry.get("senses", [])
    has_review = any(s.get("status") == "IN_REVIEW" for s in senses)
    edit_key = f"_vocab_edit_{word_id}"

    border_color = "rgba(240,173,78,0.5)" if has_review else "rgba(128,128,128,0.2)"
    bg_tint = "rgba(240,173,78,0.08)" if has_review else "transparent"
    review_badge = " `REVIEW`" if has_review else ""

    if st.session_state.get(edit_key):
        # Expanded — show sense manager with colored border via container
        with st.container(border=True):
            st.markdown(f"##### {word}")
            render_sense_manager(entry, store)
            if st.button("Đóng", key=f"close_edit_{word_id}", use_container_width=True):
                st.session_state.pop(edit_key, None)
                st.rerun()
    else:
        # Compact card
        meanings_str = ", ".join(
            s.get("meaning", "") for s in senses if s.get("meaning")
        )
        st.markdown(
            f"<div style='border:1px solid {border_color};border-left:3px solid {border_color};"
            f"border-radius:6px;padding:8px 12px;margin:4px 0;background:{bg_tint}'>"
            f"<span style='font-size:1.1em;font-weight:600'>{html.escape(word)}</span>"
            f"<span style='color:#f0ad4e;font-size:0.8em'>{review_badge}</span>"
            f"<br><span style='color:#aaaaaa;font-size:0.9em'><i>{html.escape(meanings_str)}</i></span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("✏️ Sửa", key=f"edit_card_{word_id}", use_container_width=True):
                st.session_state[edit_key] = True
                st.rerun()
        with col2:
            del_key = f"_confirm_card_del_{word_id}"
            if st.session_state.get(del_key):
                if st.button("✓ Xác nhận", key=f"card_confirm_del_{word_id}",
                             type="primary", use_container_width=True):
                    try:
                        run_async(store.delete_vocab(word_id))
                        bust_review_cache()
                        st.session_state.pop(del_key, None)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Xoá thất bại: {exc}")
            else:
                if st.button("🗑️ Xoá", key=f"card_del_{word_id}", use_container_width=True):
                    st.session_state[del_key] = True
                    st.rerun()


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

    # ── Quick-add bar ───────────────────────────────────────────────────────
    render_quick_add_bar(store, user_id)

    st.divider()

    # ── Bulk insert ─────────────────────────────────────────────────────────
    with st.expander("📥 Nhập hàng loạt"):
        render_bulk_insert(store, user_id)

    st.divider()

    # ── Mini test ───────────────────────────────────────────────────────────
    render_mini_quiz(store, user_id)

    st.divider()

    # ── Sort / Filter toolbar ───────────────────────────────────────────────
    st.markdown("### 📋 Danh sách từ")

    cf1, cf2, cf3 = st.columns([3, 2, 1])
    with cf1:
        filter_text = st.text_input(
            "🔍 Lọc", placeholder="Lọc từ hoặc nghĩa…",
            key="vocab_filter", label_visibility="collapsed",
        )
    with cf2:
        sort_by = st.selectbox(
            "Sắp xếp", ["Mới nhất", "A → Z"],
            key="vocab_sort", label_visibility="collapsed",
        )
    with cf3:
        review_only = st.checkbox("REVIEW", key="vocab_review_filter",
                                   help="Chỉ hiện từ có nghĩa đang review")

    # Reset offset when sort or filter changes
    prev_sort = st.session_state.get("_vocab_prev_sort")
    prev_filter = st.session_state.get("_vocab_prev_filter")
    prev_review = st.session_state.get("_vocab_prev_review")
    if (prev_sort is not None and prev_sort != sort_by) or \
       (prev_filter is not None and prev_filter != filter_text) or \
       (prev_review is not None and prev_review != review_only):
        st.session_state["vocab_offset"] = 0
    st.session_state["_vocab_prev_sort"] = sort_by
    st.session_state["_vocab_prev_filter"] = filter_text
    st.session_state["_vocab_prev_review"] = review_only

    # ── Fetch ───────────────────────────────────────────────────────────────
    page_size = 50
    offset = st.session_state.get("vocab_offset", 0)
    store_sort = "word" if sort_by == "A → Z" else "created_at"

    try:
        entries = run_async(store.get_vocab(
            user_id=user_id, limit=page_size, offset=offset, sort_by=store_sort,
        ))
        if offset == 0:
            total_count = run_async(store.count_vocab(user_id))
        else:
            total_count = total  # from header
    except Exception as exc:
        st.error(f"Lỗi tải dữ liệu: {exc}")
        return

    # ── Client-side filter ──────────────────────────────────────────────────
    ft = filter_text.strip().lower()
    if ft:
        entries = [
            e for e in entries
            if ft in e.get("word", "").lower()
            or any(ft in s.get("meaning", "").lower() for s in e.get("senses", []))
        ]
    if review_only:
        entries = [
            e for e in entries
            if any(s.get("status") == "IN_REVIEW" for s in e.get("senses", []))
        ]

    if not entries:
        st.caption("Không có từ nào khớp.")
        return

    # ── Results info ────────────────────────────────────────────────────────
    st.markdown(
        f"<small style='color:gray'>Hiển thị {offset + 1}–{offset + len(entries)} / {total_count} từ</small>",
        unsafe_allow_html=True,
    )

    # ── Card list ───────────────────────────────────────────────────────────
    for entry in entries:
        _render_card(entry, store)

    # ── Load more ───────────────────────────────────────────────────────────
    if not ft and not review_only and offset + page_size < total_count:
        if st.button("Xem thêm…", use_container_width=True):
            st.session_state["vocab_offset"] = offset + page_size
            st.rerun()
