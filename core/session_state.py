"""Single in-memory record of a study session.

The Orchestrator reads/writes this; agents only see the fields they need.
Keep this dataclass dumb — no behavior, just data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Phase(str, Enum):
    INIT = "init"
    ASSESSMENT = "assessment"
    ANALYSIS = "analysis"
    DIAGNOSTIC_REVIEW = "diagnostic_review"
    PRACTICE = "practice"
    EVALUATION = "evaluation"
    PRACTICE_REVIEW = "practice_review"
    FEEDBACK = "feedback"
    DONE = "done"


@dataclass
class SessionState:
    subject: str = ""
    level: str = "beginner"
    source_text: str = ""

    phase: Phase = Phase.INIT

    # --- Configurable question count (Task 4) ---
    # Set by the UI before start(); assessment agent reads this.
    question_count: int = 10

    # --- Configurable practice-round cap ---
    # Set by the UI/CLI before start(); the Orchestrator reads this instead
    # of config.MAX_PRACTICE_ROUNDS. Clamped to 1–5 in Orchestrator.start().
    max_rounds: int = 3

    # --- Timer (Task 3) ---
    started_at: float = 0.0        # time.time() when session starts
    elapsed_seconds: float | None = None  # computed at finalize

    diagnostic_questions: list[dict[str, Any]] = field(default_factory=list)
    diagnostic_answers: list[str] = field(default_factory=list)
    diagnostic_results: list[dict[str, Any]] = field(default_factory=list)

    weak_topics: list[dict[str, Any]] = field(default_factory=list)

    practice_questions: list[dict[str, Any]] = field(default_factory=list)
    practice_answers: list[str] = field(default_factory=list)
    practice_results: list[dict[str, Any]] = field(default_factory=list)

    # --- Practice history for wrong-answer list (Task 2) ---
    # Each entry: {"iteration": int, "questions": [...], "results": [...]}
    # Appended by orchestrator after each practice evaluation.
    practice_history: list[dict[str, Any]] = field(default_factory=list)

    iteration: int = 0
    diagnostic_score: float | None = None
    practice_score: float | None = None
    passed: bool = False

    # --- Score progression (Task 5) ---
    # [diagnostic_score, practice_round_1, practice_round_2, ...]
    round_scores: list[float] = field(default_factory=list)

    # --- Confidence ratings (Task 7) ---
    # question_id → 1 (Low) / 2 (Medium) / 3 (High)
    confidence_ratings: dict[str, int] = field(default_factory=dict)

    final_report: dict[str, Any] | None = None
    judge_scores: dict[str, Any] | None = None

    # Internal: a concurrent.futures.Future producing the next practice round,
    # kicked off while the user is on the review screen. Excluded from repr
    # and equality so dataclass introspection still works.
    pending_future: Any = field(default=None, repr=False, compare=False)
    pending_weak_topics: list[dict[str, Any]] | None = field(
        default=None, repr=False, compare=False
    )
