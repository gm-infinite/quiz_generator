# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo

- GitHub: https://github.com/gm-infinite/quiz_generator
- Active branch: `ayberk` (this is where work lands; no `main` exists yet).

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

# smoke test the LLM wiring (one structured call)
python -m scripts.smoke_test

# tests (20 deterministic, no real API calls)
pytest -q
pytest tests/test_orchestrator.py -q             # one file
pytest tests/test_agents.py::test_evaluator_pass_by_absolute_threshold -q   # one test
```

`OPENROUTER_API_KEY` is read from `.env` (preferred) or `.env.example` as a fallback — `llm/llm_client.py` loads both via `python-dotenv`. The key is required for `app.py`, `run_cli`, and `smoke_test`.

**Tests must never call the real API.** All tests in `tests/` use the `FakeLLMClient` fixture (`fake_client`) defined in `tests/conftest.py`, which returns canned Pydantic instances per schema. If you write a new test, pass `fake_client` (or instantiate `FakeLLMClient()` directly) — do not import `LLMClient`. If a test needs a specific LLM response, call `fake_client.set(SchemaType, lambda prompt: SchemaType(...))` to override the default for that schema only.

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
- **`llm/llm_client.py`** is the single chokepoint for every LLM call. Retries, model swaps, rate limiting all live here. Agents must not import the openai SDK directly. The client is provider-agnostic via OpenAI-compatible APIs — default is OpenRouter + Qwen, but swapping to DashScope, Ollama, or Hugging Face is just a `core/config.py` edit.

The **UI (`ui/views.py`)** only imports `Orchestrator`, `SessionState`, `Phase`, and `config`. It must not import anything from `agents/`. UI events call orchestrator methods which return a new `SessionState`; a `@gr.render(inputs=state)` block re-renders the quiz/report area on every state change — that's how PRACTICE → PRACTICE loop-backs and PRACTICE → DONE transitions display automatically without manual visibility toggling.

### Determinism rule (load-bearing)

Scoring, weak-topic detection, and the pass decision are **pure Python in `tools/scoring.py` and `agents/evaluator_agent.py`**. The LLM is asked for `EvaluationResult` and `WeaknessAnalysis` only to get human-readable rationale text — the agent **overwrites** any score/pass/accuracy field the LLM tries to set. If you add a new evaluation criterion, compute it deterministically and only ask the LLM for prose. Tests in `tests/test_agents.py` (`test_evaluator_ignores_llm_pass_claim`, `test_weakness_analyzer_uses_math_for_accuracy_not_llm`) lock this in — don't loosen them.

### Pass rule

In `agents/evaluator_agent.py`: pass iff `practice_score ≥ PASS_ABSOLUTE_THRESHOLD (0.70)` OR `(practice_score - diagnostic_score) ≥ PASS_IMPROVEMENT_DELTA (0.20)`. Thresholds live in `core/config.py`. The Orchestrator hard-caps at `MAX_PRACTICE_ROUNDS = 3` regardless of pass status.

### Loop-back behavior

When a practice round fails, `Orchestrator.submit_practice_answers` recomputes `weak_topics` from the **practice** results (not the original diagnostic) before triggering the next round. The next round chases what's still wrong, not the original gaps.

### Question generator concurrency

`agents/question_generator.py` uses `ThreadPoolExecutor(max_workers=min(4, len(weak_topics)))` to fan LLM calls out per weak topic — wall time on multi-topic rounds is `~max(per-topic)` rather than `sum(per-topic)`. Results are sorted by topic index after the join so question order is deterministic. The agent **overwrites returned `id` and `topic` fields** (`p{iter}-{topicIdx}-{qIdx}`) to prevent collisions across topics/rounds and to force the topic tag to match the requested weak topic.

Note: `generate_with_search` is currently an alias for `generate_structured` — Qwen has no native search tool. Real search grounding (via Tavily/Serper) is a Phase 2 follow-up.

### Structured output

Every LLM call goes through `llm/llm_client.py` with a Pydantic schema from `llm/schemas.py`. The client tries OpenAI's strict structured-output path first (`beta.chat.completions.parse(response_format=PydanticClass)`), then falls back to JSON mode + manual `schema.model_validate_json(...)` if the model rejects strict json_schema. Agents never see this — they always get a validated Pydantic instance.

### Vocabulary note

User-visible strings say "initial test" / "test"; internal field names still say `diagnostic_*` (`diagnostic_questions`, `diagnostic_score`, etc.). Don't rename the fields without a good reason — the churn isn't worth it. Just keep the UI/CLI/prompt-facing copy consistent with "test."

## Stack

- Python 3.11+ (developed on 3.13)
- `openai` SDK (used against any OpenAI-compatible endpoint — default OpenRouter)
- Pydantic v2, Gradio (6.x — note `theme` and `css` belong on `launch()`, not `Blocks()`)
- In-memory `SessionState` only — no database, no persistence between sessions
- Default model: `qwen/qwen3.6-plus:free` (`core/config.LLM_MODEL`) on OpenRouter. The free-tier catalog rotates — if the default 404s, pick a current `:free` Qwen model at https://openrouter.ai/models?max_price=0. Other options listed in `core/config.py`.

## What NOT to do

- Don't introduce LangChain / LangGraph / any agent framework. The custom orchestrator is a deliberate pedagogical choice for the assignment.
- Don't call the openai SDK from inside an agent — route through `LLMClient`.
- Don't inline prompt strings in agent files — all templates live in `llm/prompts.py`.
- Don't have the UI talk to agents directly. UI → Orchestrator → Agents, one way.
- Don't trust LLM-returned scores/pass-decisions/accuracy numbers — compute deterministically and use the LLM only for rationale text.
