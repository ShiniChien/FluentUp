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
from fluentup.models import CriterionFeedback, EvaluationResult, Turn, UserProfile
from fluentup.evaluator import LiveEvaluationPipeline, CRITERIA
from fluentup.question_gen import QuestionGenerator
from fluentup.live_session import gemini_transcribe_only
from fluentup.store import FluentUpStore
from fluentup.config import ACCENT_LABELS, DEFAULT_ACCENT, PART1_QUESTIONS_PER_SESSION


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

_STATE_VERSION = 7


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
            # Ensure the bg loop exists before creating the Motor client,
            # so the client binds to the same loop used for all store operations.
            _get_bg_loop()
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


_BAND_LIGHT_BG: dict[str, str] = {
    "#00695C": "#E0F2F1",
    "#2E7D32": "#E8F5E9",
    "#558B2F": "#F1F8E9",
    "#E65100": "#FFF3E0",
    "#BF360C": "#FBE9E7",
    "#B71C1C": "#FFEBEE",
}


def _band_light_bg(color: str) -> str:
    """Light background tint for a band color — suitable for dark text."""
    return _BAND_LIGHT_BG.get(color, "#F5F5F5")


_bg_loop: asyncio.AbstractEventLoop | None = None
_bg_thread: threading.Thread | None = None


def _get_bg_loop() -> asyncio.AbstractEventLoop:
    """
    Return a long-lived background event loop, stored in st.session_state so it
    survives Streamlit reruns (which reset module-level globals to None).
    A new loop is only created when no running loop exists yet for this browser session.
    """
    global _bg_loop, _bg_thread

    # Prefer the loop stored in session_state (survives reruns)
    persisted = st.session_state.get("_bg_loop")
    if persisted is not None and persisted.is_running():
        _bg_loop = persisted
        return _bg_loop

    # Module global still alive (same Python process, same Streamlit worker thread)
    if _bg_loop is not None and _bg_loop.is_running():
        st.session_state["_bg_loop"] = _bg_loop
        return _bg_loop

    # Need a fresh loop — also invalidate store so Motor re-binds to the new loop
    _bg_loop = asyncio.new_event_loop()
    _bg_thread = threading.Thread(target=_bg_loop.run_forever, daemon=True)
    _bg_thread.start()
    st.session_state["_bg_loop"] = _bg_loop
    # Invalidate store: its Motor client is bound to the old (now-dead) loop
    st.session_state.pop("store", None)
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

