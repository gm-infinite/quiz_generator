# QuizMind — How the Code Works (and How to Run It)

This is a walkthrough of the repo for someone landing on the `kuzey` branch and trying to understand what's going on before adding new features. It mirrors what's in `CLAUDE.md` and `project_skeleton.md`, but with more "where do I click, what calls what" detail.

---

## 1. The 10-second mental model

QuizMind is a small **state machine** that walks one `SessionState` object through six phases. The UI never talks to the LLM. The agents never talk to each other. There is exactly one entry point (`Orchestrator`) and exactly one LLM chokepoint (`LLMClient`).

```
UI / CLI  ─▶  Orchestrator  ─▶  Agents  ─▶  LLMClient  ─▶  Qwen (OpenRouter)
                  ▲                              │
                  └──── mutated SessionState ◀───┘
```

The orchestrator decides *which* agent runs next. Each agent reads the state, calls the LLM (or pure Python for scoring), writes results back. The UI just renders whatever the latest `SessionState` looks like.

---

## 2. The state machine

Defined in `core/session_state.py` (`Phase` enum) and driven by `core/orchestrator.py`:

```
INIT
  │ start(subject, level)
  ▼
ASSESSMENT          ← AssessmentAgent builds the broad initial test
  │ submit_diagnostic_answers()
  ▼
ANALYSIS            ← WeaknessAnalyzer scores answers + flags weak topics
  │
  │ (if weak_topics is empty → skip to FEEDBACK)
  ▼
PRACTICE            ← QuestionGenerator fans out grounded calls per topic
  │ submit_practice_answers()
  ▼
EVALUATION          ← EvaluatorAgent applies the pass rule
  │
  ├── passed OR iteration >= MAX_PRACTICE_ROUNDS → FEEDBACK
  └── otherwise → recompute weak_topics from practice → PRACTICE again
  ▼
FEEDBACK            ← FeedbackAgent + JudgeAgent (final report + judge scores)
  ▼
DONE
```

Two important rules baked in:

1. **The loop cap is hard.** The user picks the round cap per session (1–5, default `MAX_PRACTICE_ROUNDS = 3` in `core/config.py`); it's stored as `SessionState.max_rounds`. Even if the student is still failing, the loop exits when the cap is hit.
2. **Weak topics get recomputed each loop.** When a practice round fails, `Orchestrator.submit_practice_answers` rebuilds `weak_topics` from the **practice** results (not the original diagnostic), so the next round chases what's still wrong.

---

## 3. Folder map

```
quiz_generator/
├── app.py                   # Gradio entry point — `python app.py`
├── requirements.txt
├── .env.example             # template for OPENROUTER_API_KEY
├── README.md
├── CLAUDE.md                # rules for Claude Code (and useful for humans)
├── project_skeleton.md      # design doc, audience = grader
│
├── core/
│   ├── orchestrator.py      # the state machine. NEVER calls the LLM.
│   ├── session_state.py     # the one dataclass everything passes around
│   └── config.py            # thresholds, model name, loop cap
│
├── agents/
│   ├── base_agent.py        # tiny ABC: run(state) -> state
│   ├── assessment_agent.py  # broad-coverage initial test
│   ├── weakness_analyzer.py # deterministic scoring + LLM rationale text
│   ├── question_generator.py# grounded calls per weak topic (thread pool)
│   ├── evaluator_agent.py   # pass-rule logic; LLM only for rationale
│   ├── feedback_agent.py    # human-readable final report
│   └── judge_agent.py       # LLM-as-judge scoring of the whole session
│
├── llm/
│   ├── llm_client.py        # the ONLY file that imports the openai SDK
│   ├── prompts.py           # every prompt template lives here
│   └── schemas.py           # Pydantic schemas for structured output
│
├── tools/
│   └── scoring.py           # pure Python: grade, per-topic accuracy, weak-topic detection
│
├── ui/
│   └── views.py             # Gradio Blocks. Imports Orchestrator only.
│
├── scripts/
│   ├── run_cli.py           # terminal driver (no Gradio)
│   ├── smoke_test.py        # one-call sanity check on the LLM wiring
│   └── bench.py
│
└── tests/                   # 20+ tests, none of them hit the real API
    ├── conftest.py          # FakeLLMClient fixture
    ├── test_orchestrator.py
    ├── test_agents.py
    └── test_scoring.py
```

---

## 4. Who does what, in execution order

### `Orchestrator` (`core/orchestrator.py`)
Owns the state machine. Construction wires up one instance of every agent. It exposes three things the UI/CLI actually calls:

