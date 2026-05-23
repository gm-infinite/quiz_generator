"""Time a few assessment calls to measure end-to-end latency.

Usage: python -m scripts.bench
"""
from __future__ import annotations

import time

from llm.llm_client import LLMClient
from llm.prompts import assessment_prompt
from llm.schemas import QuestionSet
from core import config


def main() -> int:
    client = LLMClient()
    print(f"Model: {config.LLM_MODEL}")
    print(f"Questions per call: {config.DIAGNOSTIC_QUESTION_COUNT}\n")

    times: list[float] = []
    for i in range(3):
        prompt = assessment_prompt(
            subject="basic Python",
            level="beginner",
            n_questions=config.DIAGNOSTIC_QUESTION_COUNT,
        )
        t0 = time.perf_counter()
        result: QuestionSet = client.generate_structured(prompt, QuestionSet)
        dt = time.perf_counter() - t0
        times.append(dt)
        print(f"Run {i + 1}: {dt:.2f}s ({len(result.questions)} questions)")

    print(f"\nAvg: {sum(times) / len(times):.2f}s | "
          f"min: {min(times):.2f}s | max: {max(times):.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
