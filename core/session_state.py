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

    diagnostic_questions: list[dict[str, Any]] = field(default_factory=list)
    diagnostic_answers: list[str] = field(default_factory=list)
    diagnostic_results: list[dict[str, Any]] = field(default_factory=list)

    weak_topics: list[dict[str, Any]] = field(default_factory=list)

    practice_questions: list[dict[str, Any]] = field(default_factory=list)
    practice_answers: list[str] = field(default_factory=list)
    practice_results: list[dict[str, Any]] = field(default_factory=list)

    iteration: int = 0
    diagnostic_score: float | None = None
    practice_score: float | None = None
    passed: bool = False

    final_report: dict[str, Any] | None = None
    judge_scores: dict[str, Any] | None = None

    # Internal: a concurrent.futures.Future producing the next practice round,
    # kicked off while the user is on the review screen. Excluded from repr
    # and equality so dataclass introspection still works.
    pending_future: Any = field(default=None, repr=False, compare=False)
    pending_weak_topics: list[dict[str, Any]] | None = field(
        default=None, repr=False, compare=False
    )
