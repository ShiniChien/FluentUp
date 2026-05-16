"""pages/3_Chat.py — Live Chat: persona selection, memory injection, tool dispatch."""
from __future__ import annotations

import streamlit as st

from core.async_utils import run_async
from core.auth import current_user, is_logged_in
from core.chat.personas import PERSONAS, PERSONA_BY_KEY, build_system_prompt
from core.chat.session_manager import GeminiLiveSession
from core.chat.tools import LIVE_TOOLS
from core.config import VOICES
from core.shared import get_store, load_secrets


# ── Session helpers ───────────────────────────────────────────────────────────

def _reset_session() -> None:
    old: GeminiLiveSession | None = st.session_state.pop("chat_session", None)
    if old is not None:
        old.stop()
    for key in ("chat_last_hash", "chat_persona_key", "chat_system_prompt"):
        st.session_state.pop(key, None)


def _ensure_session(api_key: str, model: str, system_prompt: str, voice: str) -> GeminiLiveSession:
    session: GeminiLiveSession | None = st.session_state.get("chat_session")
    if session is None or not session.is_alive:
        if session is not None:
            session.stop()
        session = GeminiLiveSession(api_key, model, system_prompt, voice, tools=LIVE_TOOLS)
        st.session_state["chat_session"] = session
    return session


def _dispatch_tool_calls(calls: list[dict], user_id: str, store) -> None:
    if not calls or store is None:
        return
    for call in calls:
        name = call.get("name")
        args = call.get("args", {})
        try:
            if name == "add_vocabulary":
                word = args.get("word", "").strip()
                definition = args.get("definition", "").strip()
                example = args.get("example_sentence", "").strip()
                meaning = definition + (f" | e.g. {example}" if example else "")
                if word and definition:
                    run_async(store.save_vocab(word=word, meaning=meaning, user_id=user_id))
                    st.toast(f"📝 Saved vocab: **{word}**", icon="✅")
            elif name == "save_memory":
                fact = args.get("fact", "").strip()
                if fact:
                    run_async(store.save_user_memory(user_id=user_id, fact=fact))
                    st.toast("🧠 Memory saved", icon="✅")
        except Exception:
            pass


# ── Persona selector ──────────────────────────────────────────────────────────

def _render_persona_selector() -> None:
    st.markdown("## 👋 Choose your AI companion")
    st.caption("Your partner for this conversation. Start a new session anytime to switch.")
    st.markdown("")

    cols = st.columns(len(PERSONAS))
    for col, persona in zip(cols, PERSONAS):
        with col:
            if st.button(
                f"{persona.emoji} **{persona.display_name}**\n\n{persona.tagline}",
                use_container_width=True,
                key=f"persona_{persona.key}",
            ):
                st.session_state["chat_persona_key"] = persona.key
                st.rerun()


# ── Main page ─────────────────────────────────────────────────────────────────

def main() -> None:
    secrets = load_secrets()
    api_key = secrets.get("gemini_api_key", "")
    model   = secrets.get("live_model", "")
    store   = get_store(secrets)
    user    = current_user()
    user_id = str(user.get("_id", "default"))
    user_name = user.get("name") or user.get("username", "")

    if not api_key:
        st.error("GEMINI_API_KEY not configured in secrets.toml.")
        return

    # Persona selection gate
    if "chat_persona_key" not in st.session_state:
        _render_persona_selector()
        return

    persona_key = st.session_state["chat_persona_key"]
    persona = PERSONA_BY_KEY.get(persona_key, PERSONAS[0])

    # Build system prompt (persona + memory) — once per session
    if "chat_system_prompt" not in st.session_state:
        memory_facts: list[str] = []
        if store is not None:
            try:
                mem_docs = run_async(store.list_user_memory(user_id))
                memory_facts = [d["fact"] for d in mem_docs]
            except Exception:
                pass
        st.session_state["chat_system_prompt"] = build_system_prompt(persona, user_name, memory_facts)

    system_prompt: str = st.session_state["chat_system_prompt"]

    # Header
    col_title, col_change = st.columns([7, 1])
    with col_title:
        st.markdown(f"## {persona.emoji} Chatting with {persona.display_name}")
        st.caption(persona.tagline)
    with col_change:
        if st.button("Change", use_container_width=True):
            _reset_session()
            st.rerun()

    # Sidebar: voice selector
    prev_voice = st.session_state.get("chat_voice", "Kore")
    voice: str = st.sidebar.selectbox(
        "Voice", options=VOICES,
        index=VOICES.index(prev_voice) if prev_voice in VOICES else 0,
        key="chat_voice",
    )
    if voice != prev_voice:
        _reset_session()
        st.rerun()

    # Session lifecycle
    session = _ensure_session(api_key, model, system_prompt, voice)

    if session.error:
        st.error(f"Connection error: {session.error}")
        if st.button("Retry"):
            _reset_session()
            st.rerun()
        return

    if not session.is_ready:
        with st.spinner(f"Connecting to {persona.display_name}…"):
            ready = session.wait_ready(timeout=10.0)
        if not ready:
            st.error("Connection timed out. Check your API key and network.")
            _reset_session()
            return
        st.rerun()

    st.success(f"Connected — speaking with {persona.display_name}")

    # Transcript
    messages = session.get_messages()
    if not messages:
        st.info(f"Say hello to {persona.display_name}! Record your first message below.")
    else:
        for i, msg in enumerate(messages):
            with st.chat_message(msg.role):
                st.write(msg.text)
                wav = st.session_state.get(f"chat_wav_{i}")
                if wav:
                    is_last = i == len(messages) - 1
                    autoplay = is_last and st.session_state.pop("chat_autoplay_last", False)
                    st.audio(wav, format="audio/wav", autoplay=autoplay)

    # Audio input
    st.divider()
    audio_file = st.audio_input("Your turn — record your message", key="chat_audio_input")

    if audio_file is not None:
        wav_bytes  = audio_file.read()
        audio_hash = hash(wav_bytes)

        if st.session_state.get("chat_last_hash") != audio_hash:
            st.session_state["chat_last_hash"] = audio_hash

            with st.spinner(f"{persona.display_name} is responding…"):
                try:
                    session.send_turn_wav(wav_bytes)
                    user_tr, asst_tr, response_wav = session.wait_turn_complete(timeout=30.0)
                except Exception as exc:
                    st.error(f"Error: {exc}")
                    return

            tool_calls = session.drain_tool_calls()
            _dispatch_tool_calls(tool_calls, user_id, store)

            msgs_after = session.get_messages()
            n = len(msgs_after)
            if n >= 2:
                st.session_state[f"chat_wav_{n - 2}"] = wav_bytes
                st.session_state[f"chat_wav_{n - 1}"] = response_wav

            st.session_state["chat_autoplay_last"] = True
            st.rerun()


if not is_logged_in():
    st.error("Bạn chưa đăng nhập. Vui lòng quay lại trang chủ để đăng nhập.")
    if st.button("Về trang chủ"):
        st.switch_page("pages/0_Home.py")
else:
    main()
