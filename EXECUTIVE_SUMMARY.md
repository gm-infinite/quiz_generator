# QuizMind — Executive Summary

## What it is

QuizMind is a multi-agent adaptive learning system. A student picks a subject and difficulty level; the system administers a broad diagnostic test, identifies the topics the student is weakest on, generates fresh practice questions targeting those gaps, evaluates whether the student improved, and loops until a defined pass rule fires or a round cap is reached.

Built for **SEN4018 Agentic AI**, Bahçeşehir University, Spring 2026.

## The problem it solves

Conventional study tools spend most of a learner's time on material they already know. QuizMind inverts that: it measures where the learner actually struggles and concentrates practice there, refusing to declare success until measurable improvement occurs. Unlike a static quiz bank, every practice round is generated on demand and re-targeted at what is *still* wrong.

## How it works (one paragraph)

Five specialized agents operate under a single orchestrator that decides who acts next. The **Assessment Agent** runs the diagnostic. The **Weakness Analyzer** turns the results into a structured list of weak topics. The **Question Generator** produces targeted practice questions per weak topic. The **Evaluator & Feedback Agent** grades the practice round and decides whether to pass or loop. A final **Judge Agent** gives a qualitative read on the whole session after the loop ends. The orchestrator is the only component that sees the full session and the only entry point the user interface calls.

```
INIT → ASSESSMENT → ANALYSIS → PRACTICE → EVALUATION → FEEDBACK → DONE
                                  ^            |
                                  +----loop----+   (up to 3 rounds, then DONE)
```

## What makes it trustworthy

- **Deterministic decisions.** Scoring, weak-topic detection, and the pass/fail decision are pure Python — never the LLM's opinion. The model is used only to write human-readable explanations; any score it returns is discarded. This means the system's grades are reproducible and auditable.
- **Pass rule is explicit.** A student passes when their practice score reaches 0.70, *or* when they improve by at least 0.20 over their diagnostic. The loop stops after at most 3 rounds regardless, so a session always terminates.
- **Grounded questions.** When a student uploads source material (PDF or text), questions stay within that material. Otherwise, generation can optionally be grounded in live web search. Neither path is load-bearing — the system degrades gracefully if grounding is unavailable.

## Key outcomes for the assignment

- A working multi-agent pipeline with clean separation of concerns: orchestration, agents, and the LLM client are independently testable layers.
- A custom orchestrator (no LangChain/LangGraph) — a deliberate pedagogical choice that keeps the agent control flow explicit and inspectable.
- A deterministic evaluation core that makes the "agentic" decisions reproducible rather than relying on the model's self-assessment.
- Provider-agnostic LLM integration: the default is Alibaba DashScope with Qwen, but the system runs against any OpenAI-compatible endpoint via a single config change.
- A comprehensive automated test suite (~104 tests) that never calls the real API, so correctness can be verified offline and for free.

## Operational footprint

- **Runtime:** Python 3.11+, a Gradio web UI, in-memory session state. Completed sessions are appended to a local JSONL file — no database to operate.
- **Dependencies:** the OpenAI SDK (against any compatible endpoint), Pydantic, Gradio, plus small libraries for PDF handling. One API key is required to run live; optional keys enable web-search grounding.
- **Cost control:** diagnostic tests are cached, LLM calls for question generation are fanned out concurrently to reduce wall-clock latency, and duplicate questions are filtered before they reach the student.

## Team

| Name | ID |
|------|------|
| Ayberk Karataban | 2201256 |
| Kuzey Berk Yılmaz | 2200014 |
