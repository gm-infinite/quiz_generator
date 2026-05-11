"""Shared test fixtures: a fake GeminiClient that returns canned schema objects.

No tests in this project should call the real API.
"""
from __future__ import annotations

from typing import Callable, TypeVar

import pytest
from pydantic import BaseModel

from llm.schemas import (
    EvaluationResult,
    FinalReport,
    JudgeScore,
    JudgeScores,
    Question,
    QuestionSet,
    WeaknessAnalysis,
    WeakTopic,
)

T = TypeVar("T", bound=BaseModel)


def _q(qid: str, topic: str, correct: str = "A") -> Question:
    return Question(
        id=qid,
        topic=topic,
        prompt=f"Stub question {qid} on {topic}?",
        choices=["A", "B", "C", "D"],
        correct_answer=correct,
        explanation="because.",
    )


class FakeGeminiClient:
    """Returns a default valid instance for any schema. Override per test."""

    def __init__(self) -> None:
        self.handlers: dict[type, Callable[[str], BaseModel]] = {}
        self.calls: list[tuple[type, str]] = []

    def set(self, schema: type[T], handler: Callable[[str], T]) -> None:
        self.handlers[schema] = handler  # type: ignore[assignment]

    def _default(self, schema: type[T]) -> T:
        if schema is QuestionSet:
            return QuestionSet(  # type: ignore[return-value]
                questions=[_q("d1", "alpha"), _q("d2", "beta")]
            )
        if schema is WeaknessAnalysis:
            return WeaknessAnalysis(  # type: ignore[return-value]
                weak_topics=[WeakTopic(topic="alpha", accuracy=0.0, explanation="...")],
                summary="weak in alpha.",
            )
        if schema is EvaluationResult:
            return EvaluationResult(  # type: ignore[return-value]
                graded=[], score=0.0, improvement_delta=0.0, passed=False,
                rationale="stub rationale",
            )
        if schema is FinalReport:
            return FinalReport(  # type: ignore[return-value]
                mastered_topics=[], still_needs_work=[],
                recommended_next_steps=[], summary="stub report",
            )
        if schema is JudgeScores:
            s = JudgeScore(score=8, justification="ok")
            return JudgeScores(  # type: ignore[return-value]
                relevance=s, difficulty_calibration=s, improvement_validity=s,
                overall_comment="ok",
            )
        raise NotImplementedError(f"no default for {schema}")

    def generate_structured(self, prompt: str, schema: type[T]) -> T:
        self.calls.append((schema, prompt))
        if schema in self.handlers:
            return self.handlers[schema](prompt)  # type: ignore[return-value]
        return self._default(schema)

    def generate_with_search(self, prompt: str, schema: type[T]) -> T:
        return self.generate_structured(prompt, schema)


@pytest.fixture
def fake_client() -> FakeGeminiClient:
    return FakeGeminiClient()


@pytest.fixture
def make_question():
    return _q
