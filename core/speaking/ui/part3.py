from __future__ import annotations

import asyncio
import threading
import time

import streamlit as st

from core.async_utils import run_async
from core.config import DEFAULT_ACCENT
from core.models import Turn
from core.speaking.question_gen import QuestionGenerator
from core.speaking.session import ExamSession
from .eval import render_evaluation, render_streaming_eval
from .helpers import _RESULT_LOCK, clear_streaming_state, hear_question


def _start_next_part3_question_gen(prev_question: str, answer_wav: bytes) -> None:
    qgen: QuestionGenerator | None = st.session_state.get("question_gen")
    if qgen is None:
        return
    accent = st.session_state.get("examiner_accent", DEFAULT_ACCENT)
    profile = st.session_state.get("user_profile")
    sess: ExamSession = st.session_state.session
    part2_topic = sess.part2_topic or ""

    result: dict = {"ready": False, "text": "", "wav": b"", "_started": time.time()}
    st.session_state["p3_next_q"] = result

    def _worker() -> None:
        try:
            text, wav = asyncio.run(qgen.generate_next_part3_question(
                prev_question=prev_question,
                answer_wav=answer_wav,
                part2_topic=part2_topic,
                accent=accent,
                profile=profile,
            ))
            with _RESULT_LOCK:
                result["text"] = text
                result["wav"] = wav
        except Exception as exc:
            with _RESULT_LOCK:
                result["error"] = str(exc)
        finally:
            result["ready"] = True

    threading.Thread(target=_worker, daemon=True).start()


def render_part3_loading() -> None:
    sess: ExamSession = st.session_state.session
    qgen: QuestionGenerator = st.session_state.question_gen

    st.header("Part 3 — Discussion")

    if qgen is None:
        st.error("Gemini API key required to generate questions.")
        return

    with st.spinner("Generating first question..."):
        try:
            questions = run_async(
                qgen.generate_part3_questions(
                    part2_topic=sess.part2_topic,
                    part2_cue_card=sess.part2_cue_card,
                    profile=st.session_state.get("user_profile"),
                    n=1,
                )
            )
            sess.part3_questions = questions
            sess.part3_index = 0
            st.session_state.pop("p3_next_q", None)
            sess.phase = "part3_idle"
            st.rerun()
        except Exception as e:
            st.error(f"Failed to generate questions: {e}")
            if st.button("Retry", use_container_width=True):
                st.rerun()


def render_part3_idle() -> None:
    sess: ExamSession = st.session_state.session
    idx = sess.part3_index

    st.header("Part 3 — Two-way Discussion")

    next_q: dict | None = st.session_state.get("p3_next_q")
    if next_q is not None and not next_q.get("ready", False):
        elapsed = time.time() - next_q.get("_started", time.time())
        if elapsed > 45:
            next_q["error"] = "Question generation timed out."
            next_q["ready"] = True
            st.rerun()
            return
        st.caption(f"Question {idx + 1}")
        st.info("Preparing next question...")
        time.sleep(0.5)
        st.rerun()
        return

    if next_q is not None and next_q.get("ready", False):
        if next_q.get("error"):
            st.warning(f"Could not generate next question: {next_q['error']}")
        q_text = next_q.get("text", "").strip()
        q_wav = next_q.get("wav", b"")
        if q_text:
            sess.part3_questions.append(q_text)
            if q_wav:
                st.session_state["p3_next_q_wav"] = q_wav
        st.session_state.pop("p3_next_q", None)
        st.rerun()
        return

    question = sess.current_part3_question()
    st.caption(f"Question {idx + 1}")

    next_wav = st.session_state.pop("p3_next_q_wav", None)
    if next_wav:
        st.audio(next_wav, format="audio/wav", autoplay=True)

    if question is None:
        sess.phase = "part3_summary"
        st.rerun()
        return

    st.markdown(
        f"<div style='border-left:4px solid #E65100;border-radius:6px;padding:20px 24px;"
        f"font-size:1.3em;font-weight:500;margin:20px 0'>{question}</div>",
        unsafe_allow_html=True,
    )

    hear_question(question, key=f"p3_tts_{idx}")

    audio = st.audio_input("Record your answer", key=f"p3_audio_{idx}")

    col1, col2 = st.columns([4, 1])
    with col1:
        if audio is not None:
            wav_bytes = audio.getvalue()
            if len(wav_bytes) < 4000:
                st.warning("Recording too short. Please try again.")
            else:
                sess.turns.append(Turn(part=3, question=question, audio_bytes=wav_bytes))
                sess.part3_index += 1
                _start_next_part3_question_gen(question, wav_bytes)
                clear_streaming_state()
                sess.phase = "part3_result"
                st.rerun()
    with col2:
        if st.button("End Part 3", key=f"p3_end_{idx}", use_container_width=True):
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

    st.header("Part 3 — Evaluation")
    st.caption(f"Question {idx}")

    if turn.result is None:
        if render_streaming_eval(turn, part=3):
            st.rerun()
        return

    with st.expander("Your answer (playback)", expanded=False):
        st.audio(turn.audio_bytes, format="audio/wav")

    render_evaluation(turn.result)

    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Next Question", type="primary", use_container_width=True):
            sess.phase = "part3_idle"
            st.rerun()
    with col2:
        if st.button("Retry This Question", use_container_width=True):
            sess.turns.pop()
            sess.part3_index -= 1
            st.session_state.pop("p3_next_q", None)
            st.session_state.pop("p3_next_q_wav", None)
            sess.phase = "part3_idle"
            st.rerun()
    with col3:
        if st.button("End Part 3", use_container_width=True):
            sess.phase = "part3_summary"
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
