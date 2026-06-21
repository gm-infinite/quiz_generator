"""Cross-round question deduplication.

The LLM is asked (via `avoid_prompts`) to skip prior stems, but ignores
that instruction often enough that we need a hard filter. We normalize
stems (lowercase, strip punctuation, collapse whitespace) and reject
any new question whose normalized stem matches a previous one exactly,
or whose token-set overlap with a previous stem is above a threshold.
"""
from __future__ import annotations

import re

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    return _WS_RE.sub(" ", _PUNCT_RE.sub(" ", text.lower())).strip()


def _token_set(text: str) -> set[str]:
    return {t for t in normalize(text).split() if len(t) > 2}


def is_duplicate(
    stem: str,
    prior_stems: list[str],
    overlap_threshold: float = 0.80,
) -> bool:
    """True if `stem` is a near-duplicate of any string in `prior_stems`.

    Stems without enough content to compare (e.g. just punctuation) are
    treated as non-duplicates — we can't meaningfully judge them.
    """
    new_tokens = _token_set(stem)
    if not new_tokens:
        return False
    n = normalize(stem)
    for p in prior_stems:
        prior_tokens = _token_set(p)
        if not prior_tokens:
            continue
        if n == normalize(p):
            return True
        overlap = len(new_tokens & prior_tokens) / max(
            len(new_tokens), len(prior_tokens)
        )
        if overlap >= overlap_threshold:
            return True
    return False
