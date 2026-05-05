from __future__ import annotations

import random

import streamlit as st

from core.config import LIVE_MODEL, LISTENING_TURNS_MIN, LISTENING_TURNS_MAX, EXAMINER_ACCENTS
from core.async_utils import run_async
from core.viet_words import generate_topic
from core.listening.dialogue_gen import generate_turn
from .constants import SPEAKER_COLORS, VOICES
from .scoring import score_answers, mask_line, QUESTION_TYPES

_Q_TYPE_COLOR = "#7B5EA7"


def render_idle(secrets: dict) -> None:
    st.markdown(
        "<h1 style='margin-bottom:4px'>🎧 Listening Practice</h1>"
        "<p style='color:#666;margin-top:0'>Nghe hội thoại AI rồi điền từ còn thiếu "
        "hoặc luyện ghi chép toàn bộ.</p>",
        unsafe_allow_html=True,
    )

    if err := st.session_state.pop("echo_error", None):
        st.error(f"Generation failed: {err}")

    col_left, col_right = st.columns([3, 1])
    with col_left:
        topic = st.text_input(
            "Topic",
            value=st.session_state["echo_topic"],
            placeholder="Enter a topic or click ✨ to generate one…",
        )
        st.session_state["echo_topic"] = topic
    with col_right:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("✨ Generate topic", use_container_width=True):
            or_base = secrets.get("openrouter_base_url", "")
            or_key  = secrets.get("openrouter_api_key", "")
            or_model = secrets.get("openrouter_model", "")
            if not (or_base and or_key and or_model):
                st.error("OpenRouter credentials not configured.")
            else:
                with st.spinner("Generating topic…"):
                    try:
                        new_topic = run_async(generate_topic(
                            openrouter_base_url=or_base,
                            openrouter_api_key=or_key,
                            openrouter_model=or_model,
                        ))
                        st.session_state["echo_topic"] = new_topic
                    except Exception as exc:
                        st.error(f"Failed to generate topic: {exc}")
            st.rerun()

    mode = st.radio(
        "Exercise mode",
        options=["fill_blank", "transcription"],
        format_func=lambda m: "Fill in the Blank" if m == "fill_blank" else "Full Transcription",
        horizontal=True,
        index=0 if st.session_state["echo_mode"] == "fill_blank" else 1,
        key="echo_mode_radio",
    )
    st.session_state["echo_mode"] = mode

    n_turns = st.slider(
        "Number of turns",
        min_value=LISTENING_TURNS_MIN,
        max_value=LISTENING_TURNS_MAX,
        value=st.session_state["echo_n_turns"],
        step=1,
        key="echo_n_turns_slider",
    )
    st.session_state["echo_n_turns"] = n_turns

    st.markdown("")
    if st.button("▶ Generate Dialogue", type="primary", use_container_width=True):
        if not secrets["gemini_api_key"]:
            st.error("GEMINI_API_KEY not configured.")
        else:
            st.session_state["echo_phase"]    = "generating"
            st.session_state["echo_dialogue"] = []
            st.session_state["echo_masked"]   = []
            st.session_state["echo_answers"]  = {}
            st.session_state["echo_scores"]   = []
            voice_a, voice_b = random.sample(VOICES, 2)
            st.session_state["echo_voice_a"]  = voice_a
            st.session_state["echo_voice_b"]  = voice_b
            st.rerun()


def _fill_blank_inline(i: int, masked: dict, answers: dict) -> None:
    words  = masked["words"]
    blanks = masked["blanks"]

    blank_map = {b[1]: (b[2], j) for j, b in enumerate(blanks)}
    parts: list[str] = []
    k = 0
    while k < len(words):
        if k in blank_map:
            _end, j = blank_map[k]
            parts.append(f"**[{j+1}]** \\___")
            k = _end + 1
        else:
            parts.append(words[k])
            k += 1
    st.markdown(" ".join(parts))

    cols = st.columns(len(blanks)) if blanks else []
    for j, (phrase, _s, _e) in enumerate(blanks):
        with cols[j]:
            key = f"{i}_{j}"
            answers[key] = st.text_input(
                f"[{j+1}]",
                value=answers.get(key, ""),
                key=f"inp_{key}",
                placeholder="···",
            )


def _render_turn(i: int, line: dict, masked_line: dict | None, mode: str, answers: dict) -> None:
    speaker = line["speaker"]
    color   = SPEAKER_COLORS[speaker]

    col_label, col_audio = st.columns([1, 4])
    with col_label:
        st.markdown(
            f"<div style='padding-top:10px'>"
            f"<span style='color:{color};font-weight:bold;font-size:1.05em'>"
            f"Speaker {speaker}</span></div>",
            unsafe_allow_html=True,
        )
    with col_audio:
        if line.get("audio"):
            st.audio(line["audio"], format="audio/wav")

    if mode == "fill_blank" and masked_line:
        _fill_blank_inline(i, masked_line, answers)
    else:
        key = str(i)
        answers[key] = st.text_area(
            "Your transcription", value=answers.get(key, ""), key=f"inp_{key}",
            height=68, label_visibility="collapsed", placeholder="Type what you heard…",
        )

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)


