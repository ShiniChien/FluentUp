from __future__ import annotations

import streamlit as st

from core.writing.evaluator import start_evaluation

_MIN_WORDS = 250


def render_task2(secrets: dict) -> None:
    topic = st.session_state["writing_topic"]

    st.markdown(f"**{topic['prompt']}**")

    essay = st.text_area(
        "Bài viết của bạn",
        value=st.session_state["writing_essay"],
        height=400,
        key="writing_essay_input",
        placeholder=f"Viết ít nhất {_MIN_WORDS} từ...",
    )
    st.session_state["writing_essay"] = essay

    word_count = len(essay.split()) if essay.strip() else 0
    color = "green" if word_count >= _MIN_WORDS else "red"
    st.markdown(f"Số từ: :{color}[**{word_count}**] / {_MIN_WORDS} (tối thiểu)")

    if st.button("Nộp bài", disabled=(word_count < _MIN_WORDS)):
        start_evaluation(
            secrets=secrets,
            task_type="task2",
            topic=topic,
            essay=essay,
        )
        st.session_state["writing_phase"] = "evaluating"
        st.rerun()
