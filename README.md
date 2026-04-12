# 🧠 QuizMind — A Multi-Agent Adaptive Learning System

> *Because studying the same thing you already know is just procrastination with extra steps.*

---

## What is this?

QuizMind is a multi-agent AI system that figures out what you *actually* don't know — and then relentlessly quizzes you on exactly that until you do.

You pick a subject. The system takes over from there.

It gives you a diagnostic quiz, analyzes where you struggled, generates fresh practice questions targeted at your weak spots, evaluates how you did, and decides whether to keep pushing or move on. No static question banks. No one-size-fits-all quizzes. Just a loop that keeps going until you've genuinely improved.

---

## Why did we build this?

We've both sat through study sessions where we spent 80% of the time reviewing things we already knew and 20% (if that) on the stuff that actually trips us up. It's inefficient, and honestly, a bit demoralizing.

The idea was simple: what if the system could figure out your weak spots automatically, generate new questions specifically for those gaps, and not let you off the hook until you've actually gotten better? That's the problem we wanted to solve.

There's also a real challenge here technically — this isn't just a chatbot or a static quiz app. It requires multiple agents making decisions, handing off to each other, and looping back when needed. Building that pipeline cleanly was the interesting engineering problem.

---

## How it works

There are six agents working together under an orchestrator that decides who goes next:

**🎯 Orchestrator** — the traffic controller. Looks at where the student is in the process and decides which agent should act next. It's the only agent with a full picture of the session.

**📋 Assessment Agent** — kicks things off with a diagnostic quiz to map out what you know across different topics.

**🔍 Weakness Analyzer** — goes through your answers, spots the patterns, and produces a structured breakdown of where you're struggling.

**✏️ Question Generator** — uses web search and an LLM to create brand new practice questions targeting your weak areas. No recycled questions.

**✅ Evaluator Agent** — grades your answers on the new questions and decides: did you actually improve, or do you need another round?

**📝 Feedback Agent** — wraps everything up with a clear, human-readable report on what got better and what still needs work.

The loop keeps running until the Evaluator is satisfied. The Orchestrator makes sure no one skips ahead.

---

## Tech stack

- **LLM backbone:** Claude (via Anthropic API)
- **Agent orchestration:** Custom multi-agent pipeline
- **Tools used:** Web search, Python execution, session storage
- **Deployment:** Hugging Face Spaces (Gradio interface)
- **Language:** Python

---

## Team

| Name | Role |
|------|------|
| [Team Member 1] | Agent architecture & orchestration logic |
| [Team Member 2] | Question generation, evaluation, UI |

*(Solo/duo project for SEN4018 — Agentic AI, Spring 2026)*

---

## Project timeline

| Milestone | Date |
|-----------|------|
| Initial documentation & motivation | April 12, 2026 |
| Technical report & architecture details | May 3, 2026 |
| Finished & deployed project | May 31, 2026 |
| Presentation | Weeks 14–15 |

---

## Running it locally

```bash
git clone https://github.com/[your-repo]/quizmind
cd quizmind
pip install -r requirements.txt
python app.py
```

You'll need an Anthropic API key set as `ANTHROPIC_API_KEY` in your environment.

---

## Status

🟡 In progress — Upload #1 submitted. Building out agent pipeline next.

---

*Built for SEN4018 @ Bahçeşehir University, Spring 2026.*
