# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

QuizMind — a multi-agent adaptive quiz system. Student picks subject + level, the app runs a broad-coverage test, identifies weak topics, generates targeted practice questions, evaluates improvement, and loops until the pass rule fires or the round cap (3) is hit. Built for SEN4018 Agentic AI, Bahçeşehir University, Spring 2026.

## Commands

```bash
# install
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# run the app (Gradio, http://127.0.0.1:7860)
python app.py

# run end-to-end in terminal (no UI)
python -m scripts.run_cli

# smoke test the Gemini wiring (one structured call)
python -m scripts.smoke_test

# tests (20 deterministic, no real API calls)
pytest -q
pytest tests/test_orchestrator.py -q             # one file
pytest tests/test_agents.py::test_evaluator_pass_by_absolute_threshold -q   # one test
```

`GEMINI_API_KEY` is read from `.env` (preferred) or `.env.example` as a fallback — `llm/gemini_client.py` loads both via `python-dotenv`. The key is required for `app.py`, `run_cli`, and `smoke_test`; tests don't need it (they use a `FakeGeminiClient` from `tests/conftest.py`).

## Architecture

State flows through one `SessionState` dataclass driven by a state machine in `core/orchestrator.py`:

```
INIT → ASSESSMENT → ANALYSIS → PRACTICE → EVALUATION → FEEDBACK → DONE
                                  ^            |
                                  +----loop----+   (max 3 iterations, then DONE)
```

Three layers, each with a hard rule:

- **`core/orchestrator.py`** owns the state machine and is the only entry point the UI/CLI calls. It **never calls the LLM** — it delegates to agents and inspects what they wrote to `SessionState`. Adding a new phase means adding a method here and updating `Phase`.
- **`agents/*`** each do one thing and return the mutated `SessionState`. They construct prompts (from `llm/prompts.py`), call `self.client.generate_structured` or `generate_with_search`, and write results back. They never import each other.
- **`llm/gemini_client.py`** is the single chokepoint for every Gemini call. Retries, model swaps, rate limiting all live here. Agents must not import `google.genai` directly.

The **UI (`ui/views.py`)** only imports `Orchestrator`, `SessionState`, `Phase`, and `config`. It must not import anything from `agents/`. UI events call orchestrator methods which return a new `SessionState`; a `@gr.render(inputs=state)` block re-renders the quiz/report area on every state change — that's how PRACTICE → PRACTICE loop-backs and PRACTICE → DONE transitions display automatically without manual visibility toggling.

### Determinism rule (load-bearing)

Scoring, weak-topic detection, and the pass decision are **pure Python in `tools/scoring.py` and `agents/evaluator_agent.py`**. The LLM is asked for `EvaluationResult` and `WeaknessAnalysis` only to get human-readable rationale text — the agent **overwrites** any score/pass/accuracy field the LLM tries to set. If you add a new evaluation criterion, compute it deterministically and only ask the LLM for prose. Tests in `tests/test_agents.py` (`test_evaluator_ignores_llm_pass_claim`, `test_weakness_analyzer_uses_math_for_accuracy_not_llm`) lock this in — don't loosen them.

### Pass rule

In `agents/evaluator_agent.py`: pass iff `practice_score ≥ PASS_ABSOLUTE_THRESHOLD (0.70)` OR `(practice_score - diagnostic_score) ≥ PASS_IMPROVEMENT_DELTA (0.20)`. Thresholds live in `core/config.py`. The Orchestrator hard-caps at `MAX_PRACTICE_ROUNDS = 3` regardless of pass status.

### Loop-back behavior

When a practice round fails, `Orchestrator.submit_practice_answers` recomputes `weak_topics` from the **practice** results (not the original diagnostic) before triggering the next round. The next round chases what's still wrong, not the original gaps.

### Question generator concurrency

`agents/question_generator.py` uses `ThreadPoolExecutor(max_workers=min(4, len(weak_topics)))` to fan grounded Gemini calls out per weak topic — wall time on multi-topic rounds is `~max(per-topic)` rather than `sum(per-topic)`. Results are sorted by topic index after the join so question order is deterministic. The agent **overwrites returned `id` and `topic` fields** (`p{iter}-{topicIdx}-{qIdx}`) to prevent collisions across topics/rounds and to force the topic tag to match the requested weak topic.

### Structured output

Every LLM call goes through `llm/gemini_client.py` with a Pydantic schema from `llm/schemas.py` passed as `response_schema`. `generate_with_search` has a fallback path for the (occasional) case where Gemini rejects combining a search tool with a response schema — it does the grounded call free-form, then a second call to reformat into the schema. Agents never see this — they always get a validated Pydantic instance.

### Vocabulary note

User-visible strings say "initial test" / "test"; internal field names still say `diagnostic_*` (`diagnostic_questions`, `diagnostic_score`, etc.). Don't rename the fields without a good reason — the churn isn't worth it. Just keep the UI/CLI/prompt-facing copy consistent with "test."

## Stack

- Python 3.11+ (developed on 3.13)
- `google-genai` (the modern SDK, not the deprecated `google-generativeai`)
- Pydantic v2, Gradio (6.x — note `theme` and `css` belong on `launch()`, not `Blocks()`)
- In-memory `SessionState` only — no database, no persistence between sessions
- Default model: `gemini-2.5-flash` (`core/config.GEMINI_MODEL`). For more speed, swap to `gemini-2.5-flash-lite`. Don't use `gemini-3.1-flash` — the README says it but that model doesn't exist.

## What NOT to do

- Don't introduce LangChain / LangGraph / any agent framework. The custom orchestrator is a deliberate pedagogical choice for the assignment.
- Don't call `google.genai` from inside an agent — route through `GeminiClient`.
- Don't inline prompt strings in agent files — all templates live in `llm/prompts.py`.
- Don't have the UI talk to agents directly. UI → Orchestrator → Agents, one way.
- Don't trust LLM-returned scores/pass-decisions/accuracy numbers — compute deterministically and use the LLM only for rationale text.
