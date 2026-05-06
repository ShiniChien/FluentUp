"""pages/3_Chat.py — Audio-to-audio conversation with Gemini Live (push-to-talk)."""
from __future__ import annotations

import streamlit as st

from core.auth import is_logged_in
from core.shared import load_secrets
from core.async_utils import run_async
from core.live_session import gemini_live_once, pcm_to_wav
from core.config import OUTPUT_RATE

_DEFAULT_SYSTEM = (
    "You are a friendly, natural English conversation partner. "
    "Keep responses concise — 1 to 3 sentences unless asked for more. "
    "Speak clearly at a natural conversational pace."
)

_MAX_HISTORY_TURNS = 10  # turns (user+assistant pairs) included in context


def _build_system_prompt(base: str, messages: list[dict]) -> str:
    """Prepend recent conversation history to the system prompt."""
    if not messages:
        return base
    lines = []
    for m in messages[-_MAX_HISTORY_TURNS * 2 :]:
        role = "User" if m["role"] == "user" else "Assistant"
        lines.append(f"{role}: {m['text']}")
    history = "\n".join(lines)
    return f"{base}\n\nConversation so far:\n{history}"


def main() -> None:
    st.title("Live Chat")
    st.caption("Push-to-talk conversation with Gemini Live")

    secrets = load_secrets()
    api_key = secrets["gemini_api_key"]
    model   = secrets["live_model"]

    if not api_key:
        st.error("GEMINI_API_KEY not configured in secrets.toml.")
        return

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
    col_clear, _ = st.columns([2, 8])
    with col_clear:
        if st.button("Clear chat", type="secondary"):
            st.session_state["chat_messages"] = []
            st.session_state.pop("chat_last_hash", None)
            st.rerun()

    # ── Transcript ────────────────────────────────────────────────────────────
    messages: list[dict] = st.session_state.setdefault("chat_messages", [])

    if not messages:
        st.info("Record your first message below to start the conversation.")
    else:
        for i, msg in enumerate(messages):
            with st.chat_message(msg["role"]):
                st.write(msg["text"])
                if msg.get("audio"):
                    # Autoplay only the very last assistant message
                    is_last = i == len(messages) - 1
                    autoplay = is_last and st.session_state.get("chat_autoplay_last", False)
                    st.audio(msg["audio"], format="audio/wav", autoplay=autoplay)
        # Reset autoplay flag after first render that triggered it
        st.session_state["chat_autoplay_last"] = False

    # ── Audio input ───────────────────────────────────────────────────────────
    st.divider()
    audio_file = st.audio_input("Your turn — record your message", key="chat_audio_input")

    if audio_file is not None:
        wav_bytes = audio_file.read()
        audio_hash = hash(wav_bytes)

        # Deduplicate: only process if this is a new recording
        if st.session_state.get("chat_last_hash") != audio_hash:
            st.session_state["chat_last_hash"] = audio_hash

            effective_prompt = _build_system_prompt(system_prompt, messages)

            with st.spinner("Gemini is responding…"):
                try:
                    user_tr, assistant_tr, pcm = run_async(
                        gemini_live_once(
                            api_key=api_key,
                            system_prompt=effective_prompt,
                            wav_bytes=wav_bytes,
                            model=model,
                        )
                    )
                except Exception as exc:
                    st.error(f"Error: {exc}")
                    return

            wav_response = pcm_to_wav(pcm, OUTPUT_RATE) if pcm else b""

            messages.append({
                "role": "user",
                "text": user_tr or "(no transcript)",
                "audio": None,
            })
            messages.append({
                "role": "assistant",
                "text": assistant_tr or "",
                "audio": wav_response if wav_response else None,
            })
            st.session_state["chat_autoplay_last"] = True
            st.rerun()


if not is_logged_in():
    st.error("Bạn chưa đăng nhập. Vui lòng quay lại trang chủ để đăng nhập.")
    if st.button("Về trang chủ"):
        st.switch_page("pages/0_Home.py")
else:
    main()
