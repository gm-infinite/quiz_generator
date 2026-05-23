"""Per-agent unit tests using the fake client."""
from __future__ import annotations

from agents.assessment_agent import AssessmentAgent
from agents.evaluator_agent import EvaluatorAgent
from agents.feedback_agent import FeedbackAgent
from agents.judge_agent import JudgeAgent
from agents.question_generator import QuestionGenerator
from agents.weakness_analyzer import WeaknessAnalyzer
from core import config
from core.session_state import SessionState
from llm.schemas import (
    EvaluationResult,
    Question,
    QuestionSet,
    WeaknessAnalysis,
    WeakTopic,
)


def _stub_q(qid, topic, correct="A"):
    return Question(
        id=qid, topic=topic,
        prompt="?", choices=["A", "B", "C", "D"],
        correct_answer=correct, explanation="",
    )


def test_assessment_populates_diagnostic_questions(fake_client):
    fake_client.set(
        QuestionSet,
        lambda _p: QuestionSet(questions=[_stub_q("d1", "x"), _stub_q("d2", "y")]),
    )
    state = SessionState(subject="math", level="beginner")
    AssessmentAgent(fake_client).run(state)
    assert len(state.diagnostic_questions) == 2
    assert state.diagnostic_questions[0]["topic"] == "x"


def test_weakness_analyzer_skips_llm_if_no_weak_topics(fake_client):
    state = SessionState(subject="math", level="beginner")
    state.diagnostic_questions = [_stub_q("d1", "x").model_dump()]
    state.diagnostic_answers = ["A"]  # correct
    WeaknessAnalyzer(fake_client).run(state)
    assert state.weak_topics == []
    assert state.diagnostic_score == 1.0
    # Should not have called the LLM for explanation.
    assert all(schema is not WeaknessAnalysis for schema, _ in fake_client.calls)


def test_weakness_analyzer_uses_math_for_accuracy_not_llm(fake_client):
    # LLM returns nonsense accuracy; agent must ignore it.
    fake_client.set(
        WeaknessAnalysis,
        lambda _p: WeaknessAnalysis(
            weak_topics=[WeakTopic(topic="x", accuracy=0.99, explanation="lol")],
            summary="",
        ),
    )
    state = SessionState(subject="math", level="beginner")
    state.diagnostic_questions = [
        _stub_q("d1", "x").model_dump(),
        _stub_q("d2", "x").model_dump(),
    ]
    state.diagnostic_answers = ["B", "C"]  # both wrong
    WeaknessAnalyzer(fake_client).run(state)
    assert state.weak_topics[0]["topic"] == "x"
    assert state.weak_topics[0]["accuracy"] == 0.0  # deterministic, not 0.99
    assert state.weak_topics[0]["explanation"] == "lol"


def test_question_generator_reassigns_ids_and_topic(fake_client):
    # Agent should overwrite returned ids with deterministic ones
    # and force the topic tag to match the requested weak topic.
    fake_client.set(
        QuestionSet,
        lambda _p: QuestionSet(questions=[
            _stub_q("wrong-id", "wrong-topic"),
            _stub_q("also-wrong", "wrong-topic"),
        ]),
    )
    state = SessionState(subject="math", level="beginner")
    state.iteration = 0
    state.weak_topics = [{"topic": "derivatives", "accuracy": 0.0, "explanation": ""}]
    QuestionGenerator(fake_client).run(state)
    ids = [q["id"] for q in state.practice_questions]
    topics = {q["topic"] for q in state.practice_questions}
    assert ids == ["p1-1-1", "p1-1-2"]
    assert topics == {"derivatives"}


