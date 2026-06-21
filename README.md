# QuizMind — A Multi-Agent Adaptive Learning System

QuizMind figures out what you *actually* don't know, then relentlessly quizzes you on exactly that until you do.

You pick a subject and level. The system runs a broad diagnostic test, identifies your weak topics, generates fresh practice questions aimed at those gaps, evaluates whether you improved, and loops until you pass or the round cap is hit. No static question banks, no one-size-fits-all quizzes — just a feedback loop built from agents that hand off to each other.

Built for **SEN4018 Agentic AI**, Bahçeşehir University, Spring 2026.

---

## Why we built it

Most study time gets spent reviewing things you already know. The 20% that actually trips you up gets the least attention. QuizMind inverts that: it detects weak spots automatically, generates targeted questions for them, and won't let you off the hook until you've genuinely improved.

Technically, this isn't a chatbot or a static quiz app — it's a pipeline of agents making decisions, handing off, and looping back. Building that loop cleanly was the interesting problem.

---

## Features

- **Adaptive loop** — diagnostic → weak-topic analysis → targeted practice → evaluation → repeat (up to 3 rounds), chasing what's *still* wrong each round, not the original gaps.
- **Deterministic scoring** — all scoring, weak-topic detection, and the pass/fail decision are pure Python. The LLM is only ever asked for human-readable rationale; its scores are overwritten.
- **Source-grounded questions** — upload a PDF or paste text and questions stay within your material.
- **Web-search grounding** — without uploaded sources, generation can be grounded in real web results (Tavily or Serper), degrading silently to ungrounded generation if no key is set.
- **PDF report export** — download a full session report (Unicode font support).
- **Session history** — completed sessions persist to `~/.quizmind/sessions.jsonl` and show in the UI.
- **Final judge** — a qualitative LLM pass over the whole transcript after the loop ends (does not affect the pass decision).
- **Keyboard shortcuts** — keys `1`–`4` select answers during a quiz.
- **Provider-agnostic** — works against any OpenAI-compatible endpoint (DashScope, OpenRouter, Ollama, Hugging Face) via one config edit.

---

## How it works

State flows through a single `SessionState` driven by a state machine in `core/orchestrator.py`. The orchestrator is the only entry point the UI/CLI calls, and it *never* calls the LLM — it delegates to agents and inspects what they wrote.

```
INIT → ASSESSMENT → ANALYSIS → PRACTICE → EVALUATION → FEEDBACK → DONE
                                  ^            |
                                  +----loop----+   (max 3 rounds, then DONE)
```

The agents, each doing one thing:

| Agent | Role |
|-------|------|
| **Orchestrator** | Traffic controller. Owns the state machine; decides who acts next. Never calls the LLM. |
| **Assessment Agent** | Runs the broad diagnostic test that maps what you know across topics. |
| **Weakness Analyzer** | Finds the patterns in your answers and produces a structured breakdown of weak topics (accuracy computed in Python, not by the LLM). |
| **Question Generator** | Creates fresh practice questions per weak topic, fanned out concurrently. |
| **Evaluator & Feedback** | Grades practice answers deterministically, decides pass/fail, and writes feedback prose. |
| **Judge** | Runs once after the loop ends for a qualitative read on the whole session. |

**Pass rule:** you pass iff `practice_score ≥ 0.70` **OR** `(practice_score − diagnostic_score) ≥ 0.20`. The loop also stops once the round cap (default 3, max 5) is reached, regardless of pass status.

---

## Architecture

Three layers, each with a hard rule:

- **`core/`** — the orchestrator + `SessionState`. The state machine lives here and only here.
- **`agents/`** — each agent does one thing, returns the mutated `SessionState`, and never imports another agent. Prompts come from `llm/prompts.py`.
- **`llm/llm_client.py`** — the single chokepoint for *every* LLM call. Retries, model swaps, structured output, and rate limiting all live here. Agents never touch the openai SDK directly.

The **UI (`ui/views.py`)** only talks to the orchestrator — never to agents directly. Flow is one-way: `UI → Orchestrator → Agents`.

```
quiz_generator/
├── app.py                  # Gradio entry point
├── core/                   # orchestrator, session state, config
├── agents/                 # one file per agent
├── llm/                    # client, prompts, Pydantic schemas
├── tools/                  # scoring, dedupe, web search, file/PDF, storage
├── ui/                     # Gradio views
├── scripts/                # CLI runner, smoke test, benchmark
└── tests/                  # ~104 deterministic tests (no real API calls)
```

---

## Setup

```bash
# 1. virtual environment
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. dependencies
pip install -r requirements.txt

# 3. API key — add to a .env file in the project root
echo "DASHSCOPE_API_KEY=sk-..." > .env

# 4. confirm the wiring
python -m scripts.smoke_test

# 5. run the app → http://127.0.0.1:7860
python app.py
```

The default provider is **Alibaba DashScope** with the `qwen-plus` model (set in `core/config.py`). The client also reads `OPENROUTER_API_KEY` and `LLM_API_KEY`, so to use OpenRouter, Ollama, or Hugging Face instead, point `LLM_API_BASE` and `LLM_MODEL` at your provider and set the matching key — no code changes beyond `core/config.py`.

**Optional keys** (both degrade silently if absent):
- `TAVILY_API_KEY` or `SERPER_API_KEY` — enables web-search grounding.

---

## Usage

```bash
python app.py                # Gradio UI at http://127.0.0.1:7860
python -m scripts.run_cli    # full end-to-end run in the terminal, no UI
python -m scripts.smoke_test # one structured LLM call to verify wiring
python -m scripts.bench      # time end-to-end assessment latency
```

---

## Configuration

All tunables live in `core/config.py`:

| Constant | Default | Meaning |
|----------|---------|---------|
| `DIAGNOSTIC_QUESTION_COUNT` | 10 | Questions in the initial test |
| `PRACTICE_QUESTIONS_PER_TOPIC` | 5 | Practice questions per weak topic |
| `WEAK_TOPIC_THRESHOLD` | 0.60 | Accuracy below this flags a topic as weak |
| `PASS_ABSOLUTE_THRESHOLD` | 0.70 | Practice score that ends the loop outright |
| `PASS_IMPROVEMENT_DELTA` | 0.20 | Improvement over diagnostic that ends the loop |
| `MAX_PRACTICE_ROUNDS` | 3 | Default round cap (per-session override, capped at 5) |
| `SEARCH_ENABLED` | True | Master switch for web-search grounding |

---

## Testing

```bash
pytest -q                                          # all ~104 tests
pytest tests/test_orchestrator.py -q               # one file
pytest tests/test_agents.py::test_evaluator_pass_by_absolute_threshold -q   # one test
```

Tests are deterministic and **never call the real API** — they use a `FakeLLMClient` fixture that returns canned Pydantic instances per schema.

---

## Tech stack

- **Python 3.11+** (developed on 3.13)
- **`openai` SDK** against any OpenAI-compatible endpoint (default: DashScope + Qwen)
- **Pydantic v2** for structured LLM output
- **Gradio 6.x** for the UI
- **`pypdf`** for uploaded-source extraction; **`fpdf2`** for PDF report export
- In-memory `SessionState` during a run; completed sessions append to `~/.quizmind/sessions.jsonl` — no database

---

## Team

| Name | ID |
|------|------|
| Ayberk Karataban | 2201256 |
| Kuzey Berk Yılmaz | 2200014 |
