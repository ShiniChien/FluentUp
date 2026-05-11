from __future__ import annotations

import string


def _normalize(text: str) -> str:
    text = text.lower().strip()
    return text.translate(str.maketrans("", "", string.punctuation))


def score_tfng(questions: list[dict], answers: dict) -> list[dict]:
    results = []
    for i, q in enumerate(questions):
        user    = answers.get(f"tfng_{i}", "").strip()
        correct = q["answer"]
        results.append({"correct": user == correct, "expected": correct, "user": user})
    return results


def score_headings(questions: list[dict], answers: dict) -> list[dict]:
    results = []
    for i, q in enumerate(questions):
        user    = answers.get(f"headings_{i}", "").strip()
        correct = q["correct_heading"]
        results.append({"correct": user == correct, "expected": correct, "user": user})
    return results


def score_fill_blank(questions: list[dict], answers: dict) -> list[dict]:
    results = []
    for i, q in enumerate(questions):
        user    = _normalize(answers.get(f"fill_blank_{i}", ""))
        correct = _normalize(q["answer"])
        results.append({"correct": user == correct, "expected": q["answer"], "user": answers.get(f"fill_blank_{i}", "")})
    return results


def score_mcq(questions: list[dict], answers: dict) -> list[dict]:
    results = []
    for i, q in enumerate(questions):
        user    = answers.get(f"mcq_{i}", "").strip().upper()
        correct = q["answer"].strip().upper()
        results.append({"correct": user == correct, "expected": correct, "user": user})
    return results


def compute_band(raw: int, total: int = 20) -> float:
    if total == 0:
        return 0.0
    band = raw / total * 9
    return min(9.0, round(band * 2) / 2)


def score_all(questions: dict, answers: dict) -> dict:
    tfng_results     = score_tfng(questions.get("tfng", []), answers)
    headings_results = score_headings(questions.get("headings", []), answers)
    fill_results     = score_fill_blank(questions.get("fill_blank", []), answers)
    mcq_results      = score_mcq(questions.get("mcq", []), answers)

    all_results = tfng_results + headings_results + fill_results + mcq_results
    raw   = sum(1 for r in all_results if r["correct"])
    total = len(all_results)
    band  = compute_band(raw, total)
    return {
        "raw":      raw,
        "total":    total,
        "band":     band,
        "tfng":     tfng_results,
        "headings": headings_results,
        "fill_blank": fill_results,
        "mcq":      mcq_results,
    }
