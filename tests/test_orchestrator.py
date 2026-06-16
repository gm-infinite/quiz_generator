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
    assert state.phase == Phase.DIAGNOSTIC_REVIEW
    state = orch.continue_after_diagnostic(state)
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
    assert state.phase == Phase.DIAGNOSTIC_REVIEW
    state = orch.continue_after_diagnostic(state)
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
    state = orch.continue_after_diagnostic(state)
    assert state.iteration == 1

    # All practice wrong → no improvement, fail
    state = orch.submit_practice_answers(state, ["B"] * 5)
    assert state.phase == Phase.PRACTICE_REVIEW
    state = orch.continue_after_practice(state)
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
    state = orch.continue_after_diagnostic(state)

    for _ in range(config.MAX_PRACTICE_ROUNDS):
        if state.phase == Phase.PRACTICE:
            state = orch.submit_practice_answers(state, ["B"] * 5)
            state = orch.continue_after_practice(state)

    assert state.phase == Phase.DONE
    assert state.iteration == config.MAX_PRACTICE_ROUNDS
    assert state.passed is False  # never improved, but loop is capped


def test_user_selected_max_rounds_caps_loop(fake_client):
    """A per-session max_rounds=1 should end the session after one round."""
    counts = {"n": 0}

    def handler(_p):
        counts["n"] += 1
        if counts["n"] == 1:
            return _diagnostic_set()
        return QuestionSet(questions=[_q(f"x{i}", "alpha") for i in range(5)])

    fake_client.set(QuestionSet, handler)
    orch = Orchestrator(client=fake_client)
    state = orch.start("math", "beginner", max_rounds=1)
    assert state.max_rounds == 1
    state = orch.submit_diagnostic_answers(state, ["B"] * 4 + ["A"] * 4)
    state = orch.continue_after_diagnostic(state)

    # Fail the only allowed round → must finalize, not loop.
    state = orch.submit_practice_answers(state, ["B"] * 5)
    state = orch.continue_after_practice(state)
    assert state.phase == Phase.DONE
    assert state.iteration == 1
    assert state.passed is False


def test_max_rounds_clamped_to_limit(fake_client):
    fake_client.set(QuestionSet, lambda _p: _diagnostic_set())
    orch = Orchestrator(client=fake_client)
    assert orch.start("math", "beginner", max_rounds=99).max_rounds == config.MAX_PRACTICE_ROUNDS_LIMIT
    assert orch.start("math", "beginner", max_rounds=0).max_rounds == 1


def test_submit_diagnostic_lands_on_review_phase(fake_client):
    fake_client.set(QuestionSet, lambda _p: _diagnostic_set())
    orch = Orchestrator(client=fake_client)
    state = orch.start("math", "beginner")
    state = orch.submit_diagnostic_answers(state, ["B"] * 4 + ["A"] * 4)
    assert state.phase == Phase.DIAGNOSTIC_REVIEW
    # iteration is still 0 — practice round hasn't been adopted yet.
    assert state.iteration == 0
    assert state.diagnostic_score == 0.5
    assert [w["topic"] for w in state.weak_topics] == ["alpha"]


def test_submit_practice_lands_on_review_phase(fake_client):
    calls = {"n": 0}

    def handler(_p):
        calls["n"] += 1
        if calls["n"] == 1:
            return _diagnostic_set()
        return QuestionSet(questions=[_q(f"x{i}", "alpha") for i in range(5)])

    fake_client.set(QuestionSet, handler)
    orch = Orchestrator(client=fake_client)
    state = orch.start("math", "beginner")
    state = orch.submit_diagnostic_answers(state, ["B"] * 4 + ["A"] * 4)
    state = orch.continue_after_diagnostic(state)
    state = orch.submit_practice_answers(state, ["B"] * 5)
    assert state.phase == Phase.PRACTICE_REVIEW
    assert state.practice_score == 0.0
    assert state.passed is False


def test_pregen_kicked_off_after_diagnostic(fake_client):
    """When there are weak topics, a pending future should be attached."""
    fake_client.set(QuestionSet, lambda _p: QuestionSet(
        questions=[_q(f"x{i}", "alpha") for i in range(5)]
    ) if "practice" in _p.lower() else _diagnostic_set())
    orch = Orchestrator(client=fake_client)
    state = orch.start("math", "beginner")
    state = orch.submit_diagnostic_answers(state, ["B"] * 4 + ["A"] * 4)
    assert state.phase == Phase.DIAGNOSTIC_REVIEW
    assert state.pending_future is not None


def test_pregen_not_started_when_no_weak_topics(fake_client):
    fake_client.set(QuestionSet, lambda _p: _diagnostic_set())
    orch = Orchestrator(client=fake_client)
    state = orch.start("math", "beginner")
    state = orch.submit_diagnostic_answers(state, ["A"] * 8)  # perfect
    assert state.phase == Phase.DIAGNOSTIC_REVIEW
    assert state.pending_future is None


