from __future__ import annotations

import asyncio
import random

import streamlit as st

from core.config import LIVE_MODEL, LISTENING_TURNS_MIN, LISTENING_TURNS_MAX, EXAMINER_ACCENTS
from core.listening.dialogue_gen import generate_turn
from .constants import TOPICS, SPEAKER_COLORS, VOICES
from .scoring import score_answers, mask_line


def render_idle(secrets: dict) -> None:
    st.markdown(
        "<h1 style='margin-bottom:4px'>🎧 EchoLab</h1>"
        "<p style='color:#666;margin-top:0'>Practise your English listening — "
        "hear a dialogue, then transcribe or fill in the blanks.</p>",
        unsafe_allow_html=True,
    )

    if err := st.session_state.pop("echo_error", None):
        st.error(f"Generation failed: {err}")

    col_left, col_right = st.columns([3, 1])

    with col_left:
        topic = st.selectbox(
            "Topic",
            options=TOPICS,
            index=TOPICS.index(st.session_state["echo_topic"])
                  if st.session_state["echo_topic"] in TOPICS else 0,
            key="echo_topic_select",
        )
        st.session_state["echo_topic"] = topic

    with col_right:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("🎲 Random topic", use_container_width=True):
            st.session_state["echo_topic"] = random.choice(TOPICS)
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
    """
    Render masked text + input fields as a single inline row.
    Column widths use word-count-based ratios (min/max clamped) so short
    segments don't collapse and long ones don't dominate.
    """
    display_words = masked["display"].split()
    blanks        = masked["blanks"]  # [(original_word, position), ...]
    blank_at      = {pos: order for order, (_, pos) in enumerate(blanks)}

    segments: list[tuple] = []
    buf: list[str] = []
    for j, w in enumerate(display_words):
        if j in blank_at:
            if buf:
                segments.append(("text", " ".join(buf)))
                buf = []
            segments.append(("blank", blank_at[j], blanks[blank_at[j]][0]))
        else:
            buf.append(w)
    if buf:
        segments.append(("text", " ".join(buf)))

    BLANK_W = 13
    widths = [
        min(max(len(seg[1].split()) * 8, 15), 45) if seg[0] == "text" else BLANK_W
        for seg in segments
    ]

    cols = st.columns(widths)
    for col, seg in zip(cols, segments):
        with col:
            if seg[0] == "text":
                # No explicit color — inherits from Streamlit theme (works in both light/dark)
                st.markdown(
                    f"<p style='margin:6px 0 0 0;font-size:0.95em;"
                    f"font-family:monospace'>{seg[1]}</p>",
                    unsafe_allow_html=True,
                )
            else:
                key = f"{i}_{seg[1]}"
                answers[key] = st.text_input(
                    "_", value=answers.get(key, ""),
                    key=f"inp_{key}", label_visibility="collapsed",
                    placeholder="___",
                )


def _render_turn(i: int, line: dict, masked_line: dict | None, mode: str, answers: dict) -> None:
    """Render one dialogue turn with audio + input field."""
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
    voices   = {"A": voice_a, "B": voice_b}
    accents  = {"A": accent_a, "B": accent_b}

    already_done = len(dialogue)
    still_generating = already_done < n_turns

    st.markdown(
        f"<h1 style='margin-bottom:2px'>🎧 EchoLab</h1>"
        f"<p style='color:#444'>Topic: <b>{topic}</b> &nbsp;|&nbsp; "
        f"Voice A: <code>{voice_a}</code> &nbsp;|&nbsp; "
        f"Voice B: <code>{voice_b}</code></p>",
        unsafe_allow_html=True,
    )

    if still_generating:
        st.caption(f"Generating… {already_done} / {n_turns} turns ready")
        progress_bar = st.progress(already_done / n_turns)
    else:
        mode_label = "Fill in the Blank" if mode == "fill_blank" else "Full Transcription"
        st.markdown(f"**Mode:** {mode_label}")

    st.markdown("---")

    # Pre-create placeholders for all turns so new ones appear in order
    placeholders = [st.empty() for _ in range(n_turns)]

    # Render already-generated turns from session_state
    for i, (line, m) in enumerate(zip(dialogue, masked)):
        with placeholders[i].container():
            _render_turn(i, line, m, mode, answers)

    # Generate remaining turns and render each as it arrives
    history = [{"speaker": t["speaker"], "text": t["text"]} for t in dialogue]
    for i in range(already_done, n_turns):
        speaker = "A" if i % 2 == 0 else "B"
        try:
            turn = asyncio.run(generate_turn(
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

        m = mask_line(turn["text"])
        dialogue.append(turn)
        masked.append(m)
        history.append({"speaker": turn["speaker"], "text": turn["text"]})

        # Persist progress so reruns (from user input) skip already-done turns
        st.session_state["echo_dialogue"] = list(dialogue)
        st.session_state["echo_masked"]   = list(masked)

        with placeholders[i].container():
            _render_turn(i, turn, m, mode, answers)

        progress_bar.progress((i + 1) / n_turns)

    st.session_state["echo_answers"] = answers

    # All turns done — show controls
    if len(dialogue) == n_turns:
        if still_generating:
            progress_bar.empty()
        st.markdown("---")
        col_submit, col_reset = st.columns([3, 1])
        with col_submit:
            if st.button("✔ Submit Answers", type="primary", use_container_width=True):
                st.session_state["echo_scores"] = score_answers()
                st.session_state["echo_phase"]  = "submitted"
                st.rerun()
        with col_reset:
            if st.button("↺ New Dialogue", use_container_width=True):
                st.session_state["echo_phase"]   = "idle"
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
        f"<h1 style='margin-bottom:2px'>🎧 EchoLab — Results</h1>"
        f"<p style='color:#444'>Topic: <b>{topic}</b></p>",
        unsafe_allow_html=True,
    )

    if mode == "fill_blank":
        total_blanks   = sum(len(r["blanks"]) for r in scores)
        correct_blanks = sum(b["correct"] for r in scores for b in r["blanks"])
        pct = int(correct_blanks / total_blanks * 100) if total_blanks else 0
        st.markdown(f"### Score: {correct_blanks} / {total_blanks} blanks correct ({pct}%)")
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
