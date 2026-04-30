"""
app.py — FluentUp: IELTS Speaking Practice (Streamlit)

Run locally:
    streamlit run app.py
"""
from __future__ import annotations

import asyncio
import threading
import time

import streamlit as st

from fluentup.exam_session import ExamSession, PREP_SECONDS, SPEAK_SECONDS
from fluentup.models import BandScore, EvaluationResult, Turn
from fluentup.evaluator import LiveEvaluationPipeline, CRITERIA
from fluentup.question_gen import QuestionGenerator
from fluentup.store import FluentUpStore
from fluentup.config import ACCENT_LABELS, DEFAULT_ACCENT


# ── Secrets ───────────────────────────────────────────────────────────────────

def _load_secrets() -> dict:
    return {
        "gemini_api_key":       st.secrets.get("GEMINI_API_KEY", ""),
        "live_model":           st.secrets.get("GEMINI_LIVE_MODEL", ""),
        "mongodb_uri":          st.secrets.get("MONGODB_URI", ""),
        "mongodb_username":     st.secrets.get("MONGODB_USERNAME", ""),
        "mongodb_password":     st.secrets.get("MONGODB_PASSWORD", ""),
        "openrouter_base_url":  st.secrets.get("OPENROUTER_BASE_URL", ""),
        "openrouter_api_key":   st.secrets.get("OPENROUTER_API_KEY", ""),
        "openrouter_model":     st.secrets.get("OPENROUTER_MODEL", ""),
    }


# ── State init ────────────────────────────────────────────────────────────────

_STATE_VERSION = 6


def _init_state(secrets: dict) -> None:
    if st.session_state.get("_state_version") != _STATE_VERSION:
        for key in ("evaluator", "question_gen", "store"):
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
    """Background color for a band score — all dark enough for white text."""
    if band >= 8.0:
        return "#00695C"   # dark teal
    if band >= 7.0:
        return "#2E7D32"   # dark green
    if band >= 6.0:
        return "#558B2F"   # dark olive-green
    if band >= 5.0:
        return "#E65100"   # dark orange
    if band >= 4.0:
        return "#BF360C"   # deep orange-red
    return "#B71C1C"       # dark red


def _band_bar(band: float) -> str:
    fill = round(band / 9.0 * 20)
    empty = 20 - fill
    return "█" * fill + "░" * empty


_bg_loop: asyncio.AbstractEventLoop | None = None
_bg_thread: threading.Thread | None = None


def _get_bg_loop() -> asyncio.AbstractEventLoop:
    global _bg_loop, _bg_thread
    if _bg_loop is None or not _bg_loop.is_running():
        _bg_loop = asyncio.new_event_loop()
        _bg_thread = threading.Thread(target=_bg_loop.run_forever, daemon=True)
        _bg_thread.start()
    return _bg_loop


def _run_async(coro):
    import concurrent.futures
    loop = _get_bg_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


