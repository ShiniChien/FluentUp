from __future__ import annotations

import time

import streamlit as st

from core.async_utils import run_async
from core.shared import load_secrets, get_store
from core.writing.topic_pool import get_topic
from core.writing.ui.state import init_state
from core.writing.ui.task1 import render_task1
from core.writing.ui.task2 import render_task2
from core.writing.ui.result import render_result
from core.writing.evaluator import _RESULT_LOCK

_POLL_INTERVAL = 0.5
_EVAL_TIMEOUT_SECS = 120


def main() -> None:
    st.title("IELTS Writing Practice")
    init_state()
    secrets = load_secrets()
    store   = get_store(secrets)

    phase = st.session_state["writing_phase"]

    if phase == "idle":
        _render_idle(secrets, store)

    elif phase == "generating_topic":
        _render_generating(secrets, store)

    elif phase == "writing":
        task_type = st.session_state["writing_task_type"]
        if task_type == "task1":
            render_task1(secrets)
        else:
            render_task2(secrets)

    elif phase == "evaluating":
        _render_evaluating()

    elif phase == "result":
        render_result()

    else:
        st.session_state["writing_phase"] = "idle"
        st.rerun()


def _render_idle(secrets, store) -> None:
    if st.session_state.get("writing_error"):
        st.error(st.session_state["writing_error"])
        st.session_state["writing_error"] = None
    st.markdown("Chọn loại bài viết để bắt đầu luyện tập:")
    task_type = st.radio(
        "Loại bài",
        options=["task1", "task2"],
        format_func=lambda x: "Task 1 — Mô tả biểu đồ" if x == "task1" else "Task 2 — Viết luận",
        horizontal=True,
    )
    if st.button("Bắt đầu"):
        st.session_state["writing_task_type"] = task_type
        st.session_state["writing_phase"]     = "generating_topic"
        st.rerun()


def _render_generating(secrets, store) -> None:
    if store is None:
        st.session_state["writing_error"] = "MongoDB không được cấu hình. Vui lòng kiểm tra kết nối."
        st.session_state["writing_phase"] = "idle"
        st.rerun()
        return
    with st.spinner("Đang tạo đề..."):
        task_type = st.session_state["writing_task_type"]
        try:
            topic = run_async(get_topic(store, task_type, secrets))
            st.session_state["writing_topic"] = topic
            st.session_state["writing_phase"] = "writing"
            st.rerun()
        except Exception as exc:
            st.session_state["writing_error"] = f"Không thể tạo đề: {exc}"
            st.session_state["writing_phase"] = "idle"
            st.rerun()


def _render_evaluating() -> None:
    with _RESULT_LOCK:
        result = st.session_state.get("writing_eval_result")
    if result is not None:
        st.session_state["writing_phase"] = "result"
        st.rerun()
        return
    elapsed = time.time() - st.session_state.get("writing_eval_started_at", time.time())
    if elapsed > _EVAL_TIMEOUT_SECS:
        st.session_state["writing_eval_result"] = {"error": "Đánh giá quá thời gian chờ."}
        st.session_state["writing_phase"] = "result"
        st.rerun()
        return
    with st.spinner("Đang chấm bài..."):
        time.sleep(_POLL_INTERVAL)
    st.rerun()
