# QuizMind — Final Implementation Plan

Two phases. Phase 1 ships alone, gets merged to GitHub, then we start Phase 2.

- **Phase 1 — Qwen migration.** Same features, same behavior, swap the LLM. Nothing else changes. Must work end-to-end before any feature work begins.
- **Phase 2 — New features.** Everything from round 2: loading states, library, file sources, persistence, per-question feedback, spaced repetition. Built on top of the Qwen-powered base.

Branch: `kuzey`.

---

## Confirmed decisions (locked, no more questions on these)

| Topic | Decision |
|---|---|
| Library location | `~/.quizmind/library.json`; plan per-user keying when deploying |
| Replay scoring | Show score, flag "review — not counted" |
| Similar-topics level | Ask user each time |
| File sources | Per-session only, vanish after session |
| PDF strategy | Gemini File API (Phase 2 → OpenAI-compat: skip File API, use local pypdf primarily) |
| UI structure | `gr.Tabs` with Quiz / Library |
| Review screen | Dedicated phase between rounds — full breakdown w/ explanations, Continue button |
| Quota error UX | Primary "come back tomorrow" + secondary "browse library" link |
| Rate limits | Deferred — see §1.6 below |
| SR toggle scope | Global default + per-session override |
| Resume banner | Non-blocking; user can ignore. Soft reminder if WIP file > 7 days old |
| LLM client refactor | Done as part of Phase 1 |
| Abandoned sessions | Library records as `status="abandoned"` |

---

## Assumptions I'm making without asking

These are the calls I made on your behalf. Tell me if any are wrong.

- **LLM provider: OpenRouter** as default. OAI-compatible API, single signup, no Alibaba Cloud account needed, free-tier Qwen variants available. The client is provider-agnostic — switching to DashScope, Ollama, or Hugging Face later is a `.env` change, not a code change.
- **Default Qwen model: a free-tier Qwen variant on OpenRouter (`:free` suffix).** Zero cost, no billing required. Free tiers are rate-limited (typically ~20 requests/min, daily cap of a few hundred) but adequate for development and grading runs. If quality is insufficient or rate limits bite, swap to a paid Qwen model (~$0.40 per million tokens) — it's a one-line config change. We'll pick the specific model name at signup time since OpenRouter's free-tier catalog rotates; recommended starting points listed in §1.2.
- **Search grounding dropped in Phase 1.** Qwen has no native Google Search tool. The `generate_with_search` method becomes a thin alias for `generate_structured` with a TODO comment. The question generator still works — questions are slightly less factually grounded but the LLM's training data is enough for typical academic subjects. Real search grounding (via Tavily/Serper) is a Phase 2 follow-up if we want it back.
- **Client class renamed `GeminiClient` → `LLMClient`.** It's no longer Gemini-specific. Module renamed `llm/gemini_client.py` → `llm/llm_client.py`. Agents update one import line each.
- **Structured output: try OpenAI's `beta.chat.completions.parse(response_format=PydanticClass)` first, fall back to JSON mode + manual Pydantic validation.** Not every Qwen-on-OpenRouter combo supports strict json_schema; the fallback handles the rest.

---

# Phase 1 — Qwen migration

The goal: every existing feature works identically, but the LLM behind it is Qwen on OpenRouter instead of Gemini on Google. Smoke test passes, all existing tests pass, you can complete a full session end-to-end.

## 1.1. Provider setup (you do this once)

1. Go to https://openrouter.ai and sign up (Google/GitHub login works).
2. **Skip billing — we're starting on the free tier.** No credit card needed. You can add billing later if you want better models or higher rate limits.
3. Browse https://openrouter.ai/models?max_price=0 and pick a Qwen `:free` model with the highest context window / best benchmark numbers currently available. Good candidates as of recent catalogs (verify these still exist at signup time):
   - `qwen/qwen-2.5-72b-instruct:free` — strongest free Qwen, slower
   - `qwen/qwen-2.5-7b-instruct:free` — faster, lighter quality
   - `qwen/qwq-32b-preview:free` — reasoning-tuned variant
