"""
app.py — FluentUp: IELTS Speaking Practice (Streamlit)

Run locally:
    streamlit run app.py
"""
from __future__ import annotations

import asyncio
import re
import time

import streamlit as st

from fluentup.exam_session import ExamSession, PREP_SECONDS, SPEAK_SECONDS
from fluentup.models import Turn, BandScore, EvaluationResult
from fluentup.transcriber import GeminiTranscriber
from fluentup.evaluator import EvaluationPipeline
from fluentup.question_gen import QuestionGenerator
from fluentup.store import FluentUpStore


# ── Secrets ───────────────────────────────────────────────────────────────────

def _load_secrets() -> dict:
    return {
        "gemini_api_key":      st.secrets.get("GEMINI_API_KEY", ""),
        "gemini_model":        st.secrets.get("GEMINI_MODEL", "gemini-2.0-flash"),
        "openrouter_api_key":  st.secrets.get("OPENROUTER_API_KEY", ""),
        "openrouter_base_url": st.secrets.get("OPENROUTER_BASE_URL", ""),
        "openrouter_model":    st.secrets.get("OPENROUTER_MODEL", ""),
        "mongodb_uri":         st.secrets.get("MONGODB_URI", ""),
        "mongodb_username":    st.secrets.get("MONGODB_USERNAME", ""),
        "mongodb_password":    st.secrets.get("MONGODB_PASSWORD", ""),
    }


# ── State init ────────────────────────────────────────────────────────────────

def _init_state(secrets: dict) -> None:
    if "session" not in st.session_state:
        st.session_state.session = ExamSession()
    if "transcriber" not in st.session_state:
        if secrets["gemini_api_key"]:
            st.session_state.transcriber = GeminiTranscriber(
                api_key=secrets["gemini_api_key"],
                model=secrets["gemini_model"],
            )
        else:
            st.session_state.transcriber = None
    if "evaluator" not in st.session_state:
        if secrets["openrouter_api_key"] and secrets["openrouter_base_url"]:
            st.session_state.evaluator = EvaluationPipeline(
                base_url=secrets["openrouter_base_url"],
                api_key=secrets["openrouter_api_key"],
                model=secrets["openrouter_model"],
            )
        else:
            st.session_state.evaluator = None
    if "question_gen" not in st.session_state:
        if secrets["gemini_api_key"]:
            st.session_state.question_gen = QuestionGenerator(
                api_key=secrets["gemini_api_key"],
                model=secrets["gemini_model"],
            )
        else:
            st.session_state.question_gen = None
    if "store" not in st.session_state:
        if secrets["mongodb_uri"] and secrets["mongodb_username"]:
            st.session_state.store = FluentUpStore(
                uri=secrets["mongodb_uri"],
                username=secrets["mongodb_username"],
                password=secrets["mongodb_password"],
            )
        else:
            st.session_state.store = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _band_color(band: float) -> str:
    if band >= 8.0:
        return "#00695C"
    if band >= 7.0:
        return "#2E7D32"
    if band >= 6.0:
        return "#7CB342"
    if band >= 5.0:
        return "#FDD835"
    if band >= 4.0:
        return "#FB8C00"
    return "#E53935"


def _band_bar(band: float) -> str:
    fill = round(band / 9.0 * 20)
    empty = 20 - fill
    return "█" * fill + "░" * empty


