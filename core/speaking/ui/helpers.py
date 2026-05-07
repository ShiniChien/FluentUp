from __future__ import annotations

import threading

import streamlit as st

from core.async_utils import run_async
from core.speaking.config import DEFAULT_ACCENT
from core.speaking.question_gen import QuestionGenerator


_RESULT_LOCK = threading.Lock()


def hear_question(question: str, key: str) -> None:
    qgen: QuestionGenerator | None = st.session_state.get("question_gen")
    if qgen is None:
        return
    accent = st.session_state.get("examiner_accent", DEFAULT_ACCENT)
    listening_mode = st.session_state.get("listening_mode", True)
    cache_key = f"_q_audio_{key}"
    played_key = f"_q_audio_{key}_played"

    if listening_mode:
        wav = st.session_state.get(cache_key)
        if wav:
            # Already generated — show player (no button)
            autoplay = not st.session_state.get(played_key, False)
            st.audio(wav, format="audio/wav", autoplay=autoplay)
            st.session_state[played_key] = True
        else:
            if st.button("Hear question", key=key, use_container_width=True):
                with st.spinner("Generating audio..."):
                    try:
                        wav = run_async(qgen.speak_question(question, accent=accent))
                        st.session_state[cache_key] = wav
                        st.session_state[played_key] = False
                        st.rerun()
                    except Exception as e:
                        st.warning(f"TTS unavailable: {e}")
    else:
        if st.button("Hear question", key=key, use_container_width=True):
            with st.spinner("Generating audio..."):
                try:
                    wav = run_async(qgen.speak_question(question, accent=accent))
                    st.audio(wav, format="audio/wav", autoplay=True)
                except Exception as e:
                    st.warning(f"TTS unavailable: {e}")


def seed_question_audio_cache(key: str, wav: bytes) -> None:
    """Pre-populate hear_question cache from a pre-generated wav so it won't re-generate."""
    cache_key = f"_q_audio_{key}"
    played_key = f"_q_audio_{key}_played"
    st.session_state[cache_key] = wav
    st.session_state[played_key] = True  # already played via autoplay


def clear_streaming_state() -> None:
    for key in ("eval_result", "eval_auto_played"):
        st.session_state.pop(key, None)
    # clear per-question audio caches
    for k in list(st.session_state.keys()):
        if k.startswith("_q_audio_"):
            del st.session_state[k]