def render_generating(secrets: dict) -> None:
    topic    = st.session_state["echo_topic"]
    n_turns  = st.session_state["echo_n_turns"]
    mode     = st.session_state["echo_mode"]
    voice_a  = st.session_state["echo_voice_a"]
    voice_b  = st.session_state["echo_voice_b"]
    accent_a = EXAMINER_ACCENTS.get(st.session_state["echo_accent_a"], "")
    accent_b = EXAMINER_ACCENTS.get(st.session_state["echo_accent_b"], "")
    dialogue: list[dict] = st.session_state["echo_dialogue"]
    masked:   list[dict] = st.session_state["echo_masked"]
    answers:  dict       = st.session_state["echo_answers"]
    voices  = {"A": voice_a, "B": voice_b}
    accents = {"A": accent_a, "B": accent_b}

    # Truncate stale dialogue if user reduced n_turns (e.g. after Try Again)
    if len(dialogue) > n_turns:
        del dialogue[n_turns:]
        del masked[n_turns:]
        st.session_state["echo_dialogue"] = list(dialogue)
        st.session_state["echo_masked"]   = list(masked)

    already_done     = len(dialogue)
    still_generating = already_done < n_turns

    if mode == "fill_blank" and already_done == 0:
        st.session_state["echo_q_type"] = random.choice(QUESTION_TYPES)
    q_type = st.session_state["echo_q_type"]

    st.markdown(
        f"<h1 style='margin-bottom:2px'>🎧 Listening Practice</h1>"
        f"<p style='color:#444'>Topic: <b>{topic}</b> &nbsp;|&nbsp; "
        f"Voice A: <code>{voice_a}</code> &nbsp;|&nbsp; "
        f"Voice B: <code>{voice_b}</code></p>",
        unsafe_allow_html=True,
    )

    if mode == "fill_blank":
        st.markdown(
            f"<div style='background:#F3EEF9;border-left:3px solid {_Q_TYPE_COLOR};"
            f"padding:6px 12px;border-radius:4px;margin-bottom:8px'>"
            f"<span style='font-size:0.82em;color:#555'>Answer type:</span> "
            f"<strong style='color:{_Q_TYPE_COLOR}'>{q_type}</strong></div>",
            unsafe_allow_html=True,
        )

    if still_generating:
        st.caption(f"Generating… {already_done} / {n_turns} turns ready")
        progress_bar = st.progress(already_done / n_turns)
        st.markdown("---")

        placeholders = [st.empty() for _ in range(n_turns)]

        for i, (line, m) in enumerate(zip(dialogue, masked)):
            with placeholders[i].container():
                _render_turn(i, line, m, mode, answers)

        history = [{"speaker": t["speaker"], "text": t["text"]} for t in dialogue]
        _next = "B" if dialogue and dialogue[-1]["speaker"] == "A" else "A"

        for i in range(already_done, n_turns):
            speaker = _next
            _next   = "B" if speaker == "A" else "A"
            try:
                turn = run_async(generate_turn(
                    topic=topic,
                    speaker=speaker,
                    voice=voices[speaker],
                    history=history,
                    api_key=secrets["gemini_api_key"],
                    model=secrets.get("live_model", LIVE_MODEL),
                    accent_instruction=accents[speaker],
                ))
            except Exception as exc:
                st.error(f"Turn {i + 1} failed: {exc}")
                st.session_state["echo_phase"] = "idle"
                return

            try:
                m = mask_line(turn["text"], q_type=q_type)
            except Exception:
                m = {"words": turn["text"].split(), "blanks": [], "q_type": q_type, "max_span": 1}
            dialogue.append(turn)
            masked.append(m)
            history.append({"speaker": turn["speaker"], "text": turn["text"]})

            st.session_state["echo_dialogue"] = list(dialogue)
            st.session_state["echo_masked"]   = list(masked)

            with placeholders[i].container():
                _render_turn(i, turn, m, mode, answers)

            progress_bar.progress((i + 1) / n_turns)

        progress_bar.empty()
        for ph in placeholders:
            ph.empty()
        st.rerun()

    else:
        st.markdown("---")
        _render_form(dialogue, masked, mode, answers)


def _collect_answers(mode: str, masked: list[dict]) -> dict:
    answers: dict = {}
    for i, m in enumerate(masked):
        if mode == "fill_blank":
            for b_idx in range(len(m["blanks"])):
                key = f"{i}_{b_idx}"
                answers[key] = st.session_state.get(f"inp_{key}", "")
        else:
            answers[str(i)] = st.session_state.get(f"inp_{i}", "")
    return answers


