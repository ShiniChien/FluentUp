"""core/vocab/quiz.py — Inline mini quiz on the vocab page."""
from __future__ import annotations

import random

import streamlit as st

from core.async_utils import run_async
from core.log import get_logger

_logger = get_logger(__name__)


def _all_meanings(entry: dict) -> list[str]:
    seen: set[str] = set()
    result = []
    for s in entry.get("senses", []):
        m = s.get("meaning", "").strip()
        if m and m not in seen:
            seen.add(m)
            result.append(m)
    return result


def render_mini_quiz(store, user_id: str) -> None:
    """Render a 5-word en→vi mini quiz. Inline — no HTML export."""
    st.markdown("### 🎲 Mini Test")
    st.caption("Chọn 5 từ ngẫu nhiên để kiểm tra nhanh (en → vi).")

    if st.button("🎲 Tạo quiz", type="secondary", use_container_width=True, key="mini_quiz_gen"):
        # Reset quiz state
        st.session_state.pop("mini_quiz_words", None)
        st.session_state.pop("mini_quiz_answers", None)
        st.session_state.pop("mini_quiz_submitted", None)
        st.rerun()

    # Only proceed if generating fresh
    if "mini_quiz_words" not in st.session_state:
        try:
            all_vocab = run_async(store.get_vocab(user_id=user_id, limit=9999))
        except Exception:
            _logger.exception("mini_quiz: failed to fetch vocab")
            all_vocab = []

        if len(all_vocab) < 5:
            st.info(f"Cần ít nhất 5 từ vựng để tạo quiz (hiện có {len(all_vocab)}).")
            return

        words = random.sample(all_vocab, 5)
        st.session_state["mini_quiz_words"] = words
        st.session_state["mini_quiz_answers"] = [""] * 5
        st.session_state["mini_quiz_submitted"] = False
        st.rerun()

    words = st.session_state["mini_quiz_words"]
    submitted = st.session_state.get("mini_quiz_submitted", False)

    st.markdown("---")
    for idx, entry in enumerate(words):
        word = entry.get("word", "")
        col_q, col_a = st.columns([1, 2])
        with col_q:
            st.markdown(f"**{idx + 1}. {word}**")
        with col_a:
            if submitted:
                correct_meanings = _all_meanings(entry)
                user_ans = st.session_state["mini_quiz_answers"][idx].strip().lower()
                ok = any(user_ans == m.strip().lower() for m in correct_meanings)
                if ok:
                    st.markdown(f"✅ *{user_ans}*")
                else:
                    st.markdown(f"❌ *{user_ans}* — Đáp án: {', '.join(correct_meanings)}")
            else:
                st.session_state["mini_quiz_answers"][idx] = st.text_input(
                    "Nghĩa tiếng Việt", key=f"mini_quiz_{idx}",
                    label_visibility="collapsed", placeholder="Nhập nghĩa…",
                )

    if not submitted:
        if st.button("📝 Nộp bài", type="primary", use_container_width=True, key="mini_quiz_submit"):
            st.session_state["mini_quiz_submitted"] = True
            st.rerun()
    else:
        # Score
        correct = 0
        for idx, entry in enumerate(words):
            correct_meanings = [m.strip().lower() for m in _all_meanings(entry)]
            user_ans = st.session_state["mini_quiz_answers"][idx].strip().lower()
            if user_ans in correct_meanings:
                correct += 1
        st.markdown(f"### ✅ Kết quả: {correct}/{len(words)}")
        if st.button("🔄 Làm lại", use_container_width=True, key="mini_quiz_retry"):
            st.session_state.pop("mini_quiz_words", None)
            st.session_state.pop("mini_quiz_answers", None)
            st.session_state.pop("mini_quiz_submitted", None)
            st.rerun()
