from __future__ import annotations

import difflib
import random
import re

import streamlit as st


def mask_line(text: str) -> dict:
    """Return {display: str, blanks: [(original_word, word_index)]}."""
    words = text.split()
    n = random.randint(1, min(3, max(1, len(words) - 1)))
    indices = sorted(random.sample(range(len(words)), n))
    blanks = [(words[i], i) for i in indices]
    masked = words.copy()
    for _, i in blanks:
        masked[i] = "___"
    return {"display": " ".join(masked), "blanks": blanks}


def _normalize(s: str) -> str:
    return re.sub(r"[^\w\s]", "", s.lower()).strip()


def check_blank(user: str, expected: str) -> bool:
    return _normalize(user) == _normalize(expected)


def word_accuracy(user: str, expected: str) -> tuple[int, int]:
    """Return (correct_words, total_expected_words) using difflib matching."""
    u = _normalize(user).split()
    e = _normalize(expected).split()
    matcher = difflib.SequenceMatcher(None, e, u)
    correct = sum(n for _, _, n in matcher.get_matching_blocks())
    return correct, len(e)


def score_answers() -> list[dict]:
    dialogue = st.session_state["echo_dialogue"]
    masked   = st.session_state["echo_masked"]
    answers  = st.session_state["echo_answers"]
    mode     = st.session_state["echo_mode"]
    results  = []

    for i, line in enumerate(dialogue):
        if mode == "fill_blank":
            blank_results = []
            for b_idx, (word, _) in enumerate(masked[i]["blanks"]):
                user_ans = answers.get(f"{i}_{b_idx}", "").strip()
                blank_results.append({
                    "expected": word,
                    "user":     user_ans,
                    "correct":  check_blank(user_ans, word),
                })
            results.append({"line": i, "mode": "fill_blank", "blanks": blank_results})
        else:
            user_ans = answers.get(str(i), "").strip()
            correct, total = word_accuracy(user_ans, line["text"])
            results.append({
                "line":     i,
                "mode":     "transcription",
                "user":     user_ans,
                "expected": line["text"],
                "correct":  correct,
                "total":    total,
            })
    return results
