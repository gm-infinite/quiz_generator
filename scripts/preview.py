"""Live visual preview of every QuizMind UI component — no API key, no server.

Renders the real CUSTOM_CSS plus the real HTML render helpers against a fake
completed session, writes one standalone HTML file, and opens it in a browser.

    python -m scripts.preview          # write + open
    python -m scripts.preview --no-open # just write, print the path

ponytail: static sample markup for the radio/quiz widgets (those live inside
Gradio and can't render standalone) — everything else is the real functions.
"""
from __future__ import annotations

import sys
import tempfile
import webbrowser

from core.session_state import Phase, SessionState
from ui.views import (
    CUSTOM_CSS,
    _format_report_html,
    _render_timeline,
    _score_chart_html,
)


def _fake_done_state() -> SessionState:
    s = SessionState(subject="Calculus", level="intermediate", phase=Phase.DONE)
    s.question_count = 10
    s.iteration = 2
    s.diagnostic_score = 0.50
    s.practice_score = 0.80
    s.passed = True
    s.elapsed_seconds = 372
    s.round_scores = [0.50, 0.65, 0.80]
    s.weak_topics = [
        {"topic": "Chain rule", "accuracy": 0.33},
        {"topic": "Integration by parts", "accuracy": 0.50},
    ]
    s.diagnostic_questions = [
        {
            "id": "d-0",
            "topic": "Chain rule",
            "prompt": "What is the derivative of sin(x^2)?",
            "choices": ["2x·cos(x^2)", "cos(x^2)", "2x·sin(x^2)", "-cos(x^2)"],
            "correct_answer": "2x·cos(x^2)",
            "explanation": "Apply the chain rule: d/dx sin(u) = cos(u)·u'.",
        },
    ]
    s.diagnostic_results = [
        {
            "question_id": "d-0",
            "correct": False,
            "student_answer": "cos(x^2)",
            "correct_answer": "2x·cos(x^2)",
        },
    ]
    s.practice_history = [
        {
            "iteration": 1,
            "questions": [
                {
                    "id": "p1-0-0",
                    "topic": "Integration by parts",
                    "prompt": "∫ x·e^x dx = ?",
                    "choices": ["x·e^x - e^x + C", "e^x + C", "x^2·e^x + C", "x·e^x + C"],
                    "correct_answer": "x·e^x - e^x + C",
                    "explanation": "Let u = x, dv = e^x dx.",
                }
            ],
            "results": [
                {
                    "question_id": "p1-0-0",
                    "correct": False,
                    "student_answer": "e^x + C",
                    "correct_answer": "x·e^x - e^x + C",
                }
            ],
        }
    ]
    s.final_report = {
        "evaluator_rationale": "Practice score rose 30 points over the diagnostic, clearing the pass rule.",
        "summary": "Strong recovery on chain rule; integration by parts still shaky.",
        "mastered_topics": ["Chain rule", "Product rule"],
        "still_needs_work": ["Integration by parts"],
        "recommended_next_steps": [
            "Drill 5 integration-by-parts problems.",
            "Review the LIATE heuristic for choosing u.",
        ],
    }
    s.judge_scores = {
        "relevance": {"score": 9, "justification": "Questions tracked the flagged weak topics closely."},
        "difficulty_calibration": {"score": 8, "justification": "Difficulty matched the intermediate level."},
        "improvement_validity": {"score": 9, "justification": "Gains reflect real learning, not repeats."},
        "overall_comment": "A well-calibrated session with genuine improvement.",
    }
    return s


# --- static sample markup for Gradio-bound widgets (real class names) ---

