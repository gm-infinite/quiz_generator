"""Unit tests for tools.dedupe."""
from __future__ import annotations

from tools.dedupe import is_duplicate, normalize


def test_normalize_lowercases_and_strips_punctuation():
    assert normalize("Hello, WORLD!?") == "hello world"


def test_normalize_collapses_whitespace():
    assert normalize("a  \t\nb") == "a b"


def test_exact_normalized_match_is_duplicate():
    assert is_duplicate(
        "What is the capital of France?",
        ["what is the capital of france"],
    )


def test_punctuation_differences_still_match():
    assert is_duplicate(
        "What is the capital of France?",
        ["What — is the capital of France!!!"],
    )


def test_no_priors_means_not_duplicate():
    assert is_duplicate("Anything at all here?", []) is False


def test_unrelated_stems_are_not_duplicates():
    assert (
        is_duplicate(
            "What is the boiling point of water at sea level?",
            ["Who wrote the novel Anna Karenina?"],
        )
        is False
    )


def test_high_token_overlap_is_duplicate():
    # Same content, slight reorder/wording — token overlap should catch it.
    a = "Which Python list method appends a single element to the end of the list"
    b = "Which method appends a single element to the end of a Python list"
    assert is_duplicate(a, [b])


def test_short_stems_pass_through():
    # No tokens long enough to compare → cannot dedup.
    assert is_duplicate("?", ["?"]) is False
    assert is_duplicate("ab", ["cd"]) is False


def test_threshold_respected():
    a = "the quick brown fox jumps over the lazy dog"
    b = "the quick brown fox sprints around the sleepy cat"
    # Partial overlap; with default 0.80 threshold should NOT match.
    assert is_duplicate(a, [b]) is False
    # But with a lower threshold it should.
    assert is_duplicate(a, [b], overlap_threshold=0.4) is True
