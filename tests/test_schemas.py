"""Schema-level validation tests for llm.schemas."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from llm.schemas import Question


def _kwargs(**overrides):
    base = dict(
        id="q1",
        topic="alpha",
        prompt="What?",
        choices=["A", "B", "C", "D"],
        correct_answer="A",
        explanation="because.",
    )
    base.update(overrides)
    return base


def test_valid_question_accepted():
    q = Question(**_kwargs())
    assert q.correct_answer in q.choices
    assert q.distractor_rationales == {}


def test_correct_answer_must_be_in_choices():
    with pytest.raises(ValidationError, match="not one of the choices"):
        Question(**_kwargs(correct_answer="Z"))


def test_duplicate_choices_rejected():
    with pytest.raises(ValidationError, match="duplicate choices"):
        Question(**_kwargs(choices=["A", "A", "B", "C"]))


def test_duplicate_choices_after_strip_rejected():
    # Whitespace-only difference should still count as duplicate.
    with pytest.raises(ValidationError, match="duplicate choices"):
        Question(**_kwargs(choices=["A", " A ", "B", "C"]))


def test_empty_choice_rejected():
    with pytest.raises(ValidationError, match="empty choice"):
        Question(**_kwargs(choices=["A", "", "B", "C"]))


def test_too_few_choices_rejected():
    with pytest.raises(ValidationError):
        Question(**_kwargs(choices=["A"], correct_answer="A"))


def test_distractor_rationales_optional_and_typed():
    q = Question(
        **_kwargs(
            distractor_rationales={
                "B": "B is wrong because…",
                "C": "C is wrong because…",
            }
        )
    )
    assert q.distractor_rationales["B"].startswith("B is wrong")
