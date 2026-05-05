from __future__ import annotations

import json

import streamlit as st
from openai import OpenAI

from core.async_utils import run_async
from core.live_session import gemini_transcribe_only
from core.models import UserProfile
from core.speaking.session import ExamSession
from core.store import FluentUpStore
from .helpers import hear_question

_OCC_LABELS = {"student": "Studying", "worker": "Working", "other": "Other"}
_OCC_DETAIL_LABELS = {
    "student": "What are you studying?",
    "worker":  "What do you do for work?",
    "other":   "Tell us more about yourself",
}

PROFILE_QUESTIONS = [
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


def render_intro() -> None:
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
                        pid = run_async(store.save_profile(profile))
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


def render_profile_question(phase_key: str, question: str, next_phase: str) -> None:
    sess: ExamSession = st.session_state.session
    secrets: dict = st.session_state.get("_secrets", {})

    st.header("Profile Setup")
    step = PROFILE_QUESTIONS.index((phase_key, question)) + 1
    st.progress(step / len(PROFILE_QUESTIONS), text=f"Question {step} of {len(PROFILE_QUESTIONS)}")
    st.markdown(f"### {question}")
    st.caption("Record your answer below. Speak naturally — we'll pick up what you say.")

    hear_question(question, key=f"profile_tts_{phase_key}")

    wav = st.audio_input("Your answer", key=f"profile_audio_{phase_key}")

    col1, col2 = st.columns(2)
    with col1:
        if wav is not None:
            if st.button("Submit Answer", type="primary", use_container_width=True):
                with st.spinner("Transcribing…"):
                    try:
                        transcript = run_async(gemini_transcribe_only(
                            api_key=secrets.get("gemini_api_key", ""),
                            wav_bytes=wav.getvalue(),
                            model=secrets.get("live_model", ""),
                        ))
                    except Exception as e:
                        st.error(f"Transcription failed: {e}")
                        return

                st.session_state[f"profile_raw_{phase_key}"] = transcript
                sess.phase = next_phase
                st.rerun()
    with col2:
        if st.button("Skip", use_container_width=True):
            st.session_state[f"profile_raw_{phase_key}"] = ""
            sess.phase = next_phase
            st.rerun()


def render_profile_confirm() -> None:
    sess: ExamSession = st.session_state.session
    store: FluentUpStore | None = st.session_state.get("store")
    secrets: dict = st.session_state.get("_secrets", {})
    current: UserProfile | None = st.session_state.get("user_profile")

    st.header("Profile Setup")
    st.progress(1.0, text="Confirm your profile")

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
                    PROFILE_QUESTIONS[0][1], q1_raw,
                    secrets.get("openrouter_base_url", ""),
                    secrets.get("openrouter_api_key", ""),
                    secrets.get("openrouter_model", ""),
                )
                if parsed.get("value"):
                    draft["name"] = str(parsed["value"])

            if q2_raw:
                parsed = _extract_profile_field(
                    PROFILE_QUESTIONS[1][1], q2_raw,
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
                    PROFILE_QUESTIONS[2][1], q3_raw,
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

    _OCC_LABELS_LOCAL = {"student": "Studying", "worker": "Working", "other": "Other"}
    name = st.text_input("Name", value=draft["name"], key="pconf_name")
    age = st.number_input("Age", min_value=10, max_value=80, value=draft["age"], key="pconf_age")

    occ_options = list(_OCC_LABELS_LOCAL.keys())
    occ_idx = occ_options.index(draft["occupation"]) if draft["occupation"] in occ_options else 0
    occupation = st.radio(
        "Currently…",
        options=occ_options,
        format_func=lambda x: _OCC_LABELS_LOCAL[x],
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
                    pid = run_async(store.save_profile(profile))
                    profile.profile_id = pid
                except Exception as e:
                    st.warning(f"Could not save to MongoDB: {e}")
            st.session_state["user_profile"] = profile
            st.session_state.pop("sidebar_profiles_cache", None)
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
