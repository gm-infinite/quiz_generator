"""Deterministic scoring. No LLM calls in this file.

Kept separate from agents so the math is easy to test and impossible to
hallucinate.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable


def grade_answers(
    questions: list[dict],
    answers: list[str],
) -> list[dict]:
    """Return per-question grading records: id, topic, correct, given, expected."""
    if len(questions) != len(answers):
        raise ValueError(
            f"questions ({len(questions)}) and answers ({len(answers)}) length mismatch"
        )
    out: list[dict] = []
    for q, a in zip(questions, answers):
        correct = (a or "").strip() == q["correct_answer"].strip()
        out.append(
            {
                "question_id": q["id"],
                "topic": q["topic"],
                "correct": correct,
                "student_answer": a,
                "correct_answer": q["correct_answer"],
            }
        )
    return out


def overall_accuracy(graded: Iterable[dict]) -> float:
    graded = list(graded)
    if not graded:
        return 0.0
    return sum(1 for g in graded if g["correct"]) / len(graded)


def per_topic_accuracy(graded: Iterable[dict]) -> dict[str, float]:
    totals: dict[str, int] = defaultdict(int)
    correct: dict[str, int] = defaultdict(int)
    for g in graded:
        totals[g["topic"]] += 1
        if g["correct"]:
            correct[g["topic"]] += 1
    return {t: correct[t] / totals[t] for t in totals}


def weak_topics(
    per_topic: dict[str, float],
    threshold: float,
) -> list[str]:
    return sorted(
        [t for t, a in per_topic.items() if a < threshold],
        key=lambda t: per_topic[t],
    )


def confidence_adjusted_accuracy(
    graded: list[dict],
    confidence: dict[str, int],
    low_conf_weight: float = 0.5,
) -> dict[str, float]:
    """Per-topic accuracy where correct+low-confidence counts as low_conf_weight correct.

    confidence maps question_id → 1 (Low) / 2 (Medium) / 3 (High).
    Missing entries default to Medium (full weight).
    """
    totals: dict[str, int] = defaultdict(int)
    weighted: dict[str, float] = defaultdict(float)
    for g in graded:
        totals[g["topic"]] += 1
        if g["correct"]:
            conf_level = confidence.get(g["question_id"], 2)
            weight = low_conf_weight if conf_level == 1 else 1.0
            weighted[g["topic"]] += weight
    return {t: weighted[t] / totals[t] for t in totals}
