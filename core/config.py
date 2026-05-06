"""Central config for FluentUp — shared constants used by both Speaking and Listening."""
from __future__ import annotations

# ── Gemini Live ───────────────────────────────────────────────────────────────

LIVE_MODEL  = "models/gemini-3.1-flash-live-preview"
INPUT_RATE  = 16000  # Hz — Gemini Live expects 16 kHz PCM input
OUTPUT_RATE = 24000  # Hz — Gemini Live audio output is 24 kHz PCM
CHUNK_MS    = 100    # milliseconds per audio chunk sent to Live API

# ── English accents (used by both Speaking examiner TTS and Listening dialogue) ─

ENGLISH_ACCENTS: dict[str, str] = {
    "us": (
        "You are a professional IELTS Speaking examiner with a clear, neutral American English accent. "
        "Your delivery is calm, professional, and encouraging. "
        "Speak at a natural conversational pace with typical American vowels and rhotic 'r'. "
        "Always read the given text exactly as written — do not add, omit, or rephrase anything."
    ),
    "uk": (
        "You are a professional IELTS Speaking examiner with a standard British English (Received Pronunciation) accent. "
        "Your delivery is measured, clear, and authoritative. "
        "Use non-rhotic 'r', long vowels, and British intonation patterns. "
        "Always read the given text exactly as written — do not add, omit, or rephrase anything."
    ),
    "in": (
        "You are a professional IELTS Speaking examiner with an educated Indian English accent. "
        "Your delivery is clear, polite, and professional with characteristic Indian English rhythm and stress patterns. "
        "Maintain consistent pace and clarity. "
        "Always read the given text exactly as written — do not add, omit, or rephrase anything."
    ),
    "au": (
        "You are a professional IELTS Speaking examiner with a standard Australian English accent. "
        "Your delivery is friendly, clear, and professional with Australian vowel qualities. "
        "Always read the given text exactly as written — do not add, omit, or rephrase anything."
    ),
}

ACCENT_LABELS: dict[str, str] = {
    "us": "American (US)",
    "uk": "British (UK)",
    "in": "Indian",
    "au": "Australian",
}

# ── TTS voices (used by both Speaking examiner TTS and Listening dialogue) ────

VOICES: list[str] = [
    "Zephyr", "Charon", "Fenrir", "Orus", "Callirrhoe", "Enceladus",
    "Umbriel", "Despina", "Algenib", "Laomedeia", "Alnilam", "Gacrux",
    "Achird", "Vindemiatrix", "Sadaltager", "Puck", "Kore", "Leda",
    "Aoede", "Autonoe", "Iapetus", "Algieba", "Erinome", "Rasalgethi",
    "Achernar", "Schedar", "Pulcherrima", "Zubenelgenubi", "Sadachbia", "Sulafat",
]
