"""core/vocab/quiz.py — Inline mini quiz on the vocab page."""
from __future__ import annotations

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
    """Render a 5-word en→vi mini quiz. Single state dict, single rerun."""
    st.markdown("### 🎲 Mini Test")

    quiz = st.session_state.get("vocab_quiz", {"phase": "idle"})

    # ── Idle — show start button ────────────────────────────────────────────
    if quiz["phase"] == "idle":
        st.caption("Chọn 5 từ ngẫu nhiên để kiểm tra nhanh (en → vi).")
        if st.button("🎲 Làm quiz 5 từ", type="secondary", use_container_width=True,
                      key="mini_quiz_start"):
            try:
                words = run_async(store.sample_vocab(user_id, n=5))
            except Exception:
                _logger.exception("mini_quiz: sample_vocab failed")
                words = []
            if len(words) < 5:
                st.info(f"Cần ít nhất 5 từ để tạo quiz (hiện có {len(words)}).")
                return
            st.session_state["vocab_quiz"] = {
                "phase": "active",
                "words": words,
                "answers": [""] * 5,
            }
            st.rerun()

    # ── Active — show questions ─────────────────────────────────────────────
    elif quiz["phase"] == "active":
        words = quiz["words"]
        total = len(words)
        answered = sum(1 for a in quiz["answers"] if a.strip())
        st.progress(answered / total, f"Câu {answered}/{total}")

        st.markdown("---")
        for idx, entry in enumerate(words):
            word = entry.get("word", "")
            col_q, col_a = st.columns([1, 2])
            with col_q:
                st.markdown(f"**{idx + 1}. {word}**")
            with col_a:
                quiz["answers"][idx] = st.text_input(
                    "Nghĩa tiếng Việt", key=f"mini_quiz_{idx}",
                    label_visibility="collapsed", placeholder="Nhập nghĩa…",
                )

        if st.button("📝 Nộp bài", type="primary", use_container_width=True,
                      key="mini_quiz_submit"):
            st.session_state["vocab_quiz"]["phase"] = "submitted"
            st.rerun()

    # ── Submitted — show results ────────────────────────────────────────────
    elif quiz["phase"] == "submitted":
        words = quiz["words"]
        correct = 0
        wrong_indices = []

        for idx, entry in enumerate(words):
            correct_meanings = [m.strip().lower() for m in _all_meanings(entry)]
            user_ans = quiz["answers"][idx].strip().lower()
            if user_ans in correct_meanings:
                correct += 1
            else:
                wrong_indices.append(idx)

        st.markdown(f"### ✅ Kết quả: {correct}/{len(words)}")

        for idx, entry in enumerate(words):
            word = entry.get("word", "")
            correct_meanings = _all_meanings(entry)
            user_ans = quiz["answers"][idx].strip().lower()
            ok = any(user_ans == m.strip().lower() for m in correct_meanings)
            if ok:
                st.markdown(f"✅ **{word}** — *{user_ans}*")
            else:
                st.markdown(
                    f"❌ **{word}** — *{user_ans or '(bỏ trống)'}*  \n"
                    f"<small style='color:#f0ad4e'>Đáp án: {', '.join(correct_meanings)}</small>",
                    unsafe_allow_html=True,
                )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Làm lại", use_container_width=True, key="mini_quiz_retry"):
                st.session_state.pop("vocab_quiz", None)
                st.rerun()
        with col2:
            if wrong_indices and st.button("📋 Từ sai → REVIEW", use_container_width=True,
                                            key="mini_quiz_review"):
                for idx in wrong_indices:
                    entry = words[idx]
                    try:
                        run_async(store.mark_sense_review(entry["_id"], 0))
                    except Exception:
                        _logger.exception("mini_quiz: mark_sense_review failed")
                st.toast(f"✅ Đã đánh dấu {len(wrong_indices)} từ cần ôn tập")
                st.rerun()
