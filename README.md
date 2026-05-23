#  QuizMind — A Multi-Agent Adaptive Learning System

---

## What is this?

QuizMind is a multi agent AI system that figures out what you *actually* don't know and then relentlessly quizzes you on exactly that until you do.

You pick a subject. The system takes over from there.

It gives you a diagnostic quiz, analyzes where you struggled, generates fresh practice questions targeted at your weak spots, evaluates how you did, and decides whether to keep pushing or move on. No static question banks. No one size fits all quizzes. Just a loop that keeps going until you've genuinely improved.

---

## Why did we build this?

We've both sat through study sessions where we spent 80% of the time reviewing things we already knew and 20% (if that) on the stuff that actually trips us up. It's inefficient, and honestly, a bit demoralizing.

The idea was simple: what if the system could figure out your weak spots automatically, generate new questions specifically for those gaps, and not let you off the hook until you've actually gotten better? That's the problem we wanted to solve.

There's also a real challenge here technically this isn't just a chatbot or a static quiz app. It requires multiple agents making decisions, handing off to each other, and looping back when needed. Building that pipeline cleanly was the interesting engineering problem.

---

## How it works

There are five agents working together under an orchestrator that decides who goes next:

**Orchestrator** — the traffic controller. Looks at where the student is in the process and decides which agent should act next. It's the only agent with a full picture of the session.

**Assessment Agent** — kicks things off with a diagnostic quiz to map out what you know across different topics.

**Weakness Analyzer** — goes through your answers, spots the patterns, and produces a structured breakdown of where you're struggling.

**Question Generator** — uses an LLM to create brand new practice questions targeting your weak areas.

**Evaluator & Feedback Agent** — grades your answers on the new questions and decides: did you actually improve, or do you need another round and gives a feedback


The loop keeps running until the Evaluator is satisfied. The Orchestrator makes sure no one skips ahead.

---

## Tech stack

- **LLM backbone:** Qwen (via OpenRouter, OpenAI-compatible API). Provider-agnostic — the client also works against DashScope, Ollama, or any other OpenAI-compatible endpoint via `core/config.py`.
- **Agent orchestration:** Custom multi-agent pipeline
- **Tools used:** Python execution, session storage
- **Language:** Python

## Setup

1. Create and activate a virtual environment: `python -m venv .venv && source .venv/bin/activate` (Windows: `.venv\Scripts\activate`).
2. Install dependencies: `pip install -r requirements.txt`.
3. Sign up at https://openrouter.ai, create an API key, and add it to `.env` as `OPENROUTER_API_KEY=sk-or-v1-...`.
4. Run `python -m scripts.smoke_test` to confirm the wiring.
5. Run `python app.py` and open http://127.0.0.1:7860.

The default model is the free-tier `qwen/qwen3.6-plus:free`. To change it, edit `LLM_MODEL` in `core/config.py`.

---

## Team

| Name |
|------|
| Ayberk Karataban  2201256 |
| Kuzey Berk Yılmaz 2200014 |

---

