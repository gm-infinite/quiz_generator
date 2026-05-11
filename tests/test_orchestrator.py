"""End-to-end state-machine tests with a fake client."""
from __future__ import annotations

from core import config
from core.orchestrator import Orchestrator
from core.session_state import Phase
from llm.schemas import Question, QuestionSet


def _q(qid, topic, correct="A"):
    return Question(
        id=qid, topic=topic, prompt="?",
        choices=["A", "B", "C", "D"],
        correct_answer=correct, explanation="",
    )


def _diagnostic_set():
    # Two topics, 4 questions each → easy to control accuracy per topic.
    return QuestionSet(questions=[
        _q("d1", "alpha"), _q("d2", "alpha"), _q("d3", "alpha"), _q("d4", "alpha"),
        _q("d5", "beta"),  _q("d6", "beta"),  _q("d7", "beta"),  _q("d8", "beta"),
    ])


def test_perfect_diagnostic_skips_practice_jumps_to_feedback(fake_client):
    fake_client.set(QuestionSet, lambda _p: _diagnostic_set())
    orch = Orchestrator(client=fake_client)
    state = orch.start("math", "beginner")
    assert state.phase == Phase.ASSESSMENT
    assert len(state.diagnostic_questions) == 8

    state = orch.submit_diagnostic_answers(state, ["A"] * 8)
    assert state.weak_topics == []
    assert state.passed is True
    assert state.phase == Phase.DONE
    assert state.iteration == 0


def test_weak_topic_triggers_practice_round(fake_client):
    call_count = {"n": 0}

    def question_handler(_prompt):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _diagnostic_set()  # diagnostic
        # practice set: 5 questions on whatever weak topic
        return QuestionSet(questions=[_q(f"x{i}", "alpha") for i in range(5)])

    fake_client.set(QuestionSet, question_handler)
    orch = Orchestrator(client=fake_client)
    state = orch.start("math", "beginner")

    # Alpha wrong, beta right → alpha is weak (0%), beta 100%
    answers = ["B"] * 4 + ["A"] * 4
    state = orch.submit_diagnostic_answers(state, answers)
    assert state.phase == Phase.PRACTICE
    assert state.iteration == 1
    assert [w["topic"] for w in state.weak_topics] == ["alpha"]
    assert len(state.practice_questions) == 5


def test_practice_round_loops_when_failing(fake_client):
    """Failing practice round should loop back to PRACTICE, not terminate."""
    counts = {"n": 0}

    def handler(_p):
        counts["n"] += 1
        if counts["n"] == 1:
            return _diagnostic_set()
        return QuestionSet(questions=[_q(f"x{i}", "alpha") for i in range(5)])

    fake_client.set(QuestionSet, handler)
    orch = Orchestrator(client=fake_client)
    state = orch.start("math", "beginner")
    state = orch.submit_diagnostic_answers(state, ["B"] * 4 + ["A"] * 4)
    assert state.iteration == 1

    # All practice wrong → no improvement, fail
    state = orch.submit_practice_answers(state, ["B"] * 5)
    assert state.passed is False
    assert state.phase == Phase.PRACTICE  # looped
    assert state.iteration == 2


def test_max_rounds_hard_caps_loop(fake_client):
    counts = {"n": 0}

    def handler(_p):
        counts["n"] += 1
        if counts["n"] == 1:
            return _diagnostic_set()
        return QuestionSet(questions=[_q(f"x{i}", "alpha") for i in range(5)])

    fake_client.set(QuestionSet, handler)
    orch = Orchestrator(client=fake_client)
    state = orch.start("math", "beginner")
    state = orch.submit_diagnostic_answers(state, ["B"] * 4 + ["A"] * 4)

    for _ in range(config.MAX_PRACTICE_ROUNDS):
        if state.phase == Phase.PRACTICE:
            state = orch.submit_practice_answers(state, ["B"] * 5)

    assert state.phase == Phase.DONE
    assert state.iteration == config.MAX_PRACTICE_ROUNDS
    assert state.passed is False  # never improved, but loop is capped


def test_orchestrator_does_not_call_llm_directly(fake_client):
    """Smoke check that the Orchestrator delegates and doesn't bypass agents."""
    fake_client.set(QuestionSet, lambda _p: _diagnostic_set())
    orch = Orchestrator(client=fake_client)
    state = orch.start("math", "beginner")
    state = orch.submit_diagnostic_answers(state, ["A"] * 8)
    # If the Orchestrator ever called the client directly without going
    # through an agent, this wouldn't be tracked — but we at least confirm
    # the agents *did* drive the calls we expect.
    assert any(schema.__name__ == "QuestionSet" for schema, _ in fake_client.calls)
    assert any(schema.__name__ == "FinalReport" for schema, _ in fake_client.calls)
    assert any(schema.__name__ == "JudgeScores" for schema, _ in fake_client.calls)
