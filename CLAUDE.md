# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo

- GitHub: https://github.com/gm-infinite/quiz_generator
- Active branch: `ayberk` (this is where work lands). `main` exists and is the PR base.

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

# time end-to-end assessment latency
python -m scripts.bench

# tests (~104, deterministic, no real API calls)
pytest -q
pytest tests/test_orchestrator.py -q             # one file
pytest tests/test_agents.py::test_evaluator_pass_by_absolute_threshold -q   # one test
```

`DASHSCOPE_API_KEY` is read from `.env` (preferred) or `.env.example` as a fallback — `llm/llm_client.py` loads both via `python-dotenv`. The client also accepts `OPENROUTER_API_KEY` / `LLM_API_KEY` for other providers. The key is required for `app.py`, `run_cli`, `smoke_test`, and `bench`.

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
- **`llm/llm_client.py`** is the single chokepoint for every LLM call. Retries, model swaps, rate limiting all live here. Agents must not import the openai SDK directly. The client is provider-agnostic via OpenAI-compatible APIs — default is Alibaba DashScope + Qwen (`LLM_API_BASE` points at `dashscope-intl.aliyuncs.com`), but swapping to OpenRouter, Ollama, or Hugging Face is just a `core/config.py` edit.

The **UI (`ui/views.py`)** only imports `Orchestrator`, `SessionState`, `Phase`, and `config`. It must not import anything from `agents/`. UI events call orchestrator methods which return a new `SessionState`; a `@gr.render(inputs=state)` block re-renders the quiz/report area on every state change — that's how PRACTICE → PRACTICE loop-backs and PRACTICE → DONE transitions display automatically without manual visibility toggling.

### Determinism rule (load-bearing)

Scoring, weak-topic detection, and the pass decision are **pure Python in `tools/scoring.py` and `agents/evaluator_agent.py`**. The LLM is asked for `EvaluationResult` and `WeaknessAnalysis` only to get human-readable rationale text — the agent **overwrites** any score/pass/accuracy field the LLM tries to set. If you add a new evaluation criterion, compute it deterministically and only ask the LLM for prose. Tests in `tests/test_agents.py` (`test_evaluator_ignores_llm_pass_claim`, `test_weakness_analyzer_uses_math_for_accuracy_not_llm`) lock this in — don't loosen them.

### Pass rule

In `agents/evaluator_agent.py`: pass iff `practice_score ≥ PASS_ABSOLUTE_THRESHOLD (0.70)` OR `(practice_score - diagnostic_score) ≥ PASS_IMPROVEMENT_DELTA (0.20)`. Thresholds live in `core/config.py`. The round cap is per-session (`SessionState.max_rounds`, default `MAX_PRACTICE_ROUNDS = 3`); the user can override it at `start()`, clamped to 1–`MAX_PRACTICE_ROUNDS_LIMIT (5)`. The Orchestrator stops the loop once `iteration >= max_rounds` regardless of pass status.

### Loop-back behavior

When a practice round fails, `Orchestrator.submit_practice_answers` recomputes `weak_topics` from the **practice** results (not the original diagnostic) before triggering the next round. The next round chases what's still wrong, not the original gaps.

### Question generator concurrency

`agents/question_generator.py` uses `ThreadPoolExecutor(max_workers=min(4, len(weak_topics)))` to fan LLM calls out per weak topic — wall time on multi-topic rounds is `~max(per-topic)` rather than `sum(per-topic)`. Results are sorted by topic index after the join so question order is deterministic. The agent **overwrites returned `id` and `topic` fields** (`p{iter}-{topicIdx}-{qIdx}`) to prevent collisions across topics/rounds and to force the topic tag to match the requested weak topic.

Cross-round repeats: the generator asks the LLM (via `avoid_prompts`) to skip prior stems, but it ignores that often enough that `tools/dedupe.py` applies a hard post-filter — normalized-stem exact match plus token-overlap threshold — to reject duplicates. Don't rely on the prompt instruction alone.

Note: `generate_with_search(prompt, schema, search_query=...)` grounds generation with real web search via `tools/web_search.py` (Tavily or Serper, auto-detected from `TAVILY_API_KEY` / `SERPER_API_KEY` in `.env`). Snippets are injected above the prompt via `prompts.search_grounding_block`. No key, empty `search_query`, or any search failure degrades silently to plain `generate_structured` — search is never load-bearing, and tests must never hit the network (`_post_json` is always monkeypatched; see `tests/test_web_search.py`). Sessions with uploaded source material skip search entirely (questions must stay within the source). Search constants (`SEARCH_ENABLED`, `SEARCH_MAX_RESULTS`, etc.) live in `core/config.py`.

### Judge agent (post-loop)

`agents/judge_agent.py` runs **once after the state machine terminates** (pass or round cap) to produce qualitative `JudgeScores` over the full session transcript — diagnostic + every practice round, weak topics, and final scores. It's the only place an LLM judgment lands on the session as a whole; it does not influence the pass decision (the deterministic rule above already fired) and writes only to `state.judge_scores`.

### Structured output

Every LLM call goes through `llm/llm_client.py` with a Pydantic schema from `llm/schemas.py`. The client tries OpenAI's strict structured-output path first (`beta.chat.completions.parse(response_format=PydanticClass)`), then falls back to JSON mode + manual `schema.model_validate_json(...)` if the model rejects strict json_schema. Agents never see this — they always get a validated Pydantic instance.

### Vocabulary note

User-visible strings say "initial test" / "test"; internal field names still say `diagnostic_*` (`diagnostic_questions`, `diagnostic_score`, etc.). Don't rename the fields without a good reason — the churn isn't worth it. Just keep the UI/CLI/prompt-facing copy consistent with "test."

## Stack

- Python 3.11+ (developed on 3.13)
- `openai` SDK (used against any OpenAI-compatible endpoint — default DashScope)
- Pydantic v2, Gradio (6.x — note `theme` and `css` belong on `launch()`, not `Blocks()`)
- `pypdf` for uploaded-source extraction (`tools/file_loader.py`); `fpdf2` for PDF report export (Unicode font support)
- In-memory `SessionState` during a run; completed sessions are appended to `~/.quizmind/sessions.jsonl` by `tools/session_storage.py` — no database
- Default model: `qwen-plus` (`core/config.LLM_MODEL`) on DashScope. `USE_STRICT_PARSE` is `False` because DashScope's OpenAI-compat endpoint doesn't reliably honor strict JSON mode — flip it on if you switch to a provider that does. Other model/provider options are commented in `core/config.py`.

## What NOT to do

- Don't introduce LangChain / LangGraph / any agent framework. The custom orchestrator is a deliberate pedagogical choice for the assignment.
- Don't call the openai SDK from inside an agent — route through `LLMClient`.
- Don't inline prompt strings in agent files — all templates live in `llm/prompts.py`.
- Don't have the UI talk to agents directly. UI → Orchestrator → Agents, one way.
- Don't trust LLM-returned scores/pass-decisions/accuracy numbers — compute deterministically and use the LLM only for rationale text.
