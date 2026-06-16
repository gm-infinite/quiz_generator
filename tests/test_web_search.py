"""tools/web_search + grounding wiring. No real network calls anywhere —
_post_json is always monkeypatched.
"""
from __future__ import annotations

from agents.question_generator import QuestionGenerator
from core import config
from core.session_state import SessionState
from llm import prompts
from tools import web_search


def _clear_keys(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("SERPER_API_KEY", raising=False)


def test_no_key_returns_empty(monkeypatch):
    _clear_keys(monkeypatch)
    assert web_search.search_snippets("anything") == ""


def test_disabled_flag_returns_empty(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setattr(config, "SEARCH_ENABLED", False)
    assert web_search.search_snippets("anything") == ""


def test_empty_query_returns_empty(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    assert web_search.search_snippets("") == ""


def test_tavily_formatting(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setattr(
        web_search,
        "_post_json",
        lambda url, payload, headers: {
            "results": [
                {"title": "T1", "url": "http://a", "content": "C1"},
                {"title": "T2", "url": "http://b", "content": "C2"},
            ]
        },
    )
    out = web_search.search_snippets("python lists")
    assert "[1] T1 (http://a)" in out
    assert "[2] T2 (http://b)" in out
    assert "C1" in out and "C2" in out


def test_serper_formatting(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("SERPER_API_KEY", "k")
    monkeypatch.setattr(
        web_search,
        "_post_json",
        lambda url, payload, headers: {
            "organic": [{"title": "S1", "link": "http://s", "snippet": "snip"}]
        },
    )
    out = web_search.search_snippets("x")
    assert "[1] S1 (http://s)" in out and "snip" in out


def test_search_failure_degrades_to_empty(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "k")

    def boom(*_a, **_k):
        raise OSError("network down")

    monkeypatch.setattr(web_search, "_post_json", boom)
    assert web_search.search_snippets("x") == ""


def test_snippets_truncated(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    long = "z" * (config.SEARCH_SNIPPET_MAX_CHARS + 100)
    monkeypatch.setattr(
        web_search,
        "_post_json",
        lambda *a, **k: {"results": [{"title": "T", "url": "u", "content": long}]},
    )
    out = web_search.search_snippets("x")
    assert long not in out
    assert "z" * config.SEARCH_SNIPPET_MAX_CHARS in out


def test_grounding_block_wraps_snippets():
    block = prompts.search_grounding_block("[1] T (u)\nsnip")
    assert "WEB SEARCH RESULTS START" in block
    assert "[1] T (u)" in block
    assert "WEB SEARCH RESULTS END" in block


def test_question_generator_passes_search_query(fake_client):
    state = SessionState(subject="math", level="beginner")
    state.weak_topics = [{"topic": "algebra", "accuracy": 0.0, "explanation": ""}]
    QuestionGenerator(fake_client).run(state)
    assert fake_client.search_queries == ["math: algebra (beginner)"]


def test_question_generator_skips_search_with_source_text(fake_client):
    """Uploaded-file sessions must not be grounded by the open web."""
    state = SessionState(subject="math", level="beginner", source_text="some notes")
    state.weak_topics = [{"topic": "algebra", "accuracy": 0.0, "explanation": ""}]
    QuestionGenerator(fake_client).run(state)
    assert fake_client.search_queries == [""]
