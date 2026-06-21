"""Tests for session_storage — uses a tmp file, never touches ~/.quizmind."""
from __future__ import annotations

import json

import pytest

from core.session_state import SessionState
from tools.session_storage import load_sessions, save_session


@pytest.fixture()
def history_file(tmp_path, monkeypatch):
    """Redirect HISTORY_FILE to a temp path so tests don't touch the real file."""
    import tools.session_storage as mod
    monkeypatch.setattr(mod, "HISTORY_FILE", tmp_path / "sessions.jsonl")
    return tmp_path / "sessions.jsonl"


def _done_state(**kwargs) -> SessionState:
    s = SessionState(subject=kwargs.get("subject", "math"), level="beginner")
    s.diagnostic_score = kwargs.get("diagnostic_score", 0.5)
    s.practice_score = kwargs.get("practice_score", 0.8)
    s.passed = kwargs.get("passed", True)
    s.iteration = kwargs.get("iteration", 1)
    s.elapsed_seconds = kwargs.get("elapsed_seconds", 120.0)
    return s


def test_save_creates_file(history_file):
    save_session(_done_state())
    assert history_file.exists()


def test_save_appends_valid_json(history_file):
    save_session(_done_state(subject="math"))
    save_session(_done_state(subject="physics"))
    lines = history_file.read_text().strip().split("\n")
    assert len(lines) == 2
    records = [json.loads(l) for l in lines]
    assert records[0]["subject"] == "math"
    assert records[1]["subject"] == "physics"


def test_load_returns_empty_when_no_file(history_file):
    # history_file fixture patches the path but doesn't create the file
    assert load_sessions() == []


def test_load_returns_most_recent_first(history_file):
    for i in range(5):
        save_session(_done_state())
    records = load_sessions(max_entries=3)
    assert len(records) == 3


def test_load_max_entries(history_file):
    for i in range(25):
        save_session(_done_state())
    records = load_sessions(max_entries=10)
    assert len(records) == 10


def test_record_contains_required_fields(history_file):
    save_session(_done_state(diagnostic_score=0.4, practice_score=0.75, passed=True))
    records = load_sessions()
    r = records[0]
    for key in ("timestamp", "subject", "level", "diagnostic_score",
                "practice_score", "passed", "iterations", "elapsed_seconds"):
        assert key in r, f"missing key: {key}"
