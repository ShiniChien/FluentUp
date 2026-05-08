# tests/test_vocab_quiz.py
import random
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_WORDS = [
    {"word": "happy", "notes": "vui vẻ"},
    {"word": "sad", "notes": "buồn"},
    {"word": "angry", "notes": "tức giận"},
    {"word": "excited", "notes": "hào hứng"},
    {"word": "tired", "notes": "mệt mỏi"},
]

GLOBAL_POOL = SAMPLE_WORDS + [
    {"word": "beautiful", "notes": "đẹp"},
    {"word": "ugly", "notes": "xấu"},
    {"word": "fast", "notes": "nhanh"},
    {"word": "slow", "notes": "chậm"},
]
