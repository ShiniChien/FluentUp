# scripts/vocab_quiz.py
from __future__ import annotations

import random
from typing import Any


_QUESTION_TYPES = ["en_vi", "vi_en", "multiple_choice"]
_WEIGHTS = [6, 1, 3]


def build_question(
    entry: dict[str, Any],
    global_pool: list[dict[str, Any]],
    force_type: str | None = None,
) -> dict[str, Any]:
    """Build one quiz question dict from a vocabulary entry."""
    q_type = force_type or random.choices(_QUESTION_TYPES, weights=_WEIGHTS, k=1)[0]

    if q_type == "en_vi":
        return {
            "type": "SHORT_ANSWER",
            "question_text": entry["word"],
            "correct_answer": entry["notes"],
            "choices": None,
        }

    if q_type == "vi_en":
        return {
            "type": "SHORT_ANSWER",
            "question_text": entry["notes"],
            "correct_answer": entry["word"],
            "choices": None,
        }

    # multiple_choice — random direction 50-50
    if random.random() < 0.5:
        question_text = entry["word"]
        correct_answer = entry["notes"]
        distractor_pool = [e["notes"] for e in global_pool if e["notes"] != correct_answer]
    else:
        question_text = entry["notes"]
        correct_answer = entry["word"]
        distractor_pool = [e["word"] for e in global_pool if e["word"] != correct_answer]

    distractors = random.sample(distractor_pool, min(3, len(distractor_pool)))
    choices = [correct_answer] + distractors
    random.shuffle(choices)

    return {
        "type": "MULTIPLE_CHOICE",
        "question_text": question_text,
        "correct_answer": correct_answer,
        "choices": choices,
    }
