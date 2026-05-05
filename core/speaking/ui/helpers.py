from __future__ import annotations

import threading

import streamlit as st

from core.async_utils import run_async
from core.config import DEFAULT_ACCENT
from core.speaking.question_gen import QuestionGenerator


_RESULT_LOCK = threading.Lock()


def hear_question(question: str, key: str) -> None:
    qgen: QuestionGenerator | None = st.session_state.get("question_gen")
    if qgen is None:
        return
    accent = st.session_state.get("examiner_accent", DEFAULT_ACCENT)
    if st.button("Hear question", key=key, use_container_width=True):
        with st.spinner("Generating audio..."):
            try:
                wav = run_async(qgen.speak_question(question, accent=accent))
                st.audio(wav, format="audio/wav", autoplay=True)
            except Exception as e:
                st.warning(f"TTS unavailable: {e}")


def clear_streaming_state() -> None:
    for key in ("eval_result", "eval_auto_played"):
        st.session_state.pop(key, None)