def _hear_question(question: str, key: str) -> None:
    """Render a small TTS button; plays the question via Gemini Live audio."""
    qgen: QuestionGenerator | None = st.session_state.get("question_gen")
    if qgen is None:
        return
    accent = st.session_state.get("examiner_accent", DEFAULT_ACCENT)
    if st.button("Hear question", key=key, use_container_width=True):
        with st.spinner("Generating audio..."):
            try:
                wav = _run_async(qgen.speak_question(question, accent=accent))
                st.audio(wav, format="audio/wav", autoplay=True)
            except Exception as e:
                st.warning(f"TTS unavailable: {e}")


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _render_sidebar(secrets: dict) -> None:
    with st.sidebar:
        st.markdown("## FluentUp")
        st.caption("IELTS Speaking Practice")

        st.divider()
        st.markdown("**Examiner Accent**")
        accent_options = list(ACCENT_LABELS.keys())
        current = st.session_state.get("examiner_accent", DEFAULT_ACCENT)
        selected_idx = accent_options.index(current) if current in accent_options else 0
        chosen = st.selectbox(
            "Voice accent",
            options=accent_options,
            format_func=lambda a: ACCENT_LABELS[a],
            index=selected_idx,
            key="accent_select",
            label_visibility="collapsed",
        )
        st.session_state["examiner_accent"] = chosen

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

        # Quick history in sidebar
        store: FluentUpStore | None = st.session_state.get("store")
        if store is not None:
            st.markdown("**Session History**")
            with st.expander("View / manage", expanded=False):
                _render_sidebar_history(store)
            st.divider()

        if phase != "home":
            if st.button("New Session", use_container_width=True):
                st.session_state.session = ExamSession()
                _clear_streaming_state()
                st.rerun()

        if "part1" in phase:
            st.markdown("**Part 1 Tips**")
            st.caption("- Answer in 2–3 sentences\n- Add a reason or example\n- Use present tenses for habits")
        elif "part2" in phase:
            st.markdown("**Part 2 Tips**")
            st.caption("- Cover all bullet points\n- Use past tense for stories\n- Start with a clear topic sentence")
        elif "part3" in phase:
            st.markdown("**Part 3 Tips**")
            st.caption("- Give your opinion clearly\n- Use phrases like 'I believe...' / 'It seems to me...'\n- Compare and contrast ideas")


# ── Streaming evaluation ──────────────────────────────────────────────────────

