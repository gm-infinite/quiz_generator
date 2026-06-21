"""Preloaded diagnostic question banks for the predefined subjects.

Each predefined (subject, level) ships a hand-prepared bank at
``data/diagnostics/<slug>__<level>.json`` so the opening test can be served
without an LLM call. Custom subjects and uploaded-source sessions have no
bank and fall through to generation.
"""
from __future__ import annotations

from pathlib import Path

from llm.schemas import QuestionSet

_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "diagnostics"


def _slug(subject: str) -> str:
    # "JavaScript & Web Development" -> "javascript_web_development"
    return "_".join(subject.lower().replace("&", " ").split())


def load_cached(subject: str, level: str, count: int) -> list[dict] | None:
    """First ``count`` cached questions for a predefined (subject, level), or
    None when there's no bank, it can't be parsed, or it holds fewer than
    ``count`` questions (banks are 10 each; larger requests regenerate).
    """
    path = _CACHE_DIR / f"{_slug(subject)}__{level}.json"
    if not path.exists():
        return None
    try:
        parsed = QuestionSet.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if len(parsed.questions) < count:
        return None
    return [q.model_dump() for q in parsed.questions[:count]]