- `start(subject, level)` → returns a state with `diagnostic_questions` populated
- `submit_diagnostic_answers(state, answers)` → grades, finds weak topics, generates first practice round (or jumps to feedback if there are none)
- `submit_practice_answers(state, answers)` → grades, decides pass/fail, either finalizes or loops

**Rule:** the orchestrator never imports the openai SDK and never calls `self.client.generate_*`. It only inspects what agents wrote to state.

### `AssessmentAgent` (`agents/assessment_agent.py`)
One call. Asks the LLM for `DIAGNOSTIC_QUESTION_COUNT = 10` multiple-choice questions, broad coverage across subtopics. Each question is a `Question` Pydantic instance with `id`, `topic`, `prompt`, `choices`, `correct_answer`, `explanation`. Writes them into `state.diagnostic_questions`.

### `WeaknessAnalyzer` (`agents/weakness_analyzer.py`)
1. **Pure Python.** Calls `tools.scoring.grade_answers` to build per-question grading records.
2. **Pure Python.** Computes `per_topic_accuracy` and flags topics below `WEAK_TOPIC_THRESHOLD = 0.60`.
3. **LLM call.** Asks the LLM for short prose explanations per weak topic — **never for the numbers themselves**. The agent reads only `analysis.weak_topics[i].explanation` and discards anything the LLM said about accuracy.

If no topics fall below threshold, `state.weak_topics` is left empty and the orchestrator skips practice.

### `QuestionGenerator` (`agents/question_generator.py`)
Per weak topic, one LLM call (`generate_with_search`, which first runs a Tavily/Serper web search on the subject + weak topic and injects the snippets into the prompt — see `tools/web_search.py`; without an API key it generates ungrounded) for `PRACTICE_QUESTIONS_PER_TOPIC = 5` questions. The calls are fanned out across a `ThreadPoolExecutor(max_workers=min(4, len(weak_topics)))`, so wall time is roughly `max(per-topic)` rather than `sum(per-topic)`.

Two extra correctness moves:
- Results are sorted by topic index after the join so question order is deterministic.
- The agent **overwrites** the LLM-returned `id` and `topic` fields with `f"p{iteration+1}-{i+1}-{j+1}"` and the requested weak-topic name, so ids never collide across topics/rounds and the topic tag actually matches.

It also passes `avoid_prompts` (all prior question stems from diagnostic + earlier practice) into the prompt, so the LLM is steered away from repeating itself across rounds.

### `EvaluatorAgent` (`agents/evaluator_agent.py`)
The deterministic decision sits here:

```python
passed = (
    practice_score >= PASS_ABSOLUTE_THRESHOLD       # 0.70
    or (practice_score - diagnostic_score) >= PASS_IMPROVEMENT_DELTA   # 0.20
)
```

The LLM is still called (with the `EvaluationResult` schema) but **only for the `rationale` string**. Its `passed`/`score` fields are ignored. Two tests in `tests/test_agents.py` lock this in:
- `test_evaluator_ignores_llm_pass_claim`
- `test_weakness_analyzer_uses_math_for_accuracy_not_llm`

Don't loosen these — the determinism is the whole point.

### `FeedbackAgent` (`agents/feedback_agent.py`)
One LLM call. Produces `FinalReport` (mastered topics / still-weak topics / next steps / summary). Merged into `state.final_report` alongside the evaluator's rationale.

### `JudgeAgent` (`agents/judge_agent.py`)
LLM-in-the-loop evaluation. Sees the whole session summary, returns three scores 0–10:
- **Relevance** — did practice questions actually target the flagged weak topics?
- **Difficulty calibration** — appropriate for the stated level?
- **Improvement validity** — was the score gain real, or were practice questions just easier?

These scores show up at the bottom of the final report. They're for the assignment's "LLM-as-judge" requirement, not for the loop decision.

### `LLMClient` (`llm/llm_client.py`)
The single chokepoint. Provider-agnostic via the OpenAI-compatible API surface — by default it points at OpenRouter, but the same code works against DashScope, Ollama, or Hugging Face by editing `LLM_API_BASE` and `LLM_MODEL` in `core/config.py`. Two methods:
- `generate_structured(prompt, schema)` — structured JSON output validated against a Pydantic schema. Tries OpenAI's strict `beta.chat.completions.parse(response_format=...)` first, then falls back to JSON mode + manual Pydantic validation if the model rejects strict json_schema.
- `generate_with_search(prompt, schema, search_query=None)` — runs `search_query` through `tools/web_search.py` (Tavily or Serper, auto-detected from which API key is set) and prepends the snippets to the prompt before calling `generate_structured`. Degrades silently to ungrounded generation when no key is configured, the query is empty, or the search fails.