def _render_sidebar_history(store: FluentUpStore) -> None:
    """Compact history list in sidebar with Load/Delete per row."""
    try:
        history = _run_async(store.get_recent_sessions(limit=10))
    except Exception as e:
        st.caption(f"Could not load: {e}")
        return

    if not history:
        st.caption("No saved sessions yet.")
        return

    view_id: str | None = st.session_state.get("history_view_id")

    for h in history:
        sid = h["_id"]
        ts = h.get("created_at", "")
        if hasattr(ts, "strftime"):
            ts = ts.strftime("%m-%d %H:%M")
        overall = h.get("overall", 0.0)
        color = _band_color(overall)

        r1, r2 = st.columns([5, 2])
        with r1:
            st.markdown(
                f"<div style='border-left:3px solid {color};padding:3px 8px;"
                f"font-size:0.85em'>"
                f"<b style='color:{color}'>{overall:.1f}</b> {ts}<br>"
                f"<span style='color:#888'>FC:{h.get('avg_fc',0):.1f} "
                f"LR:{h.get('avg_lr',0):.1f} "
                f"GR:{h.get('avg_gr',0):.1f} "
                f"PR:{h.get('avg_pronun',0):.1f}</span></div>",
                unsafe_allow_html=True,
            )
        with r2:
            c1, c2 = st.columns(2)
            with c1:
                if st.button("📂", key=f"sb_load_{sid}", help="Load"):
                    st.session_state["history_view_id"] = None if view_id == sid else sid
                    st.rerun()
            with c2:
                if st.button("🗑", key=f"sb_del_{sid}", help="Delete"):
                    try:
                        _run_async(store.delete_session(sid))
                        if view_id == sid:
                            st.session_state.pop("history_view_id", None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete failed: {e}")

        if view_id == sid:
            try:
                doc = _run_async(store.get_session(sid))
                if doc:
                    _render_history_detail(doc)
            except Exception as e:
                st.caption(f"Load failed: {e}")


def _clear_streaming_state() -> None:
    for key in ("eval_partial", "eval_auto_played", "eval_errors"):
        st.session_state.pop(key, None)


def _start_streaming_eval(turn: Turn, part: int) -> None:
    evaluator: LiveEvaluationPipeline | None = st.session_state.get("evaluator")
    if evaluator is None:
        return

    # Use plain Python dicts — threads must NOT touch st.session_state directly
    # (it is a thread-local proxy and raises KeyError from non-main threads).
    partial: dict = {}
    errors: dict = {}
    st.session_state["eval_partial"] = partial
    st.session_state["eval_auto_played"] = set()
    st.session_state["eval_errors"] = errors

    def _worker(criterion: str, results: dict, errs: dict) -> None:
        try:
            score, _, wav = asyncio.run(evaluator.eval_one(
                criterion=criterion,
                audio_bytes=turn.audio_bytes,
                question=turn.question,
                part=part,
            ))
            results[criterion] = {"score": score, "wav": wav}
        except Exception as exc:
            errs[criterion] = str(exc)

    for c in CRITERIA:
        threading.Thread(target=_worker, args=(c, partial, errors), daemon=True).start()


def _render_streaming_eval(turn: Turn, part: int) -> bool:
    """
    Show per-criterion results as they arrive.
    Returns True when all 4 are done and turn.result has been assembled.
    """
    evaluator = st.session_state.get("evaluator")
    if evaluator is None:
        st.error("Gemini API key required for evaluation.")
        return False

    partial = st.session_state.get("eval_partial")
    if partial is None:
        _start_streaming_eval(turn, part)
        st.rerun()
        return False

    errors: dict = st.session_state.get("eval_errors", {})
    played: set = st.session_state.get("eval_auto_played", set())

    done_count = len(partial) + len(errors)
    total = len(CRITERIA)

    if done_count < total:
        st.markdown(f"**Evaluating… ({done_count}/{total} criteria complete)**")
        st.progress(done_count / total)
    else:
        st.markdown(f"**Evaluation complete ({total}/{total})**")
        st.progress(1.0)

    for criterion in CRITERIA:
        if criterion in partial:
            item = partial[criterion]
            score: BandScore = item["score"]
            wav: bytes = item["wav"]
            with st.expander(
                f"{criterion} — {score.band:.1f}  {_band_bar(score.band)}",
                expanded=True,
            ):
                if wav:
                    # autoplay first appearance, then normal player
                    autoplay = criterion not in played
                    st.audio(wav, format="audio/wav", autoplay=autoplay)
                    if autoplay:
                        played.add(criterion)
                        st.session_state["eval_auto_played"] = played
                elif score.feedback:
                    # No audio from Gemini Live — show spoken evaluation as text
                    st.markdown(
                        f"<div style='background:#f8f9fa;border-left:4px solid #6c757d;"
                        f"padding:10px 14px;border-radius:4px;font-size:0.95em'>"
                        f"{score.feedback}</div>",
                        unsafe_allow_html=True,
                    )
                if score.weak_points:
                    st.markdown("**Weak points:**")
                    for wp in score.weak_points:
                        st.markdown(f"- {wp}")
                if score.tips:
                    st.markdown("**Improvements:**")
                    for tip in score.tips:
                        st.markdown(f"- {tip}")
        elif criterion in errors:
            with st.expander(f"{criterion} — Error", expanded=True):
                st.error(errors[criterion])

    if done_count < total:
        time.sleep(0.8)
        st.rerun()
        return False

    # All done — assemble EvaluationResult and save to turn
    scores = []
    criterion_audio: dict[str, bytes] = {}
    for criterion in CRITERIA:
        if criterion in partial:
            item = partial[criterion]
            scores.append(item["score"])
            if item["wav"]:
                criterion_audio[criterion] = item["wav"]
        else:
            scores.append(BandScore(
                criterion=criterion, band=0.0,
                feedback=errors.get(criterion, "Failed"),
                examples=[], tips=[], weak_points=[],
            ))

    turn.result = EvaluationResult(
        transcript="",
        scores=scores,
        criterion_audio=criterion_audio,
    )
    _clear_streaming_state()
    return True


# ── Evaluation summary display ────────────────────────────────────────────────

def _render_evaluation(result: EvaluationResult) -> None:
    st.markdown("#### Evaluation Summary")

    overall = result.overall_band
    color = _band_color(overall)
    st.markdown(
        f"<div style='background:{color};color:white;padding:10px 16px;"
        f"border-radius:8px;font-size:1.2em;font-weight:bold;margin-bottom:12px'>"
        f"Overall Band: {overall:.1f} / 9.0</div>",
        unsafe_allow_html=True,
    )

    cols = st.columns(4)
    for i, score in enumerate(result.scores):
        with cols[i]:
            c = _band_color(score.band)
            st.markdown(
                f"<div style='text-align:center;border:2px solid {c};"
                f"border-radius:8px;padding:10px'>"
                f"<b style='color:{c}'>{score.criterion}</b><br>"
                f"<span style='font-size:1.4em;font-weight:bold'>{score.band:.1f}</span><br>"
                f"<span style='font-family:monospace;font-size:0.7em'>{_band_bar(score.band)}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    feedback_text = f"Overall Band: {overall:.1f}\n\n"
    for score in result.scores:
        feedback_text += f"{score.criterion}: {score.band:.1f}\n"
        if score.weak_points:
            feedback_text += "Weak points: " + "; ".join(score.weak_points) + "\n"
        if score.tips:
            feedback_text += "Tips: " + "; ".join(score.tips) + "\n"
        feedback_text += "\n"
    st.download_button(
        "Download Feedback",
        data=feedback_text,
        file_name="feedback.txt",
        mime="text/plain",
    )


# ── Part selector (home) ──────────────────────────────────────────────────────

def _render_home() -> None:
    st.title("FluentUp")
    st.subheader("IELTS Speaking Practice")
    st.markdown("Choose a part to start practicing:")

    sess: ExamSession = st.session_state.session
    has_part2 = bool(sess.part2_topic)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            "<div style='border:2px solid #1565C0;border-radius:10px;padding:20px;text-align:center'>"
            "<h3 style='color:#1565C0'>Part 1</h3>"
            "<p>Introduction &amp; Interview</p>"
            "<p style='font-size:0.9em'>10 questions on familiar topics</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button("Start Part 1", key="start_p1", use_container_width=True):
            sess.phase = "part1_loading"
            st.rerun()

    with col2:
        p2_color = "#6A1B9A" if not has_part2 else "#9E9E9E"
        st.markdown(
            f"<div style='border:2px solid {p2_color};border-radius:10px;padding:20px;text-align:center;opacity:{'1' if not has_part2 else '0.5'}'>"
            f"<h3 style='color:{p2_color}'>Part 2</h3>"
            "<p>Individual Long Turn</p>"
            "<p style='font-size:0.9em'>Cue card, 1 min prep, 2 min speech</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.button(
            "Complete Part 1 first",
            key="start_p2",
            use_container_width=True,
            disabled=True,
        )

    with col3:
        p3_color = "#E65100" if has_part2 else "#9E9E9E"
        p3_hint = "5-6 abstract discussion questions" if has_part2 else "Complete Part 2 first to unlock"
        st.markdown(
            f"<div style='border:2px solid {p3_color};border-radius:10px;padding:20px;text-align:center;opacity:{'1' if has_part2 else '0.5'}'>"
            f"<h3 style='color:{p3_color}'>Part 3</h3>"
            "<p>Two-way Discussion</p>"
            f"<p style='font-size:0.9em'>{p3_hint}</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button(
            "Start Part 3" if has_part2 else "Locked",
            key="start_p3",
            use_container_width=True,
            disabled=not has_part2,
        ):
            sess.phase = "part3_loading"
            st.rerun()


# ── Part 1 ────────────────────────────────────────────────────────────────────

def _render_part1_loading() -> None:
    sess: ExamSession = st.session_state.session
    qgen: QuestionGenerator = st.session_state.question_gen

    st.header("Part 1 — Introduction & Interview")

    if qgen is None:
        st.error("Gemini API key required to generate questions.")
        if st.button("Back to Home", use_container_width=True):
            sess.phase = "home"
            st.rerun()
        return

    with st.spinner("Loading questions..."):
        try:
            questions = _run_async(qgen.generate_part1_questions())
            sess.part1_questions = questions
            sess.part1_index = 0
            sess.phase = "part1_idle"
            st.rerun()
        except Exception as e:
            st.error(f"Failed to generate questions: {e}")
            if st.button("Retry", use_container_width=True):
                st.rerun()


def _render_part1_idle() -> None:
    sess: ExamSession = st.session_state.session
    question = sess.current_part1_question()
    idx = sess.part1_index
    total = len(sess.part1_questions)

    st.header("Part 1 — Introduction & Interview")
    st.caption(f"Question {idx + 1} of {total}")
    st.progress(idx / total)

    if question is None:
        p1_turns = sess.part_turns(1)
        sess.phase = "part1_summary" if p1_turns else "part1_summary"
        st.rerun()
        return

    st.markdown(
        f"<div style='border-left:4px solid #1565C0;border-radius:6px;padding:20px 24px;"
        f"font-size:1.3em;font-weight:500;margin:20px 0'>{question}</div>",
        unsafe_allow_html=True,
    )

    _hear_question(question, key=f"p1_tts_{idx}")

    audio = st.audio_input("Record your answer", key=f"p1_audio_{idx}")

    col1, col2, col3 = st.columns([4, 1, 1])
    with col1:
        if audio is not None:
            wav_bytes = audio.getvalue()
            if len(wav_bytes) < 4000:
                st.warning("Recording too short. Please try again.")
            else:
                sess.turns.append(Turn(part=1, question=question, audio_bytes=wav_bytes))
                sess.part1_index += 1
                _clear_streaming_state()
                sess.phase = "part1_feedback"
                st.rerun()
    with col2:
        if st.button("Skip", key=f"p1_skip_{idx}", use_container_width=True):
            sess.part1_index += 1
            if sess.part1_index >= total:
                p1_turns = sess.part_turns(1)
                sess.phase = "part1_summary" if not p1_turns else "part1_evaluating"
            st.rerun()
    with col3:
        if st.button("End Part 1", key=f"p1_end_{idx}", use_container_width=True):
            p1_turns = sess.part_turns(1)
            sess.phase = "part1_evaluating" if p1_turns else "part1_summary"
            st.rerun()


def _render_part1_feedback() -> None:
    """Evaluate the most recent Part 1 answer and show feedback before next question."""
    sess: ExamSession = st.session_state.session
    p1_turns = sess.part_turns(1)

    if not p1_turns:
        sess.phase = "part1_idle"
        st.rerun()
        return

    # The turn that was just recorded (last unevaluated)
    unevaluated = [t for t in p1_turns if t.result is None]
    if not unevaluated:
        # All evaluated, move forward
        if sess.part1_index >= len(sess.part1_questions):
            sess.phase = "part1_summary"
        else:
            sess.phase = "part1_idle"
        st.rerun()
        return

    turn = unevaluated[-1]  # the one just submitted
    idx_label = len(p1_turns)
    total = len(sess.part1_questions)

    st.header("Part 1 — Examiner Feedback")
    st.caption(f"Question {idx_label} of {total}")

    st.markdown(
        f"<div style='border-left:4px solid #1565C0;border-radius:6px;padding:12px 20px;"
        f"font-size:1.1em;color:#555;margin:12px 0'><b>Question:</b> {turn.question}</div>",
        unsafe_allow_html=True,
    )

    # Playback of user's answer
    st.markdown("**Your answer:**")
    st.audio(turn.audio_bytes, format="audio/wav")

    st.markdown("---")

    done = _render_streaming_eval(turn, part=1)

    if done:
        st.markdown("---")
        if sess.part1_index >= total:
            if st.button("View Part 1 Summary", type="primary", use_container_width=True):
                _clear_streaming_state()
                sess.phase = "part1_summary"
                st.rerun()
        else:
            if st.button("Next Question →", type="primary", use_container_width=True):
                _clear_streaming_state()
                sess.phase = "part1_idle"
                st.rerun()


def _render_part1_evaluating() -> None:
    sess: ExamSession = st.session_state.session
    p1_turns = sess.part_turns(1)

    if not p1_turns:
        sess.phase = "part1_summary"
        st.rerun()
        return

    unevaluated = [t for t in p1_turns if t.result is None]
    if not unevaluated:
        _clear_streaming_state()
        sess.phase = "part1_summary"
        st.rerun()
        return

    turn = unevaluated[0]
    done_count = len(p1_turns) - len(unevaluated)

    st.header("Part 1 — Evaluating Answers")
    st.caption(f"Answer {done_count + 1} of {len(p1_turns)}")
    st.progress(done_count / len(p1_turns))

    st.markdown(
        f"<div style='border-left:4px solid #1565C0;border-radius:6px;padding:12px 20px;"
        f"font-size:1.1em;color:#555;margin:12px 0'><b>Question:</b> {turn.question}</div>",
        unsafe_allow_html=True,
    )

    if _render_streaming_eval(turn, part=1):
        st.rerun()


def _render_part_averages(evaluated: list) -> dict:
    """Compute and render criterion average cards. Returns avgs dict."""
    avgs = {}
    for c in CRITERIA:
        bands = [t.result.get_score(c).band for t in evaluated if t.result.get_score(c)]
        avgs[c] = round(sum(bands) / len(bands) * 2) / 2 if bands else 0.0

    overall = round(sum(avgs.values()) / len(avgs) * 2) / 2
    st.markdown(
        f"<div style='background:{_band_color(overall)};color:white;"
        f"padding:12px;border-radius:8px;font-size:1.2em;font-weight:bold'>"
        f"Average Band: {overall:.1f}</div>",
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
    return avgs


def _render_part1_summary() -> None:
    sess: ExamSession = st.session_state.session
    p1_turns = sess.part_turns(1)

    st.header("Part 1 Summary")

    if not p1_turns:
        st.info("No answers recorded for Part 1.")
    else:
        evaluated = [t for t in p1_turns if t.result]

        if evaluated:
            avgs = _render_part_averages(evaluated)

            st.markdown("---")
            st.markdown("#### Per-question breakdown")
            for i, turn in enumerate(evaluated):
                band = turn.result.overall_band
                color = _band_color(band)
                with st.expander(
                    f"Q{i + 1}: {turn.question[:70]}{'…' if len(turn.question) > 70 else ''} — {band:.1f}",
                    expanded=False,
                ):
                    st.audio(turn.audio_bytes, format="audio/wav")
                    _render_evaluation(turn.result)
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


def _render_part2_thinking() -> None:
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

    if remaining <= 10:
        st.progress(progress_val, text=f"Speaking time: {mins}:{secs:02d} remaining")
        st.error(f"Almost done! {remaining}s left")
    elif remaining <= 30:
        st.progress(progress_val, text=f"Speaking time: {mins}:{secs:02d} remaining")
        st.warning(f"Wrap up soon — {remaining}s left")
    else:
        st.progress(progress_val, text=f"Speaking time: {mins}:{secs:02d} remaining")

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
            _clear_streaming_state()
            sess.phase = "part2_evaluating"
            st.rerun()

    if st.button("Finish Speaking Early", use_container_width=True):
        if not sess.part_turns(2):
            st.info("Please record your answer first using the audio input above.")
        else:
            sess.phase = "part2_evaluating"
            st.rerun()


def _render_part2_evaluating() -> None:
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

    if _render_streaming_eval(turn, part=2):
        sess.phase = "part2_result"
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

    with st.expander("Your answer (playback)", expanded=False):
        st.audio(turn.audio_bytes, format="audio/wav")

    _render_evaluation(turn.result)

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
                qgen.generate_part3_questions(
                    part2_topic=sess.part2_topic,
                    part2_cue_card=sess.part2_cue_card,
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
        f"<div style='border-left:4px solid #E65100;border-radius:6px;padding:20px 24px;"
        f"font-size:1.3em;font-weight:500;margin:20px 0'>{question}</div>",
        unsafe_allow_html=True,
    )

    _hear_question(question, key=f"p3_tts_{idx}")

    audio = st.audio_input("Record your answer", key=f"p3_audio_{idx}")

    col1, col2 = st.columns([3, 1])
    with col1:
        if audio is not None:
            wav_bytes = audio.getvalue()
            if len(wav_bytes) < 4000:
                st.warning("Recording too short. Please try again.")
            else:
                sess.turns.append(Turn(part=3, question=question, audio_bytes=wav_bytes))
                _clear_streaming_state()
                sess.phase = "part3_result"
                st.rerun()
    with col2:
        if st.button("Skip", key=f"p3_skip_{idx}", use_container_width=True):
            sess.part3_index += 1
            if sess.part3_index >= total:
                sess.phase = "part3_summary"
            st.rerun()


def _render_part3_result() -> None:
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
        if _render_streaming_eval(turn, part=3):
            st.rerun()
        return

    # Show user's own recording for self-review
    with st.expander("Your answer (playback)", expanded=False):
        st.audio(turn.audio_bytes, format="audio/wav")

    _render_evaluation(turn.result)

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


def _render_part3_summary() -> None:
    sess: ExamSession = st.session_state.session
    p3_turns = sess.part_turns(3)

    st.header("Part 3 Summary")

    if not p3_turns:
        st.info("No answers recorded for Part 3.")
    else:
        evaluated = [t for t in p3_turns if t.result]
        if evaluated:
            _render_part_averages(evaluated)

    st.markdown("---")
    if st.button("View Session Summary", type="primary", use_container_width=True):
        sess.phase = "session_summary"
        st.rerun()


# ── Session Summary ───────────────────────────────────────────────────────────

def _render_session_summary() -> None:
    sess: ExamSession = st.session_state.session
    summary = sess.build_summary()

    st.header("Session Summary")

    if not summary.turns:
        st.info("No answers recorded this session.")
        if st.button("Start New Session", use_container_width=True):
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
                st.markdown(
                    f"<div style='text-align:center;padding:12px'><b>{label}</b><br>—</div>",
                    unsafe_allow_html=True,
                )

    parts_done = []
    if sess.part_turns(1):
        parts_done.append(f"Part 1 ({len(sess.part_turns(1))} answers)")
    if sess.part_turns(2):
        parts_done.append(f"Part 2 ({len(sess.part_turns(2))} speech)")
    if sess.part_turns(3):
        parts_done.append(f"Part 3 ({len(sess.part_turns(3))} answers)")
    if parts_done:
        st.caption("Parts completed: " + " | ".join(parts_done))

    if any(a > 0 for a in avgs):
        st.markdown("**Top Areas to Improve:**")
        areas = sorted(zip(labels, avgs), key=lambda x: x[1])
        for label, avg in areas[:2]:
            if avg > 0:
                st.markdown(f"- **{label}** ({avg:.1f}) — {_improvement_tip(label)}")

    st.markdown("---")

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
            if st.button("Save to History", type="primary", use_container_width=True):
                with st.spinner("Saving to MongoDB..."):
                    try:
                        session_id = _run_async(store.save_session(summary))
                        st.success(f"Saved! ID: {session_id[:8]}…")
                    except Exception as e:
                        st.error(f"Save failed: {e}")
        else:
            st.caption("MongoDB not configured — history unavailable")
    with col3:
        if st.button("Start New Session", use_container_width=True):
            st.session_state.session = ExamSession()
            st.rerun()

    # History panel
    if store is not None:
        st.markdown("---")
        with st.expander("Session History", expanded=False):
            _render_history(store)


def _render_history(store: FluentUpStore) -> None:
    try:
        history = _run_async(store.get_recent_sessions(limit=10))
    except Exception as e:
        st.error(f"Could not load history: {e}")
        return

    if not history:
        st.caption("No saved sessions yet.")
        return

    # Track which session to show in detail
    view_id: str | None = st.session_state.get("history_view_id")

    for h in history:
        sid = h["_id"]
        ts = h.get("created_at", "")
        if hasattr(ts, "strftime"):
            ts = ts.strftime("%Y-%m-%d %H:%M")
        overall = h.get("overall", 0.0)
        color = _band_color(overall)

        info_col, load_col, del_col = st.columns([7, 1, 1])
        with info_col:
            st.markdown(
                f"<div style='border-left:4px solid {color};padding:6px 12px;margin:2px 0'>"
                f"<b style='color:{color}'>{overall:.1f}</b> — {ts} &nbsp; "
                f"FC:{h.get('avg_fc', 0):.1f} "
                f"LR:{h.get('avg_lr', 0):.1f} "
                f"GR:{h.get('avg_gr', 0):.1f} "
                f"PR:{h.get('avg_pronun', 0):.1f}"
                f"</div>",
                unsafe_allow_html=True,
            )
        with load_col:
            if st.button("Load", key=f"hist_load_{sid}", use_container_width=True):
                if view_id == sid:
                    st.session_state.pop("history_view_id", None)
                else:
                    st.session_state["history_view_id"] = sid
                st.rerun()
        with del_col:
            if st.button("Delete", key=f"hist_del_{sid}", use_container_width=True):
                try:
                    _run_async(store.delete_session(sid))
                    if view_id == sid:
                        st.session_state.pop("history_view_id", None)
                    st.rerun()
                except Exception as e:
                    st.error(f"Delete failed: {e}")

        # Show detail for the loaded session directly below its row
        if view_id == sid:
            try:
                doc = _run_async(store.get_session(sid))
                if doc:
                    _render_history_detail(doc)
            except Exception as e:
                st.error(f"Could not load session: {e}")


def _render_history_detail(doc: dict) -> None:
    """Show a read-only score breakdown for a saved session."""
    with st.container():
        st.markdown("---")
        overall = doc.get("overall", 0.0)
        color = _band_color(overall)
        st.markdown(
            f"<div style='background:{color};color:white;padding:8px 14px;"
            f"border-radius:6px;font-weight:bold;margin-bottom:8px'>"
            f"Overall: {overall:.1f}</div>",
            unsafe_allow_html=True,
        )

        turns = doc.get("turns", [])
        for turn in turns:
            part = turn.get("part", "?")
            question = turn.get("question", "")
            band = turn.get("overall_band", 0.0)
            c = _band_color(band)
            with st.expander(f"Part {part} — {question[:60]} [{band:.1f}]"):
                for score in turn.get("scores", []):
                    crit = score.get("criterion", "")
                    b = score.get("band", 0.0)
                    tips = score.get("tips", [])
                    sc = _band_color(b)
                    st.markdown(
                        f"**{crit}** <span style='color:{sc}'>{b:.1f}</span>",
                        unsafe_allow_html=True,
                    )
                    for tip in tips:
                        st.markdown(f"  - {tip}")
        st.markdown("---")


# ── Utilities ─────────────────────────────────────────────────────────────────

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
            lines.append(f"  Overall: {t.result.overall_band:.1f}")
            for score in t.result.scores:
                lines.append(f"  {score.criterion}: {score.band:.1f}")
                if score.weak_points:
                    lines.append("  Weak: " + "; ".join(score.weak_points))
                if score.tips:
                    lines.append("  Tips: " + "; ".join(score.tips))
        lines.append("")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(page_title="FluentUp", page_icon="🎯", layout="wide")

    secrets = _load_secrets()
    _init_state(secrets)
    _render_sidebar(secrets)

    if not secrets["gemini_api_key"]:
        st.error("Add `GEMINI_API_KEY` to `.streamlit/secrets.toml` to start.")
        st.info("The app requires Gemini for audio transcription and question generation.")
        return

    sess: ExamSession = st.session_state.session
    phase = sess.phase

    dispatch = {
        "home":              _render_home,
        "part1_loading":     _render_part1_loading,
        "part1_idle":        _render_part1_idle,
        "part1_feedback":    _render_part1_feedback,
        "part1_evaluating":  _render_part1_evaluating,
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
