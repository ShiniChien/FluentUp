from __future__ import annotations

import asyncio
import threading
import time

import streamlit as st

from core.async_utils import run_async
from core.speaking.config import DEFAULT_ACCENT, QUESTION_GEN_TIMEOUT_SEC, MIN_AUDIO_BYTES
from core.models import Turn, UserProfile
from core.speaking.question_gen import QuestionGenerator
from core.speaking.session import ExamSession
from core.speaking.ui.eval import render_evaluation, assemble_bg_evals, start_bg_turn_eval
from core.speaking.ui.helpers import _RESULT_LOCK, hear_question, render_question_blurred, seed_question_audio_cache

_QUESTION_POLL_INTERVAL = 0.5
_EVAL_POLL_INTERVAL = 0.8


def _start_next_question_gen(prev_question: str, answer_wav: bytes) -> None:
    qgen: QuestionGenerator | None = st.session_state.get("question_gen")
    if qgen is None:
        return
    accent = st.session_state.get("examiner_accent", DEFAULT_ACCENT)
    profile: UserProfile | None = st.session_state.get("user_profile")
    result: dict = {"ready": False, "text": "", "wav": b"", "_started": time.time()}
    st.session_state["p1_next_q"] = result

    def _worker() -> None:
        try:
            text, wav = asyncio.run(qgen.generate_next_part1_question(
                prev_question=prev_question,
                answer_wav=answer_wav,
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


def render_part_averages(evaluated: list) -> None:
    st.markdown(
        f"<div style='background:#E3F2FD;border-left:4px solid #1565C0;"
        f"padding:10px 16px;border-radius:6px;font-size:1.05em;color:#1a1a1a'>"
        f"<b>{len(evaluated)}</b> answer(s) evaluated — listen to each examiner's feedback below."
        f"</div>",
        unsafe_allow_html=True,
    )


def render_part1_loading() -> None:
    sess: ExamSession = st.session_state.session
    qgen: QuestionGenerator = st.session_state.question_gen

    st.header("Part 1 — Introduction & Interview")

    if qgen is None:
        st.error("Gemini API key required to generate questions.")
        if st.button("Back to Home", use_container_width=True):
            sess.phase = "home"
            st.rerun()
        return

    with st.spinner("Loading first question..."):
        try:
            profile: UserProfile | None = st.session_state.get("user_profile")
            questions = run_async(qgen.generate_part1_questions(n=1, profile=profile))
            sess.part1_questions = questions
            sess.part1_index = 0
            st.session_state.pop("p1_next_q", None)
            sess.phase = "part1_idle"
            st.rerun()
        except Exception as e:
            st.error(f"Failed to generate questions: {e}")
            if st.button("Retry", use_container_width=True):
                st.rerun()


def render_part1_idle() -> None:
    sess: ExamSession = st.session_state.session
    idx = sess.part1_index

    st.header("Part 1 — Introduction & Interview")

    next_q: dict | None = st.session_state.get("p1_next_q")
    if next_q is not None and not next_q.get("ready", False):
        elapsed = time.time() - next_q.get("_started", time.time())
        if elapsed > QUESTION_GEN_TIMEOUT_SEC:
            next_q["error"] = "Question generation timed out."
            next_q["ready"] = True
            st.rerun()
            return
        st.caption(f"Question {idx + 1}")
        st.info("Preparing next question...")
        time.sleep(_QUESTION_POLL_INTERVAL)
        st.rerun()
        return

    if next_q is not None and next_q.get("ready", False):
        if next_q.get("error"):
            st.warning(f"Could not generate next question: {next_q['error']}")
        q_text = next_q.get("text", "").strip()
        q_wav = next_q.get("wav", b"")
        if q_text:
            sess.part1_questions.append(q_text)
            if q_wav:
                st.session_state["p1_next_q_wav"] = q_wav
        st.session_state.pop("p1_next_q", None)
        st.rerun()
        return

    question = sess.current_part1_question()
    st.caption(f"Question {idx + 1}")

    next_wav = st.session_state.pop("p1_next_q_wav", None)
    if next_wav:
        st.audio(next_wav, format="audio/wav", autoplay=True)
        seed_question_audio_cache(f"p1_tts_{idx}", next_wav)

    if question is None:
        sess.phase = "part1_summary"
        st.rerun()
        return

    render_question_blurred(
        f"<div style='border-left:4px solid #1565C0;border-radius:6px;padding:20px 24px;"
        f"font-size:1.3em;font-weight:500;margin:20px 0'>{question}</div>",
        uid=f"p1_{idx}",
    )

    hear_question(question, key=f"p1_tts_{idx}")

    audio = st.audio_input("Record your answer", key=f"p1_audio_{idx}")

    col1, col2 = st.columns([5, 1])
    with col1:
        if audio is not None:
            wav_bytes = audio.getvalue()
            if len(wav_bytes) < MIN_AUDIO_BYTES:
                st.warning("Recording too short. Please try again.")
            else:
                sess.turns.append(Turn(part=1, question=question, audio_bytes=wav_bytes))
                turn_idx = len(sess.turns) - 1
                sess.part1_index += 1
                start_bg_turn_eval(sess.turns[turn_idx], turn_idx, part=1)
                _start_next_question_gen(question, wav_bytes)
                st.rerun()
    with col2:
        if st.button("End Part 1", key=f"p1_end_{idx}", use_container_width=True):
            sess.phase = "part1_summary"
            st.rerun()


def render_part1_summary() -> None:
    sess: ExamSession = st.session_state.session
    p1_turns = sess.part_turns(1)

    st.header("Part 1 Summary")

    pending = assemble_bg_evals(sess)
    if pending > 0:
        evaluated_count = sum(1 for t in p1_turns if t.result is not None)
        total = len(p1_turns)
        st.info(f"Evaluating answers in background… ({evaluated_count}/{total} complete)")
        st.progress(evaluated_count / total if total else 0)
        time.sleep(_EVAL_POLL_INTERVAL)
        st.rerun()
        return

    if not p1_turns:
        st.info("No answers recorded for Part 1.")
    else:
        evaluated = [t for t in p1_turns if t.result]

        if evaluated:
            render_part_averages(evaluated)

            st.markdown("---")
            st.markdown("#### Per-question breakdown")
            for i, turn in enumerate(evaluated):
                with st.expander(
                    f"Q{i + 1}: {turn.question[:70]}{'…' if len(turn.question) > 70 else ''}",
                    expanded=False,
                ):
                    st.audio(turn.audio_bytes, format="audio/wav")
                    render_evaluation(turn.result, key_suffix=f"p1_{i}", question=turn.question)
        else:
            st.info("No evaluated answers yet.")

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Continue to Part 2", type="primary", use_container_width=True):
            sess.phase = "part2_idle"
            st.rerun()
    with col2:
        if st.button("Go to Part 3", use_container_width=True):
            sess.phase = "part3_loading"
            st.rerun()
