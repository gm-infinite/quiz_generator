"""Append-only local session history stored in ~/.quizmind/sessions.jsonl."""
from __future__ import annotations

import json
import time
from pathlib import Path

from core.session_state import SessionState

HISTORY_FILE = Path.home() / ".quizmind" / "sessions.jsonl"


def save_session(state: SessionState) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": time.time(),
        "subject": state.subject,
        "level": state.level,
        "diagnostic_score": state.diagnostic_score,
        "practice_score": state.practice_score,
        "passed": state.passed,
        "iterations": state.iteration,
        "elapsed_seconds": state.elapsed_seconds,
    }
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def load_sessions(max_entries: int = 20) -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    text = HISTORY_FILE.read_text(encoding="utf-8").strip()
    if not text:
        return []
    records = []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records[-max_entries:]
