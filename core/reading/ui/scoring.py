from __future__ import annotations

import string


def _normalize(text: str) -> str:
    text = text.lower().strip()
    return text.translate(str.maketrans("", "", string.punctuation))


def score_fill_blank(questions: list[dict], answers: dict) -> list[dict]:
    results = []
    for i, q in enumerate(questions):
        user    = _normalize(answers.get(f"fill_{i}", ""))
        correct = _normalize(q["answer"])
        results.append({
            "correct":  user == correct,
            "expected": q["answer"],
            "user":     answers.get(f"fill_{i}", ""),
        })
    return results


def compute_band(raw: int, total: int) -> float:
    if total == 0:
        return 0.0
    return min(9.0, round(raw / total * 9 * 2) / 2)


def score_all(questions: dict, answers: dict) -> dict:
    fill_results = score_fill_blank(questions.get("questions", []), answers)
    raw   = sum(1 for r in fill_results if r["correct"])
    total = len(fill_results)
    return {
        "raw":        raw,
        "total":      total,
        "band":       compute_band(raw, total),
        "fill_blank": fill_results,
    }
