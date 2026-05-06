from __future__ import annotations

import time

import streamlit as st

from core.async_utils import run_async
from core.auth import current_user
from core.models import Turn
from core.shared import get_store
from core.speaking.question_gen import QuestionGenerator
from core.speaking.config import MIN_AUDIO_BYTES, SPEAK_WARN_SECONDS, SPEAK_ALERT_SECONDS
from core.speaking.session import ExamSession, PREP_SECONDS, SPEAK_SECONDS
from core.speaking.ui.eval import render_evaluation, render_streaming_eval
from core.speaking.ui.helpers import clear_streaming_state


def render_part2_idle() -> None:
    sess: ExamSession = st.session_state.session
    qgen: QuestionGenerator = st.session_state.question_gen

    st.header("Part 2 — Individual Long Turn")

    if sess.part2_cue_card is None:
        if qgen is None:
            st.error("Gemini API key required to generate cue card.")
            return

        with st.spinner("Generating cue card..."):
            try:
                cue = run_async(qgen.generate_cue_card(
                    profile=st.session_state.get("user_profile"),
                ))
                sess.part2_cue_card = cue
                sess.part2_topic = cue.topic
                st.rerun()
            except Exception as e:
                st.error(f"Failed to generate cue card: {e}")
                if st.button("Retry", use_container_width=True):
                    st.rerun()
                return

    cue = sess.part2_cue_card
    st.markdown(
        f"<div style='border:2px solid #6A1B9A;border-radius:12px;padding:24px;font-size:1.1em;margin:16px 0'>"
        f"<h3 style='color:#6A1B9A'>{cue.topic}</h3>"
        f"<p><b>You should say:</b></p>"
        f"<ul>{''.join(f'<li>{p}</li>' for p in cue.points)}</ul>"
        f"<p><i>{cue.explain}</i></p>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.info("You have 1 minute to prepare, then 2 minutes to speak.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Start Preparation", type="primary", use_container_width=True):
            sess.prep_start_time = time.time()
            sess.phase = "part2_thinking"
            st.rerun()
    with col2:
        if st.button("New Cue Card", use_container_width=True):
            sess.part2_cue_card = None
            sess.part2_topic = ""
            st.rerun()


@st.fragment(run_every=1)
def _prep_countdown_fragment():
    sess: ExamSession = st.session_state.session
    remaining = sess.prep_remaining()
    progress_val = (PREP_SECONDS - remaining) / PREP_SECONDS
    st.progress(progress_val, text=f"Preparation time: {remaining}s remaining")
    if remaining == 0:
        sess.phase = "part2_recording"
        sess.speaking_start_time = time.time()
        st.rerun()


def render_part2_thinking() -> None:
    sess: ExamSession = st.session_state.session
    cue = sess.part2_cue_card

    st.header("Part 2 — Preparation Time")

    if cue:
        st.markdown(
            f"<div style='border:2px solid #6A1B9A;"
            f"border-radius:12px;padding:20px;font-size:1.05em'>"
            f"<h3 style='color:#6A1B9A'>{cue.topic}</h3>"
            f"<ul>{''.join(f'<li>{p}</li>' for p in cue.points)}</ul>"
            f"<p><i>{cue.explain}</i></p>"
            f"</div>",
            unsafe_allow_html=True,
        )

    _prep_countdown_fragment()

    if st.button("Start Speaking Early", use_container_width=True):
        sess.phase = "part2_recording"
        sess.speaking_start_time = time.time()
        st.rerun()


@st.fragment(run_every=1)
def _speak_countdown_fragment():
    sess: ExamSession = st.session_state.session
    remaining = sess.speak_remaining()
    progress_val = (SPEAK_SECONDS - remaining) / SPEAK_SECONDS
    mins = remaining // 60
    secs = remaining % 60

    if remaining <= SPEAK_ALERT_SECONDS:
        st.progress(progress_val, text=f"Speaking time: {mins}:{secs:02d} remaining")
        st.error(f"Almost done! {remaining}s left")
    elif remaining <= SPEAK_WARN_SECONDS:
        st.progress(progress_val, text=f"Speaking time: {mins}:{secs:02d} remaining")
        st.warning(f"Wrap up soon — {remaining}s left")
    else:
        st.progress(progress_val, text=f"Speaking time: {mins}:{secs:02d} remaining")

    if remaining == 0:
        sess.phase = "part2_evaluating"
        st.rerun()


def render_part2_recording() -> None:
    sess: ExamSession = st.session_state.session
    cue = sess.part2_cue_card

    st.header("Part 2 — Speaking")

    if cue:
        with st.expander("Cue Card (reference)", expanded=True):
            st.markdown(f"**{cue.topic}**")
            for p in cue.points:
                st.markdown(f"- {p}")
            st.markdown(f"*{cue.explain}*")

    _speak_countdown_fragment()

    audio = st.audio_input("Record your speech (up to 2 minutes)", key="p2_audio")

    if audio is not None:
        wav_bytes = audio.getvalue()
        if len(wav_bytes) < MIN_AUDIO_BYTES:
            st.warning("Recording too short. Please try again.")
        else:
            question = cue.topic if cue else "Part 2 speech"
            sess.turns.append(Turn(part=2, question=question, audio_bytes=wav_bytes))
            clear_streaming_state()
            sess.phase = "part2_evaluating"
            st.rerun()

    if st.button("Finish Speaking Early", use_container_width=True):
        if not sess.part_turns(2):
            st.info("Please record your answer first using the audio input above.")
        else:
            sess.phase = "part2_evaluating"
            st.rerun()


def render_part2_evaluating() -> None:
    sess: ExamSession = st.session_state.session

    p2_turns = sess.part_turns(2)
    if not p2_turns:
        st.error("No audio recorded for Part 2.")
        if st.button("Go back", use_container_width=True):
            sess.phase = "part2_recording"
            st.rerun()
        return

    turn = p2_turns[-1]

    if turn.result is not None:
        sess.phase = "part2_result"
        st.rerun()
        return

    st.header("Part 2 — Evaluation")

    if render_streaming_eval(turn, part=2):
        sess.phase = "part2_result"
        st.rerun()


def render_part2_result() -> None:
    sess: ExamSession = st.session_state.session
    p2_turns = sess.part_turns(2)

    if not p2_turns or p2_turns[-1].result is None:
        sess.phase = "part2_evaluating"
        st.rerun()
        return

    turn = p2_turns[-1]
    st.header("Part 2 — Result")

    # Save attempt to store once per result (keyed by turn index)
    save_key = f"p2_saved_{len(p2_turns) - 1}"
    if not st.session_state.get(save_key):
        try:
            u = current_user()
            user_id = u.get("_id", "default") if u else "default"
            cue = sess.part2_cue_card
            run_async(get_store().save_part2_attempt(
                user_id=str(user_id),
                topic=sess.part2_topic,
                transcript=turn.result.transcript,
                cue_points=cue.points if cue else [],
                cue_explain=cue.explain if cue else "",
            ))
            st.session_state[save_key] = True
        except Exception:
            pass  # non-critical — don't block the UI

    with st.expander("Your answer (playback)", expanded=False):
        st.audio(turn.audio_bytes, format="audio/wav")

    render_evaluation(turn.result, question=turn.question)

    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Continue to Part 3", type="primary", use_container_width=True):
            sess.phase = "part3_loading"
            st.rerun()
    with col2:
        if st.button("New Cue Card", use_container_width=True):
            sess.part2_cue_card = None
            sess.part2_topic = ""
            sess.phase = "part2_idle"
            st.rerun()
    with col3:
        if st.button("Go to Summary", use_container_width=True):
            sess.phase = "session_summary"
            st.rerun()
