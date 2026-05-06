"""core/vocab_sidebar.py — Global Personal Dictionary: sidebar button + dialog."""
from __future__ import annotations

import re

import streamlit as st
from googletrans import Translator

from core.async_utils import run_async
from core.auth import current_user, is_logged_in


# ── Translation helper ────────────────────────────────────────────────────────

async def _translate_to_vi(word: str) -> str:
    async with Translator() as t:
        result = await t.translate(word.strip(), dest="vi", src="auto")
        return result.text


def _is_duplicate(word: str, entries: list[dict]) -> bool:
    w = word.strip().lower()
    return any(e.get("word", "").lower() == w for e in entries)


def _is_valid_regex(pattern: str) -> bool:
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False


def _render_entry_list(entries: list[dict], store) -> None:
    for entry in entries:
        col_word, col_del = st.columns([8, 1])
        with col_word:
            w = entry.get("word", "")
            n = entry.get("notes", "")
            if n:
                st.markdown(f"**{w}** — _{n}_")
            else:
                st.markdown(f"**{w}**")
        with col_del:
            if st.button("×", key=f"del_vocab_{entry['_id']}", help="Xoá"):
                try:
                    run_async(store.delete_vocab(entry["_id"]))
                    st.rerun()
                except Exception as exc:
                    st.error(f"Xoá thất bại: {exc}")


# ── Dialog ────────────────────────────────────────────────────────────────────

@st.dialog("📖 Từ điển cá nhân", width="large")
def _vocab_dialog(store, user_id: str) -> None:
    # ── Combined search / new-word input ──────────────────────────────────────
    query = st.text_input(
        "Từ / cụm từ",
        placeholder="Nhập để tìm kiếm hoặc thêm từ mới…",
        key="vd_query",
    )

    # ── Fetch from Mongo on every render ─────────────────────────────────────
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

    # ── Match list ────────────────────────────────────────────────────────────
    if not q:
        if entries:
            st.markdown(
                f"<small style='color:gray'>20 từ gần nhất</small>",
                unsafe_allow_html=True,
            )
            _render_entry_list(entries, store)
        else:
            st.caption("Chưa có từ nào. Hãy thêm từ đầu tiên!")
    else:
        if entries:
            st.markdown(
                f"<small style='color:gray'>{len(entries)} kết quả</small>",
                unsafe_allow_html=True,
            )
            _render_entry_list(entries, store)
        elif _is_valid_regex(q):
            st.caption("Không tìm thấy từ nào khớp.")

    # ── Add new section ───────────────────────────────────────────────────────
    if q:
        st.divider()
        st.markdown("##### Thêm mới")

        if st.button("🔍 Dịch sang tiếng Việt", use_container_width=True):
            with st.spinner("Đang dịch…"):
                try:
                    translation = run_async(_translate_to_vi(q))
                    st.session_state["vd_notes"] = translation
                except Exception as exc:
                    st.error(f"Dịch thất bại: {exc}")

        notes = st.text_input("Ghi chú / nghĩa", placeholder="nghĩa, ví dụ…", key="vd_notes")

        is_dup = _is_duplicate(q, entries)
        if is_dup:
            st.warning(f'"{q}" đã có trong từ điển.')

        if st.button("💾 Lưu từ", type="primary", use_container_width=True, disabled=is_dup):
            try:
                run_async(store.save_vocab(q, notes.strip(), user_id=user_id))
                st.session_state.pop("vd_notes", None)
                st.session_state.pop("vd_query", None)
                st.rerun()
            except Exception as exc:
                st.error(f"Lưu thất bại: {exc}")


# ── Sidebar button ────────────────────────────────────────────────────────────

def render_vocab_sidebar(store) -> None:
    if not is_logged_in():
        return

    st.sidebar.markdown("---")
    if st.sidebar.button("📖 Từ điển cá nhân", use_container_width=True, shortcut="Alt+V"):
        user_id = (current_user() or {}).get("_id", "default")
        _vocab_dialog(store, user_id)

