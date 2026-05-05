from __future__ import annotations

import streamlit as st

from core.auth import current_user
from core.models import UserProfile
from core.shared import load_secrets
from core.speaking.evaluator import LiveEvaluationPipeline
from core.speaking.question_gen import QuestionGenerator
from core.speaking.session import ExamSession

from .helpers import clear_streaming_state
from .sidebar import render_sidebar
from .home import render_home
from .part1 import render_part1_loading, render_part1_idle, render_part1_summary
from .part2 import render_part2_idle, render_part2_thinking, render_part2_recording, render_part2_evaluating, render_part2_result
from .part3 import render_part3_loading, render_part3_idle, render_part3_result, render_part3_summary
from .summary import render_session_summary

_STATE_VERSION = 8


def _init_state(secrets: dict) -> None:
    if st.session_state.get("_state_version") != _STATE_VERSION:
        for key in ("evaluator", "question_gen"):
            st.session_state.pop(key, None)
        st.session_state["_state_version"] = _STATE_VERSION

    if "session" not in st.session_state:
        st.session_state.session = ExamSession()
    if "evaluator" not in st.session_state:
        if secrets["gemini_api_key"]:
            st.session_state.evaluator = LiveEvaluationPipeline(
                api_key=secrets["gemini_api_key"],
                model=secrets["live_model"],
                openrouter_base_url=secrets["openrouter_base_url"],
                openrouter_api_key=secrets["openrouter_api_key"],
                openrouter_model=secrets["openrouter_model"],
            )
        else:
            st.session_state.evaluator = None
    if "question_gen" not in st.session_state:
        if secrets["gemini_api_key"]:
            st.session_state.question_gen = QuestionGenerator(
                api_key=secrets["gemini_api_key"],
                live_model=secrets["live_model"],
                openrouter_base_url=secrets["openrouter_base_url"],
                openrouter_api_key=secrets["openrouter_api_key"],
                openrouter_model=secrets["openrouter_model"],
            )
        else:
            st.session_state.question_gen = None

    # Sync user_profile from logged-in account if not set
    if "user_profile" not in st.session_state:
        user = current_user()
        if user and user.get("name"):
            st.session_state["user_profile"] = UserProfile(
                name=user.get("name", ""),
                age=int(user.get("age") or 22),
                occupation=user.get("occupation", "student"),
                occupation_detail=user.get("occupation_detail", ""),
                gender=user.get("gender", "male"),
            )


def main() -> None:
    secrets = load_secrets()
    _init_state(secrets)
    st.session_state["_secrets"] = secrets
    render_sidebar(secrets)

    if not secrets["gemini_api_key"]:
        st.error("Add `GEMINI_API_KEY` to `.streamlit/secrets.toml` to start.")
        st.info("The app requires Gemini for audio transcription and question generation.")
        return

    sess: ExamSession = st.session_state.session
    phase = sess.phase

    dispatch = {
        "home":             render_home,
        "part1_loading":    render_part1_loading,
        "part1_idle":       render_part1_idle,
        "part1_summary":    render_part1_summary,
        "part2_idle":       render_part2_idle,
        "part2_thinking":   render_part2_thinking,
        "part2_recording":  render_part2_recording,
        "part2_evaluating": render_part2_evaluating,
        "part2_result":     render_part2_result,
        "part3_loading":    render_part3_loading,
        "part3_idle":       render_part3_idle,
        "part3_result":     render_part3_result,
        "part3_summary":    render_part3_summary,
        "session_summary":  render_session_summary,
    }

    renderer = dispatch.get(phase, render_home)
    renderer()
