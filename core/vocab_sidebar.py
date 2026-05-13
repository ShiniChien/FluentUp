"""core/vocab_sidebar.py — Global Personal Dictionary: sidebar button + dialog."""
from __future__ import annotations

import re

import streamlit as st
from googletrans import Translator

from core.async_utils import run_async
from core.auth import current_user, is_logged_in
from core.log import get_logger

_logger = get_logger(__name__)


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
            senses = entry.get("senses", [])
            if senses:
                meanings = "; ".join(
                    f"_{s['meaning']}_" + (" `REVIEW`" if s.get("status") == "IN_REVIEW" else "")
                    for s in senses if s.get("meaning")
                )
                st.markdown(f"**{w}** — {meanings}")
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
            _logger.exception("vocab_sidebar: failed to search vocab from DB")
            existing = []
        if _is_duplicate(q, existing):
            return
        try:
            st.session_state["vd_notes"] = run_async(_translate_to_vi(q))
        except Exception:
            _logger.exception("vocab_sidebar: translation to Vietnamese failed")

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
                _logger.exception("vocab_sidebar: failed to search vocab")
                entries = []
    else:
        try:
            entries = run_async(store.get_vocab(user_id=user_id))
        except Exception:
            _logger.exception("vocab_sidebar: failed to get vocab list")
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
            word_id = dup_entry["_id"]
            senses: list[dict] = dup_entry.get("senses", [])

            col_title, col_del_word = st.columns([7, 2])
            with col_title:
                st.markdown(f"##### {dup_entry['word']}")
            with col_del_word:
                if st.button("🗑️ Xóa từ", use_container_width=True, key="del_whole_word"):
                    st.session_state["_confirm_delete_word"] = word_id

            if st.session_state.get("_confirm_delete_word") == word_id:
                st.warning("Xóa toàn bộ từ này?")
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("Xác nhận xóa", type="primary", use_container_width=True, key="confirm_del_word"):
                        try:
                            run_async(store.delete_vocab(word_id))
                            st.session_state.pop("_confirm_delete_word", None)
                            st.session_state.pop("vd_query", None)
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Xoá thất bại: {exc}")
                with cc2:
                    if st.button("Hủy", use_container_width=True, key="cancel_del_word"):
                        st.session_state.pop("_confirm_delete_word", None)
                        st.rerun()

            if senses:
                st.markdown("**Các nghĩa hiện có:**")
                for idx, sense in enumerate(senses):
                    edit_key = f"_edit_sense_{word_id}_{idx}"
                    is_editing = st.session_state.get(edit_key, False)
                    status_badge = " `REVIEW`" if sense.get("status") == "IN_REVIEW" else ""
                    s_col, e_col, d_col = st.columns([7, 1, 1])
                    with s_col:
                        if is_editing:
                            new_meaning = st.text_input(
                                "Sửa nghĩa", value=sense.get("meaning", ""),
                                key=f"sense_input_{word_id}_{idx}",
                                label_visibility="collapsed",
                            )
                        else:
                            st.markdown(f"• _{sense.get('meaning', '')}_" + status_badge)
                    with e_col:
                        if is_editing:
                            if st.button("✅", key=f"save_sense_{word_id}_{idx}", help="Lưu"):
                                val = st.session_state.get(f"sense_input_{word_id}_{idx}", "").strip()
                                if val:
                                    try:
                                        run_async(store.update_sense(word_id, idx, val))
                                        st.session_state.pop(edit_key, None)
                                        st.rerun()
                                    except Exception as exc:
                                        st.error(f"Cập nhật thất bại: {exc}")
                        else:
                            if st.button("✏️", key=f"edit_sense_{word_id}_{idx}", help="Sửa"):
                                st.session_state[edit_key] = True
                                st.rerun()
                    with d_col:
                        if st.button("🗑️", key=f"del_sense_{word_id}_{idx}", help="Xoá nghĩa"):
                            try:
                                run_async(store.delete_sense(word_id, idx))
                                st.session_state.pop("vd_query", None)
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Xoá thất bại: {exc}")
            else:
                st.caption("Từ này chưa có nghĩa nào.")

            st.markdown("**Thêm nghĩa mới:**")
            new_meaning_val = st.text_input(
                "Nghĩa mới", placeholder="nghĩa, ví dụ…",
                key="vd_new_sense", label_visibility="collapsed",
            )
            if st.button("💾 Thêm nghĩa", type="primary", use_container_width=True):
                val = new_meaning_val.strip()
                if val:
                    try:
                        run_async(store.add_sense(word_id, val))
                        st.session_state.pop("vd_new_sense", None)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Thêm nghĩa thất bại: {exc}")
                else:
                    st.warning("Vui lòng nhập nghĩa.")

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