def _render_form(dialogue: list[dict], masked: list[dict], mode: str, answers: dict) -> None:
    with st.form("echo_answer_form", border=False):
        for i, (line, m) in enumerate(zip(dialogue, masked)):
            _render_turn(i, line, m, mode, answers)
        st.markdown("---")
        submitted = st.form_submit_button("✔ Submit Answers", type="primary", use_container_width=True)

    if submitted:
        st.session_state["echo_answers"] = _collect_answers(mode, masked)
        st.session_state["echo_scores"]  = score_answers()
        st.session_state["echo_phase"]   = "submitted"
        st.rerun()

    if st.button("↺ New Dialogue", use_container_width=True):
        st.session_state["echo_phase"]    = "idle"
        st.session_state["echo_dialogue"] = []
        st.session_state["echo_masked"]   = []
        st.session_state["echo_answers"]  = {}
        st.rerun()


def render_submitted() -> None:
    dialogue = st.session_state["echo_dialogue"]
    scores   = st.session_state["echo_scores"]
    mode     = st.session_state["echo_mode"]
    topic    = st.session_state["echo_topic"]

    st.markdown(
        f"<h1 style='margin-bottom:2px'>🎧 Listening — Results</h1>"
        f"<p style='color:#444'>Topic: <b>{topic}</b></p>",
        unsafe_allow_html=True,
    )

    if mode == "fill_blank":
        q_type         = st.session_state.get("echo_q_type", "")
        total_blanks   = sum(len(r["blanks"]) for r in scores)
        correct_blanks = sum(b["correct"] for r in scores for b in r["blanks"])
        pct = int(correct_blanks / total_blanks * 100) if total_blanks else 0
        st.markdown(f"### Score: {correct_blanks} / {total_blanks} blanks correct ({pct}%)")
        st.markdown(
            f"<p style='margin:-8px 0 8px 0;font-size:0.85em;font-style:italic;"
            f"color:{_Q_TYPE_COLOR}'>Answer type: {q_type}</p>",
            unsafe_allow_html=True,
        )
    else:
        total_correct = sum(r["correct"] for r in scores)
        total_words   = sum(r["total"] for r in scores)
        pct = int(total_correct / total_words * 100) if total_words else 0
        st.markdown(f"### Word accuracy: {total_correct} / {total_words} words ({pct}%)")

    st.markdown("---")

    for line, result in zip(dialogue, scores):
        speaker = line["speaker"]
        color   = SPEAKER_COLORS[speaker]

        st.markdown(
            f"<span style='color:{color};font-weight:bold'>Speaker {speaker}</span>",
            unsafe_allow_html=True,
        )

        if line.get("audio"):
            st.audio(line["audio"], format="audio/wav")

        if mode == "fill_blank":
            for b in result["blanks"]:
                expected = b["expected"]
                user_ans = b["user"] or "(empty)"
                if b["correct"]:
                    st.markdown(f"- ✅ **{expected}**")
                else:
                    st.markdown(f"- ❌ _{user_ans}_ → **{expected}**")
            st.markdown(
                f"<div style='background:#E8F5E9;border-left:3px solid #2E7D32;"
                f"padding:5px 10px;border-radius:4px;font-size:0.9em;color:#1a1a1a'>"
                f"Full line: {line['text']}</div>",
                unsafe_allow_html=True,
            )
        else:
            user_ans = result["user"] or "(no answer)"
            st.markdown(f"**You wrote:** {user_ans}")
            st.markdown(
                f"<div style='background:#E8F5E9;border-left:3px solid #2E7D32;"
                f"padding:5px 10px;border-radius:4px;font-size:0.9em;color:#1a1a1a'>"
                f"Expected: {line['text']}</div>",
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    st.markdown("---")
    col_retry, col_new = st.columns(2)
    with col_retry:
        if st.button("↺ Try Again (same dialogue)", use_container_width=True):
            st.session_state["echo_phase"]   = "generating"
            st.session_state["echo_answers"] = {}
            st.session_state["echo_scores"]  = []
            if mode == "fill_blank":
                st.session_state["echo_masked"] = [
                    mask_line(line["text"])
                    for line in st.session_state["echo_dialogue"]
                ]
            st.rerun()
    with col_new:
        if st.button("▶ New Dialogue", type="primary", use_container_width=True):
            st.session_state["echo_phase"]    = "idle"
            st.session_state["echo_dialogue"] = []
            st.session_state["echo_masked"]   = []
            st.session_state["echo_answers"]  = {}
            st.session_state["echo_scores"]   = []
            st.rerun()
