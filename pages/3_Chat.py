"""pages/3_Chat.py — Real-time audio-to-audio conversation with Gemini Live."""
from __future__ import annotations

import threading
from typing import Callable

import av
import numpy as np
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from streamlit_webrtc import WebRtcMode, RTCConfiguration, webrtc_streamer

from core.auth import is_logged_in
from core.shared import load_secrets
from core.config import OUTPUT_RATE, INPUT_RATE
from core.chat.session_manager import GeminiLiveSession

_RTC_CONFIG = RTCConfiguration(
    iceServers=[{"urls": ["stun:stun.l.google.com:19302"]}]
)

_DEFAULT_SYSTEM = (
    "You are a friendly, natural English conversation partner. "
    "Keep responses concise — 1 to 3 sentences unless asked for more. "
    "Speak clearly at a natural conversational pace."
)


# ── Audio callback factory ────────────────────────────────────────────────────

def _make_audio_callback(session: GeminiLiveSession) -> Callable:
    """
    Returns a stateful audio_frame_callback closure.

    Input path : av.AudioFrame (browser mic) → resample to 16 kHz mono PCM
                 → session.push_audio()
    Output path: session.pop_output() → PCM 24 kHz → resample to input sample
                 rate → av.AudioFrame (browser speakers)
    """
    out_buffer = bytearray()
    buf_lock   = threading.Lock()

    def callback(frame: av.AudioFrame) -> av.AudioFrame:
        nonlocal out_buffer

        # ── Input: mic → PCM 16 kHz mono ────────────────────────────────────
        arr = frame.to_ndarray()  # (channels, samples)

        if frame.format.name == "fltp":
            mono_f = arr.mean(axis=0) if arr.shape[0] > 1 else arr[0]
            mono_i = (np.clip(mono_f, -1.0, 1.0) * 32_767).astype(np.int16)
        else:
            mono_i = (arr.mean(axis=0) if arr.shape[0] > 1 else arr[0]).astype(
                np.int16
            )

        if frame.sample_rate != INPUT_RATE:
            n_out = max(1, round(len(mono_i) * INPUT_RATE / frame.sample_rate))
            mono_i = np.interp(
                np.linspace(0, len(mono_i) - 1, n_out),
                np.arange(len(mono_i)),
                mono_i.astype(np.float32),
            ).astype(np.int16)

        session.push_audio(mono_i.tobytes())

        # ── Output: drain Gemini PCM → browser frame ─────────────────────────
        with buf_lock:
            while True:
                chunk = session.pop_output()
                if chunk is None:
                    break
                out_buffer.extend(chunk)

            # How many 24 kHz samples fill this frame's duration?
            frame_dur     = frame.samples / frame.sample_rate
            n_out_samples = int(frame_dur * OUTPUT_RATE)
            n_out_bytes   = n_out_samples * 2  # int16

            if len(out_buffer) >= n_out_bytes:
                pcm_out = bytes(out_buffer[:n_out_bytes])
                del out_buffer[:n_out_bytes]
            else:
                pcm_out = bytes(out_buffer) + b"\x00" * (n_out_bytes - len(out_buffer))
                out_buffer.clear()

        out_24k = np.frombuffer(pcm_out, dtype=np.int16).astype(np.float32)

        # Resample 24 kHz → frame.sample_rate for WebRTC compatibility
        if frame.sample_rate != OUTPUT_RATE:
            n_resampled = max(1, round(len(out_24k) * frame.sample_rate / OUTPUT_RATE))
            out_24k = np.interp(
                np.linspace(0, len(out_24k) - 1, n_resampled),
                np.arange(len(out_24k)),
                out_24k,
            )

        out_arr   = out_24k.astype(np.int16).reshape(1, -1)
        out_frame = av.AudioFrame.from_ndarray(out_arr, format="s16", layout="mono")
        out_frame.sample_rate = frame.sample_rate
        return out_frame

    return callback


# ── Session management ────────────────────────────────────────────────────────

def _reset_session() -> None:
    old: GeminiLiveSession | None = st.session_state.pop("chat_session", None)
    if old is not None:
        old.stop()
    st.session_state.pop("chat_callback", None)
    st.session_state["chat_session_id"] = (
        st.session_state.get("chat_session_id", 0) + 1
    )


def _ensure_session(api_key: str, model: str, system_prompt: str) -> GeminiLiveSession:
    session: GeminiLiveSession | None = st.session_state.get("chat_session")
    if session is None or not session.is_alive:
        if session is not None:
            session.stop()
        session = GeminiLiveSession(api_key, model, system_prompt)
        st.session_state["chat_session"] = session
    return session


# ── Main page ─────────────────────────────────────────────────────────────────

def main() -> None:
    st.title("Live Chat")
    st.caption("Real-time audio conversation with Gemini Live")

    secrets = load_secrets()
    api_key = secrets["gemini_api_key"]
    model   = secrets["live_model"]

    if not api_key:
        st.error("GEMINI_API_KEY not configured in secrets.toml.")
        return

    # ── System prompt ─────────────────────────────────────────────────────────
    with st.expander("System prompt", expanded=False):
        system_prompt: str = st.text_area(
            "system_prompt_area",
            value=st.session_state.get("chat_system_prompt", _DEFAULT_SYSTEM),
            height=120,
            label_visibility="collapsed",
            key="chat_system_prompt",
        )

    # ── Controls ──────────────────────────────────────────────────────────────
    col_btn, col_status = st.columns([2, 8])
    with col_btn:
        if st.button("New session", type="secondary"):
            _reset_session()
            st.rerun()

    # ── Session lifecycle ─────────────────────────────────────────────────────
    session = _ensure_session(api_key, model, system_prompt)

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
        st.success("Connected — press **Start** below, then speak")

    # ── WebRTC streamer ───────────────────────────────────────────────────────
    # Cache the callback so it is not recreated on every rerun (the closure
    # holds the output PCM buffer; recreating it would lose buffered audio).
    session_id = st.session_state.get("chat_session_id", 0)
    if "chat_callback" not in st.session_state:
        st.session_state["chat_callback"] = _make_audio_callback(session)

    webrtc_streamer(
        key=f"live-chat-{session_id}",
        mode=WebRtcMode.SENDRECV,
        rtc_configuration=_RTC_CONFIG,
        audio_frame_callback=st.session_state["chat_callback"],
        media_stream_constraints={"audio": True, "video": False},
        async_processing=True,
    )

    # ── Transcript ────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Transcript")

    messages = session.get_messages()
    if not messages:
        st.caption("Your conversation will appear here once you start speaking.")
    else:
        for msg in messages:
            with st.chat_message(msg.role):
                st.write(msg.text)

    # Refresh transcript every 1.5 s while the page is open
    st_autorefresh(interval=1500, key="chat_autorefresh")


if not is_logged_in():
    st.error("Bạn chưa đăng nhập. Vui lòng quay lại trang chủ để đăng nhập.")
    if st.button("Về trang chủ"):
        st.switch_page("pages/0_Home.py")
else:
    main()
