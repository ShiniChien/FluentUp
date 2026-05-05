from __future__ import annotations

import asyncio
import threading
import time

import streamlit as st

from core.models import CriterionFeedback, EvaluationResult, Turn
from core.speaking.evaluator import LiveEvaluationPipeline
from .helpers import _RESULT_LOCK, clear_streaming_state


def start_bg_turn_eval(turn: Turn, turn_idx: int, part: int) -> None:
    evaluator: LiveEvaluationPipeline | None = st.session_state.get("evaluator")
    if evaluator is None:
        return
    language: str = st.session_state.get("feedback_language", "vi")
    turn_evals: dict = st.session_state.setdefault("turn_evals", {})
    result: dict = {"_started": time.time()}
    turn_evals[turn_idx] = result

    def _worker() -> None:
        try:
            eval_result, _ = asyncio.run(evaluator.evaluate(
                audio_bytes=turn.audio_bytes,
                question=turn.question,
                part=part,
                language=language,
            ))
            with _RESULT_LOCK:
                result["done"] = eval_result
        except Exception as exc:
            with _RESULT_LOCK:
                result["error"] = str(exc)

    threading.Thread(target=_worker, daemon=True).start()


def assemble_bg_evals(sess) -> int:
    """Assemble completed background evals into turn.result. Returns pending count."""
    turn_evals: dict = st.session_state.get("turn_evals", {})
    _timeout = 120.0
    pending = 0
    for i, turn in enumerate(sess.turns):
        if turn.result is not None:
            continue
        state = turn_evals.get(i)
        if state is None:
            continue
        elapsed = time.time() - state.get("_started", time.time())
        if "done" not in state and "error" not in state:
            if elapsed > _timeout:
                with _RESULT_LOCK:
                    state["error"] = "Evaluation timed out."
            else:
                pending += 1
                continue
        if "done" in state:
            turn.result = state["done"]
        else:
            turn.result = EvaluationResult(
                transcript="",
                feedbacks=[CriterionFeedback(
                    criterion="Examiner",
                    feedback=state["error"],
                    audio=b"",
                )],
            )
    return pending


def _start_streaming_eval(turn: Turn, part: int) -> None:
    evaluator: LiveEvaluationPipeline | None = st.session_state.get("evaluator")
    if evaluator is None:
        return
    language: str = st.session_state.get("feedback_language", "vi")

    result: dict = {"_started": time.time()}
    st.session_state["eval_result"] = result
    st.session_state["eval_auto_played"] = set()

    def _worker() -> None:
        try:
            eval_result, _ = asyncio.run(evaluator.evaluate(
                audio_bytes=turn.audio_bytes,
                question=turn.question,
                part=part,
                language=language,
            ))
            with _RESULT_LOCK:
                result["done"] = eval_result
        except Exception as exc:
            with _RESULT_LOCK:
                result["error"] = str(exc)

    threading.Thread(target=_worker, daemon=True).start()


def render_streaming_eval(turn: Turn, part: int) -> bool:
    """Show evaluator feedback when ready. Returns True when done."""
    evaluator = st.session_state.get("evaluator")
    if evaluator is None:
        st.error("Gemini API key required for evaluation.")
        return False

    result_state = st.session_state.get("eval_result")
    if result_state is None:
        _start_streaming_eval(turn, part)
        st.rerun()
        return False

    if "done" not in result_state and "error" not in result_state:
        elapsed = time.time() - result_state.get("_started", time.time())
        if elapsed > 120:
            with _RESULT_LOCK:
                result_state["error"] = "Evaluation timed out after 2 minutes. Please try again."
            st.rerun()
            return False
        st.markdown("**Examiner is reviewing your answer…**")
        st.progress(min(elapsed / 90, 0.95), text="This may take a moment with thinking enabled")
        time.sleep(0.8)
        st.rerun()
        return False

    played: set = st.session_state.get("eval_auto_played", set())

    if "done" in result_state:
        eval_result: EvaluationResult = result_state["done"]
        for fb in eval_result.feedbacks:
            if fb.audio:
                autoplay = fb.criterion not in played
                st.markdown("**🎙 Listen to examiner feedback + model answer:**")
                st.audio(fb.audio, format="audio/wav", autoplay=autoplay)
                if autoplay:
                    played.add(fb.criterion)
                    st.session_state["eval_auto_played"] = played
            if fb.feedback:
                with st.expander("Read feedback", expanded=False):
                    st.markdown(
                        f"<div style='background:#f8f9fa;border-left:4px solid #6c757d;"
                        f"padding:10px 14px;border-radius:4px;font-size:0.95em;color:#212529'>"
                        f"{fb.feedback}</div>",
                        unsafe_allow_html=True,
                    )
        turn.result = eval_result
    else:
        st.error(result_state["error"])
        turn.result = EvaluationResult(
            transcript="",
            feedbacks=[CriterionFeedback(
                criterion="Examiner",
                feedback=result_state["error"],
                audio=b"",
            )],
        )

    clear_streaming_state()
    return True


def render_evaluation(result: EvaluationResult, key_suffix: str = "") -> None:
    st.markdown("#### Examiner Feedback")

    if result.transcript:
        with st.expander("Your answer (transcript)", expanded=False):
            st.markdown(
                f"<div style='background:#f8f9fa;padding:10px 14px;border-radius:4px;"
                f"font-size:0.9em;color:#555'>{result.transcript}</div>",
                unsafe_allow_html=True,
            )

    for fb in result.feedbacks:
        if fb.audio:
            st.markdown("**🎙 Listen to examiner feedback + model answer:**")
            st.audio(fb.audio, format="audio/wav")
        if fb.feedback:
            with st.expander("Read feedback", expanded=False):
                st.markdown(
                    f"<div style='background:#f8f9fa;border-left:4px solid #6c757d;"
                    f"padding:10px 14px;border-radius:4px;font-size:0.95em;color:#212529'>"
                    f"{fb.feedback}</div>",
                    unsafe_allow_html=True,
                )

    feedback_text = "\n".join(fb.feedback for fb in result.feedbacks if fb.feedback)
    if feedback_text:
        st.download_button(
            "Download Feedback",
            data=feedback_text,
            file_name="feedback.txt",
            mime="text/plain",
            key=f"dl_feedback_{key_suffix}" if key_suffix else None,
        )
