"""core/vocab/shared.py — Shared UI components for vocab dialog + page."""
from __future__ import annotations

import re

import streamlit as st
from googletrans import Translator

from core.async_utils import run_async
from core.log import get_logger

_logger = get_logger(__name__)


def bust_review_cache() -> None:
    st.session_state.pop("_vocab_review_count", None)


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


def render_entry_list(entries: list[dict], store) -> None:
    """Render word list with × delete button per entry."""
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
                    bust_review_cache()
                    st.rerun()
                except Exception as exc:
                    st.error(f"Xoá thất bại: {exc}")


def render_search_input(on_query_change) -> str:
    """Search box. Returns current query string."""
    return st.text_input(
        "Từ / cụm từ",
        placeholder="Nhập để tìm kiếm hoặc thêm từ mới…",
        key="vd_query",
        on_change=on_query_change,
    )


def render_sense_manager(entry: dict, store) -> None:
    """Inline add/edit/delete senses for an existing word."""
    word_id = entry["_id"]
    senses: list[dict] = entry.get("senses", [])

    col_title, col_del_word = st.columns([7, 2])
    with col_title:
        st.markdown(f"##### {entry['word']}")
    with col_del_word:
        if st.button("🗑️ Xóa từ", use_container_width=True, key=f"del_whole_word_{word_id}"):
            st.session_state["_confirm_delete_word"] = word_id

    if st.session_state.get("_confirm_delete_word") == word_id:
        st.warning("Xóa toàn bộ từ này?")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("Xác nhận xóa", type="primary", use_container_width=True, key=f"confirm_del_word_{word_id}"):
                try:
                    run_async(store.delete_vocab(word_id))
                    st.session_state.pop("_confirm_delete_word", None)
                    st.session_state.pop("vd_query", None)
                    bust_review_cache()
                    st.rerun()
                except Exception as exc:
                    st.error(f"Xoá thất bại: {exc}")
        with cc2:
            if st.button("Hủy", use_container_width=True, key=f"cancel_del_word_{word_id}"):
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
                    st.text_input(
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
                                bust_review_cache()
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
                        bust_review_cache()
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Xoá thất bại: {exc}")
    else:
        st.caption("Từ này chưa có nghĩa nào.")

    st.markdown("**Thêm nghĩa mới:**")
    new_val = st.text_input(
        "Nghĩa mới", placeholder="nghĩa, ví dụ…",
        key=f"vd_new_sense_{word_id}", label_visibility="collapsed",
    )
    if st.button("💾 Thêm nghĩa", type="primary", use_container_width=True):
        val = new_val.strip()
        if val:
            try:
                run_async(store.add_sense(word_id, val))
                st.session_state.pop("vd_new_sense", None)
                bust_review_cache()
                st.rerun()
            except Exception as exc:
                st.error(f"Thêm nghĩa thất bại: {exc}")
        else:
            st.warning("Vui lòng nhập nghĩa.")


def render_add_new_word(word: str, store, user_id: str) -> None:
    """Add new word form (for when no existing entry matches)."""
    st.markdown("##### Thêm mới")
    notes = st.text_input("Ghi chú / nghĩa", placeholder="nghĩa, ví dụ…", key="vd_notes")
    if st.button("💾 Lưu từ", type="primary", use_container_width=True):
        try:
            run_async(store.save_vocab(word, notes.strip(), user_id=user_id))
            st.session_state.pop("vd_notes", None)
            st.session_state.pop("vd_query", None)
            bust_review_cache()
            st.rerun()
        except Exception as exc:
            st.error(f"Lưu thất bại: {exc}")


def render_bulk_insert(store, user_id: str) -> None:
    """Bulk insert: textarea, one `word = meaning` per line, skip existing."""
    st.markdown("**📥 Nhập hàng loạt**")
    st.caption("Mỗi dòng một từ: `word = meaning`. Dòng không hợp lệ sẽ bị bỏ qua.")
    raw = st.text_area(
        "Danh sách từ", placeholder="bank = bờ sông\nlook after = chăm sóc\nresult in = dẫn đến",
        key="vocab_bulk_input", label_visibility="collapsed", height=150,
    )
    if st.button("📥 Nhập", type="primary", use_container_width=True, key="vocab_bulk_submit"):
        if not raw.strip():
            st.warning("Vui lòng nhập danh sách từ.")
            return
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        added = 0
        skipped = 0
        appended = 0
        for line in lines:
            parts = re.split(r"\s*=\s*", line, maxsplit=1)
            if len(parts) != 2:
                skipped += 1
                continue
            w, m = parts[0].strip(), parts[1].strip()
            if not w or not m:
                skipped += 1
                continue
            try:
                existing = run_async(store.search_vocab(user_id=user_id, query=re.escape(w), limit=1))
            except Exception:
                existing = []
            if existing:
                doc = existing[0]
                existing_meanings = {s.get("meaning", "").strip().lower() for s in doc.get("senses", []) if s.get("meaning")}
                if m.lower() in existing_meanings:
                    skipped += 1
                else:
                    run_async(store.add_sense(doc["_id"], m))
                    appended += 1
            else:
                run_async(store.save_vocab(w, m, user_id=user_id))
                added += 1
        bust_review_cache()
        parts = []
        if added:
            parts.append(f"Thêm {added} từ mới")
        if appended:
            parts.append(f"Thêm {appended} nghĩa")
        if skipped:
            parts.append(f"Bỏ qua {skipped} (đã tồn tại hoặc lỗi định dạng)")
        st.success("Đã xong: " + ", ".join(parts))


def search_on_query_change(store, user_id: str) -> None:
    """Auto-translate new word when query changes (no existing match)."""
    q = st.session_state.get("vd_query", "").strip()
    if not q or not _is_valid_regex(q):
        return
    try:
        existing = run_async(store.search_vocab(user_id=user_id, query=re.escape(q)))
    except Exception:
        _logger.exception("vocab: failed to search vocab from DB")
        existing = []
    if _is_duplicate(q, existing):
        return
    try:
        st.session_state["vd_notes"] = run_async(_translate_to_vi(q))
    except Exception:
        _logger.exception("vocab: translation to Vietnamese failed")