def test_pregen_adopted_in_continue_after_diagnostic(fake_client):
    """The practice round from pregen should appear after continue."""
    diag = _diagnostic_set()
    practice = QuestionSet(questions=[_q(f"x{i}", "alpha") for i in range(5)])

    calls = {"n": 0}

    def handler(_p):
        calls["n"] += 1
        return diag if calls["n"] == 1 else practice

    fake_client.set(QuestionSet, handler)
    orch = Orchestrator(client=fake_client)
    state = orch.start("math", "beginner")
    state = orch.submit_diagnostic_answers(state, ["B"] * 4 + ["A"] * 4)
    state = orch.continue_after_diagnostic(state)
    assert state.phase == Phase.PRACTICE
    assert state.iteration == 1
    assert len(state.practice_questions) == 5
    # Only 2 LLM calls total — pregen result was reused, not regenerated.
    assert calls["n"] == 2
    assert state.pending_future is None


def test_pregen_for_next_practice_round_when_failing(fake_client):
    """A failed practice round should pre-generate the next one."""
    counts = {"n": 0}

    def handler(_p):
        counts["n"] += 1
        if counts["n"] == 1:
            return _diagnostic_set()
        return QuestionSet(questions=[_q(f"x{counts['n']}-{i}", "alpha") for i in range(5)])

    fake_client.set(QuestionSet, handler)
    orch = Orchestrator(client=fake_client)
    state = orch.start("math", "beginner")
    state = orch.submit_diagnostic_answers(state, ["B"] * 4 + ["A"] * 4)
    state = orch.continue_after_diagnostic(state)
    state = orch.submit_practice_answers(state, ["B"] * 5)
    assert state.phase == Phase.PRACTICE_REVIEW
    assert state.pending_future is not None
    assert state.pending_weak_topics is not None
    state = orch.continue_after_practice(state)
    assert state.phase == Phase.PRACTICE
    assert state.iteration == 2
    assert state.pending_future is None


def test_pregen_failure_falls_back_to_synchronous(fake_client):
    """If the background pre-gen raises, continue must still produce a round."""
    calls = {"n": 0}

    def handler(_p):
        calls["n"] += 1
        if calls["n"] == 1:
            return _diagnostic_set()
        if calls["n"] == 2:
            # Background pregen call — explode.
            raise RuntimeError("pregen blew up")
        # Synchronous fallback call.
        return QuestionSet(questions=[_q(f"x{i}", "alpha") for i in range(5)])

    fake_client.set(QuestionSet, handler)
    orch = Orchestrator(client=fake_client)
    state = orch.start("math", "beginner")
    state = orch.submit_diagnostic_answers(state, ["B"] * 4 + ["A"] * 4)
    state = orch.continue_after_diagnostic(state)
    assert state.phase == Phase.PRACTICE
    assert len(state.practice_questions) == 5


def test_failed_round_with_no_weak_topics_finalizes(fake_client):
    """If overall fails but no per-topic accuracy is below the weak threshold,
    there's nothing concrete to drill — finalize instead of running an empty
    practice round.

    Setup: diagnostic 50% on a single topic (alpha), practice 60% on alpha.
    practice_score 0.60 < 0.70 (no absolute pass).
    delta 0.10 < 0.20 (no delta pass).
    alpha practice accuracy 0.60 is NOT < 0.60 (so not weak).
    """

    diag = QuestionSet(questions=[_q(f"d{i}", "alpha") for i in range(4)])
    practice = QuestionSet(questions=[_q(f"p{i}", "alpha") for i in range(5)])

    calls = {"n": 0}

    def handler(_p):
        calls["n"] += 1
        return diag if calls["n"] == 1 else practice

    fake_client.set(QuestionSet, handler)
    orch = Orchestrator(client=fake_client)
    state = orch.start("math", "beginner")

    # 2/4 right on diagnostic → alpha = 50% → weak.
    state = orch.submit_diagnostic_answers(state, ["A", "A", "B", "B"])
    state = orch.continue_after_diagnostic(state)
    assert state.phase == Phase.PRACTICE

    # 3/5 right on practice → 60% → not below threshold, not passing either.
    state = orch.submit_practice_answers(state, ["A", "A", "A", "B", "B"])
    assert state.passed is False
    assert state.pending_weak_topics is None  # per-topic accuracy >= threshold
    state = orch.continue_after_practice(state)
    # Should NOT have started an empty practice round.
    assert state.phase == Phase.DONE


def test_orchestrator_does_not_call_llm_directly(fake_client):
    """Smoke check that the Orchestrator delegates and doesn't bypass agents."""
    fake_client.set(QuestionSet, lambda _p: _diagnostic_set())
    orch = Orchestrator(client=fake_client)
    state = orch.start("math", "beginner")
    state = orch.submit_diagnostic_answers(state, ["A"] * 8)
    state = orch.continue_after_diagnostic(state)
    # If the Orchestrator ever called the client directly without going
    # through an agent, this wouldn't be tracked — but we at least confirm
    # the agents *did* drive the calls we expect.
    assert any(schema.__name__ == "QuestionSet" for schema, _ in fake_client.calls)
    assert any(schema.__name__ == "FinalReport" for schema, _ in fake_client.calls)
    assert any(schema.__name__ == "JudgeScores" for schema, _ in fake_client.calls)