def _highlight_fillers(text: str) -> str:
    fillers = r"\b(um|uh|er|like|you know)\b"
    return re.sub(
        fillers,
        r'<span style="background:#FFF3CD;padding:0 3px;border-radius:3px">\1</span>',
        text,
        flags=re.IGNORECASE,
    )


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _render_sidebar(secrets: dict) -> None:
    with st.sidebar:
        st.markdown("## FluentUp")
        st.caption("IELTS Speaking Practice")

        st.divider()
        st.markdown("**API Status**")

        if secrets["gemini_api_key"]:
            st.success("Gemini: Connected")
        else:
            st.error("Gemini: Missing key")

        if secrets["openrouter_api_key"]:
            st.success("Evaluator: Connected")
        else:
            st.warning("Evaluator: Missing key")

        store: FluentUpStore | None = st.session_state.get("store")
        if store is not None:
            st.success("MongoDB: Connected")
        else:
            st.warning("MongoDB: Not configured")

        st.divider()

        sess: ExamSession = st.session_state.session
        phase = sess.phase

        st.markdown("**Session Progress**")
        p1_done = len(sess.part_turns(1))
        p2_done = len(sess.part_turns(2))
        p3_done = len(sess.part_turns(3))

        if p1_done > 0:
            st.caption(f"Part 1: {p1_done} answer(s)")
        if p2_done > 0:
            st.caption(f"Part 2: {p2_done} speech(es)")
        if p3_done > 0:
            st.caption(f"Part 3: {p3_done} answer(s)")

        if not any([p1_done, p2_done, p3_done]):
            st.caption("No answers yet.")

        st.divider()

        if phase != "home":
            if st.button("New Session", use_container_width=True):
                st.session_state.session = ExamSession()
                st.rerun()

        # Part tips
        if "part1" in phase:
            st.markdown("**Part 1 Tips**")
            st.caption("- Answer in 2–3 sentences\n- Add a reason or example\n- Use present tenses for habits")
        elif "part2" in phase:
            st.markdown("**Part 2 Tips**")
            st.caption("- Cover all bullet points\n- Use past tense for stories\n- Start with a clear topic sentence")
        elif "part3" in phase:
            st.markdown("**Part 3 Tips**")
            st.caption("- Give your opinion clearly\n- Use phrases like 'I believe...' / 'It seems to me...'\n- Compare and contrast ideas")


# ── Evaluation display ────────────────────────────────────────────────────────

