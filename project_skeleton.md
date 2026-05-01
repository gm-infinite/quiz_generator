# QuizMind — Technical Report
### Upload #2 | SEN4018 Agentic AI | Spring 2026

---

## Overview

QuizMind is a multi-agent adaptive learning system built in Python, powered by Google
Gemini 3.1 Flash. The core idea is straightforward: instead of throwing a fixed set of
questions at every student, the system first figures out where you are actually struggling,
then generates new questions specifically for those gaps, and keeps going until you have
demonstrably gotten better.

This document covers how we are building it — the architecture, the agent design, the
project structure, the tools we are using, and who is responsible for what.

---

## High-Level Architecture

The system is built around a central Orchestrator that manages a pipeline of specialized
agents. Each agent has a single, well-defined job. The Orchestrator reads the current
session state and decides which agent runs next. It never skips steps and never ends the
session until the Evaluator gives the green light.

```
User Input (Subject + Level)
        |
        v
+---------------------+
|    ORCHESTRATOR     |  <- manages state, decides next agent
+----------+----------+
           |
     +-----v------+
     | Assessment |  -> diagnostic quiz covering broad subtopics
     +-----+------+
           |
     +-----v----------+
     | Weakness       |  -> analyzes answers, outputs weak topic list
     | Analyzer       |
     +-----+----------+
           |
     +-----v----------+
     | Question       |  -> generates fresh targeted questions
     | Generator      |
     +-----+----------+
           |
     +-----v--------------+
     | Evaluator &        |  -> grades answers, decides: pass or loop back
     | Feedback Agent     |
     +-----+--------------+
           |
      Improved? --No--> back to Question Generator
           |
          Yes
           |
           v
      Final report shown to user
```

---

## Project Structure

The codebase is organized as a flat Python package with a clear separation between
agent logic, orchestration, model interfaces, and the user interface. We picked this
layout deliberately so that each agent can be written, tested, and debugged in isolation
without needing to spin up the full pipeline.

```
quizmind/
├── app.py                      # Gradio entry point, launches the UI
├── requirements.txt            # Python dependencies
├── .env.example                # Template for API keys (real .env is gitignored)
├── README.md                   # Project overview
│
├── core/
│   ├── __init__.py
│   ├── orchestrator.py         # Main control loop, state transitions
│   ├── session_state.py        # Session state dataclass and helpers
│   └── config.py               # Constants: thresholds, loop limits, model name
│
├── agents/
│   ├── __init__.py
│   ├── base_agent.py           # Abstract base class all agents inherit from
│   ├── assessment_agent.py     # Builds the diagnostic quiz
│   ├── weakness_analyzer.py    # Scores answers, identifies weak topics
│   ├── question_generator.py   # Generates targeted practice questions
│   ├── evaluator_agent.py      # Grades practice round, decides loop or end
│   ├── feedback_agent.py       # Writes the final human-readable report
│   └── judge_agent.py          # LLM-in-the-loop evaluation of the whole session
│
├── llm/
│   ├── __init__.py
│   ├── gemini_client.py        # Wrapper around google-generativeai SDK
│   ├── prompts.py              # Centralized prompt templates per agent
│   └── schemas.py              # Pydantic models for structured LLM output
│
├── tools/
│   ├── __init__.py
│   ├── web_search.py           # Wrapper for Gemini's grounding / Google Search
│   └── scoring.py              # Pure Python scoring helpers (no LLM calls)
│
├── ui/
│   ├── __init__.py
│   ├── components.py           # Reusable Gradio UI blocks
│   └── views.py                # Page layouts for each session phase
│
└── tests/
    ├── test_orchestrator.py
    ├── test_agents.py
    └── test_scoring.py
```

### Why this layout

- **`core/` vs `agents/`** — orchestration logic is fundamentally different from agent logic. The Orchestrator is pure control flow with no LLM calls. The agents do the actual reasoning. Splitting them keeps each side testable on its own.
- **`llm/` as a separate layer** — every agent talks to Gemini through the same `gemini_client`. If we ever swap the model or add retries, rate limiting, or caching, we change one file instead of six.
- **`prompts.py` is centralized** — keeping all prompt templates in one file makes it easy to compare them, version them together, and tune them without hunting through agent code.
- **`tools/` separated from `agents/`** — tools are deterministic utilities (a web search call, a scoring function). They are not agents and should not be confused with agents. This matters when explaining the system because students often conflate "tool" with "agent."
- **`ui/` isolated from logic** — Gradio code does not touch the agents directly. It only reads and writes session state through the Orchestrator. This means we can replace Gradio with Streamlit or a CLI without touching any agent code.

