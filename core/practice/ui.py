"""core/practice/ui.py — Dictation, Shadowing, and Vocab Flashcard UIs."""
from __future__ import annotations

import base64
import difflib

import streamlit as st

from core.async_utils import run_async
from core.auth import current_user
from core.config import VOICES
from core.practice.generator import generate_sentences, tts_sentence, pcm_to_wav
from core.shared import get_store, get_text_provider, load_secrets

_TOPICS = ["Daily life", "Technology", "Travel", "Food", "Work", "Education", "Environment"]
_DIFFICULTIES = ["easy", "medium", "hard"]


def _score_text(reference: str, attempt: str) -> tuple[float, list[tuple[str, str]]]:
    ref_words = reference.lower().split()
    att_words = attempt.lower().split()
    matcher   = difflib.SequenceMatcher(None, ref_words, att_words)
    tagged: list[tuple[str, str]] = []
    correct = 0
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for w in ref_words[i1:i2]:
                tagged.append((w, "correct"))
                correct += 1
        elif op == "replace":
            for w in ref_words[i1:i2]:
                tagged.append((w, "wrong"))
        elif op == "delete":
            for w in ref_words[i1:i2]:
                tagged.append((w, "missing"))
    score = correct / len(ref_words) if ref_words else 1.0
    return score, tagged


def _render_diff(tagged: list[tuple[str, str]]) -> None:
    colors = {"correct": "#2ecc71", "wrong": "#e74c3c", "missing": "#e67e22"}
    parts = " ".join(
        f"<span style='color:{colors[s]};font-weight:600'>{w}</span>"
        for w, s in tagged
    )
    st.markdown(f"<p>{parts}</p>", unsafe_allow_html=True)


async def _fetch_or_generate_item(store, secrets, mode: str, topic: str, difficulty: str) -> dict | None:
    if store is not None:
        cached = await store.get_practice_items(topic=topic, difficulty=difficulty, limit=50)
        mode_items = [c for c in cached if c.get("mode") == mode]
        if mode_items:
            import random
            return random.choice(mode_items)

    provider = get_text_provider(secrets)
    sentences = await generate_sentences(provider, mode, topic, difficulty, count=5)
    if not sentences:
        return None

    import random
    text = random.choice(sentences)
    api_key = secrets.get("gemini_api_key", "")
    voice   = st.session_state.get("practice_voice", "Kore")
    pcm     = await tts_sentence(api_key, text, voice)
    wav     = pcm_to_wav(pcm)
    audio_b64 = base64.b64encode(wav).decode()

    if store is not None:
        for s in sentences:
            pcm2  = await tts_sentence(api_key, s, voice)
            wav2  = pcm_to_wav(pcm2)
            a64   = base64.b64encode(wav2).decode()
            await store.save_practice_item(
                text=s, audio_b64=a64, topic=topic, difficulty=difficulty, mode=mode
            )

    return {"text": text, "audio_b64": audio_b64, "topic": topic, "difficulty": difficulty, "mode": mode}


def render_dictation(secrets, store) -> None:
    st.markdown("## 🎙️ Dictation")
    st.caption("Nghe câu AI đọc, gõ lại từng chữ.")

    col1, col2, col3 = st.columns(3)
    with col1:
        topic = st.selectbox("Topic", _TOPICS, key="dict_topic")
    with col2:
        difficulty = st.selectbox("Difficulty", _DIFFICULTIES, key="dict_difficulty")
    with col3:
        st.selectbox("Voice", VOICES, key="practice_voice")

    if st.button("🎲 New sentence", type="primary"):
        st.session_state.pop("dict_item", None)
        st.session_state.pop("dict_submitted", None)

    if "dict_item" not in st.session_state:
        with st.spinner("Generating…"):
            item = run_async(_fetch_or_generate_item(store, secrets, "dictation", topic, difficulty))
        if item is None:
            st.error("Could not generate a practice item. Check your API keys.")
            return
        st.session_state["dict_item"] = item

    item = st.session_state["dict_item"]
    wav  = base64.b64decode(item["audio_b64"])
    st.audio(wav, format="audio/wav")

    with st.form("dict_form"):
        attempt = st.text_input("Type what you heard:")
        submitted = st.form_submit_button("Check ✓", type="primary")

    if submitted and attempt.strip():
        st.session_state["dict_submitted"] = attempt.strip()

    if "dict_submitted" in st.session_state:
        attempt_val = st.session_state["dict_submitted"]
        score, tagged = _score_text(item["text"], attempt_val)
        st.markdown(f"**Score: {score*100:.0f}%**")
        _render_diff(tagged)
        st.caption(f"Reference: _{item['text']}_")
        if st.button("Next →"):
            st.session_state.pop("dict_item", None)
            st.session_state.pop("dict_submitted", None)
            st.rerun()


