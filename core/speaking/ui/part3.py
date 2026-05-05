from __future__ import annotations

import streamlit as st

from core.async_utils import run_async
from core.models import Turn
from core.speaking.question_gen import QuestionGenerator
from core.speaking.session import ExamSession
from .eval import render_evaluation, render_streaming_eval
from .helpers import clear_streaming_state


def render_part3_loading() -> None:
    sess: ExamSession = st.session_state.session
    qgen: QuestionGenerator = st.session_state.question_gen

    st.header("Part 3 — Discussion")

    if qgen is None:
        st.error("Gemini API key required to generate questions.")
        return

    with st.spinner("Generating discussion questions..."):
        try:
            questions = run_async(
                qgen.generate_part3_questions(
                    part2_topic=sess.part2_topic,
                    part2_cue_card=sess.part2_cue_card,
                    profile=st.session_state.get("user_profile"),
                )
            )
            sess.part3_questions = questions
            sess.part3_index = 0
            sess.phase = "part3_idle"
            st.rerun()
        except Exception as e:
            st.error(f"Failed to generate questions: {e}")
            if st.button("Retry", use_container_width=True):
                st.rerun()


def render_part3_idle() -> None:
    sess: ExamSession = st.session_state.session
    question = sess.current_part3_question()
    idx = sess.part3_index
    total = len(sess.part3_questions)

    st.header("Part 3 — Two-way Discussion")
    st.caption(f"Question {idx + 1} of {total}")
    st.progress((idx) / total)

    if question is None:
        sess.phase = "part3_summary"
        st.rerun()
        return

    st.markdown(
        f"<div style='border-left:4px solid #E65100;border-radius:6px;padding:20px 24px;"
        f"font-size:1.3em;font-weight:500;margin:20px 0'>{question}</div>",
        unsafe_allow_html=True,
    )

    from .helpers import hear_question
    hear_question(question, key=f"p3_tts_{idx}")

    audio = st.audio_input("Record your answer", key=f"p3_audio_{idx}")

    col1, col2 = st.columns([3, 1])
    with col1:
        if audio is not None:
            wav_bytes = audio.getvalue()
            if len(wav_bytes) < 4000:
                st.warning("Recording too short. Please try again.")
            else:
                sess.turns.append(Turn(part=3, question=question, audio_bytes=wav_bytes))
                clear_streaming_state()
                sess.phase = "part3_result"
                st.rerun()
    with col2:
        if st.button("Skip", key=f"p3_skip_{idx}", use_container_width=True):
            sess.part3_index += 1
            if sess.part3_index >= total:
                sess.phase = "part3_summary"
            st.rerun()


def render_part3_result() -> None:
    sess: ExamSession = st.session_state.session

    p3_turns = sess.part_turns(3)
    if not p3_turns:
        sess.phase = "part3_idle"
        st.rerun()
        return

    turn = p3_turns[-1]
    idx = sess.part3_index
    total = len(sess.part3_questions)

    st.header("Part 3 — Evaluation")
    st.caption(f"Question {idx + 1} of {total}")

    if turn.result is None:
        if render_streaming_eval(turn, part=3):
            st.rerun()
        return

    with st.expander("Your answer (playback)", expanded=False):
        st.audio(turn.audio_bytes, format="audio/wav")

    render_evaluation(turn.result)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        next_label = "Next Question" if (idx + 1) < total else "View Part 3 Summary"
        if st.button(next_label, type="primary", use_container_width=True):
            sess.part3_index += 1
            if sess.part3_index >= total:
                sess.phase = "part3_summary"
            else:
                sess.phase = "part3_idle"
            st.rerun()
    with col2:
        if st.button("Retry This Question", use_container_width=True):
            sess.turns.pop()
            sess.phase = "part3_idle"
            st.rerun()


def render_part3_summary() -> None:
    sess: ExamSession = st.session_state.session
    p3_turns = sess.part_turns(3)

    st.header("Part 3 Summary")

    if not p3_turns:
        st.info("No answers recorded for Part 3.")
    else:
        from .part1 import render_part_averages
        evaluated = [t for t in p3_turns if t.result]
        if evaluated:
            render_part_averages(evaluated)

    st.markdown("---")
    if st.button("View Session Summary", type="primary", use_container_width=True):
        sess.phase = "session_summary"
        st.rerun()
