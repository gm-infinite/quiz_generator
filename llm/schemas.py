"""Pydantic schemas for all structured LLM output.

Every agent that asks Gemini for JSON points at one of these models.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Question(BaseModel):
    id: str
    topic: str
    prompt: str
    choices: list[str] = Field(..., min_length=2, max_length=6)
    correct_answer: str  # must match one of choices exactly
    explanation: str


class QuestionSet(BaseModel):
    questions: list[Question]


class WeakTopic(BaseModel):
    topic: str
    accuracy: float
    explanation: str


class WeaknessAnalysis(BaseModel):
    weak_topics: list[WeakTopic]
    summary: str


class GradedAnswer(BaseModel):
    question_id: str
    topic: str
    correct: bool
    student_answer: str
    correct_answer: str


class EvaluationResult(BaseModel):
    graded: list[GradedAnswer]
    score: float                    # 0..1 over this round
    improvement_delta: float        # practice_score - diagnostic_score
    passed: bool
    rationale: str


class FinalReport(BaseModel):
    mastered_topics: list[str]
    still_needs_work: list[str]
    recommended_next_steps: list[str]
    summary: str


class JudgeScore(BaseModel):
    score: int = Field(..., ge=0, le=10)
    justification: str


class JudgeScores(BaseModel):
    relevance: JudgeScore
    difficulty_calibration: JudgeScore
    improvement_validity: JudgeScore
    overall_comment: str