Reads `OPENROUTER_API_KEY` (or `LLM_API_KEY`) from `.env`, falling back to `.env.example`.

### `ui/views.py`
A single Gradio `Blocks`. Pattern:
- One `gr.State(SessionState())` holds the session.
- `start_btn.click(...)` calls `Orchestrator.start(...)`.
- A `@gr.render(inputs=state)` block re-runs every time the state changes. Based on `s.phase`, it renders the assessment quiz, the practice quiz, or the final report. This is what makes `PRACTICE → PRACTICE` loop-backs display automatically without any manual visibility toggling.
- The UI imports only `Orchestrator`, `SessionState`, `Phase`, `config`. It must not import anything from `agents/`.

---

## 5. The determinism rule (load-bearing)

If you take one thing away from this file, take this:

> **Never trust LLM-returned scores, pass decisions, or accuracy numbers. Compute them in Python. Use the LLM only for prose.**

The whole architecture leans on this. `tools/scoring.py` is the math. `agents/evaluator_agent.py` writes the final `passed` flag. Tests assert that even if a fake LLM lies about the score or the pass, the agent overrides it.

When you add a new metric or a new pass criterion, compute it deterministically in `tools/scoring.py` (or directly in the agent) and only ask the LLM for the human-readable explanation.

---

## 6. Running it

### Setup (once)

```bash
# from repo root
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# add your key
cp .env.example .env
# then edit .env and set OPENROUTER_API_KEY=sk-or-v1-...
```

Get an OpenRouter API key at https://openrouter.ai. The default model (`qwen/qwen3.6-plus:free`) is free; no credit card needed. Free-tier limits cap you around ~20 requests/minute and a few hundred per day, which is enough for ~20–30 full sessions per day.

> **Branch note.** You're on `kuzey`. There's no `main` yet — `ayberk` and `kuzey` are the two work branches. Pull from `ayberk` if you want to start from Ayberk's latest, or just keep iterating on `kuzey`.

### Smoke-test the wiring

Cheapest possible sanity check — one structured call, three questions:

```bash
python -m scripts.smoke_test
```

If this errors, the rest won't work. Common causes: missing key, wrong `LLM_MODEL` in `core/config.py` (the free-tier catalog rotates), blocked outbound network.

### Run the full app (Gradio)

```bash
python app.py
# open http://127.0.0.1:7860
```

You'll see a subject box and a beginner/intermediate/advanced radio. Pick something narrow at first (`"basic Python"`, `"geography of Turkey"`) — broad subjects burn more tokens.

### Run end-to-end without the UI

```bash
python -m scripts.run_cli
```

Same loop, terminal-only. Useful for debugging agents without Gradio in the way.

### Tests

```bash
pytest -q                                          # all 20+ tests
pytest tests/test_orchestrator.py -q               # one file
pytest tests/test_agents.py::test_evaluator_pass_by_absolute_threshold -q
```

Tests **must never hit the real API**. They use `FakeLLMClient` from `tests/conftest.py`, which returns canned Pydantic instances per schema. If you write a new test, pass the `fake_client` fixture — don't instantiate `LLMClient`. To force a specific LLM response for one schema, call `fake_client.set(SchemaType, lambda prompt: SchemaType(...))`.

---

## 7. Tuning knobs (everything in `core/config.py`)

| Constant | Default | What it does |
|---|---|---|
| `LLM_API_BASE` | `https://openrouter.ai/api/v1` | OpenAI-compatible endpoint. Swap to DashScope / Ollama / Hugging Face by changing this line. |
| `LLM_MODEL` | `qwen/qwen3.6-plus:free` | Free-tier Qwen (May 2026). Catalog rotates — verify the exact name at https://openrouter.ai/models?max_price=0. Other options: `qwen/qwen3.6-plus-preview:free` (newer, logs data), `qwen/qwen3-coder:free` (code-tuned), `qwen/qwen3.6-plus` (paid). |
| `DIAGNOSTIC_QUESTION_COUNT` | 10 | Size of the broad initial test. |
| `PRACTICE_QUESTIONS_PER_TOPIC` | 5 | How many questions per weak topic per round. |
| `WEAK_TOPIC_THRESHOLD` | 0.60 | Topics under this accuracy get flagged as weak. |
| `PASS_ABSOLUTE_THRESHOLD` | 0.70 | Practice score that ends the loop outright. |
| `PASS_IMPROVEMENT_DELTA` | 0.20 | Improvement over diagnostic that also ends the loop. |
| `MAX_PRACTICE_ROUNDS` | 3 | Default round cap; user can pick 1–`MAX_PRACTICE_ROUNDS_LIMIT` per session. Loop exits whether passed or not. |
| `MAX_PRACTICE_ROUNDS_LIMIT` | 5 | Hard ceiling for the per-session round cap. |
| `LEVELS` | `("beginner", "intermediate", "advanced")` | Choices shown in the UI radio. |

