from __future__ import annotations

import difflib
import random
import re

import streamlit as st

# ── IELTS listening question types ───────────────────────────────────────────

QUESTION_TYPES: list[str] = [
    "ONE WORD ONLY",
    "ONE WORD AND/OR A NUMBER",
    "NO MORE THAN TWO WORDS",
    "NO MORE THAN TWO WORDS AND/OR A NUMBER",
    "NO MORE THAN THREE WORDS",
    "NO MORE THAN THREE WORDS AND/OR A NUMBER",
]

_MAX_SPAN: dict[str, int] = {
    "ONE WORD ONLY": 1,
    "ONE WORD AND/OR A NUMBER": 1,
    "NO MORE THAN TWO WORDS": 2,
    "NO MORE THAN TWO WORDS AND/OR A NUMBER": 2,
    "NO MORE THAN THREE WORDS": 3,
    "NO MORE THAN THREE WORDS AND/OR A NUMBER": 3,
}


_NUMBER_RE = re.compile(r'^[\d,.\-/]+$')


def _is_number_token(word: str) -> bool:
    return bool(_NUMBER_RE.match(word.strip("()[]")))


def _span_for_type(max_possible: int, q_type: str) -> int:
    """
    Pick a span length appropriate for the question type.
    - ONE WORD*        → always 1
    - NO MORE THAN TWO WORDS*  → prefer 2; fall back to 1
    - NO MORE THAN THREE WORDS* → prefer 3 or 2; rarely 1
    """
    if max_possible == 0:
        return 0
    if _MAX_SPAN[q_type] == 1:
        return 1
    if _MAX_SPAN[q_type] == 2:
        # 80 % chance span = 2, else 1
        if max_possible >= 2:
            return 2 if random.random() < 0.80 else 1
        return 1
    # max_span == 3
    if max_possible >= 3:
        # weights: span 3 → 50 %, span 2 → 35 %, span 1 → 15 %
        return random.choices([3, 2, 1], weights=[50, 35, 15])[0]
    if max_possible == 2:
        return random.choices([2, 1], weights=[70, 30])[0]
    return 1


def _select_blanks(
    words: list[str], n_blanks: int, q_type: str
) -> list[tuple[str, int, int]]:
    """
    Randomly select up to n_blanks non-adjacent spans.
    Rules per type:
      - ONE WORD*              → span always 1
      - *AND/OR A NUMBER       → prefer start positions that include a numeric token
      - NO MORE THAN TWO WORDS → prefer span = 2
      - NO MORE THAN THREE WORDS → prefer span 2-3
    Adjacency: at least one unmasked word between any two blanks.
    """
    n_words = len(words)
    wants_number = "NUMBER" in q_type
    excluded: set[int] = set()
    blanks: list[tuple[str, int, int]] = []

    for _ in range(n_blanks):
        available = [j for j in range(n_words) if j not in excluded]
        if not available:
            break

        if wants_number:
            # Prefer positions whose reachable span contains at least one numeric token
            preferred = [
                j for j in available
                if any(
                    _is_number_token(words[k])
                    for k in range(j, min(j + _MAX_SPAN[q_type], n_words))
                    if k not in excluded
                )
            ]
            candidates = preferred if preferred else available
        else:
            candidates = available

        start = random.choice(candidates)

        # Compute maximum reachable span from start
        max_possible = 0
        for j in range(start, min(start + _MAX_SPAN[q_type], n_words)):
            if j in excluded:
                break
            max_possible += 1
        if max_possible == 0:
            continue

        span = _span_for_type(max_possible, q_type)
        end  = start + span - 1
        phrase = " ".join(words[start : end + 1])
        blanks.append((phrase, start, end))

        # Mark span + immediate neighbours as off-limits
        for k in range(max(0, start - 1), min(n_words, end + 2)):
            excluded.add(k)

    blanks.sort(key=lambda b: b[1])
    return blanks


def mask_line(text: str, q_type: str | None = None) -> dict:
    """
    Return a masked-line dict:
      words    – original word list
      blanks   – [(phrase, start_idx, end_idx_inclusive), ...]
      q_type   – IELTS question type label
      max_span – max words allowed per blank answer
    """
    words   = text.split()
    n_words = len(words)

    if q_type is None:
        q_type = random.choice(QUESTION_TYPES)

    max_span = _MAX_SPAN[q_type]

    if n_words == 0:
        return {"words": words, "blanks": [], "q_type": q_type, "max_span": max_span}

    # How many blanks fit given the preferred span size?
    # Use max_span+1 as minimum "slot" (span + 1 separator word).
    slot = max_span + 1
    max_blanks = max(1, n_words // slot)
    n_blanks = random.randint(1, min(3, max_blanks))

    blanks = _select_blanks(words, n_blanks, q_type)

    return {"words": words, "blanks": blanks, "q_type": q_type, "max_span": max_span}


# ── Normalisation & scoring ──────────────────────────────────────────────────

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
            for b_idx, (phrase, *_) in enumerate(masked[i]["blanks"]):
                user_ans = answers.get(f"{i}_{b_idx}", "").strip()
                blank_results.append({
                    "expected": phrase,
                    "user":     user_ans,
                    "correct":  check_blank(user_ans, phrase),
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