def test_question_generator_drops_duplicates_across_rounds(fake_client):
    # Diagnostic already contained this prompt. The generator should
    # filter the duplicate from this round's practice set.
    diag_prompt = "What is the derivative of x squared with respect to x"

    def stub(_p):
        return QuestionSet(questions=[
            Question(
                id="r1", topic="t", prompt=diag_prompt,
                choices=["A", "B", "C", "D"],
                correct_answer="A", explanation="",
            ),
            Question(
                id="r2", topic="t",
                prompt="What does the chain rule say in plain words",
                choices=["A", "B", "C", "D"],
                correct_answer="A", explanation="",
            ),
        ])

    fake_client.set(QuestionSet, stub)
    state = SessionState(subject="math", level="beginner")
    state.iteration = 0
    state.diagnostic_questions = [
        {"prompt": diag_prompt, "id": "d1", "topic": "t",
         "choices": ["A"], "correct_answer": "A", "explanation": ""}
    ]
    state.weak_topics = [{"topic": "t", "accuracy": 0.0, "explanation": ""}]

    QuestionGenerator(fake_client).run(state)
    prompts = [q["prompt"] for q in state.practice_questions]
    assert diag_prompt not in prompts
    assert len(state.practice_questions) == 1


def test_question_generator_drops_intra_round_duplicates(fake_client):
    repeated = "Explain how list comprehensions work in Python"

    def stub(_p):
        return QuestionSet(questions=[
            Question(
                id="x1", topic="t", prompt=repeated,
                choices=["A", "B", "C", "D"],
                correct_answer="A", explanation="",
            ),
            Question(
                id="x2", topic="t", prompt=repeated,
                choices=["A", "B", "C", "D"],
                correct_answer="A", explanation="",
            ),
        ])

    fake_client.set(QuestionSet, stub)
    state = SessionState(subject="python", level="beginner")
    state.iteration = 0
    state.weak_topics = [{"topic": "t", "accuracy": 0.0, "explanation": ""}]
    QuestionGenerator(fake_client).run(state)
    # Second occurrence in the same round should be dropped.
    assert len(state.practice_questions) == 1


def test_evaluator_pass_by_absolute_threshold(fake_client):
    state = SessionState(subject="math", level="beginner")
    state.diagnostic_score = 0.2
    state.practice_questions = [_stub_q(f"p{i}", "x").model_dump() for i in range(10)]
    # 8/10 correct → 0.8 ≥ PASS_ABSOLUTE_THRESHOLD (0.7)
    state.practice_answers = ["A"] * 8 + ["B"] * 2
    EvaluatorAgent(fake_client).run(state)
    assert state.practice_score == 0.8
    assert state.passed is True


def test_evaluator_pass_by_improvement_delta(fake_client):
    state = SessionState(subject="math", level="beginner")
    state.diagnostic_score = 0.3
    state.practice_questions = [_stub_q(f"p{i}", "x").model_dump() for i in range(10)]
    # 6/10 correct → 0.6 < absolute; delta 0.6-0.3=0.3 ≥ 0.2 → pass
    state.practice_answers = ["A"] * 6 + ["B"] * 4
    EvaluatorAgent(fake_client).run(state)
    assert state.passed is True


def test_evaluator_fails_when_below_both_thresholds(fake_client):
    state = SessionState(subject="math", level="beginner")
    state.diagnostic_score = 0.5
    state.practice_questions = [_stub_q(f"p{i}", "x").model_dump() for i in range(10)]
    # 5/10 = 0.5, delta 0.0 → fail
    state.practice_answers = ["A"] * 5 + ["B"] * 5
    EvaluatorAgent(fake_client).run(state)
    assert state.passed is False


def test_evaluator_ignores_llm_pass_claim(fake_client):
    # LLM lies and claims passed=True; agent must ignore that.
    fake_client.set(
        EvaluationResult,
        lambda _p: EvaluationResult(
            graded=[], score=0.99, improvement_delta=0.99,
            passed=True, rationale="LLM says pass",
        ),
    )
    state = SessionState(subject="math", level="beginner")
    state.diagnostic_score = 0.5
    state.practice_questions = [_stub_q(f"p{i}", "x").model_dump() for i in range(10)]
    state.practice_answers = ["B"] * 10  # 0/10
    EvaluatorAgent(fake_client).run(state)
    assert state.passed is False
    assert state.practice_score == 0.0


def test_feedback_and_judge_populate_state(fake_client):
    state = SessionState(subject="math", level="beginner")
    FeedbackAgent(fake_client).run(state)
    assert state.final_report is not None
    assert "summary" in state.final_report
    JudgeAgent(fake_client).run(state)
    assert state.judge_scores is not None
    assert state.judge_scores["relevance"]["score"] == 8