---

## 8. Where to plug in your ideas

Some natural extension points, all of which fit cleanly into the current architecture:

**Add a new phase** (e.g. a "review wrong answers" phase between EVALUATION and FEEDBACK)
1. Add the value to the `Phase` enum in `core/session_state.py`.
2. Add a method to `Orchestrator` that runs in that phase.
3. Add a UI branch in `ui/views.py` under the `@gr.render(inputs=state)` block.

**Add a new agent**
1. Create `agents/your_agent.py` inheriting `BaseAgent`. Implement `run(state) -> state`.
2. Add the prompt to `llm/prompts.py` (don't inline it).
3. Add the response schema to `llm/schemas.py`.
4. Wire it into `Orchestrator.__init__` and call it from the right phase.

**Add a new evaluation criterion** (e.g. "consistency across rounds")
1. Add a pure-Python function to `tools/scoring.py`.
2. Have `EvaluatorAgent` compute it deterministically.
3. If you want a human-readable explanation, ask the LLM for *only the prose* and merge it into `final_report`.

**Persistence** (the current system is in-memory only)
- Add a `core/persistence.py` that serializes `SessionState` to JSON.
- Hook save/load into the orchestrator's phase boundaries.
- Don't put I/O inside agents — keep that boundary.

**Different output format** (e.g. open-ended questions instead of MCQ)
- Adjust the `Question` schema in `llm/schemas.py`.
- Update the relevant prompts.
- The hard part is grading — `tools.scoring.grade_answers` currently does exact string match. You'd need an LLM-grading helper (deterministic about pass/fail, LLM about why) for free-response.

---

## 9. Things not to do

These are repeated from `CLAUDE.md` because they're easy to forget:

- **Don't** import the openai SDK from inside an agent. Route through `LLMClient`.
- **Don't** inline prompt strings in agent files. All templates live in `llm/prompts.py`.
- **Don't** have the UI talk to agents directly. UI → Orchestrator → Agents, one direction.
- **Don't** trust LLM scores, pass decisions, or accuracy. Compute deterministically; ask the LLM only for rationale.
- **Don't** introduce LangChain / LangGraph / any agent framework. The custom orchestrator is the assignment.
- **Don't** rename `diagnostic_*` fields to `initial_test_*`. User-facing copy says "initial test" / "test"; internal fields stay `diagnostic_*`.

---

## 10. Quick troubleshooting

| Symptom | Likely cause |
|---|---|
| `RuntimeError: OPENROUTER_API_KEY is not set` | `.env` missing or key not exported. Check `cat .env`. |
| 404 / model-not-found from OpenRouter | Wrong `LLM_MODEL` in `core/config.py`. The free catalog rotates — pick a currently-listed `:free` model at https://openrouter.ai/models?max_price=0. |
| 429 rate-limit errors | Hitting OpenRouter's free-tier per-minute or daily cap. The client already retries 429s with exponential backoff; if it's the daily cap, either wait, add ~$5 of credit and use a paid Qwen, or run Qwen locally via Ollama. |
| Practice round never ends | `MAX_PRACTICE_ROUNDS` cap should always force exit. If it doesn't, check that `state.iteration` is being incremented in `_run_practice_round`. |
| Same questions repeated across rounds | `avoid_prompts` list is empty or being reset. Check `QuestionGenerator.run` — it should aggregate diagnostic + all prior practice stems. |
| LLM returned weird JSON, tests pass anyway | Expected. `LLMClient._chat_parsed` falls back from strict json_schema to JSON-mode + manual Pydantic validation. Agents only see validated Pydantic instances. |
| UI doesn't update after submit | The `@gr.render(inputs=state)` block only re-runs when `state` is reassigned. Make sure the orchestrator method returns the (mutated) state and the handler routes it back to `state_var`. |

---

That should be everything. The codebase is small on purpose — 8 agent/core files, one client, one prompts file, one scoring file. If something feels like it doesn't fit, it probably belongs in one of those existing buckets rather than a new layer.
