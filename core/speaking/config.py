"""Speaking-specific configuration for FluentUp."""
from __future__ import annotations

# ── Part 2 timing ─────────────────────────────────────────────────────────────

PREP_SECONDS        = 60   # preparation time before speaking
SPEAK_SECONDS       = 120  # maximum speaking time
SPEAK_WARN_SECONDS  = 30   # show "wrap up" warning when this many seconds remain
SPEAK_ALERT_SECONDS = 10   # show urgent alert when this many seconds remain

# ── Part 1 ────────────────────────────────────────────────────────────────────

PART1_QUESTIONS_PER_SESSION = 10  # questions sampled per session
QUESTION_GEN_TIMEOUT_SEC    = 45  # give up on background question generation after this many seconds
MIN_AUDIO_BYTES             = 4000  # WAV files smaller than this are treated as empty/too short

# ── Part 3 ────────────────────────────────────────────────────────────────────

PART3_QUESTIONS_PER_SESSION = 5

PART3_TOPICS = [
    "education",
    "technology and society",
    "environmental challenges",
    "cultural traditions",
    "urban development",
    "health and wellbeing",
]

# ── Cue card topic seeding ────────────────────────────────────────────────────

SEED_WORDS_MIN = 1  # minimum Vietnamese seed words per cue card
SEED_WORDS_MAX = 3  # maximum Vietnamese seed words per cue card

# ── Examiner voice & accent ───────────────────────────────────────────────────

DEFAULT_VOICE  = "Kore"
DEFAULT_ACCENT = "us"

from core.config import ENGLISH_ACCENTS, ACCENT_LABELS  # noqa: E402 – re-exported for speaking consumers

DEFAULT_FEEDBACK_LANGUAGE = "vi"

FEEDBACK_LANGUAGE_LABELS: dict[str, str] = {
    "vi": "Tiếng Việt",
    "en": "English",
}