---

## Agents — Detailed Breakdown

### Orchestrator

The Orchestrator is the backbone of the system. It holds the full session state — what
subject the student picked, which topics came up weak, how many practice rounds have
been completed, and whether the Evaluator has signed off. It decides which agent runs
next based on those state flags. It does not call the LLM itself. It is purely control logic.

The state machine has six phases: `INIT → ASSESSMENT → ANALYSIS → PRACTICE → EVALUATION → FEEDBACK`,
with a back-edge from `EVALUATION` to `PRACTICE` when the student needs another round.

We also added a maximum loop limit (3 rounds by default) so the system does not get
stuck chasing a student who keeps getting the same questions wrong indefinitely.

### Assessment Agent

This is the first agent the student actually interacts with. It takes the subject and
difficulty level as input, prompts Gemini to generate a 10-question diagnostic quiz
covering a broad range of subtopics, and presents those questions through the Gradio UI.
Every question comes back as structured JSON with a topic tag attached, so the Weakness
Analyzer knows exactly which area each wrong answer belongs to.

### Weakness Analyzer Agent

Once the student finishes the diagnostic, this agent goes through the results and groups
wrong answers by topic. It calculates an accuracy score per topic and flags anything below
60% as a weak area. The output is a ranked list of those weak topics, which gets passed
directly to the Question Generator. If the student aced everything, the Orchestrator skips
ahead to feedback.

This agent does not strictly need an LLM — the scoring is deterministic. We use the LLM
only to write a short natural-language explanation of why a topic was flagged, which gets
shown in the final report.

### Question Generator Agent

This is where the adaptive part actually happens. The agent receives the weak topic list
and uses Gemini 3.1 Flash with web search grounding to generate 5 new, targeted practice
questions per weak topic. The questions are generated fresh every run — there is no static
question bank. This means a student can go through multiple rounds and not see the same
question twice.

### Evaluator and Feedback Agent

After the student answers the practice questions, the Evaluator grades them and computes
an improvement delta compared to the diagnostic round. If the student's score improved by
at least 20% or reached 70% overall, the session ends. Otherwise, the Orchestrator is told
to loop back and run another round of question generation.

The Feedback Agent then writes the final report covering what topics the student has now
mastered, what still needs work, and what they should focus on next.

### Judge Agent (Evaluation Framework)

A separate Judge Agent runs at the end of each session as the LLM-in-the-loop evaluator
required by the assignment. It looks at the full session history and scores three things:

- Relevance — were the generated questions actually targeting the weak topics that were identified?
- Difficulty calibration — were the questions appropriately challenging for the student's level?
- Improvement validity — did the score improvement reflect real learning, or were the practice questions just easier than the diagnostic?

The Judge returns a score from 0 to 10 for each criterion with a short written justification.
These scores are logged and shown to the student alongside their final report.

---

## Session State

The system does not use any external dataset. All questions are generated dynamically by
the LLM based on the subject the student provides. Session data lives in memory as a
dataclass for the duration of the session:

```python
@dataclass
class SessionState:
    subject: str
    level: str                       # beginner / intermediate / advanced
    diagnostic_results: list         # per-question results from Assessment
    weak_topics: list                # output of Weakness Analyzer
    practice_results: list           # per-question results from practice round
    iteration: int                   # how many practice rounds have run
    passed: bool                     # Evaluator decision
    judge_scores: dict | None        # populated at end of session
```

---

## Frameworks and Tools

| Component | Tool |
|-----------|------|
| LLM | Google Gemini 3.1 Flash (via google-generativeai SDK) |
| Agent orchestration | Custom Python classes |
| Web search | Gemini native grounding with Google Search |
| Structured output | Pydantic models passed via `response_json_schema` |
| UI | Gradio (deployed on Hugging Face Spaces) |
| State management | In-memory dataclass per session |
| Language | Python 3.11 |

We deliberately avoided LangChain or LangGraph. Using a custom orchestrator means we
have full visibility into what fires when, which makes debugging significantly easier and
keeps the architecture transparent. For a course focused on understanding agentic systems,
we thought it made more sense to build the control loop ourselves rather than abstract
it away.

---

## Deployment Plan

The finished project will be deployed on Hugging Face Spaces with a Gradio interface.
It will be publicly accessible without requiring a login. The Gemini API key will be stored
as a Hugging Face secret and never hardcoded in the repository.



*SEN4018 — Agentic AI, Bahçeşehir University, Spring 2026*