def render_shadowing(secrets, store) -> None:
    st.markdown("## 🔁 Shadowing")
    st.caption("Nghe câu, sau đó nói lại — luyện phát âm và ngữ điệu.")

    col1, col2, col3 = st.columns(3)
    with col1:
        topic = st.selectbox("Topic", _TOPICS, key="shad_topic")
    with col2:
        difficulty = st.selectbox("Difficulty", _DIFFICULTIES, key="shad_difficulty")
    with col3:
        st.selectbox("Voice", VOICES, key="practice_voice")

    if st.button("🎲 New sentence", type="primary"):
        st.session_state.pop("shad_item", None)
        st.session_state.pop("shad_result", None)

    if "shad_item" not in st.session_state:
        with st.spinner("Generating…"):
            item = run_async(_fetch_or_generate_item(store, secrets, "shadowing", topic, difficulty))
        if item is None:
            st.error("Could not generate a practice item.")
            return
        st.session_state["shad_item"] = item

    item = st.session_state["shad_item"]
    wav  = base64.b64decode(item["audio_b64"])

    st.markdown("**1. Listen:**")
    st.audio(wav, format="audio/wav")

    st.markdown("**2. Record yourself saying it:**")
    recorded = st.audio_input("Your recording", key="shad_audio_input")

    if recorded is not None:
        rec_bytes = recorded.read()
        rec_hash  = hash(rec_bytes)
        if st.session_state.get("shad_last_hash") != rec_hash:
            st.session_state["shad_last_hash"] = rec_hash
            api_key = secrets.get("gemini_api_key", "")
            from core.live_session import wav_to_pcm16k
            import google.genai as genai_mod
            from google.genai import types as gtypes
            with st.spinner("Comparing…"):
                client = genai_mod.Client(api_key=api_key)
                pcm16 = wav_to_pcm16k(rec_bytes)
                audio_part = gtypes.Part.from_bytes(
                    data=pcm16,
                    mime_type="audio/pcm;rate=16000",
                )
                resp = run_async(client.aio.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[audio_part, "Transcribe this audio exactly. Return only the transcription text."],
                ))
                transcript = resp.text.strip() if resp.text else ""
            score, tagged = _score_text(item["text"], transcript)
            st.session_state["shad_result"] = {"score": score, "tagged": tagged, "transcript": transcript}

    if "shad_result" in st.session_state:
        r = st.session_state["shad_result"]
        st.markdown(f"**Score: {r['score']*100:.0f}%**")
        _render_diff(r["tagged"])
        st.caption(f"Your transcript: _{r['transcript']}_")
        st.caption(f"Reference: _{item['text']}_")
        if st.button("Next →"):
            for k in ("shad_item", "shad_result", "shad_last_hash"):
                st.session_state.pop(k, None)
            st.rerun()


def render_flashcards(store) -> None:
    st.markdown("## 🃏 Vocab Flashcards")
    st.caption("Ôn từ vựng của bạn theo kiểu flashcard.")

    user = current_user()
    user_id = str(user.get("_id", "default"))

    if store is None:
        st.warning("Không có kết nối MongoDB.")
        return

    if "flash_queue" not in st.session_state or st.session_state.get("flash_reload"):
        st.session_state.pop("flash_reload", None)
        with st.spinner("Loading vocab…"):
            all_vocab = run_async(store.get_vocab(user_id=user_id, limit=200))
        if not all_vocab:
            st.info("Chưa có từ vựng nào. Hãy luyện nói chuyện với AI để tự động thêm từ!")
            return
        import random
        queue = list(all_vocab)
        random.shuffle(queue)
        st.session_state["flash_queue"]   = queue
        st.session_state["flash_idx"]     = 0
        st.session_state["flash_flipped"] = False

    queue   = st.session_state["flash_queue"]
    idx     = st.session_state.get("flash_idx", 0)
    flipped = st.session_state.get("flash_flipped", False)

    if idx >= len(queue):
        st.success(f"🎉 Done! You reviewed {len(queue)} words.")
        if st.button("Start over"):
            st.session_state["flash_reload"] = True
            st.rerun()
        return

    card    = queue[idx]
    word    = card.get("word", "")
    senses  = card.get("senses", [])
    meaning = senses[0].get("meaning", "") if senses else card.get("meaning", "")

    st.markdown(f"**{idx+1} / {len(queue)}**")
    st.progress(idx / len(queue))

    if not flipped:
        st.markdown(
            f"<div style='border:2px solid #4a9eff;border-radius:16px;padding:48px;text-align:center;"
            f"font-size:2em;font-weight:700;margin:24px 0'>{word}</div>",
            unsafe_allow_html=True,
        )
        if st.button("Flip to see meaning", use_container_width=True):
            st.session_state["flash_flipped"] = True
            st.rerun()
    else:
        st.markdown(
            f"<div style='border:2px solid #2ecc71;border-radius:16px;padding:32px;text-align:center;"
            f"margin:24px 0'><div style='font-size:1.8em;font-weight:700;margin-bottom:12px'>{word}</div>"
            f"<div style='font-size:1.1em;opacity:0.85'>{meaning}</div></div>",
            unsafe_allow_html=True,
        )
        col_know, col_again = st.columns(2)
        with col_know:
            if st.button("✅ Got it", type="primary", use_container_width=True):
                st.session_state["flash_idx"]     = idx + 1
                st.session_state["flash_flipped"] = False
                st.rerun()
        with col_again:
            if st.button("🔁 Review again", use_container_width=True):
                queue.append(queue.pop(idx))
                st.session_state["flash_queue"]   = queue
                st.session_state["flash_flipped"] = False
                st.rerun()


def main() -> None:
    secrets = load_secrets()
    store   = get_store(secrets)

    tab_dict, tab_shad, tab_flash = st.tabs(["🎙️ Dictation", "🔁 Shadowing", "🃏 Flashcards"])

    with tab_dict:
        render_dictation(secrets, store)
    with tab_shad:
        render_shadowing(secrets, store)
    with tab_flash:
        render_flashcards(store)
