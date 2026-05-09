from __future__ import annotations

import streamlit as st

from core.writing.ui.state import reset_state
from core.writing.evaluator import _first_criterion_name


def render_result() -> None:
    result = st.session_state["writing_eval_result"]
    task_type = st.session_state["writing_task_type"]

    if result is None:
        st.error("Không có kết quả.")
        return

    if "error" in result:
        st.error(f"Lỗi chấm bài: {result['error']}")
        if st.button("Thử lại"):
            st.session_state["writing_phase"] = "writing"
            st.rerun()
        return

    overall = result.get("overall_band", "—")
    st.markdown(f"## Kết quả: Band **{overall}**")
    st.divider()

    first_name = _first_criterion_name(task_type)
    criteria = [
        (first_name, result["task_achievement"]),
        ("Coherence & Cohesion", result["coherence_cohesion"]),
        ("Lexical Resource", result["lexical_resource"]),
        ("Grammatical Range & Accuracy", result["grammatical_range"]),
    ]
    cols = st.columns(4)
    for col, (name, data) in zip(cols, criteria):
        with col:
            st.metric(label=name, value=str(data["band"]))
            st.caption(data["comment"])

    st.divider()
    st.markdown("**Nhận xét tổng:**")
    st.write(result.get("summary", ""))

    if st.button("Làm bài mới"):
        reset_state()
        st.rerun()
