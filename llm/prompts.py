"""All prompt templates. Edit here, not inside agents.

Each function returns a fully-formatted prompt string. Keeping these as
functions (not bare strings) makes it obvious what variables each prompt
depends on and lets us refactor without touching agent code.
"""
from __future__ import annotations


def assessment_prompt(
    subject: str,
    level: str,
    n_questions: int,
    source_text: str = "",
) -> str:
    source_block = ""
    if source_text:
        source_block = (
            f"\nGround every question STRICTLY in the source material below — do not "
            f"introduce facts that are not stated or directly implied by it. If the "
            f"source is short, stay focused on what it actually covers.\n"
            f"\n--- SOURCE MATERIAL START ---\n{source_text}\n--- SOURCE MATERIAL END ---\n"
        )
    return (
        f"You are designing a broad-coverage initial test to map a student's knowledge "
        f"of {subject!r} at a {level} level.\n"
        f"{source_block}"
        f"\n"
        f"Generate exactly {n_questions} multiple-choice questions that span a BROAD set of "
        f"subtopics within {subject!r} — do not cluster on one area. The goal is to surface "
        f"weak spots, so coverage matters more than depth.\n"
        f"\n"
        f"Requirements per question:\n"
        f"  - 4 plausible answer choices, exactly one correct. `correct_answer` "
        f"must be EXACTLY one of the strings in `choices`. No duplicate choices.\n"
        f"  - A `topic` tag naming the specific subtopic (e.g. 'derivatives', not 'math').\n"
        f"  - A short `explanation` of why the correct answer is correct.\n"
        f"  - A `distractor_rationales` object mapping EACH incorrect choice "
        f"(the exact string) to a one-sentence explanation of why it is wrong.\n"
        f"  - A unique `id` like 'd1', 'd2', ...\n"
    )


def weakness_analysis_prompt(
    subject: str,
    per_topic_accuracy: dict[str, float],
    threshold: float,
) -> str:
    rows = "\n".join(f"  - {t}: {a:.0%}" for t, a in per_topic_accuracy.items())
    return (
        f"A student took a diagnostic quiz on {subject!r}. Per-topic accuracy:\n"
        f"{rows}\n"
        f"\n"
        f"Topics below {threshold:.0%} accuracy are considered weak. For EACH weak topic, "
        f"write a one- or two-sentence explanation of what the student likely misunderstands "
        f"— grounded in the topic itself, not generic advice. Also produce a short overall "
        f"summary (2-3 sentences).\n"
    )


def question_generator_prompt(
    subject: str,
    level: str,
    weak_topic: str,
    n_questions: int,
    avoid_prompts: list[str],
    source_text: str = "",
) -> str:
    avoid = (
        "\n\nAvoid repeating these earlier question stems:\n"
        + "\n".join(f"  - {p}" for p in avoid_prompts)
        if avoid_prompts
        else ""
    )
    source_block = ""
    if source_text:
        source_block = (
            f"\nGround every question STRICTLY in the source material below — do not "
            f"introduce facts that are not stated or directly implied by it.\n"
            f"\n--- SOURCE MATERIAL START ---\n{source_text}\n--- SOURCE MATERIAL END ---\n"
        )
    return (
        f"Generate {n_questions} fresh multiple-choice practice questions on the topic "
        f"{weak_topic!r} within {subject!r}, targeting a {level} student who got this "
        f"topic wrong on the initial test.\n"
        f"{source_block}"
        f"\n"
        f"The questions should test understanding, not recall. Each question must have "
        f"4 unique choices (no duplicates), one `correct_answer` that is EXACTLY one of "
        f"the choice strings, an `explanation`, a `distractor_rationales` object mapping "
        f"each incorrect choice to a one-sentence reason it is wrong, the topic tag "
        f"{weak_topic!r}, and a unique id prefixed with 'p'."
        f"{avoid}"
    )


def evaluator_prompt(
    diagnostic_score: float | None,
    practice_score: float,
    improvement_delta: float,
    pass_absolute: float,
    pass_delta: float,
) -> str:
    return (
        f"You are evaluating a student's practice round.\n"
        f"  - Diagnostic score: {diagnostic_score if diagnostic_score is not None else 'n/a'}\n"
        f"  - Practice score:   {practice_score:.2f}\n"
        f"  - Improvement:      {improvement_delta:+.2f}\n"
        f"\n"
        f"Pass rule: passed = True if practice_score >= {pass_absolute} OR "
        f"improvement_delta >= {pass_delta}. Apply the rule literally; do not soften it. "
        f"Then write a one-sentence rationale that names which side of the rule fired."
    )


def feedback_prompt(
    subject: str,
    weak_topics: list[str],
    practice_results: list[dict],
) -> str:
    return (
        f"Write the student's final report for their {subject!r} session.\n"
        f"\n"
        f"Topics that started weak: {weak_topics}\n"
        f"Practice round results: {practice_results}\n"
        f"\n"
        f"Produce: which topics they now show mastery in, which still need work, and "
        f"concrete next steps (resources or focus areas). Keep the tone direct and "
        f"specific — no platitudes."
    )


def judge_prompt(session_summary: dict) -> str:
    return (
        f"You are an evaluation judge for an adaptive quiz system. Score the session "
        f"below on three criteria, 0-10 each, with a one-sentence justification per score:\n"
        f"\n"
        f"  1. Relevance — did the generated practice questions actually target the weak "
        f"     topics identified by the analyzer?\n"
        f"  2. Difficulty calibration — were the practice questions appropriate for the "
        f"     stated level, neither trivially easy nor unfairly hard?\n"
        f"  3. Improvement validity — does the score improvement reflect real learning, "
        f"     or were practice questions simply easier than the diagnostic?\n"
        f"\n"
        f"Session data:\n{session_summary}\n"
    )


def search_grounding_block(snippets: str) -> str:
    """Wrapper prepended to a generation prompt when web search results exist.

    Used by LLMClient.generate_with_search — not by agents directly.
    """
    return (
        "Use the following live web search results as factual grounding. When "
        "your own memory conflicts with these results, prefer the results. "
        "Ignore any result that is irrelevant to the task below.\n"
        "\n--- WEB SEARCH RESULTS START ---\n"
        f"{snippets}\n"
        "--- WEB SEARCH RESULTS END ---\n\n"
    )