_QUIZ_SAMPLE = """
<div class="qm-card">
  <span class="qm-topic-badge" style="margin-bottom:12px;display:inline-block;">Topic: Chain rule</span>
  <div class="gr-form"><label><span>1. What is the derivative of sin(x^2)?</span></label></div>
  <div class="gr-radio">
    <label><input type="radio" name="q1"> <span>2x·cos(x^2)</span></label>
    <label><input type="radio" name="q1" checked> <span>cos(x^2)</span></label>
    <label><input type="radio" name="q1"> <span>2x·sin(x^2)</span></label>
    <label><input type="radio" name="q1"> <span>-cos(x^2)</span></label>
  </div>
  <div class="qm-confidence">
    <div class="gr-radio">
      <label><input type="radio" name="c1"> <span>Low</span></label>
      <label><input type="radio" name="c1" checked> <span>Medium</span></label>
      <label><input type="radio" name="c1"> <span>High</span></label>
    </div>
  </div>
</div>
"""

_PROGRESS_SAMPLE = """
<div class="qm-progress-container">
  <span class="qm-progress-text">3 / 5 Answered</span>
  <div class="qm-progress-bar-bg"><div class="qm-progress-bar-fill" style="width:60%"></div></div>
  <span class="qm-progress-text">60%</span>
</div>
"""

_BUTTONS_SAMPLE = """
<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
  <button class="primary">Start test</button>
  <button class="secondary">Download session JSON</button>
  <button disabled>Disabled</button>
  <input type="text" placeholder="Custom subject…" style="width:220px;">
</div>
"""

_REVIEW_SAMPLE = """
<div class="qm-card qm-review-card">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;flex-wrap:wrap;gap:8px;">
    <span class="qm-verdict incorrect">Incorrect</span>
    <span class="qm-topic-badge">Topic: Chain rule</span>
  </div>
  <h4>1. What is the derivative of sin(x^2)?</h4>
  <ul class="qm-choices-list">
    <li class="qm-choice-correct"><span>2x·cos(x^2)</span><span class="qm-tag correct">Correct Answer</span></li>
    <li class="qm-choice-chosen"><span>cos(x^2)</span><span class="qm-tag chosen">Your Answer</span></li>
    <li><span>2x·sin(x^2)</span></li>
    <div class="qm-distractor">Forgot the inner-derivative factor 2x.</div>
    <li><span>-cos(x^2)</span></li>
  </ul>
  <div class="qm-explanation">Apply the chain rule: d/dx sin(u) = cos(u)·u'.</div>
</div>
"""


def build_html() -> str:
    s = _fake_done_state()

    def section(title: str, body: str) -> str:
        return f'<h2 style="margin-top:48px;">{title}</h2>\n{body}'

    timelines = "".join(
        f'<div style="font-size:11px;color:var(--qm-muted);text-transform:uppercase;'
        f'letter-spacing:.06em;margin:16px 0 4px;">phase = {p.value}</div>'
        + _render_timeline(SessionState(phase=p))
        for p in (Phase.INIT, Phase.ASSESSMENT, Phase.PRACTICE, Phase.DONE)
    )

    body = "\n".join([
        '<div class="qm-title-container"><h1>QuizMind</h1>'
        "<p>Adaptive multi-agent quiz system. Component preview.</p></div>",
        section("Timeline (all phases)", timelines),
        section("Buttons &amp; inputs", _BUTTONS_SAMPLE),
        section("Loading indicator", '<span class="qm-loading">Generating test questions — usually 20–30 seconds.</span>'),
        section("Quiz card (selected = blue)", _QUIZ_SAMPLE),
        section("Progress bar", _PROGRESS_SAMPLE),
        section("Review card", _REVIEW_SAMPLE),
        section("Score progression chart", _score_chart_html(s.round_scores)),
        section("Final report dashboard", _format_report_html(s)),
    ])

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<style>{CUSTOM_CSS}</style></head>"
        "<body class='gradio-container'>"
        f"{body}</body></html>"
    )


def main() -> int:
    html = build_html()
    # sanity check: the redesign tokens are present, the old dark ones are gone.
    assert "#ffffff" in html and "#090d16" not in html, "dark theme leaked into preview"
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", prefix="quizmind_preview_", delete=False, encoding="utf-8"
    )
    tmp.write(html)
    tmp.close()
    print(f"Wrote {tmp.name}")
    if "--no-open" not in sys.argv:
        webbrowser.open(f"file://{tmp.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
