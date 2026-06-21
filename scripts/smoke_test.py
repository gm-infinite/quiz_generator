"""Quick check that the LLM client is wired up correctly.

Run from project root:
    python -m scripts.smoke_test

Requires OPENROUTER_API_KEY in .env or environment.
"""
from __future__ import annotations

import sys

from llm.llm_client import LLMClient
from llm.prompts import assessment_prompt
from llm.schemas import QuestionSet


def main() -> int:
    client = LLMClient()
    prompt = assessment_prompt(subject="basic Python", level="beginner", n_questions=3)
    result: QuestionSet = client.generate_structured(prompt, QuestionSet)

    print(f"Got {len(result.questions)} questions back.\n")
    for q in result.questions:
        print(f"[{q.id}] ({q.topic}) {q.prompt}")
        for c in q.choices:
            marker = "*" if c == q.correct_answer else " "
            print(f"   {marker} {c}")
        print()

    if len(result.questions) != 3:
        print("WARNING: expected 3 questions", file=sys.stderr)
        return 1

    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