def _render_sidebar_profile() -> None:
    st.markdown("**Your Profile**")
    store: FluentUpStore | None = st.session_state.get("store")
    current: UserProfile | None = st.session_state.get("user_profile")
    sess: ExamSession = st.session_state.session

    if current:
        gender_label = {"male": "M", "female": "F", "other": "—"}.get(current.gender, "")
        st.markdown(
            f"<div style='background:#E3F2FD;border-left:3px solid #1565C0;"
            f"padding:6px 10px;border-radius:4px;font-size:0.85em;color:#1a1a1a'>"
            f"<b>{current.name}</b>, {current.age} ({gender_label})<br>"
            f"<span style='color:#444'>{current.occupation_detail[:45]}</span></div>",
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Edit", key="sb_edit_profile", use_container_width=True):
                sess.phase = "profile_q1"
                st.rerun()
        with c2:
            if st.button("Clear", key="sb_clear_profile", use_container_width=True):
                st.session_state.pop("user_profile", None)
                st.rerun()
    else:
        if st.button("Set up profile", key="sb_create_profile", use_container_width=True):
            sess.phase = "profile_q1"
            st.rerun()

    # Saved profiles picker (requires MongoDB)
    if store:
        if "sidebar_profiles_cache" not in st.session_state:
            try:
                st.session_state["sidebar_profiles_cache"] = _run_async(store.get_profiles())
            except Exception:
                st.session_state["sidebar_profiles_cache"] = []

        profiles: list[dict] = st.session_state.get("sidebar_profiles_cache", [])
        if profiles:
            options_ids = [""] + [p["_id"] for p in profiles]
            current_id = current.profile_id if current else ""
            try:
                sel_index = options_ids.index(current_id)
            except ValueError:
                sel_index = 0

            def _fmt(pid: str) -> str:
                if not pid:
                    return "— select saved profile —"
                p = next((x for x in profiles if x["_id"] == pid), None)
                return f"{p['name']}, {p['age']} — {p.get('occupation_detail','')[:30]}" if p else pid

            selected = st.selectbox(
                "Saved profiles",
                options=options_ids,
                format_func=_fmt,
                index=sel_index,
                key="sb_profile_select",
                label_visibility="collapsed",
            )
            if selected and selected != current_id:
                p = next((x for x in profiles if x["_id"] == selected), None)
                if p:
                    st.session_state["user_profile"] = UserProfile(
                        name=p["name"],
                        age=p["age"],
                        occupation=p.get("occupation", "other"),
                        occupation_detail=p.get("occupation_detail", ""),
                        profile_id=p["_id"],
                        gender=p.get("gender", "male"),
                    )
                    st.rerun()

            # Delete button for selected saved profile
            if selected:
                if st.button("Delete this profile", key="sb_del_profile", use_container_width=True):
                    try:
                        _run_async(store.delete_profile(selected))
                        if current and current.profile_id == selected:
                            st.session_state.pop("user_profile", None)
                        st.session_state.pop("sidebar_profiles_cache", None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete failed: {e}")


def _render_sidebar(secrets: dict) -> None:
    with st.sidebar:
        st.markdown("## FluentUp")
        st.caption("IELTS Speaking Practice")

        st.divider()
        _render_sidebar_profile()

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

        r1, r2 = st.columns([5, 2])
        with r1:
            st.markdown(
                f"<div style='border-left:3px solid #1565C0;padding:3px 8px;"
                f"font-size:0.85em'>{ts}</div>",
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

    partial: dict = {}
    errors: dict = {}
    st.session_state["eval_partial"] = partial
    st.session_state["eval_auto_played"] = set()
    st.session_state["eval_errors"] = errors

    def _worker(criterion: str, results: dict, errs: dict) -> None:
        try:
            feedback, _ = asyncio.run(evaluator.eval_one(
                criterion=criterion,
                audio_bytes=turn.audio_bytes,
                question=turn.question,
                part=part,
            ))
            results[criterion] = feedback
        except Exception as exc:
            errs[criterion] = str(exc)

    for c in CRITERIA:
        threading.Thread(target=_worker, args=(c, partial, errors), daemon=True).start()


def _start_next_question_gen(prev_question: str, answer_wav: bytes) -> None:
    """Kick off background thread to generate the next Part 1 question via Gemini Live."""
    qgen: QuestionGenerator | None = st.session_state.get("question_gen")
    if qgen is None:
        return
    accent = st.session_state.get("examiner_accent", DEFAULT_ACCENT)
    profile: UserProfile | None = st.session_state.get("user_profile")
    # Store a plain dict in session_state BEFORE starting the thread.
    # The thread mutates the dict in-place — never touches st.session_state directly,
    # which would fail with "missing ScriptRunContext" from a non-main thread.
    result: dict = {"ready": False, "text": "", "wav": b""}
    st.session_state["p1_next_q"] = result

    def _worker() -> None:
        try:
            text, wav = asyncio.run(qgen.generate_next_part1_question(
                prev_question=prev_question,
                answer_wav=answer_wav,
                accent=accent,
                profile=profile,
            ))
            result["text"] = text
            result["wav"] = wav
        except Exception as exc:
            result["error"] = str(exc)
        finally:
            result["ready"] = True

    threading.Thread(target=_worker, daemon=True).start()


def _start_bg_turn_eval(turn: Turn, turn_idx: int, part: int) -> None:
    """Start background evaluation for a turn without blocking the UI."""
    evaluator: LiveEvaluationPipeline | None = st.session_state.get("evaluator")
    if evaluator is None:
        return
    turn_evals: dict = st.session_state.setdefault("turn_evals", {})
    partial: dict = {}
    errors: dict = {}
    turn_evals[turn_idx] = {"partial": partial, "errors": errors}

    def _worker(criterion: str) -> None:
        try:
            feedback, _ = asyncio.run(evaluator.eval_one(
                criterion=criterion,
                audio_bytes=turn.audio_bytes,
                question=turn.question,
                part=part,
            ))
            partial[criterion] = feedback
        except Exception as exc:
            errors[criterion] = str(exc)

    for c in CRITERIA:
        threading.Thread(target=_worker, args=(c,), daemon=True).start()


def _assemble_bg_evals(sess) -> int:
    """Assemble completed background evals into turn.result. Returns pending count."""
    turn_evals: dict = st.session_state.get("turn_evals", {})
    pending = 0
    for i, turn in enumerate(sess.turns):
        if turn.result is not None:
            continue
        state = turn_evals.get(i)
        if state is None:
            continue
        partial = state["partial"]
        errors = state["errors"]
        if len(partial) + len(errors) < len(CRITERIA):
            pending += 1
            continue
        feedbacks = []
        for c in CRITERIA:
            if c in partial:
                feedbacks.append(partial[c])
            else:
                feedbacks.append(CriterionFeedback(
                    criterion=c,
                    feedback=errors.get(c, "Failed"),
                    audio=b"",
                ))
        turn.result = EvaluationResult(transcript="", feedbacks=feedbacks)
    return pending


def _render_streaming_eval(turn: Turn, part: int) -> bool:
    """
    Show per-criterion feedback as it arrives.
    Returns True when all 4 criteria are done and turn.result has been assembled.
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
            fb: CriterionFeedback = partial[criterion]
            with st.expander(f"**{criterion}**", expanded=True):
                if fb.audio:
                    autoplay = criterion not in played
                    st.audio(fb.audio, format="audio/wav", autoplay=autoplay)
                    if autoplay:
                        played.add(criterion)
                        st.session_state["eval_auto_played"] = played
                if fb.feedback:
                    st.markdown(
                        f"<div style='background:#f8f9fa;border-left:4px solid #6c757d;"
                        f"padding:10px 14px;border-radius:4px;font-size:0.95em;color:#212529'>"
                        f"{fb.feedback}</div>",
                        unsafe_allow_html=True,
                    )
        elif criterion in errors:
            with st.expander(f"**{criterion}** — Error", expanded=True):
                st.error(errors[criterion])

    if done_count < total:
        time.sleep(0.8)
        st.rerun()
        return False

    feedbacks = []
    input_tr = ""
    for criterion in CRITERIA:
        if criterion in partial:
            feedbacks.append(partial[criterion])
        else:
            feedbacks.append(CriterionFeedback(
                criterion=criterion,
                feedback=errors.get(criterion, "Failed"),
                audio=b"",
            ))

    turn.result = EvaluationResult(transcript=input_tr, feedbacks=feedbacks)
    _clear_streaming_state()
    return True


# ── Evaluation summary display ────────────────────────────────────────────────

def _render_evaluation(result: EvaluationResult) -> None:
    st.markdown("#### Examiner Feedback")

    if result.transcript:
        with st.expander("Your answer (transcript)", expanded=False):
            st.markdown(
                f"<div style='background:#f8f9fa;padding:10px 14px;border-radius:4px;"
                f"font-size:0.9em;color:#555'>{result.transcript}</div>",
                unsafe_allow_html=True,
            )

    for fb in result.feedbacks:
        with st.expander(f"**{fb.criterion}**", expanded=True):
            if fb.audio:
                st.audio(fb.audio, format="audio/wav")
            if fb.feedback:
                st.markdown(
                    f"<div style='background:#f8f9fa;border-left:4px solid #6c757d;"
                    f"padding:10px 14px;border-radius:4px;font-size:0.95em;color:#212529'>"
                    f"{fb.feedback}</div>",
                    unsafe_allow_html=True,
                )

    feedback_text = ""
    for fb in result.feedbacks:
        feedback_text += f"=== {fb.criterion} ===\n{fb.feedback}\n\n"
    if feedback_text:
        st.download_button(
            "Download Feedback",
            data=feedback_text,
            file_name="feedback.txt",
            mime="text/plain",
        )


# ── Intro / Profile setup ─────────────────────────────────────────────────────

_OCC_LABELS = {"student": "Studying", "worker": "Working", "other": "Other"}
_OCC_DETAIL_LABELS = {
    "student": "What are you studying?",
    "worker":  "What do you do for work?",
    "other":   "Tell us more about yourself",
}


def _render_intro() -> None:
    sess: ExamSession = st.session_state.session
    store: FluentUpStore | None = st.session_state.get("store")

    st.header("Introduce Yourself")
    st.markdown(
        "Tell us a bit about yourself so we can ask questions that feel relevant to your life."
    )
    st.markdown("---")

    current: UserProfile | None = st.session_state.get("user_profile")

    name = st.text_input(
        "What's your name?",
        value=current.name if current else "",
        key="intro_name",
        placeholder="e.g. Minh",
    )
    age = st.number_input(
        "How old are you?",
        min_value=10, max_value=80,
        value=int(current.age) if current else 22,
        key="intro_age",
    )
    occ_options = list(_OCC_LABELS.keys())
    occ_index = occ_options.index(current.occupation) if current and current.occupation in occ_options else 0
    occupation = st.radio(
        "Are you currently…",
        options=occ_options,
        format_func=lambda x: _OCC_LABELS[x],
        index=occ_index,
        horizontal=True,
        key="intro_occ",
    )
    detail = st.text_input(
        _OCC_DETAIL_LABELS[occupation],
        value=current.occupation_detail if current else "",
        key="intro_detail",
        placeholder={
            "student": "e.g. Computer Science at HUST",
            "worker":  "e.g. Software engineer at a tech startup",
            "other":   "e.g. Recently graduated, preparing for IELTS",
        }[occupation],
    )

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Save Profile", type="primary", use_container_width=True):
            if not name.strip():
                st.warning("Please enter your name.")
            else:
                profile = UserProfile(
                    name=name.strip(),
                    age=int(age),
                    occupation=occupation,
                    occupation_detail=detail.strip(),
                    profile_id=current.profile_id if current else "",
                )
                if store:
                    try:
                        pid = _run_async(store.save_profile(profile))
                        profile.profile_id = pid
                    except Exception as e:
                        st.warning(f"Could not save to MongoDB: {e}")
                st.session_state["user_profile"] = profile
                st.session_state.pop("sidebar_profiles_cache", None)
                sess.phase = "home"
                st.rerun()
    with col2:
        if st.button("Skip", use_container_width=True):
            sess.phase = "home"
            st.rerun()


# ── Profile setup (spoken Q&A) ────────────────────────────────────────────────

# Questions asked in order; answers are transcribed and parsed into UserProfile fields.
_PROFILE_QUESTIONS = [
    ("profile_q1", "What is your name?"),
    ("profile_q2", "How old are you?"),
    ("profile_q3", "What do you do? Are you currently studying or working?"),
]

_PROFILE_EXTRACT_PROMPT = """You are a data extraction assistant.
Given the transcribed answer to the question, extract the relevant value.

Question: {question}
Transcribed answer: {answer}

Respond with a JSON object with a single key "value" containing the extracted string.
For name: the person's name (string).
For age: a number as string (e.g. "22").
For occupation: respond with a JSON object with keys "occupation" (one of: student/worker/other) and "occupation_detail" (short description).
Be concise. If unclear, make a reasonable guess."""


def _extract_profile_field(
    question: str,
    transcript: str,
    openrouter_base_url: str,
    openrouter_api_key: str,
    openrouter_model: str,
) -> dict:
    """Call OpenRouter to parse a spoken transcript into a structured field."""
    import json
    from openai import OpenAI

    client = OpenAI(base_url=openrouter_base_url, api_key=openrouter_api_key)
    prompt = _PROFILE_EXTRACT_PROMPT.format(question=question, answer=transcript)
    resp = client.chat.completions.create(
        model=openrouter_model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        max_tokens=120,
    )
    try:
        return json.loads(resp.choices[0].message.content or "{}")
    except Exception:
        return {}


def _render_profile_question(phase_key: str, question: str, next_phase: str) -> None:
    """Render a single spoken profile question step."""
    sess: ExamSession = st.session_state.session
    secrets: dict = st.session_state.get("_secrets", {})

    st.header("Profile Setup")
    step = _PROFILE_QUESTIONS.index((phase_key, question)) + 1
    st.progress(step / len(_PROFILE_QUESTIONS), text=f"Question {step} of {len(_PROFILE_QUESTIONS)}")
    st.markdown(f"### {question}")
    st.caption("Record your answer below. Speak naturally — we'll pick up what you say.")

    _hear_question(question, key=f"profile_tts_{phase_key}")

    wav = st.audio_input("Your answer", key=f"profile_audio_{phase_key}")

    col1, col2 = st.columns(2)
    with col1:
        if wav is not None:
            if st.button("Submit Answer", type="primary", use_container_width=True):
                with st.spinner("Transcribing…"):
                    try:
                        transcript = _run_async(gemini_transcribe_only(
                            api_key=secrets.get("gemini_api_key", ""),
                            wav_bytes=wav.getvalue(),
                            model=secrets.get("live_model", ""),
                        ))
                    except Exception as e:
                        st.error(f"Transcription failed: {e}")
                        return

                # Store raw transcript keyed by phase
                st.session_state[f"profile_raw_{phase_key}"] = transcript
                sess.phase = next_phase
                st.rerun()
    with col2:
        if st.button("Skip", use_container_width=True):
            st.session_state[f"profile_raw_{phase_key}"] = ""
            sess.phase = next_phase
            st.rerun()


def _render_profile_confirm() -> None:
    """Parse collected transcripts and let user review/edit before saving."""
    sess: ExamSession = st.session_state.session
    store: FluentUpStore | None = st.session_state.get("store")
    secrets: dict = st.session_state.get("_secrets", {})
    current: UserProfile | None = st.session_state.get("user_profile")

    st.header("Profile Setup")
    st.progress(1.0, text="Confirm your profile")

    # Parse stored transcripts into draft fields (only once per setup flow)
    if "profile_draft" not in st.session_state:
        draft: dict = {
            "name": current.name if current else "",
            "age": int(current.age) if current else 22,
            "occupation": current.occupation if current else "student",
            "occupation_detail": current.occupation_detail if current else "",
            "gender": current.gender if current else "male",
        }

        q1_raw = st.session_state.get("profile_raw_profile_q1", "")
        q2_raw = st.session_state.get("profile_raw_profile_q2", "")
        q3_raw = st.session_state.get("profile_raw_profile_q3", "")

        with st.spinner("Processing your answers…"):
            if q1_raw:
                parsed = _extract_profile_field(
                    _PROFILE_QUESTIONS[0][1], q1_raw,
                    secrets.get("openrouter_base_url", ""),
                    secrets.get("openrouter_api_key", ""),
                    secrets.get("openrouter_model", ""),
                )
                if parsed.get("value"):
                    draft["name"] = str(parsed["value"])

            if q2_raw:
                parsed = _extract_profile_field(
                    _PROFILE_QUESTIONS[1][1], q2_raw,
                    secrets.get("openrouter_base_url", ""),
                    secrets.get("openrouter_api_key", ""),
                    secrets.get("openrouter_model", ""),
                )
                try:
                    draft["age"] = int(str(parsed.get("value", draft["age"])))
                except (ValueError, TypeError):
                    pass

            if q3_raw:
                parsed = _extract_profile_field(
                    _PROFILE_QUESTIONS[2][1], q3_raw,
                    secrets.get("openrouter_base_url", ""),
                    secrets.get("openrouter_api_key", ""),
                    secrets.get("openrouter_model", ""),
                )
                occ = parsed.get("occupation", draft["occupation"])
                if occ in ("student", "worker", "other"):
                    draft["occupation"] = occ
                if parsed.get("occupation_detail"):
                    draft["occupation_detail"] = str(parsed["occupation_detail"])

        st.session_state["profile_draft"] = draft

    draft = st.session_state["profile_draft"]

    st.markdown("### Review your profile")
    st.caption("Edit any field that was misheard.")

    name = st.text_input("Name", value=draft["name"], key="pconf_name")
    age = st.number_input("Age", min_value=10, max_value=80, value=draft["age"], key="pconf_age")

    _OCC_LABELS = {"student": "Studying", "worker": "Working", "other": "Other"}
    occ_options = list(_OCC_LABELS.keys())
    occ_idx = occ_options.index(draft["occupation"]) if draft["occupation"] in occ_options else 0
    occupation = st.radio(
        "Currently…",
        options=occ_options,
        format_func=lambda x: _OCC_LABELS[x],
        index=occ_idx,
        horizontal=True,
        key="pconf_occ",
    )
    detail = st.text_input(
        {"student": "What are you studying?", "worker": "What do you do?", "other": "Tell us more"}[occupation],
        value=draft["occupation_detail"],
        key="pconf_detail",
    )

    gender_options = ["male", "female", "other"]
    gender_labels = {"male": "Male", "female": "Female", "other": "Other"}
    gender_idx = gender_options.index(draft["gender"]) if draft["gender"] in gender_options else 0
    gender = st.radio(
        "Gender",
        options=gender_options,
        format_func=lambda x: gender_labels[x],
        index=gender_idx,
        horizontal=True,
        key="pconf_gender",
    )

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Save Profile", type="primary", use_container_width=True):
            if not name.strip():
                st.warning("Please enter your name.")
                return
            profile = UserProfile(
                name=name.strip(),
                age=int(age),
                occupation=occupation,
                occupation_detail=detail.strip(),
                profile_id=current.profile_id if current else "",
                gender=gender,
            )
            if store:
                try:
                    pid = _run_async(store.save_profile(profile))
                    profile.profile_id = pid
                except Exception as e:
                    st.warning(f"Could not save to MongoDB: {e}")
            st.session_state["user_profile"] = profile
            st.session_state.pop("sidebar_profiles_cache", None)
            # Clean up temp state
            for key in ("profile_draft", "profile_raw_profile_q1",
                        "profile_raw_profile_q2", "profile_raw_profile_q3"):
                st.session_state.pop(key, None)
            sess.phase = "home"
            st.rerun()
    with col2:
        if st.button("Back", use_container_width=True):
            st.session_state.pop("profile_draft", None)
            sess.phase = "profile_q1"
            st.rerun()


# ── Part selector (home) ──────────────────────────────────────────────────────

def _render_home() -> None:
    st.title("FluentUp")
    st.subheader("IELTS Speaking Practice")

    profile: UserProfile | None = st.session_state.get("user_profile")
    sess: ExamSession = st.session_state.session

    if profile:
        st.markdown(
            f"<div style='background:#E3F2FD;border-left:4px solid #1565C0;"
            f"border-radius:6px;padding:10px 16px;margin-bottom:16px;color:#1a1a1a'>"
            f"👤 <b>{profile.name}</b>, {profile.age} — {profile.occupation_detail}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.info(
            "💡 Set up your profile in the sidebar so questions can be tailored to your background."
        )

    st.markdown("Choose a part to start practicing:")

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

    with st.spinner("Loading first question..."):
        try:
            profile: UserProfile | None = st.session_state.get("user_profile")
            questions = _run_async(qgen.generate_part1_questions(n=1, profile=profile))
            sess.part1_questions = questions
            sess.part1_index = 0
            st.session_state.pop("p1_next_q", None)
            sess.phase = "part1_idle"
            st.rerun()
        except Exception as e:
            st.error(f"Failed to generate questions: {e}")
            if st.button("Retry", use_container_width=True):
                st.rerun()


def _render_part1_idle() -> None:
    sess: ExamSession = st.session_state.session
    idx = sess.part1_index
    max_q = PART1_QUESTIONS_PER_SESSION

    st.header("Part 1 — Introduction & Interview")

    # Wait for next question to finish generating
    next_q: dict | None = st.session_state.get("p1_next_q")
    if next_q is not None and not next_q.get("ready", False):
        st.caption(f"Question {idx + 1} (up to {max_q})")
        st.progress(idx / max_q)
        st.info("Preparing next question...")
        time.sleep(0.5)
        st.rerun()
        return

    # Consume ready next question and re-enter to render it
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
    st.caption(f"Question {idx + 1} (up to {max_q})")
    st.progress(idx / max_q)

    # Auto-play pre-generated question audio if available
    next_wav = st.session_state.pop("p1_next_q_wav", None)
    if next_wav:
        st.audio(next_wav, format="audio/wav", autoplay=True)

    if question is None:
        sess.phase = "part1_summary"
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
                turn_idx = len(sess.turns) - 1
                sess.part1_index += 1
                _start_bg_turn_eval(sess.turns[turn_idx], turn_idx, part=1)
                if sess.part1_index < max_q:
                    _start_next_question_gen(question, wav_bytes)
                else:
                    st.session_state.pop("p1_next_q", None)
                st.rerun()
    with col2:
        if st.button("Skip", key=f"p1_skip_{idx}", use_container_width=True):
            sess.part1_index += 1
            if sess.part1_index >= max_q or not sess.current_part1_question():
                sess.phase = "part1_summary"
            st.rerun()
    with col3:
        if st.button("End Part 1", key=f"p1_end_{idx}", use_container_width=True):
            sess.phase = "part1_summary"
            st.rerun()


def _render_part_averages(evaluated: list) -> None:
    """Show a simple count of evaluated answers."""
    st.markdown(
        f"<div style='background:#E3F2FD;border-left:4px solid #1565C0;"
        f"padding:10px 16px;border-radius:6px;font-size:1.05em;color:#1a1a1a'>"
        f"<b>{len(evaluated)}</b> answer(s) evaluated — listen to each examiner's feedback below."
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_part1_summary() -> None:
    sess: ExamSession = st.session_state.session
    p1_turns = sess.part_turns(1)

    st.header("Part 1 Summary")

    # Assemble any completed background evaluations, wait for pending ones
    pending = _assemble_bg_evals(sess)
    if pending > 0:
        evaluated_count = sum(1 for t in p1_turns if t.result is not None)
        total = len(p1_turns)
        st.info(f"Evaluating answers in background… ({evaluated_count}/{total} complete)")
        st.progress(evaluated_count / total if total else 0)
        time.sleep(0.8)
        st.rerun()
        return

    if not p1_turns:
        st.info("No answers recorded for Part 1.")
    else:
        evaluated = [t for t in p1_turns if t.result]

        if evaluated:
            _render_part_averages(evaluated)

            st.markdown("---")
            st.markdown("#### Per-question breakdown")
            for i, turn in enumerate(evaluated):
                with st.expander(
                    f"Q{i + 1}: {turn.question[:70]}{'…' if len(turn.question) > 70 else ''}",
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
                cue = _run_async(qgen.generate_cue_card(
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

    parts_done = []
    if sess.part_turns(1):
        parts_done.append(f"Part 1 ({len(sess.part_turns(1))} answers)")
    if sess.part_turns(2):
        parts_done.append(f"Part 2 ({len(sess.part_turns(2))} speech)")
    if sess.part_turns(3):
        parts_done.append(f"Part 3 ({len(sess.part_turns(3))} answers)")
    if parts_done:
        st.markdown("**Parts completed:** " + " | ".join(parts_done))

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

        info_col, load_col, del_col = st.columns([7, 1, 1])
        with info_col:
            st.markdown(
                f"<div style='border-left:4px solid #1565C0;padding:6px 12px;margin:2px 0'>"
                f"{ts}</div>",
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
    """Show a read-only feedback breakdown for a saved session."""
    with st.container():
        st.markdown("---")
        turns = doc.get("turns", [])
        for turn in turns:
            part = turn.get("part", "?")
            question = turn.get("question", "")
            transcript = turn.get("transcript", "")
            with st.expander(f"Part {part} — {question[:60]}"):
                if transcript:
                    st.markdown(f"**Transcript:** {transcript}")
                for fb in turn.get("feedbacks", []):
                    crit = fb.get("criterion", "")
                    text = fb.get("feedback", "")
                    st.markdown(f"**{crit}:** {text}")
        st.markdown("---")


# ── Utilities ─────────────────────────────────────────────────────────────────

def _build_report(sess: ExamSession) -> str:
    summary = sess.build_summary()
    lines = [
        "FluentUp — IELTS Speaking Practice Session Report",
        "=" * 50,
        "",
    ]
    for t in summary.turns:
        lines.append(f"Part {t.part} — {t.question}")
        if t.result:
            if t.result.transcript:
                lines.append(f"  Transcript: {t.result.transcript}")
            for fb in t.result.feedbacks:
                lines.append(f"  [{fb.criterion}] {fb.feedback}")
        lines.append("")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(page_title="FluentUp", page_icon="🎯", layout="wide")

    secrets = _load_secrets()
    _init_state(secrets)
    st.session_state["_secrets"] = secrets
    _render_sidebar(secrets)

    if not secrets["gemini_api_key"]:
        st.error("Add `GEMINI_API_KEY` to `.streamlit/secrets.toml` to start.")
        st.info("The app requires Gemini for audio transcription and question generation.")
        return

    sess: ExamSession = st.session_state.session
    phase = sess.phase

    dispatch = {
        "home":              _render_home,
        "intro":             _render_intro,
        "profile_q1":        lambda: _render_profile_question("profile_q1", _PROFILE_QUESTIONS[0][1], "profile_q2"),
        "profile_q2":        lambda: _render_profile_question("profile_q2", _PROFILE_QUESTIONS[1][1], "profile_q3"),
        "profile_q3":        lambda: _render_profile_question("profile_q3", _PROFILE_QUESTIONS[2][1], "profile_confirm"),
        "profile_confirm":   _render_profile_confirm,
        "part1_loading":     _render_part1_loading,
        "part1_idle":        _render_part1_idle,
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