4. Create an API key. Copy it.
5. In `C:\Users\kuzey\Documents\GitHub\quiz_generator\.env`, replace the Gemini key with:
   ```
   OPENROUTER_API_KEY=sk-or-v1-...your_key...
   ```
6. The old `GEMINI_API_KEY` line can stay (we'll remove it from the codebase but no harm leaving it in `.env` temporarily) or be deleted.

**Note on free-tier rate limits:** OpenRouter's free tier typically caps you at ~20 requests/minute and a few hundred per day. A full QuizMind session is ~6–10 LLM calls (1 assessment + 1 weakness analysis + N practice topics × 1 each + 1 evaluator + 1 feedback + 1 judge), so you can comfortably run 20–30 sessions a day. If you hit limits during a dev session, wait a minute and retry — the SDK's retry-on-429 in `_chat` will handle it automatically.

## 1.2. Config changes

Edit `core/config.py`:

```python
"""Centralized constants. Tune here, not inline."""

# LLM provider config
LLM_API_BASE = "https://openrouter.ai/api/v1"   # OpenRouter (default)
# Alternatives:
#   "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"   # Alibaba DashScope
#   "http://localhost:11434/v1"                                # Ollama (local)
#   "https://api-inference.huggingface.co/v1"                  # Hugging Face

LLM_MODEL = "qwen/qwen-2.5-72b-instruct:free"
# Free tier default. Verify the exact model name at https://openrouter.ai/models?max_price=0
# at signup time — OpenRouter's free catalog rotates as model providers add/remove free hosting.
#
# Other options:
#   "qwen/qwen-2.5-7b-instruct:free"   — faster free option, lower quality
#   "qwen/qwq-32b-preview:free"        — free reasoning-tuned variant
#   "qwen/qwen-2.5-72b-instruct"       — paid, ~$0.40/M tokens, no rate limits worth mentioning
#   "qwen/qwen-2.5-32b-instruct"       — paid middle ground
#   "qwen2.5:7b"                        — if running Ollama locally

# Quiz constants (unchanged from before)
DIAGNOSTIC_QUESTION_COUNT = 10
PRACTICE_QUESTIONS_PER_TOPIC = 5
WEAK_TOPIC_THRESHOLD = 0.60
PASS_ABSOLUTE_THRESHOLD = 0.70
PASS_IMPROVEMENT_DELTA = 0.20
MAX_PRACTICE_ROUNDS = 3
LEVELS = ("beginner", "intermediate", "advanced")
```

## 1.3. Requirements

`requirements.txt`:

```
openai>=1.50.0       # replaces google-genai for OpenAI-compat API
pydantic>=2.0
python-dotenv>=1.0
gradio>=4.0
pytest>=8.0
```

Run after editing:
```powershell
pip install -r requirements.txt
pip uninstall google-genai      # optional cleanup
```

## 1.4. New LLM client

**Delete** `llm/gemini_client.py`.
**Create** `llm/llm_client.py`:

```python
"""Single chokepoint for every LLM call.

Provider-agnostic via OpenAI-compatible APIs. Default is OpenRouter + Qwen,
but the same code works with DashScope, Ollama, Hugging Face, or any other
OpenAI-compat endpoint by changing LLM_API_BASE + LLM_MODEL in core/config.

If you need retries, caching, rate limiting, or a model swap, change it here.
Agents must NOT import the openai SDK directly.
"""
from __future__ import annotations

import os
import time
from typing import TypeVar

from dotenv import load_dotenv
from openai import OpenAI, APIError, APIStatusError
from pydantic import BaseModel

from core import config

T = TypeVar("T", bound=BaseModel)

load_dotenv()
load_dotenv(".env.example", override=False)

_RETRY_ATTEMPTS = 5
_RETRY_BASE_DELAY = 2.0


def _is_transient(exc: Exception) -> bool:
    """5xx and 429 are worth retrying."""
    if isinstance(exc, APIStatusError):
        return exc.status_code >= 500 or exc.status_code == 429
    if isinstance(exc, APIError):
        return True  # generic transport errors
    return False


class LLMClient:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 base_url: str | None = None):
        key = api_key or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("LLM_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Add it to .env or export it."
            )
        self._client = OpenAI(
            api_key=key,
            base_url=base_url or config.LLM_API_BASE,
        )
        self._model = model or config.LLM_MODEL

    def _chat(self, **kwargs):
        """Wrap chat.completions with retry on transient errors."""
        last_exc: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                return self._client.chat.completions.create(**kwargs)
            except Exception as exc:
                if not _is_transient(exc):
                    raise
                last_exc = exc
                if attempt == _RETRY_ATTEMPTS - 1:
                    break
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                print(
                    f"[llm] transient error ({type(exc).__name__}); "
                    f"retrying in {delay:.0f}s (attempt {attempt + 1}/{_RETRY_ATTEMPTS})"
                )
                time.sleep(delay)
        assert last_exc is not None
        raise last_exc

    def _chat_parsed(self, schema: type[T], **kwargs) -> T:
        """Chat call that returns a validated Pydantic instance."""
        last_exc: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                resp = self._client.beta.chat.completions.parse(
                    response_format=schema, **kwargs,
                )
                parsed = resp.choices[0].message.parsed
                if parsed is None:
                    # parse() returned but couldn't structure the output —
                    # fall through to JSON-mode fallback below.
                    raise ValueError("parsed=None")
                return parsed  # type: ignore[return-value]
            except Exception as exc:
                if not _is_transient(exc):
                    break
                last_exc = exc
                if attempt == _RETRY_ATTEMPTS - 1:
                    break
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                time.sleep(delay)

        # Fallback: JSON mode + manual Pydantic validation.
        # Used when a model doesn't fully support strict json_schema.
        resp = self._chat(
            response_format={"type": "json_object"},
            **kwargs,
        )
        text = resp.choices[0].message.content or ""
        return schema.model_validate_json(text)

    def generate_structured(self, prompt: str, schema: type[T]) -> T:
        """Call the model and return a validated Pydantic instance."""
        return self._chat_parsed(
            schema=schema,
            model=self._model,
            messages=[
                {"role": "system",
                 "content": "You are a structured-data generator. Respond only "
                            "with JSON matching the requested schema."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )

    def generate_with_search(self, prompt: str, schema: type[T]) -> T:
        """Same as generate_structured. Search grounding dropped in Phase 1.

        TODO(phase-2): wire in an external search tool (Tavily/Serper) and
        inline results into the prompt before generation.
        """
        return self.generate_structured(prompt, schema)
```

## 1.5. Update agent imports

Every file in `agents/` that has `from llm.gemini_client import GeminiClient` becomes `from llm.llm_client import LLMClient`. The constructor signature is identical, so the only change is the import line and the type-hint name.

Files affected:
- `agents/base_agent.py`
- (None of the concrete agent files import the client directly — they receive it as `self.client` from BaseAgent. So `base_agent.py` is the only one.)

In `core/orchestrator.py`:
```python
from llm.llm_client import LLMClient   # was: from llm.gemini_client import GeminiClient

class Orchestrator:
    def __init__(self, client: LLMClient | None = None):
        self.client = client or LLMClient()
        ...
```

## 1.6. Rate limiting — punted

Originally Phase 2 §4 had aggressive client-side rate limiting because Gemini's free tier was burning your quota. **Decision: skip this for now.**

Reason: even on the free tier, OpenRouter's per-minute limits are forgiving enough that the SDK's retry-on-429 (already in `_chat`, with exponential backoff) handles transient bursts. The daily cap is the real ceiling, and that's a "come back tomorrow" problem solved by the WIP persistence work in Phase 2A — not by client-side throttling.

We **keep** the WIP session persistence from §4b — that's still gold regardless of which provider/tier you're on, because crashes, browser closures, and daily-cap exhaustion can all wipe a session.

If free-tier daily caps become a real friction point during development (e.g., you can't finish a debugging round in one sitting), the two cheapest escalations are:
1. Add $5 of OpenRouter credit and flip to the paid model — limits effectively disappear.
2. Run Qwen locally via Ollama — no limits, no cost, needs ~8GB RAM for the 7B model.

## 1.7. Smoke test

`scripts/smoke_test.py` already uses `GeminiClient` — update the import:

```python
from llm.llm_client import LLMClient

def main() -> int:
    client = LLMClient()
    prompt = assessment_prompt(subject="basic Python", level="beginner", n_questions=3)
    result: QuestionSet = client.generate_structured(prompt, QuestionSet)
    ...
```

Run it:
```powershell
python -m scripts.smoke_test
```

Expected output: 3 Python questions printed, "Smoke test passed."

If this works, Phase 1 is functional.

## 1.8. Test suite

`tests/conftest.py` defines `FakeGeminiClient`. Rename to `FakeLLMClient`:

```python
class FakeLLMClient:
    """Stand-in for LLMClient. Returns canned Pydantic instances per schema."""
    ...
```

Update the fixture name from `fake_client` (it can stay the same — fixture name is independent of class name) but ensure all test files import `FakeLLMClient` not `FakeGeminiClient`.

Run:
```powershell
pytest -q
```

All existing tests should pass without behavioral changes.

## 1.9. Documentation updates

- `README.md` — replace "Gemini" mentions with "Qwen via OpenRouter," update setup instructions.
- `CLAUDE.md` — update the `## Stack` section (replace `google-genai` with `openai`) and the "Don't call `google.genai` from inside an agent" rule to say "Don't call the openai SDK from inside an agent — route through `LLMClient`."
- `HOW_IT_WORKS.md` — update LLM client section to reference `LLMClient` and the new env var.
- `.env.example` — replace `GEMINI_API_KEY=your_key_here` with `OPENROUTER_API_KEY=your_key_here`.
- `project_skeleton.md` — leave it; that's the historical design doc, not a live spec.

## 1.10. Phase 1 acceptance checklist

Before merging Phase 1 to GitHub, verify:

- [ ] `pip install -r requirements.txt` clean install with no `google-genai` dependency.
- [ ] `python -m scripts.smoke_test` returns 3 questions and exits 0.
- [ ] `pytest -q` all green.
- [ ] `python app.py` launches the UI.
- [ ] You can run one full session end-to-end (initial test → practice round → final report).
- [ ] The judge agent at the end of a session still produces scores 0–10 per criterion.
- [ ] No code anywhere imports `google.genai` or references `GeminiClient`.
- [ ] `.env.example` reflects the new key name.
- [ ] `README.md` setup instructions work for someone with no prior context.

## 1.11. Phase 1 effort

~3–5 hours total. The bulk is in §1.4 (rewriting the client) and §1.8 (verifying tests still pass).

---

# Phase 2 — New features

After Phase 1 ships to GitHub, we start here. Each phase below is independently shippable.

## Phase 2A — UX safety net (1 day)

**Goal:** No more losing work.

### A1. Loading states + button protection
Two-stage `.then()` click handlers in `ui/views.py`. Button disables instantly, label swaps to `"Generating…"`, spinner markdown appears. Work stage runs; on success/failure the button re-enables. Wrapped in `try/except` so exceptions don't leave the button stuck.

### A2. Crash-safe session persistence (formerly §4b)
WIP snapshot file at every orchestrator phase boundary:
```
~/.quizmind/wip/session-{uuid}.json
```
Atomic writes via `tmp + os.replace`. New `core/persistence.py` module owns the I/O.

`SessionState` gains `session_id: str` (UUID set in `Orchestrator.start`). New `Phase.WAITING` for cases where we recover from an API failure.

**Recovery flow on app startup:** `ui/views.py` checks `~/.quizmind/wip/` for any session files. If found, shows a non-blocking banner:
> "Unfinished quiz on `geography of Turkey` (saved 14 min ago, practice round 2). [Resume] [Discard]"

If WIP file is older than 7 days, banner adds a soft reminder: "This has been sitting here a while — want to clear it?"

Discard → moves the file to `~/.quizmind/wip/archive/`, records a library session with `status="abandoned"` and whatever attempts were captured.

### A3. Mid-session API failure handling
If a Gemini/Qwen call fails with anything non-transient (auth, model-not-found, malformed schema response that even the JSON-mode fallback can't recover), the orchestrator catches it, snapshots state, returns a `phase=Phase.WAITING` state with a user-facing error message. UI shows the message + a "Retry" button + a "Save and exit" button.

Crucially: user answers for the current round are stashed on `state.practice_answers` (or `diagnostic_answers`) **before** the LLM call that grades them. If the eval call fails, the answers are still in the snapshot. The retry resumes from the same answers.

### Files touched (Phase 2A)
- `ui/views.py` (loading states, resume banner, waiting-phase rendering)
- `core/orchestrator.py` (persistence hooks, resume method, WAITING phase)
- `core/session_state.py` (`session_id`, `Phase.WAITING`)
- `core/persistence.py` (new)
- `tests/test_persistence.py` (new)

## Phase 2B — Per-question feedback (½ day)

**Goal:** Show the user what they got right/wrong with explanations, both inline after each round and in the library later.

New phase: `Phase.REVIEWING_RESULTS`. Orchestrator stops here after grading, before advancing. UI renders a results screen:
- Every question with `✓`/`✗` icon
- User's pick highlighted, correct answer marked
- The `explanation` text from the schema
- For replay/review questions: "you previously answered: X (on date)" pulled from library history

A "Continue" button calls `Orchestrator.acknowledge_results(state)` which advances to the next phase (next practice round, or feedback).

In the library tab (built later in 2C), each question gets a detail panel with the same components plus full attempt history.

### Files touched
- `ui/views.py` (results render branch)
- `core/orchestrator.py` (new `acknowledge_results` method, REVIEWING_RESULTS phase)
- `core/session_state.py` (REVIEWING_RESULTS phase)

## Phase 2C — Question library foundation (1–2 days)

**Goal:** Persistent question + attempt log; library Browse tab.

### C1. Storage layer
New `core/library.py`. JSON-on-disk at `~/.quizmind/library.json`. Schema:

```json
{
  "version": 1,
  "questions": [{
    "id": "uuid",
    "content_hash": "sha1(subject+topic+prompt)",
    "subject": "...", "level": "...", "topic": "...",
    "prompt": "...", "choices": [...], "correct_answer": "...", "explanation": "...",
    "source": "diagnostic" | "practice",
    "leitner_box": 1,                  // for Phase 2E
    "next_review_at": "ISO8601",       // for Phase 2E
    "first_seen": "ISO8601"
  }],
  "attempts": [{
    "attempt_id": "uuid", "question_id": "uuid", "session_id": "uuid",
    "user_answer": "...", "correct": bool, "answered_at": "ISO8601",
    "time_spent_ms": null, "is_replay": bool, "is_review": bool
  }],
  "sessions": [{
    "session_id": "uuid", "subject": "...", "level": "...",
    "started_at": "...", "ended_at": "...",
    "diagnostic_score": float, "practice_score": float,
    "passed": bool, "rounds": int,
    "kind": "fresh" | "from_topics" | "replay" | "review",
    "status": "completed" | "abandoned"
  }]
}
```

Pure I/O functions, no LLM imports:
```python
append_questions(...)  # returns ids; dedup by content_hash
append_attempts(...)
append_session(...)
mark_session_abandoned(session_id, attempts_so_far)
search_questions(subject=None, topic=None, wrong_only=False)
get_question_history(question_id)
get_due_for_review(subject=None, limit=20)  # for Phase 2E
```

Writes guarded by `threading.Lock`. Atomic writes via `tmp + os.replace`. First-run creates `~/.quizmind/` if missing.

### C2. Orchestrator hooks
At three phase boundaries:
- After `AssessmentAgent.run` → write diagnostic questions
- After `EvaluatorAgent.run` → write practice questions + attempts
- In `_finalize` → write session summary

Agents themselves remain library-unaware.

### C3. Library Browse tab
`gr.Tabs` with Quiz / Library tabs. Library tab's Browse pane:
- Filter controls: subject dropdown, topic dropdown, "show only wrong answers" checkbox
- Question list, click → opens detail panel (the Phase 2B feedback view, but for any historical question)
- "Retry this question" button on the detail panel adds it to a one-question replay session

### Files touched
- `core/library.py` (new)
- `core/orchestrator.py` (3 hook calls, abandoned-session helper)
- `core/session_state.py` (`session_id`, `kind`, `started_at`, `ended_at`, `status`)
- `ui/views.py` (tabs, library tab, browse view)
- `tests/test_library.py` (new)

## Phase 2D — Library-driven quizzes (1 day)

**Goal:** Build a new quiz from library data; two modes.

### D1. New orchestrator entry points
```python
def start_from_topics(self, subject: str, level: str, topics: list[str]) -> SessionState:
    """Skip diagnostic, jump to practice on these topics. Counts toward stats."""

def start_replay(self, question_ids: list[str]) -> SessionState:
    """Replay exact questions. Marked is_replay=True. Score shown, flagged
    'review — not counted' in the UI. Attempts logged in library but the
    session is kind='replay' so it doesn't pollute the subject score trend."""
```

A new `Phase.REPLAY` skips the evaluator/judge/feedback pipeline (no rationale needed, no improvement delta meaningful for the same questions twice). REVIEWING_RESULTS from Phase 2B still fires so the user sees the breakdown.

### D2. UI — "New quiz from library" sub-view
On the Library tab:
- Filter to subject (and optionally topics).
- Level radio (asked every time).
- Mode radio:
  - `Generate fresh questions on these topics` → `start_from_topics(subject, level, topics)`
  - `Replay these exact questions` → multi-select question list appears → `start_replay(question_ids)`

### Files touched
- `core/orchestrator.py` (2 new methods, REPLAY phase logic)
- `core/session_state.py` (`Phase.REPLAY`)
- `ui/views.py` (library quiz-builder UI)

## Phase 2E — Spaced repetition (1 day)

**Goal:** Resurface wrong answers on a curve. Toggleable.

### E1. Leitner box algorithm
Per-question `leitner_box: int` (1–5) and `next_review_at: ISO8601` in the library schema.

On each attempt:
- Correct → box level + 1 (capped at 5)
- Wrong → box level back to 1
- `next_review_at = now + {1d, 3d, 7d, 21d, 60d}[box - 1]`

### E2. Settings file
New `core/settings.py`. Stores at `~/.quizmind/settings.json`:
```json
{"spaced_repetition_enabled": false}
```

Surfaced as:
- Global checkbox in the Library tab's settings area
- Per-session checkbox on the Quiz tab's setup screen (overrides global for that session)

### E3. "Due for review" pane
On the Library tab, when SR is enabled:
- Pane lists questions whose `next_review_at <= now`, sorted oldest first.
- Two buttons: `[Review N questions now]` (calls `start_review_session(question_ids)`) and `[Skip for now]`.
- Cap the session at 20 questions to prevent backlog explosion.

### E4. Review-mode sessions
New orchestrator method `start_review_session(question_ids)`. Similar to `start_replay` but:
- Attempts marked `is_review=True`
- Leitner boxes updated based on answers
- Score shown to user, not added to subject trend

### Files touched
- `core/library.py` (Leitner update logic, `get_due_for_review`)
- `core/orchestrator.py` (`start_review_session`)
- `core/settings.py` (new)
- `ui/views.py` (toggle widget, due-for-review pane)
- `tests/test_spaced_repetition.py` (new)

## Phase 2F — File sources (1 day)

**Goal:** Upload files as grounding sources; optional exclusive mode.

### F1. Upload widget
In the Quiz tab setup section:
```python
sources_in = gr.File(file_count="multiple", file_types=[".txt", ".md", ".pdf"],
                     label="Optional source files")
exclusive_in = gr.Checkbox(label="Use these sources exclusively (no general knowledge)")
```

Disabled once a session begins. Per-session only — files vanish at session end.

### F2. SessionState plumbing
```python
sources: list[dict] = field(default_factory=list)
# each: {"filename": str, "mime_type": str, "content": str | None, "file_uri": str | None}
use_sources_exclusively: bool = False
```

### F3. PDF handling
Note from Phase 1: we're on OpenAI-compat now, so Gemini's File API isn't available. Strategy revised:
- **Primary path:** local text extraction with `pypdf` for PDFs. Inline content into the prompt.
- **Fallback:** if `pypdf` fails (encrypted, scanned image-only PDF), surface a UI warning and skip that file. OCR via Tesseract is a future option but out of scope here.

For text/markdown: read as UTF-8 with `errors="replace"`. Cap inlined content at ~500KB per source; truncate with a UI warning if larger.

### F4. Prompt updates
`llm/prompts.py` gains a `_sources_block(sources, exclusive)` helper that's injected into the assessment and question-generator prompts when sources exist.

When `use_sources_exclusively=True`: prompt instructs to base questions only on sources; `QuestionGenerator` skips its (already-stubbed) search call.

### F5. Client signature
`LLMClient.generate_structured` doesn't need a `files` parameter — sources are inlined as text in the prompt. The client stays unchanged from Phase 1.

### Files touched
- `core/session_state.py` (2 new fields)
- `llm/prompts.py` (sources block helper)
- `agents/assessment_agent.py`, `agents/question_generator.py` (read sources from state, pass to prompt)
- `ui/views.py` (upload widget, checkbox, ingestion handler)
- `requirements.txt` (add `pypdf`)

---

## Phase 2 effort summary

| Phase | Description | Effort |
|---|---|---|
| 2A | Loading states + WIP persistence + failure recovery | 1 day |
| 2B | Per-question feedback (dedicated review screen) | ½ day |
| 2C | Library foundation + Browse tab | 1–2 days |
| 2D | Library-driven quizzes (from_topics + replay) | 1 day |
| 2E | Spaced repetition (toggleable) | 1 day |
| 2F | File sources | 1 day |

Total Phase 2: ~5.5–6.5 working days. Each phase ships independently.

---

## When you're ready

Phase 1 starts when you say "go." I'll:
1. Rewrite `llm/gemini_client.py` → `llm/llm_client.py` with the OpenAI-compat client.
2. Update `core/config.py`, `agents/base_agent.py`, `core/orchestrator.py`, `scripts/smoke_test.py`, tests, README, CLAUDE.md, HOW_IT_WORKS.md, .env.example.
3. Pause for you to:
   - Sign up at OpenRouter and put the key in `.env`
   - Run `pip install -r requirements.txt` (it'll pull in `openai`, you can `pip uninstall google-genai` to clean up)
   - Run `python -m scripts.smoke_test` to confirm it works
   - Run `pytest -q` to confirm tests still pass
   - Run `python app.py` and walk through a full session
4. You merge to GitHub. We start Phase 2.

The only thing I won't do automatically is the OpenRouter signup — that's your account and your key. Everything else is mine.
