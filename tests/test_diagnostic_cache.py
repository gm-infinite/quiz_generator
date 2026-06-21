"""Preloaded diagnostic banks: loader + assessment-agent integration."""
from agents.assessment_agent import AssessmentAgent
from core.session_state import SessionState
from llm.schemas import QuestionSet
from tools import diagnostic_cache
from tools.diagnostic_cache import _slug, load_cached


def test_slug_handles_ampersand_and_spaces():
    assert _slug("JavaScript & Web Development") == "javascript_web_development"
    assert _slug("Geography of Turkey") == "geography_of_turkey"


def test_load_cached_hit_returns_count_questions():
    qs = load_cached("Biology", "beginner", 10)
    assert qs is not None and len(qs) == 10
    assert {"id", "topic", "prompt", "choices", "correct_answer"} <= qs[0].keys()


def test_load_cached_trims_to_requested_count():
    assert len(load_cached("Calculus", "advanced", 5)) == 5


def test_load_cached_misses_when_more_than_bank_requested():
    # Banks hold 10; asking for more must miss so we regenerate a full set.
    assert load_cached("Biology", "beginner", 11) is None


def test_load_cached_misses_for_unknown_subject():
    assert load_cached("Quantum Basketball", "beginner", 10) is None


def test_assessment_serves_cache_without_llm(fake_client):
    # If the cache is used, the fake LLM's marker question never appears.
    fake_client.set(QuestionSet, lambda _p: _llm_marker())
    state = SessionState(subject="Biology", level="beginner")
    state.question_count = 10
    AssessmentAgent(fake_client).run(state)
    assert len(state.diagnostic_questions) == 10
    assert all(q["topic"] != "FROM_LLM" for q in state.diagnostic_questions)


def test_assessment_falls_back_to_llm_for_custom_subject(fake_client):
    fake_client.set(QuestionSet, lambda _p: _llm_marker())
    state = SessionState(subject="Quantum Basketball", level="beginner")
    state.question_count = 10
    AssessmentAgent(fake_client).run(state)
    assert state.diagnostic_questions[0]["topic"] == "FROM_LLM"


def test_assessment_skips_cache_when_source_uploaded(fake_client):
    fake_client.set(QuestionSet, lambda _p: _llm_marker())
    state = SessionState(subject="Biology", level="beginner", source_text="some notes")
    state.question_count = 10
    AssessmentAgent(fake_client).run(state)
    assert state.diagnostic_questions[0]["topic"] == "FROM_LLM"


def _llm_marker() -> QuestionSet:
    return QuestionSet(questions=[QuestionSet.model_validate({
        "questions": [{
            "id": "d1", "topic": "FROM_LLM", "prompt": "p?",
            "choices": ["a", "b"], "correct_answer": "a", "explanation": "e",
        }]
    }).questions[0]])
