"""pages/3_Chat.py — Audio-to-audio conversation with Gemini Live (push-to-talk)."""
from __future__ import annotations

import streamlit as st

from core.auth import is_logged_in
from core.shared import load_secrets
from core.config import VOICES
from core.chat.session_manager import GeminiLiveSession

_DEFAULT_SYSTEM = (
    "You are a friendly, natural English conversation partner. "
    "Keep responses concise — 1 to 3 sentences unless asked for more. "
    "Speak clearly at a natural conversational pace."
)


# ── Session management ────────────────────────────────────────────────────────

def _reset_session() -> None:
    old: GeminiLiveSession | None = st.session_state.pop("chat_session", None)
    if old is not None:
        old.stop()
    st.session_state.pop("chat_last_hash", None)


def _ensure_session(api_key: str, model: str, system_prompt: str, voice: str) -> GeminiLiveSession:
    session: GeminiLiveSession | None = st.session_state.get("chat_session")
    if session is None or not session.is_alive:
        if session is not None:
            session.stop()
        session = GeminiLiveSession(api_key, model, system_prompt, voice)
        st.session_state["chat_session"] = session
    return session


# ── Main page ─────────────────────────────────────────────────────────────────

def main() -> None:
    st.title("Live Chat")
    st.caption("Push-to-talk conversation · single persistent socket with Gemini Live")

    secrets = load_secrets()
    api_key = secrets["gemini_api_key"]
    model   = secrets["live_model"]

    if not api_key:
        st.error("GEMINI_API_KEY not configured in secrets.toml.")
        return

    # ── Sidebar: voice selector ───────────────────────────────────────────────
    prev_voice = st.session_state.get("chat_voice", "Kore")
    voice: str = st.sidebar.selectbox(
        "Gemini voice",
        options=VOICES,
        index=VOICES.index(prev_voice) if prev_voice in VOICES else 0,
        key="chat_voice",
    )
    if voice != prev_voice:
        _reset_session()
        st.rerun()

    # ── System prompt ─────────────────────────────────────────────────────────
    with st.expander("System prompt", expanded=False):
        system_prompt: str = st.text_area(
            "sp",
            value=st.session_state.get("chat_system_prompt", _DEFAULT_SYSTEM),
            height=120,
            label_visibility="collapsed",
            key="chat_system_prompt",
        )

    # ── Controls ──────────────────────────────────────────────────────────────
    col_clear, col_status = st.columns([2, 8])
    with col_clear:
        if st.button("New session", type="secondary"):
            _reset_session()
            st.rerun()

    # ── Session lifecycle ─────────────────────────────────────────────────────
    session = _ensure_session(api_key, model, system_prompt, voice)

    if session.error:
        with col_status:
            st.error(f"Connection error: {session.error}")
        if st.button("Retry"):
            _reset_session()
            st.rerun()
        return

    if not session.is_ready:
        with col_status:
            with st.spinner("Connecting to Gemini Live…"):
                ready = session.wait_ready(timeout=10.0)
        if not ready:
            st.error("Connection timed out. Check your API key and network.")
            _reset_session()
            return
        st.rerun()

    with col_status:
        st.success("Connected — 1 socket, Gemini remembers the full conversation")

    # ── Transcript ────────────────────────────────────────────────────────────
    messages = session.get_messages()

    if not messages:
        st.info("Record your first message below to start the conversation.")
    else:
        for i, msg in enumerate(messages):
            with st.chat_message(msg.role):
                st.write(msg.text)
                wav = st.session_state.get(f"chat_wav_{i}")
                if wav:
                    is_last = i == len(messages) - 1
                    autoplay = is_last and st.session_state.pop("chat_autoplay_last", False)
                    st.audio(wav, format="audio/wav", autoplay=autoplay)

    # ── Audio input ───────────────────────────────────────────────────────────
    st.divider()
    audio_file = st.audio_input("Your turn — record your message", key="chat_audio_input")

    if audio_file is not None:
        wav_bytes  = audio_file.read()
        audio_hash = hash(wav_bytes)

        if st.session_state.get("chat_last_hash") != audio_hash:
            st.session_state["chat_last_hash"] = audio_hash

            with st.spinner("Gemini is responding…"):
                try:
                    session.send_turn_wav(wav_bytes)
                    user_tr, asst_tr, response_wav = session.wait_turn_complete(timeout=30.0)
                except Exception as exc:
                    st.error(f"Error: {exc}")
                    return

            # Store audio keyed by message index (get_messages returns after turn_complete)
            msgs_after = session.get_messages()
            n = len(msgs_after)
            # user message is at n-2, assistant at n-1
            if n >= 2:
                st.session_state[f"chat_wav_{n - 2}"] = wav_bytes       # user audio
                st.session_state[f"chat_wav_{n - 1}"] = response_wav    # assistant audio

            st.session_state["chat_autoplay_last"] = True
            st.rerun()


if not is_logged_in():
    st.error("Bạn chưa đăng nhập. Vui lòng quay lại trang chủ để đăng nhập.")
    if st.button("Về trang chủ"):
        st.switch_page("pages/0_Home.py")
else:
    main()
