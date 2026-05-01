# QuizMind — Technical Report
### Upload #2 | SEN4018 Agentic AI | 

---

## Overview

QuizMind is a multi-agent adaptive learning system built in Python, powered by Google Gemini.
The core idea is straightforward: instead of throwing a fixed set of questions at every student,
the system first figures out where you're actually struggling, then generates new questions
specifically for those gaps, and keeps going until you've demonstrably gotten better.

This document covers how we're building it — the architecture, the agent design, the tools
we're using, and who is responsible for what.

---

## Architecture

The system is built around a central Orchestrator that manages a pipeline of specialized agents.
Each agent has a single, well-defined job. The Orchestrator reads the current session state and
decides which agent runs next. It never skips steps and never ends the session until the
Evaluator gives the green light.

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

## Agents — Detailed Breakdown

### Orchestrator

The Orchestrator is the backbone of the system. It holds the full session state — what subject
the student picked, which topics came up weak, how many practice rounds have been completed,
and whether the Evaluator has signed off. It decides which agent runs next based on those
state flags. It does not call the LLM itself. It is purely control logic.

We also added a maximum loop limit (3 rounds by default) so the system does not get stuck
chasing a student who keeps getting the same questions wrong indefinitely.

### Assessment Agent

This is the first agent the student actually interacts with. It takes the subject and difficulty
level as input, prompts Gemini to generate a 10-question diagnostic quiz covering a broad range
of subtopics, and presents those questions through the Gradio UI. Every question comes back
as structured data with a topic tag attached, so the Weakness Analyzer knows exactly which
area each wrong answer belongs to.

### Weakness Analyzer Agent

Once the student finishes the diagnostic, this agent goes through the results and groups
wrong answers by topic. It calculates an accuracy score per topic and flags anything below
60% as a weak area. The output is a ranked list of those weak topics, which gets passed
directly to the Question Generator. If the student aced everything, the Orchestrator skips
ahead to feedback.

### Question Generator Agent

This is where the adaptive part actually happens. The agent receives the weak topic list
and uses Gemini with web search grounding to generate 5 new, targeted practice questions
per weak topic. The questions are generated fresh every run — there is no static question
bank. This means a student can go through multiple rounds and not see the same question twice.

### Evaluator and Feedback Agent

After the student answers the practice questions, this agent grades them and computes
an improvement delta compared to the diagnostic round. If the student's score improved
by at least 20% or reached 70% overall, the session ends and the feedback report is
generated. Otherwise, the Orchestrator is told to loop back and run another round of
question generation.

The feedback report covers what topics the student has now mastered, what still needs
work, and what they should focus on next.

---

## Data Flow

The system does not use any external dataset. All questions are generated dynamically
by the LLM based on the subject the student provides.

Session data lives in memory as a Python dictionary for the duration of the session:

```python
session_state = {
    "subject": str,
    "level": str,                    # beginner / intermediate / advanced
    "diagnostic_results": list,      # per-question results from Assessment
    "weak_topics": list,             # output of Weakness Analyzer
    "practice_results": list,        # per-question results from practice round
    "iteration": int,                # how many practice rounds have run
    "passed": bool                   # Evaluator decision
}
```

---

## Frameworks and Tools

| Component | Tool |
|-----------|------|
| LLM | Google Gemini 1.5 Flash (via google-generativeai SDK) |
| Agent orchestration | Custom Python classes |
| Web search | Gemini native grounding with Google Search |
| UI | Gradio |
| State management | In-memory Python dict per session |
| Language | Python 3.11 |

We deliberately avoided LangChain or LangGraph. Using a custom orchestrator means we have
full visibility into what fires when, which makes debugging significantly easier and keeps
the architecture transparent. For a course focused on understanding agentic systems, we
thought it made more sense to build the control loop ourselves rather than abstract it away.

---

## Evaluation Framework

To satisfy the LLM-in-the-loop evaluation requirement, we are including a separate Judge Agent
that runs at the end of each session. It evaluates the session across three dimensions:

- Relevance — were the generated questions actually targeting the weak topics that were identified?
- Difficulty calibration — were the questions appropriately challenging for the student's level?
- Improvement validity — did the score improvement reflect real learning, or were the practice questions just easier than the diagnostic?

The Judge Agent returns a score from 0 to 10 for each criterion with a short written justification.
These scores are logged and shown to the student alongside their final report.

---

## Deployment Plan

The finished project will be deployed on Hugging Face Spaces with a Gradio interface.
It will be publicly accessible without requiring a login. The Gemini API key will be stored
as a Hugging Face secret and never hardcoded in the repository.

---

## Team Responsibilities

| Name | Student ID | Responsibilities |
|------|------------|-----------------|
| Ayberk Karataban | 2201256 | Orchestrator logic, Assessment Agent, Weakness Analyzer, overall pipeline integration |
| Kuzey Berk Yılmaz | 2200014 | Question Generator, Evaluator and Feedback Agent, Judge Agent, Gradio UI, Hugging Face deployment |


