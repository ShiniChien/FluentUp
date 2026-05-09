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

_POLL_INTERVAL = 0.5


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
    with st.spinner("Đang tạo đề..."):
        task_type = st.session_state["writing_task_type"]
        try:
            topic = run_async(get_topic(store, task_type, secrets))
            st.session_state["writing_topic"] = topic
            st.session_state["writing_phase"] = "writing"
        except Exception as exc:
            st.error(f"Không thể tạo đề: {exc}")
            st.session_state["writing_phase"] = "idle"
    st.rerun()


def _render_evaluating() -> None:
    with st.spinner("Đang chấm bài..."):
        while st.session_state["writing_eval_result"] is None:
            time.sleep(_POLL_INTERVAL)
    st.session_state["writing_phase"] = "result"
    st.rerun()
