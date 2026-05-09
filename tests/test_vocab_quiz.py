# tests/test_vocab_quiz.py
import random
import datetime
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

from scripts.vocab_quiz import build_question


def test_short_answer_en_to_vi():
    random.seed(0)
    entry = {"word": "happy", "notes": "vui vẻ"}
    q = build_question(entry, GLOBAL_POOL, force_type="en_vi")
    assert q["type"] == "SHORT_ANSWER"
    assert q["question_text"] == "happy"
    assert q["correct_answer"] == "vui vẻ"
    assert q["choices"] is None


def test_short_answer_vi_to_en():
    entry = {"word": "happy", "notes": "vui vẻ"}
    q = build_question(entry, GLOBAL_POOL, force_type="vi_en")
    assert q["type"] == "SHORT_ANSWER"
    assert q["question_text"] == "vui vẻ"
    assert q["correct_answer"] == "happy"
    assert q["choices"] is None


def test_multiple_choice_has_4_choices():
    random.seed(42)
    entry = {"word": "happy", "notes": "vui vẻ"}
    q = build_question(entry, GLOBAL_POOL, force_type="multiple_choice")
    assert q["type"] == "MULTIPLE_CHOICE"
    assert len(q["choices"]) == 4
    assert q["correct_answer"] in q["choices"]


def test_multiple_choice_correct_not_in_distractors():
    random.seed(42)
    entry = {"word": "happy", "notes": "vui vẻ"}
    q = build_question(entry, GLOBAL_POOL, force_type="multiple_choice")
    correct = q["correct_answer"]
    others = [c for c in q["choices"] if c != correct]
    assert correct not in others


def test_multiple_choice_small_pool():
    """Pool nhỏ hơn 3 distractors vẫn hoạt động."""
    small_pool = [
        {"word": "happy", "notes": "vui vẻ"},
        {"word": "sad", "notes": "buồn"},
    ]
    entry = {"word": "happy", "notes": "vui vẻ"}
    q = build_question(entry, small_pool, force_type="multiple_choice")
    assert q["type"] == "MULTIPLE_CHOICE"
    assert len(q["choices"]) >= 1
    assert q["correct_answer"] in q["choices"]


from unittest.mock import patch, MagicMock
from scripts.vocab_quiz import send_discord


def test_send_discord_posts_correct_payload():
    with patch("scripts.vocab_quiz.requests_lib") as mock_requests:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_requests.post.return_value = mock_resp

        send_discord("https://discord.webhook/test", "Hello world")

        mock_requests.post.assert_called_once_with(
            "https://discord.webhook/test",
            json={"content": "Hello world"},
            timeout=10,
        )
        mock_resp.raise_for_status.assert_called_once()


from scripts.vocab_quiz import generate_quiz_html


def test_generate_quiz_html_contains_username():
    questions = [
        {"type": "SHORT_ANSWER", "question_text": "happy", "correct_answer": "vui vẻ", "choices": None},
    ]
    html = generate_quiz_html("shinichien", questions, "2026-05-09_07-00")
    assert "shinichien" in html


def test_generate_quiz_html_short_answer_has_input():
    questions = [
        {"type": "SHORT_ANSWER", "question_text": "happy", "correct_answer": "vui vẻ", "choices": None},
    ]
    html = generate_quiz_html("u", questions, "2026-05-09_07-00")
    assert 'type="text"' in html
    assert "happy" in html


def test_generate_quiz_html_multiple_choice_has_radio():
    questions = [
        {"type": "MULTIPLE_CHOICE", "question_text": "sad", "correct_answer": "buồn",
         "choices": ["buồn", "vui vẻ", "tức giận", "hào hứng"]},
    ]
    html = generate_quiz_html("u", questions, "2026-05-09_07-00")
    assert 'type="radio"' in html
    assert "buồn" in html
    assert "vui vẻ" in html


def test_generate_quiz_html_correct_answer_embedded():
    questions = [
        {"type": "SHORT_ANSWER", "question_text": "happy", "correct_answer": "vui vẻ", "choices": None},
    ]
    html = generate_quiz_html("u", questions, "2026-05-09_07-00")
    assert "vui vẻ" in html


def test_generate_quiz_html_has_submit_button():
    questions = [
        {"type": "SHORT_ANSWER", "question_text": "happy", "correct_answer": "vui vẻ", "choices": None},
    ]
    html = generate_quiz_html("u", questions, "2026-05-09_07-00")
    assert "submit" in html.lower() or "nộp" in html.lower()


import os
import tempfile
from scripts.vocab_quiz import cleanup_old_quiz_files


def test_cleanup_removes_old_files():
    with tempfile.TemporaryDirectory() as d:
        old_date = (datetime.date.today() - datetime.timedelta(days=4)).isoformat()
        old_file = os.path.join(d, f"user_{old_date}_07-00.html")
        with open(old_file, "w") as f:
            f.write("old")
        cleanup_old_quiz_files(d, days=3)
        assert not os.path.exists(old_file)


def test_cleanup_keeps_recent_files():
    with tempfile.TemporaryDirectory() as d:
        today = datetime.date.today().isoformat()
        new_file = os.path.join(d, f"user_{today}_07-00.html")
        with open(new_file, "w") as f:
            f.write("new")
        cleanup_old_quiz_files(d, days=3)
        assert os.path.exists(new_file)


def test_cleanup_ignores_non_matching_files():
    with tempfile.TemporaryDirectory() as d:
        other = os.path.join(d, "index.html")
        with open(other, "w") as f:
            f.write("index")
        cleanup_old_quiz_files(d, days=3)
        assert os.path.exists(other)
