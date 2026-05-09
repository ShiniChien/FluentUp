from __future__ import annotations

import streamlit as st

from core.writing.chart_gen import build_figure
from core.shared import get_text_provider
from core.writing.evaluator import start_evaluation

_MIN_WORDS = 150


def render_task1(secrets: dict) -> None:
    topic = st.session_state["writing_topic"]

    st.markdown(f"**{topic['prompt']}**")

    if topic.get("chart_data"):
        try:
            fig = build_figure(topic["chart_data"])
            st.plotly_chart(fig, use_container_width=True)
        except Exception as exc:
            st.warning(f"Không thể hiển thị biểu đồ: {exc}")

    essay = st.text_area(
        "Bài viết của bạn",
        value=st.session_state["writing_essay"],
        height=350,
        key="writing_essay_input",
        placeholder=f"Viết ít nhất {_MIN_WORDS} từ...",
    )
    st.session_state["writing_essay"] = essay

    word_count = len(essay.split()) if essay.strip() else 0
    color = "green" if word_count >= _MIN_WORDS else "red"
    st.markdown(f"Số từ: :{color}[**{word_count}**] / {_MIN_WORDS} (tối thiểu)")

    if st.button("Nộp bài", disabled=(word_count < _MIN_WORDS)):
        start_evaluation(
            provider=get_text_provider(secrets),
            task_type="task1",
            topic=topic,
            essay=essay,
        )
        st.session_state["writing_phase"] = "evaluating"
        st.rerun()