def _render_evaluation(result: EvaluationResult) -> None:
    st.markdown("#### Evaluation")

    overall = result.overall_band
    color = _band_color(overall)
    st.markdown(
        f"<div style='background:{color};color:white;padding:10px 16px;"
        f"border-radius:8px;font-size:1.2em;font-weight:bold;margin-bottom:12px'>"
        f"Overall Band: {overall:.1f} / 9.0</div>",
        unsafe_allow_html=True,
    )

    cols = st.columns(2)
    for i, score in enumerate(result.scores):
        with cols[i % 2]:
            c = _band_color(score.band)
            st.markdown(
                f"<div style='border:1px solid {c};border-radius:6px;padding:8px;margin:4px 0'>"
                f"<b style='color:{c}'>{score.criterion}</b>&nbsp;&nbsp;"
                f"<span style='font-size:1.1em;font-weight:bold'>{score.band:.1f}</span><br>"
                f"<span style='font-family:monospace;font-size:0.8em'>{_band_bar(score.band)}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("---")
    for score in result.scores:
        c = _band_color(score.band)
        with st.expander(f"{score.criterion} — {score.band:.1f}  {_band_bar(score.band)}"):
            if score.feedback:
                st.markdown(score.feedback)
            if score.examples:
                st.markdown("**Examples from your speech:**")
                for ex in score.examples:
                    st.markdown(f'> "{ex}"')
            if score.tips:
                st.markdown("**Improvement tips:**")
                for tip in score.tips:
                    st.markdown(f"- {tip}")

    # Copy feedback button
    feedback_text = f"Overall Band: {overall:.1f}\n\n"
    for score in result.scores:
        feedback_text += f"{score.criterion}: {score.band:.1f}\n{score.feedback}\n"
        if score.tips:
            feedback_text += "Tips: " + "; ".join(score.tips) + "\n"
        feedback_text += "\n"
    st.download_button(
        "Copy/Download Feedback",
        data=feedback_text,
        file_name="feedback.txt",
        mime="text/plain",
    )


def _render_transcript(transcript: str) -> None:
    st.markdown("#### Your Transcript")
    highlighted = _highlight_fillers(transcript)
    st.markdown(
        f"<div style='background:#f8f9fa;border-left:4px solid #6c757d;"
        f"padding:12px 16px;border-radius:4px;line-height:1.6'>{highlighted}</div>",
        unsafe_allow_html=True,
    )
    st.caption("Orange highlights = filler words (um, uh, er, like, you know)")


# ── Part selector (home) ──────────────────────────────────────────────────────

def _render_home() -> None:
    st.title("FluentUp")
    st.subheader("IELTS Speaking Practice")
    st.markdown("Choose a part to start practicing:")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            "<div style='background:#E3F2FD;border-radius:10px;padding:20px;text-align:center'>"
            "<h3 style='color:#1565C0'>Part 1</h3>"
            "<p>Introduction & Interview</p>"
            "<p style='color:#555;font-size:0.9em'>10 questions on familiar topics</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button("Start Part 1", use_container_width=True, key="start_p1"):
            st.session_state.session.phase = "part1_loading"
            st.rerun()

    with col2:
        st.markdown(
            "<div style='background:#F3E5F5;border-radius:10px;padding:20px;text-align:center'>"
            "<h3 style='color:#6A1B9A'>Part 2</h3>"
            "<p>Individual Long Turn</p>"
            "<p style='color:#555;font-size:0.9em'>Cue card, 1 min prep, 2 min speech</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button("Start Part 2", use_container_width=True, key="start_p2"):
            st.session_state.session.phase = "part2_idle"
            st.rerun()

    with col3:
        st.markdown(
            "<div style='background:#FFF3E0;border-radius:10px;padding:20px;text-align:center'>"
            "<h3 style='color:#E65100'>Part 3</h3>"
            "<p>Two-way Discussion</p>"
            "<p style='color:#555;font-size:0.9em'>5-6 abstract discussion questions</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button("Start Part 3", use_container_width=True, key="start_p3"):
            st.session_state.session.phase = "part3_loading"
            st.rerun()


# ── Part 1 ────────────────────────────────────────────────────────────────────

def _render_part1_loading() -> None:
    sess: ExamSession = st.session_state.session
    qgen: QuestionGenerator = st.session_state.question_gen

    st.header("Part 1 — Introduction & Interview")

    if qgen is None:
        st.error("Gemini API key required to generate questions.")
        if st.button("Back to Home"):
            sess.phase = "home"
            st.rerun()
        return

    with st.spinner("Generating 10 questions..."):
        try:
            questions = _run_async(qgen.generate_part1_questions(n=10))
            sess.part1_questions = questions
            sess.part1_index = 0
            sess.phase = "part1_idle"
            st.rerun()
        except Exception as e:
            st.error(f"Failed to generate questions: {e}")
            if st.button("Retry"):
                st.rerun()


def _render_part1_idle() -> None:
    sess: ExamSession = st.session_state.session
    question = sess.current_part1_question()
    idx = sess.part1_index
    total = len(sess.part1_questions)

    st.header("Part 1 — Introduction & Interview")
    st.caption(f"Question {idx + 1} of {total}")
    st.progress((idx) / total)

    if question is None:
        sess.phase = "part1_summary"
        st.rerun()
        return

    st.markdown(
        f"<div style='background:#E3F2FD;border-radius:10px;padding:24px;"
        f"font-size:1.3em;font-weight:500;margin:20px 0'>{question}</div>",
        unsafe_allow_html=True,
    )

    audio = st.audio_input("Record your answer", key=f"p1_audio_{idx}")

    col1, col2 = st.columns([3, 1])
    with col1:
        if audio is not None:
            wav_bytes = audio.getvalue()
            if len(wav_bytes) < 4000:  # ~0.1s at 16kHz mono
                st.warning("Recording too short. Please try again.")
            else:
                sess.turns.append(Turn(
                    part=1,
                    question=question,
                    audio_bytes=wav_bytes,
                ))
                sess.phase = "part1_result"
                st.rerun()
    with col2:
        if st.button("Skip", key=f"p1_skip_{idx}"):
            sess.part1_index += 1
            if sess.part1_index >= total:
                sess.phase = "part1_summary"
            st.rerun()


def _render_part1_result() -> None:
    sess: ExamSession = st.session_state.session
    transcriber: GeminiTranscriber = st.session_state.transcriber
    evaluator: EvaluationPipeline = st.session_state.evaluator

    # Get the latest turn
    p1_turns = sess.part_turns(1)
    if not p1_turns:
        sess.phase = "part1_idle"
        st.rerun()
        return

    turn = p1_turns[-1]
    idx = sess.part1_index
    total = len(sess.part1_questions)

    st.header("Part 1 — Result")
    st.caption(f"Question {idx + 1} of {total}")

    if turn.result is None:
        # Transcribe + evaluate
        if transcriber is None:
            st.error("Gemini API key required for transcription.")
        elif evaluator is None:
            st.error("OpenRouter API key required for evaluation.")
        else:
            with st.spinner("Transcribing..."):
                try:
                    transcript = _run_async(transcriber.transcribe(turn.audio_bytes))
                except Exception as e:
                    st.error(f"Transcription failed: {e}")
                    if st.button("Retry"):
                        st.rerun()
                    return

            with st.spinner("Evaluating (4 criteria in parallel)..."):
                try:
                    result = _run_async(evaluator.evaluate(
                        transcript=transcript,
                        question=turn.question,
                        part=1,
                    ))
                    turn.result = result
                except Exception as e:
                    st.error(f"Evaluation failed: {e}")
                    if st.button("Retry"):
                        st.rerun()
                    return
            st.rerun()
        return

    # Display result
    _render_transcript(turn.result.transcript)
    st.markdown("---")
    _render_evaluation(turn.result)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        next_label = "Next Question" if (idx + 1) < total else "View Part 1 Summary"
        if st.button(next_label, type="primary"):
            sess.part1_index += 1
            if sess.part1_index >= total:
                sess.phase = "part1_summary"
            else:
                sess.phase = "part1_idle"
            st.rerun()
    with col2:
        if st.button("Retry This Question"):
            # Remove the last turn
            sess.turns.pop()
            sess.phase = "part1_idle"
            st.rerun()


def _render_part1_summary() -> None:
    sess: ExamSession = st.session_state.session
    p1_turns = sess.part_turns(1)

    st.header("Part 1 Summary")

    if not p1_turns:
        st.info("No answers recorded for Part 1.")
    else:
        summary = sess.build_summary()
        # Calculate part 1 specific averages
        evaluated = [t for t in p1_turns if t.result]

        if evaluated:
            criteria = ["FC", "LR", "GR", "Pronunciation"]
            avgs = {}
            for c in criteria:
                bands = [t.result.get_score(c).band for t in evaluated if t.result.get_score(c)]
                avgs[c] = round(sum(bands) / len(bands) * 2) / 2 if bands else 0.0

            overall = round(sum(avgs.values()) / len(avgs) * 2) / 2

            st.markdown(
                f"<div style='background:{_band_color(overall)};color:white;"
                f"padding:12px;border-radius:8px;font-size:1.2em;font-weight:bold'>"
                f"Part 1 Average Band: {overall:.1f}</div>",
                unsafe_allow_html=True,
            )

            cols = st.columns(4)
            for i, (c, avg) in enumerate(avgs.items()):
                with cols[i]:
                    color = _band_color(avg)
                    st.markdown(
                        f"<div style='text-align:center;border:2px solid {color};"
                        f"border-radius:8px;padding:10px'>"
                        f"<b style='color:{color}'>{c}</b><br>"
                        f"<span style='font-size:1.4em;font-weight:bold'>{avg:.1f}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
        else:
            st.info("No evaluated answers yet.")

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Continue to Part 2", type="primary"):
            sess.phase = "part2_idle"
            st.rerun()
    with col2:
        if st.button("Go to Part 3"):
            sess.phase = "part3_loading"
            st.rerun()


# ── Part 2 ────────────────────────────────────────────────────────────────────

def _render_part2_idle() -> None:
    sess: ExamSession = st.session_state.session
    qgen: QuestionGenerator = st.session_state.question_gen

    st.header("Part 2 — Individual Long Turn")

    if sess.part2_cue_card is None:
        if qgen is None:
            st.error("Gemini API key required to generate cue card.")
            return

        with st.spinner("Generating cue card..."):
            try:
                cue = _run_async(qgen.generate_cue_card())
                sess.part2_cue_card = cue
                sess.part2_topic = cue.topic
                st.rerun()
            except Exception as e:
                st.error(f"Failed to generate cue card: {e}")
                if st.button("Retry"):
                    st.rerun()
                return

    cue = sess.part2_cue_card
    st.markdown(
        f"<div style='background:#F3E5F5;border:2px solid #CE93D8;"
        f"border-radius:12px;padding:24px;font-size:1.1em;margin:16px 0'>"
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
        if st.button("Start Preparation", type="primary"):
            sess.prep_start_time = time.time()
            sess.phase = "part2_thinking"
            st.rerun()
    with col2:
        if st.button("New Cue Card"):
            sess.part2_cue_card = None
            sess.part2_topic = ""
            st.rerun()


@st.fragment(run_every=1)
def _prep_countdown_fragment():
    sess: ExamSession = st.session_state.session
    remaining = sess.prep_remaining()

    progress_val = (PREP_SECONDS - remaining) / PREP_SECONDS
    color = "normal"
    if remaining <= 10:
        color = "error"
    elif remaining <= 20:
        color = "warning"

    st.progress(progress_val, text=f"Preparation time: {remaining}s remaining")

    if remaining == 0:
        sess.phase = "part2_recording"
        sess.speaking_start_time = time.time()
        st.rerun()


def _render_part2_thinking() -> None:
    sess: ExamSession = st.session_state.session
    cue = sess.part2_cue_card

    st.header("Part 2 — Preparation Time")

    if cue:
        st.markdown(
            f"<div style='background:#F3E5F5;border:2px solid #CE93D8;"
            f"border-radius:12px;padding:20px;font-size:1.05em'>"
            f"<h3 style='color:#6A1B9A'>{cue.topic}</h3>"
            f"<ul>{''.join(f'<li>{p}</li>' for p in cue.points)}</ul>"
            f"<p><i>{cue.explain}</i></p>"
            f"</div>",
            unsafe_allow_html=True,
        )

    _prep_countdown_fragment()

    if st.button("Start Speaking Early"):
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

    if remaining <= 10:
        bar_text = f"Speaking time: {mins}:{secs:02d} remaining"
        st.progress(progress_val, text=bar_text)
        st.error(f"Almost done! {remaining}s left")
    elif remaining <= 30:
        bar_text = f"Speaking time: {mins}:{secs:02d} remaining"
        st.progress(progress_val, text=bar_text)
        st.warning(f"Wrap up soon — {remaining}s left")
    else:
        bar_text = f"Speaking time: {mins}:{secs:02d} remaining"
        st.progress(progress_val, text=bar_text)

    if remaining == 0:
        sess.phase = "part2_evaluating"
        st.rerun()


def _render_part2_recording() -> None:
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
        if len(wav_bytes) < 4000:
            st.warning("Recording too short. Please try again.")
        else:
            question = cue.topic if cue else "Part 2 speech"
            sess.turns.append(Turn(part=2, question=question, audio_bytes=wav_bytes))
            sess.phase = "part2_evaluating"
            st.rerun()

    if st.button("Finish Speaking Early"):
        # Only process if we have an audio input already submitted
        if not sess.part_turns(2):
            st.info("Please record your answer first using the audio input above.")
        else:
            sess.phase = "part2_evaluating"
            st.rerun()


def _render_part2_evaluating() -> None:
    sess: ExamSession = st.session_state.session
    transcriber: GeminiTranscriber = st.session_state.transcriber
    evaluator: EvaluationPipeline = st.session_state.evaluator

    p2_turns = sess.part_turns(2)
    if not p2_turns:
        st.error("No audio recorded for Part 2.")
        if st.button("Go back"):
            sess.phase = "part2_recording"
            st.rerun()
        return

    turn = p2_turns[-1]

    if turn.result is not None:
        sess.phase = "part2_result"
        st.rerun()
        return

    st.header("Part 2 — Processing")

    if transcriber is None:
        st.error("Gemini API key required for transcription.")
        return
    if evaluator is None:
        st.error("OpenRouter API key required for evaluation.")
        return

    with st.spinner("Transcribing your 2-minute speech..."):
        try:
            transcript = _run_async(transcriber.transcribe(turn.audio_bytes))
        except Exception as e:
            st.error(f"Transcription failed: {e}")
            if st.button("Retry"):
                st.rerun()
            return

    with st.spinner("Evaluating your speech (4 criteria)..."):
        try:
            result = _run_async(evaluator.evaluate(
                transcript=transcript,
                question=turn.question,
                part=2,
            ))
            turn.result = result
            sess.phase = "part2_result"
            st.rerun()
        except Exception as e:
            st.error(f"Evaluation failed: {e}")
            if st.button("Retry"):
                st.rerun()


def _render_part2_result() -> None:
    sess: ExamSession = st.session_state.session
    p2_turns = sess.part_turns(2)

    if not p2_turns or p2_turns[-1].result is None:
        sess.phase = "part2_evaluating"
        st.rerun()
        return

    turn = p2_turns[-1]
    st.header("Part 2 — Result")

    _render_transcript(turn.result.transcript)
    st.markdown("---")
    _render_evaluation(turn.result)

    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Continue to Part 3", type="primary"):
            # Pass Part 2 topic to Part 3
            sess.phase = "part3_loading"
            st.rerun()
    with col2:
        if st.button("New Cue Card"):
            sess.part2_cue_card = None
            sess.part2_topic = ""
            sess.phase = "part2_idle"
            st.rerun()
    with col3:
        if st.button("Go to Summary"):
            sess.phase = "session_summary"
            st.rerun()


# ── Part 3 ────────────────────────────────────────────────────────────────────

def _render_part3_loading() -> None:
    sess: ExamSession = st.session_state.session
    qgen: QuestionGenerator = st.session_state.question_gen

    st.header("Part 3 — Discussion")

    if qgen is None:
        st.error("Gemini API key required to generate questions.")
        return

    with st.spinner("Generating discussion questions..."):
        try:
            questions = _run_async(
                qgen.generate_part3_questions(part2_topic=sess.part2_topic, n=5)
            )
            sess.part3_questions = questions
            sess.part3_index = 0
            sess.phase = "part3_idle"
            st.rerun()
        except Exception as e:
            st.error(f"Failed to generate questions: {e}")
            if st.button("Retry"):
                st.rerun()


def _render_part3_idle() -> None:
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
        f"<div style='background:#FFF3E0;border-radius:10px;padding:24px;"
        f"font-size:1.3em;font-weight:500;margin:20px 0'>{question}</div>",
        unsafe_allow_html=True,
    )

    audio = st.audio_input("Record your answer", key=f"p3_audio_{idx}")

    col1, col2 = st.columns([3, 1])
    with col1:
        if audio is not None:
            wav_bytes = audio.getvalue()
            if len(wav_bytes) < 4000:
                st.warning("Recording too short. Please try again.")
            else:
                sess.turns.append(Turn(
                    part=3,
                    question=question,
                    audio_bytes=wav_bytes,
                ))
                sess.phase = "part3_result"
                st.rerun()
    with col2:
        if st.button("Skip", key=f"p3_skip_{idx}"):
            sess.part3_index += 1
            if sess.part3_index >= total:
                sess.phase = "part3_summary"
            st.rerun()


def _render_part3_result() -> None:
    sess: ExamSession = st.session_state.session
    transcriber: GeminiTranscriber = st.session_state.transcriber
    evaluator: EvaluationPipeline = st.session_state.evaluator

    p3_turns = sess.part_turns(3)
    if not p3_turns:
        sess.phase = "part3_idle"
        st.rerun()
        return

    turn = p3_turns[-1]
    idx = sess.part3_index
    total = len(sess.part3_questions)

    st.header("Part 3 — Result")
    st.caption(f"Question {idx + 1} of {total}")

    if turn.result is None:
        if transcriber is None:
            st.error("Gemini API key required for transcription.")
        elif evaluator is None:
            st.error("OpenRouter API key required for evaluation.")
        else:
            with st.spinner("Transcribing..."):
                try:
                    transcript = _run_async(transcriber.transcribe(turn.audio_bytes))
                except Exception as e:
                    st.error(f"Transcription failed: {e}")
                    if st.button("Retry"):
                        st.rerun()
                    return

            with st.spinner("Evaluating (4 criteria in parallel)..."):
                try:
                    result = _run_async(evaluator.evaluate(
                        transcript=transcript,
                        question=turn.question,
                        part=3,
                    ))
                    turn.result = result
                except Exception as e:
                    st.error(f"Evaluation failed: {e}")
                    if st.button("Retry"):
                        st.rerun()
                    return
            st.rerun()
        return

    _render_transcript(turn.result.transcript)
    st.markdown("---")
    _render_evaluation(turn.result)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        next_label = "Next Question" if (idx + 1) < total else "View Part 3 Summary"
        if st.button(next_label, type="primary"):
            sess.part3_index += 1
            if sess.part3_index >= total:
                sess.phase = "part3_summary"
            else:
                sess.phase = "part3_idle"
            st.rerun()
    with col2:
        if st.button("Retry This Question"):
            sess.turns.pop()
            sess.phase = "part3_idle"
            st.rerun()


def _render_part3_summary() -> None:
    sess: ExamSession = st.session_state.session
    p3_turns = sess.part_turns(3)

    st.header("Part 3 Summary")

    if not p3_turns:
        st.info("No answers recorded for Part 3.")
    else:
        evaluated = [t for t in p3_turns if t.result]
        if evaluated:
            criteria = ["FC", "LR", "GR", "Pronunciation"]
            avgs = {}
            for c in criteria:
                bands = [t.result.get_score(c).band for t in evaluated if t.result.get_score(c)]
                avgs[c] = round(sum(bands) / len(bands) * 2) / 2 if bands else 0.0

            overall = round(sum(avgs.values()) / len(avgs) * 2) / 2

            st.markdown(
                f"<div style='background:{_band_color(overall)};color:white;"
                f"padding:12px;border-radius:8px;font-size:1.2em;font-weight:bold'>"
                f"Part 3 Average Band: {overall:.1f}</div>",
                unsafe_allow_html=True,
            )

            cols = st.columns(4)
            for i, (c, avg) in enumerate(avgs.items()):
                with cols[i]:
                    color = _band_color(avg)
                    st.markdown(
                        f"<div style='text-align:center;border:2px solid {color};"
                        f"border-radius:8px;padding:10px'>"
                        f"<b style='color:{color}'>{c}</b><br>"
                        f"<span style='font-size:1.4em;font-weight:bold'>{avg:.1f}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

    st.markdown("---")
    if st.button("View Session Summary", type="primary"):
        sess.phase = "session_summary"
        st.rerun()


# ── Session Summary ───────────────────────────────────────────────────────────

def _render_session_summary() -> None:
    sess: ExamSession = st.session_state.session
    summary = sess.build_summary()

    st.header("Session Summary")

    if not summary.turns:
        st.info("No answers recorded this session.")
        if st.button("Start New Session"):
            st.session_state.session = ExamSession()
            st.rerun()
        return

    overall = summary.overall
    if overall > 0:
        st.markdown(
            f"<div style='background:{_band_color(overall)};color:white;"
            f"padding:16px;border-radius:10px;font-size:1.4em;font-weight:bold;"
            f"text-align:center;margin:12px 0'>"
            f"Overall Session Band: {overall:.1f} / 9.0</div>",
            unsafe_allow_html=True,
        )

    # Per-part summary
    cols = st.columns(4)
    labels = ["FC", "LR", "GR", "Pronunciation"]
    avgs = [summary.avg_fc, summary.avg_lr, summary.avg_gr, summary.avg_pronun]
    for i, (label, avg) in enumerate(zip(labels, avgs)):
        with cols[i]:
            if avg > 0:
                color = _band_color(avg)
                st.markdown(
                    f"<div style='text-align:center;border:2px solid {color};"
                    f"border-radius:8px;padding:12px'>"
                    f"<b style='color:{color}'>{label}</b><br>"
                    f"<span style='font-size:1.5em;font-weight:bold'>{avg:.1f}</span><br>"
                    f"<span style='font-family:monospace;font-size:0.7em'>{_band_bar(avg)}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(f"<div style='text-align:center;padding:12px'><b>{label}</b><br>—</div>", unsafe_allow_html=True)

    # Parts breakdown
    st.markdown("---")
    parts_done = []
    if sess.part_turns(1):
        parts_done.append(f"Part 1 ({len(sess.part_turns(1))} answers)")
    if sess.part_turns(2):
        parts_done.append(f"Part 2 ({len(sess.part_turns(2))} speech)")
    if sess.part_turns(3):
        parts_done.append(f"Part 3 ({len(sess.part_turns(3))} answers)")
    if parts_done:
        st.caption("Parts completed: " + " | ".join(parts_done))

    # Top improvement areas
    if any(a > 0 for a in avgs):
        st.markdown("**Top Areas to Improve:**")
        areas = sorted(zip(labels, avgs), key=lambda x: x[1])
        for label, avg in areas[:2]:
            if avg > 0:
                st.markdown(f"- **{label}** ({avg:.1f}) — {_improvement_tip(label)}")

    st.markdown("---")

    # Save report
    report = _build_report(sess)
    store: FluentUpStore | None = st.session_state.get("store")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button(
            "Save Report",
            data=report,
            file_name="fluentup_session.txt",
            mime="text/plain",
        )
    with col2:
        if store is not None:
            if st.button("Save to History", type="primary"):
                with st.spinner("Saving to MongoDB..."):
                    try:
                        session_id = _run_async(store.save_session(summary))
                        st.success(f"Saved! ID: {session_id[:8]}…")
                    except Exception as e:
                        st.error(f"Save failed: {e}")
        else:
            st.caption("MongoDB not configured — history unavailable")
    with col3:
        if st.button("Start New Session"):
            st.session_state.session = ExamSession()
            st.rerun()

    # History panel
    if store is not None:
        st.markdown("---")
        with st.expander("Session History", expanded=False):
            try:
                history = _run_async(store.get_recent_sessions(limit=10))
                if not history:
                    st.caption("No saved sessions yet.")
                else:
                    for h in history:
                        ts = h.get("created_at", "")
                        if hasattr(ts, "strftime"):
                            ts = ts.strftime("%Y-%m-%d %H:%M")
                        overall = h.get("overall", 0)
                        color = _band_color(overall)
                        st.markdown(
                            f"<div style='border-left:4px solid {color};"
                            f"padding:6px 12px;margin:4px 0'>"
                            f"<b style='color:{color}'>{overall:.1f}</b> — {ts} &nbsp;"
                            f"FC:{h.get('avg_fc',0):.1f} "
                            f"LR:{h.get('avg_lr',0):.1f} "
                            f"GR:{h.get('avg_gr',0):.1f} "
                            f"PR:{h.get('avg_pronun',0):.1f}"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
            except Exception as e:
                st.error(f"Could not load history: {e}")


def _improvement_tip(criterion: str) -> str:
    tips = {
        "FC": "Practice using discourse markers and reducing filler words",
        "LR": "Expand topic-specific vocabulary and use collocations",
        "GR": "Use a wider variety of sentence structures and tenses",
        "Pronunciation": "Focus on word stress and final consonant sounds",
    }
    return tips.get(criterion, "Keep practicing")


def _build_report(sess: ExamSession) -> str:
    summary = sess.build_summary()
    lines = [
        "FluentUp — IELTS Speaking Practice Session Report",
        "=" * 50,
        f"Overall Band: {summary.overall:.1f}",
        f"FC: {summary.avg_fc:.1f} | LR: {summary.avg_lr:.1f} | GR: {summary.avg_gr:.1f} | Pronunciation: {summary.avg_pronun:.1f}",
        "",
    ]
    for t in summary.turns:
        lines.append(f"Part {t.part} — {t.question}")
        if t.result:
            lines.append(f"  Transcript: {t.result.transcript[:200]}...")
            lines.append(f"  Overall: {t.result.overall_band:.1f}")
            for score in t.result.scores:
                lines.append(f"  {score.criterion}: {score.band:.1f} — {score.feedback[:100]}")
        lines.append("")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(page_title="FluentUp", page_icon="🎯", layout="wide")

    secrets = _load_secrets()
    _init_state(secrets)
    _render_sidebar(secrets)

    # Guard: need at least Gemini key
    if not secrets["gemini_api_key"]:
        st.error("Add `GEMINI_API_KEY` to `.streamlit/secrets.toml` to start.")
        st.info("The app requires Gemini for audio transcription and question generation.")
        return

    if not secrets["openrouter_api_key"]:
        st.warning("Add `OPENROUTER_API_KEY` to `.streamlit/secrets.toml` for evaluation.")

    sess: ExamSession = st.session_state.session
    phase = sess.phase

    dispatch = {
        "home":              _render_home,
        "part1_loading":     _render_part1_loading,
        "part1_idle":        _render_part1_idle,
        "part1_result":      _render_part1_result,
        "part1_summary":     _render_part1_summary,
        "part2_idle":        _render_part2_idle,
        "part2_thinking":    _render_part2_thinking,
        "part2_recording":   _render_part2_recording,
        "part2_evaluating":  _render_part2_evaluating,
        "part2_result":      _render_part2_result,
        "part3_loading":     _render_part3_loading,
        "part3_idle":        _render_part3_idle,
        "part3_result":      _render_part3_result,
        "part3_summary":     _render_part3_summary,
        "session_summary":   _render_session_summary,
    }

    renderer = dispatch.get(phase, _render_home)
    renderer()


if __name__ == "__main__":
    main()
