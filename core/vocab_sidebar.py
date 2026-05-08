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
    # ── Auto-translate on query change ────────────────────────────────────────
    def _on_query_change() -> None:
        q = st.session_state.get("vd_query", "").strip()
        if not q or not _is_valid_regex(q):
            return
        try:
            existing = run_async(store.search_vocab(user_id=user_id, query=q))
        except Exception:
            existing = []
        if _is_duplicate(q, existing):
            return
        try:
            st.session_state["vd_notes"] = run_async(_translate_to_vi(q))
        except Exception:
            pass

    # ── Combined search / new-word input ──────────────────────────────────────
    query = st.text_input(
        "Từ / cụm từ",
        placeholder="Nhập để tìm kiếm hoặc thêm từ mới…",
        key="vd_query",
        on_change=_on_query_change,
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

    # ── Add / edit section ────────────────────────────────────────────────────
    if q:
        st.divider()

        dup_entry = next((e for e in entries if e.get("word", "").lower() == q.lower()), None)

        if dup_entry:
            st.markdown("##### Chỉnh sửa")
            if "vd_notes" not in st.session_state:
                st.session_state["vd_notes"] = dup_entry.get("notes", "")
            notes = st.text_input("Ghi chú / nghĩa", placeholder="nghĩa, ví dụ…", key="vd_notes")
            if st.button("✏️ Cập nhật", type="primary", use_container_width=True):
                try:
                    run_async(store.update_vocab(dup_entry["_id"], notes))
                    st.session_state.pop("vd_notes", None)
                    st.session_state.pop("vd_query", None)
                    st.session_state["_vocab_dialog_open"] = True
                    st.rerun()
                except Exception as exc:
                    st.error(f"Cập nhật thất bại: {exc}")
        else:
            st.markdown("##### Thêm mới")
            notes = st.text_input("Ghi chú / nghĩa", placeholder="nghĩa, ví dụ…", key="vd_notes")
            if st.button("💾 Lưu từ", type="primary", use_container_width=True):
                try:
                    run_async(store.save_vocab(q, notes.strip(), user_id=user_id))
                    st.session_state.pop("vd_notes", None)
                    st.session_state.pop("vd_query", None)
                    st.session_state["_vocab_dialog_open"] = True
                    st.rerun()
                except Exception as exc:
                    st.error(f"Lưu thất bại: {exc}")


# ── Sidebar button ────────────────────────────────────────────────────────────

def render_vocab_sidebar(store) -> None:
    if not is_logged_in():
        return

    user_id = (current_user() or {}).get("_id", "default")

    st.sidebar.markdown("---")
    if st.sidebar.button("📖 Từ điển cá nhân", use_container_width=True, shortcut="Alt+V"):
        st.session_state["_vocab_dialog_open"] = True

    if st.session_state.get("_vocab_dialog_open"):
        st.session_state["_vocab_dialog_open"] = False
        _vocab_dialog(store, user_id)

