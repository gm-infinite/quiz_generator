"""Drive a full QuizMind session from the terminal — no Gradio required.

    python -m scripts.run_cli
"""
from __future__ import annotations

from core.orchestrator import Orchestrator
from core.session_state import Phase, SessionState


def _ask_question(idx: int, q: dict) -> str:
    print(f"\nQ{idx + 1} [{q['topic']}] {q['prompt']}")
    for i, choice in enumerate(q["choices"]):
        print(f"   {i + 1}. {choice}")
    while True:
        raw = input("Your answer (number or text): ").strip()
        if raw.isdigit():
            i = int(raw) - 1
            if 0 <= i < len(q["choices"]):
                return q["choices"][i]
        elif raw in q["choices"]:
            return raw
        print("  Invalid input — enter the choice number or exact text.")


def _collect_answers(questions: list[dict]) -> list[str]:
    return [_ask_question(i, q) for i, q in enumerate(questions)]


def _print_results(state: SessionState) -> None:
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    print(f"Initial test score: {state.diagnostic_score:.0%}" if state.diagnostic_score is not None else "")
    if state.practice_score is not None:
        print(f"Practice score:   {state.practice_score:.0%}")
    print(f"Passed: {state.passed}  (iterations: {state.iteration})")

    report = state.final_report or {}
    if "summary" in report:
        print(f"\nSummary: {report['summary']}")
    if report.get("mastered_topics"):
        print(f"Mastered:        {report['mastered_topics']}")
    if report.get("still_needs_work"):
        print(f"Still weak:      {report['still_needs_work']}")
    if report.get("recommended_next_steps"):
        print(f"Next steps:      {report['recommended_next_steps']}")

    if state.judge_scores:
        print("\nJudge scores:")
        for criterion in ("relevance", "difficulty_calibration", "improvement_validity"):
            entry = state.judge_scores.get(criterion, {})
            print(f"  {criterion}: {entry.get('score')}/10 — {entry.get('justification')}")
        print(f"  overall: {state.judge_scores.get('overall_comment')}")


def main() -> int:
    subject = input("Subject: ").strip() or "basic Python"
    level = input("Level (beginner/intermediate/advanced) [beginner]: ").strip() or "beginner"

    orch = Orchestrator()
    print(f"\nGenerating initial test on {subject!r} ({level})...")
    state = orch.start(subject, level)

    print(f"\n--- INITIAL TEST ({len(state.diagnostic_questions)} questions) ---")
    answers = _collect_answers(state.diagnostic_questions)
    print("\nGrading + analyzing...")
    state = orch.submit_diagnostic_answers(state, answers)
    state = orch.continue_after_diagnostic(state)

    while state.phase == Phase.PRACTICE:
        print(
            f"\n--- PRACTICE ROUND {state.iteration} "
            f"({len(state.practice_questions)} questions across "
            f"{len({q['topic'] for q in state.practice_questions})} weak topics) ---"
        )
        answers = _collect_answers(state.practice_questions)
        print("\nEvaluating...")
        state = orch.submit_practice_answers(state, answers)
        state = orch.continue_after_practice(state)

    _print_results(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
