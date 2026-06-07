"""Gradio UI for QuizMind.

This file MUST NOT import agents directly. All state changes go through
the Orchestrator. The UI's only job is rendering SessionState and pushing
user inputs back into Orchestrator methods.
"""
from __future__ import annotations

import dataclasses

import gradio as gr

from core import config
from core.orchestrator import Orchestrator
from core.session_state import Phase, SessionState
from tools.file_loader import extract_text


def _fresh(s: SessionState) -> SessionState:
    """Shallow-copy the state so `gr.State` sees a new object identity.

    The orchestrator mutates state in place, so without this `@gr.render`
    wouldn't detect that anything changed and the UI would stay stuck on
    the previous phase.
    """
    return dataclasses.replace(s)

_KEYBOARD_NAV_JS = """
<script>
(function () {
  var focusedGroup = null;

  document.addEventListener('focusin', function (e) {
    var group = e.target.closest('.gr-radio, [data-testid="radio-group"]');
    if (group) focusedGroup = group;
  }, true);

  document.addEventListener('keydown', function (e) {
    if (['1', '2', '3', '4'].indexOf(e.key) === -1) return;
    if (!focusedGroup) {
      // If nothing focused yet, try the first unanswered group.
      var allGroups = document.querySelectorAll(
        '.gr-radio:not(.qm-confidence), [data-testid="radio-group"]:not(.qm-confidence)'
      );
      for (var i = 0; i < allGroups.length; i++) {
        if (!allGroups[i].querySelector('input[type="radio"]:checked')) {
          focusedGroup = allGroups[i];
          break;
        }
      }
    }
    if (!focusedGroup) return;
    var inputs = focusedGroup.querySelectorAll('input[type="radio"]');
    var idx = parseInt(e.key, 10) - 1;
    if (inputs[idx]) {
      e.preventDefault();
      inputs[idx].click();
      inputs[idx].focus();
      // Advance focus to the next answer radio group (skip confidence groups).
      var allGroups = Array.from(document.querySelectorAll(
        '.gr-radio:not(.qm-confidence), [data-testid="radio-group"]:not(.qm-confidence)'
      ));
      var cur = allGroups.indexOf(focusedGroup);
      if (cur !== -1 && allGroups[cur + 1]) {
        var nextInput = allGroups[cur + 1].querySelector('input[type="radio"]');
        if (nextInput) {
          nextInput.focus();
          focusedGroup = allGroups[cur + 1];
        }
      }
    }
  });
})();
</script>
"""

_orch: Orchestrator | None = None


def _orchestrator() -> Orchestrator:
    global _orch
    if _orch is None:
        _orch = Orchestrator()
    return _orch


CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap');

:root, .dark, .gradio-container {
  --qm-bg: #1a1a1a;
  --qm-surface: #232323;
  --qm-surface-2: #2a2a2a;
  --qm-border: #2e2e2e;
  --qm-text: #e8e6e3;
  --qm-muted: #8a8580;
  --qm-accent: #d97757;
  --qm-accent-dim: #3a2419;
  --qm-good: #7eb069;
  --qm-bad: #c0635e;
}

html, body, .gradio-container, .gradio-container * {
  font-family: 'JetBrains Mono', 'SF Mono', 'Monaco', 'Menlo', monospace !important;
  font-feature-settings: "liga" 1, "calt" 1;
}

body, .gradio-container {
  background: var(--qm-bg) !important;
  color: var(--qm-text) !important;
}

.gradio-container {
  max-width: 820px !important;
  margin: 0 auto !important;
  padding: 32px 24px !important;
  font-size: 13px !important;
  line-height: 1.55 !important;
}

h1, h2, h3, h4 {
  color: var(--qm-text) !important;
  font-weight: 600 !important;
  letter-spacing: -0.01em !important;
}
h1 { font-size: 22px !important; margin-bottom: 4px !important; }
h2 { font-size: 16px !important; }
h3 { font-size: 14px !important; color: var(--qm-muted) !important; text-transform: uppercase; letter-spacing: 0.08em !important; }

p, span, label, .prose, .markdown-text, .gr-markdown {
  color: var(--qm-text) !important;
}

/* Strip Gradio's chunky panels */
.block, .form, .panel, .gr-block, .gr-form, .gr-panel, .gr-group {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}

/* Inputs */
input[type="text"], textarea {
  background: var(--qm-surface) !important;
  color: var(--qm-text) !important;
  border: 1px solid var(--qm-border) !important;
  border-radius: 6px !important;
  font-size: 13px !important;
}
input[type="text"]:focus, textarea:focus {
  border-color: var(--qm-accent) !important;
  outline: none !important;
}

/* Buttons */
button {
  border-radius: 6px !important;
  font-weight: 500 !important;
  font-size: 13px !important;
  transition: all 0.12s ease !important;
}
button.primary, button[variant="primary"], .primary, .lg.primary {
  background: var(--qm-accent) !important;
  color: #1a1a1a !important;
  border: none !important;
  font-weight: 600 !important;
}
button.primary:hover {
  background: #e88a6c !important;
}
button.secondary, button:not(.primary) {
  background: var(--qm-surface) !important;
  color: var(--qm-text) !important;
  border: 1px solid var(--qm-border) !important;
}

/* Radio groups — the meat of the quiz UI */
.gr-radio, [data-testid="radio"] {
  gap: 6px !important;
}
.gr-radio label, .gr-radio > div > label {
  background: var(--qm-surface) !important;
  border: 1px solid var(--qm-border) !important;
  border-radius: 6px !important;
  padding: 10px 14px !important;
  color: var(--qm-text) !important;
  cursor: pointer !important;
  transition: all 0.12s ease !important;
}
.gr-radio label:hover {
  border-color: var(--qm-accent) !important;
  background: var(--qm-surface-2) !important;
}
.gr-radio input:checked + span,
.gr-radio label:has(input:checked) {
  background: var(--qm-accent-dim) !important;
  border-color: var(--qm-accent) !important;
}

/* Question labels (the prompt above each radio group) */
.gr-form > label > span:first-child,
.label-wrap span {
  color: var(--qm-text) !important;
  font-weight: 500 !important;
  font-size: 13px !important;
  margin-bottom: 8px !important;
  display: block !important;
}

/* Markdown blocks for headings/status */
.gr-markdown h2 {
  border-bottom: 1px solid var(--qm-border) !important;
  padding-bottom: 8px !important;
  margin-top: 24px !important;
}
.gr-markdown code {
  background: var(--qm-surface) !important;
  color: var(--qm-accent) !important;
  padding: 1px 5px !important;
  border-radius: 3px !important;
  font-size: 12px !important;
}

footer { display: none !important; }

/* Loading indicator — CSS-only animated dots. */
.qm-loading {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--qm-muted) !important;
  font-style: italic;
}
.qm-loading::before {
  content: "";
  width: 12px;
  height: 12px;
  border: 2px solid var(--qm-border);
  border-top-color: var(--qm-accent);
  border-radius: 50%;
  animation: qm-spin 0.8s linear infinite;
  display: inline-block;
}
@keyframes qm-spin {
  to { transform: rotate(360deg); }
}

/* Review sheet — per-question verdict pills and answer tags. */
.qm-verdict {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 4px;
  margin-right: 8px;
  vertical-align: middle;
}
.qm-verdict.correct {
  background: rgba(126, 176, 105, 0.15);
  color: var(--qm-good) !important;
  border: 1px solid rgba(126, 176, 105, 0.4);
}
.qm-verdict.incorrect {
  background: rgba(192, 99, 94, 0.15);
  color: var(--qm-bad) !important;
  border: 1px solid rgba(192, 99, 94, 0.4);
}
.qm-tag {
  display: inline-block;
  font-size: 10px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  padding: 1px 6px;
  border-radius: 3px;
  margin-left: 6px;
  vertical-align: middle;
}
.qm-tag.correct { background: rgba(126, 176, 105, 0.15); color: var(--qm-good) !important; }
.qm-tag.chosen  { background: rgba(217, 119, 87, 0.18); color: var(--qm-accent) !important; }
.qm-choice-correct { color: var(--qm-good) !important; }
.qm-choice-chosen  { color: var(--qm-accent) !important; }

/* Progress counter shown above the submit button while answering. */
.qm-progress {
  display: inline-block;
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--qm-muted) !important;
  padding: 4px 8px;
  border: 1px solid var(--qm-border);
  border-radius: 4px;
}

/* Per-choice rationales (why a distractor was wrong) + correct-answer rationale. */
.qm-distractor {
  margin: 4px 0 8px 22px;
  padding: 6px 10px;
  border-left: 2px solid var(--qm-bad);
  background: rgba(192, 99, 94, 0.06);
  color: var(--qm-muted) !important;
  font-size: 12px;
  font-style: italic;
}
.qm-explanation {
  margin-top: 8px;
  padding: 8px 12px;
  border-left: 2px solid var(--qm-good);
  background: rgba(126, 176, 105, 0.06);
  color: var(--qm-text) !important;
  font-size: 12px;
}

/* Disabled primary button — keep it readable, not invisible. */
button.primary:disabled, button[variant="primary"]:disabled {
  background: var(--qm-surface) !important;
  color: var(--qm-muted) !important;
  cursor: not-allowed !important;
  border: 1px solid var(--qm-border) !important;
}

/* Confidence radios — smaller, muted, inline below each answer group */
.qm-confidence .gr-radio label, .qm-confidence [data-testid="radio-group"] label {
  padding: 4px 10px !important;
  font-size: 11px !important;
  color: var(--qm-muted) !important;
}
.qm-confidence .gr-radio input:checked + span,
.qm-confidence label:has(input:checked) {
  background: #2a2a2a !important;
  border-color: var(--qm-muted) !important;
  color: var(--qm-text) !important;
}
.qm-confidence > label > span:first-child {
  font-size: 10px !important;
  color: var(--qm-muted) !important;
  text-transform: uppercase;
  letter-spacing: .06em !important;
}
"""


def _md_escape(text: str) -> str:
    """Escape markdown control chars that show up in topic / prompt strings."""
    return (
        text.replace("\\", "\\\\")
        .replace("_", "\\_")
        .replace("*", "\\*")
        .replace("`", "\\`")
    )


def _format_wrong_answers(s: SessionState) -> str:
    """Build a study-list section from all incorrect answers across all rounds."""
    wrong: list[dict] = []

    # Diagnostic wrongs
    qmap = {q["id"]: q for q in s.diagnostic_questions}
    for r in s.diagnostic_results:
        if not r["correct"] and r["question_id"] in qmap:
            wrong.append({"round": "Initial test", "q": qmap[r["question_id"]], "r": r})

    # Practice round wrongs (all rounds via practice_history)
    for hist in s.practice_history:
        label = f"Practice round {hist['iteration']}"
        qmap_p = {q["id"]: q for q in hist["questions"]}
        for r in hist["results"]:
            if not r["correct"] and r["question_id"] in qmap_p:
                wrong.append({"round": label, "q": qmap_p[r["question_id"]], "r": r})

    if not wrong:
        return ""

    lines = ["\n---\n### Questions to review\n"]
    lines.append(
        f"_{len(wrong)} question{'s' if len(wrong) != 1 else ''} answered incorrectly "
        f"across all rounds._\n"
    )
    current_round = None
    for entry in wrong:
        if entry["round"] != current_round:
            current_round = entry["round"]
            lines.append(f"\n**{current_round}**\n")
        q = entry["q"]
        r = entry["r"]
        safe_topic = _md_escape(q["topic"])
        safe_prompt = _md_escape(q["prompt"])
        lines.append(f'- **[{safe_topic}]** {safe_prompt}')
        lines.append(
            f'  - Your answer: `{_md_escape(r["student_answer"])}`  '
            f'  Correct: `{_md_escape(r["correct_answer"])}`'
        )
        if explanation := q.get("explanation", ""):
            lines.append(f'  - _{explanation}_')
    return "\n".join(lines)


def _score_chart_html(round_scores: list[float]) -> str:
    """Render an inline CSS bar chart for score progression. No dependencies."""
    if not round_scores:
        return ""

    labels = ["Initial test"] + [
        f"Round {i}" for i in range(1, len(round_scores))
    ]
    PASS = 0.70
    bars = []
    for label, score in zip(labels, round_scores):
        pct = int(score * 100)
        color = "#7eb069" if score >= PASS else "#d97757"
        bars.append(
            f'<div style="margin:4px 0">'
            f'<div style="font-size:11px;color:#8a8580;margin-bottom:2px">{label}</div>'
            f'<div style="display:flex;align-items:center;gap:8px">'
            f'<div style="background:{color};width:{pct}%;height:18px;'
            f'border-radius:3px;min-width:4px;transition:width .3s"></div>'
            f'<span style="font-size:12px;color:#e8e6e3;min-width:32px">{pct}%</span>'
            f'</div></div>'
        )

    return (
        '<div style="padding:12px;background:#232323;border-radius:6px;'
        'border:1px solid #2e2e2e;margin-bottom:16px">'
        '<div style="font-size:11px;text-transform:uppercase;letter-spacing:.08em;'
        'color:#8a8580;margin-bottom:10px">Score progression</div>'
        + "".join(bars)
        + f'<div style="margin-top:10px;font-size:10px;color:#8a8580">'
        f'<span style="color:#d97757">■</span> below 70% pass threshold &nbsp;'
        f'<span style="color:#7eb069">■</span> passing</div>'
        "</div>"
    )


def _generate_export(s: SessionState) -> str:
    """Serialise the session to a temp JSON file and return its path."""
    import json
    import tempfile

    data = {
        "subject": s.subject,
        "level": s.level,
        "question_count": s.question_count,
        "passed": s.passed,
        "diagnostic_score": s.diagnostic_score,
        "practice_score": s.practice_score,
        "round_scores": s.round_scores,
        "elapsed_seconds": s.elapsed_seconds,
        "iterations": s.iteration,
        "weak_topics": s.weak_topics,
        "final_report": s.final_report,
        "judge_scores": s.judge_scores,
        "diagnostic_questions": s.diagnostic_questions,
        "diagnostic_answers": s.diagnostic_answers,
        "diagnostic_results": s.diagnostic_results,
        "practice_history": s.practice_history,
        "confidence_ratings": s.confidence_ratings,
    }
    subject_slug = s.subject.lower().replace(" ", "_")[:20]
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix=f"quizmind_{subject_slug}_",
        delete=False,
        encoding="utf-8",
    )
    json.dump(data, tmp, indent=2, ensure_ascii=False)
    tmp.close()
    return tmp.name


def _format_history() -> str:
    from tools.session_storage import load_sessions
    records = load_sessions(max_entries=20)
    if not records:
        return "_No sessions recorded yet._"
    lines = []
    for r in reversed(records):
        import datetime
        ts = datetime.datetime.fromtimestamp(r["timestamp"]).strftime("%Y-%m-%d %H:%M")
        passed_icon = "✓" if r.get("passed") else "✗"
        diag = f"{r['diagnostic_score']:.0%}" if r.get("diagnostic_score") is not None else "—"
        prac = f"{r['practice_score']:.0%}" if r.get("practice_score") is not None else "—"
        elapsed = ""
        if r.get("elapsed_seconds") is not None:
            m, s = divmod(int(r["elapsed_seconds"]), 60)
            elapsed = f" · {m}m{s}s"
        lines.append(
            f"- `{ts}` **{r.get('subject','?')}** ({r.get('level','?')}) "
            f"— init: `{diag}` → final: `{prac}` {passed_icon}{elapsed}"
        )
    return "\n".join(lines)


def _format_report(s: SessionState) -> str:
    lines = ["## Final report\n"]
    if s.diagnostic_score is not None:
        lines.append(f"- **Initial test score:** `{s.diagnostic_score:.0%}`")
    if s.practice_score is not None:
        lines.append(f"- **Practice score:** `{s.practice_score:.0%}`")
    lines.append(f"- **Passed:** `{s.passed}`  rounds: `{s.iteration}`")
    if s.elapsed_seconds is not None:
        mins, secs = divmod(int(s.elapsed_seconds), 60)
        lines.append(f"- **Time:** `{mins}m {secs}s`")

    report = s.final_report or {}
    if rationale := report.get("evaluator_rationale"):
        lines.append(f"\n**Evaluator.** {rationale}")
    if summary := report.get("summary"):
        lines.append(f"\n**Summary.** {summary}")
    if mastered := report.get("mastered_topics"):
        lines.append(f"\n**Mastered:** {', '.join(f'`{m}`' for m in mastered)}")
    if still := report.get("still_needs_work"):
        lines.append(f"\n**Still needs work:** {', '.join(f'`{s_}`' for s_ in still)}")
    if steps := report.get("recommended_next_steps"):
        lines.append("\n**Next steps:**")
        lines.extend(f"- {x}" for x in steps)

    if s.judge_scores:
        lines.append("\n---\n### Judge scores")
        for key in ("relevance", "difficulty_calibration", "improvement_validity"):
            entry = s.judge_scores.get(key, {}) or {}
            lines.append(
                f"- **{key.replace('_', ' ')}:** "
                f"`{entry.get('score', '?')}/10` — {entry.get('justification', '')}"
            )
        if overall := s.judge_scores.get("overall_comment"):
            lines.append(f"\n_{overall}_")

    wrong_section = _format_wrong_answers(s)
    if wrong_section:
        lines.append(wrong_section)

    return "\n".join(lines)


CSS = CUSTOM_CSS  # re-export so app.py can pass it to launch()


def build_blocks() -> gr.Blocks:
    with gr.Blocks(title="QuizMind") as demo:
        state = gr.State(SessionState())

        gr.Markdown(
            "# QuizMind\n"
            "_Adaptive quiz. Pick a subject. We test you, find weak spots, "
            "and drill those until you improve._"
        )

        with gr.Group() as setup_group:
            gr.Markdown("### Setup")
            category_in = gr.Dropdown(
                choices=[*config.SUBJECT_CATEGORIES, "Custom..."],
                value=config.SUBJECT_CATEGORIES[0],
                label="Category",
            )
            custom_subject_in = gr.Textbox(
                label="Custom subject",
                placeholder="e.g. Ottoman architecture",
                visible=False,
            )
            level_in = gr.Radio(
                choices=list(config.LEVELS),
                value="beginner",
                label="Level",
            )
            question_count_in = gr.Slider(
                minimum=5,
                maximum=20,
                step=5,
                value=10,
                label="Questions in initial test",
            )
            file_in = gr.File(
                label="Optional: upload a file to generate questions from "
                "(.txt, .md, .pdf)",
                file_types=[".txt", ".md", ".pdf"],
                file_count="single",
            )
            start_btn = gr.Button("Start test", variant="primary")

        def _toggle_custom(choice: str):
            return gr.update(visible=(choice == "Custom..."))

        category_in.change(
            _toggle_custom, inputs=category_in, outputs=custom_subject_in
        )

        with gr.Accordion("Session history", open=False):
            history_md = gr.Markdown(_format_history())
            refresh_btn = gr.Button("Refresh", size="sm")
            refresh_btn.click(lambda: _format_history(), outputs=history_md)

        status = gr.Markdown("")

        def start_session(category: str, custom_subject: str, level: str, question_count: int, file_obj):
            subject = custom_subject.strip() if category == "Custom..." else category
            if not subject:
                yield gr.skip(), gr.update(), "_Please pick or enter a subject._"
                return

            source_text = ""
            if file_obj is not None:
                path = file_obj.name if hasattr(file_obj, "name") else file_obj
                try:
                    source_text = extract_text(path)
                except Exception as exc:
                    yield gr.skip(), gr.update(), f"_Could not read file: {exc}_"
                    return
                if not source_text:
                    yield gr.skip(), gr.update(), "_File appears empty._"
                    return

            yield (
                gr.skip(),
                gr.update(visible=False),
                '<span class="qm-loading">Generating test questions — usually 20–30 seconds.</span>',
            )
            try:
                new_state = _orchestrator().start(
                    subject, level, source_text=source_text,
                    question_count=int(question_count),
                )
            except Exception as exc:
                import traceback
                traceback.print_exc()
                yield gr.skip(), gr.update(visible=True), f"_Could not generate test: `{exc}`_"
                return
            yield (
                _fresh(new_state),
                gr.update(visible=False),
                "",
            )

        start_btn.click(
            start_session,
            inputs=[category_in, custom_subject_in, level_in, question_count_in, file_in],
            outputs=[state, setup_group, status],
        )

        @gr.render(inputs=state)
        def render_active(s: SessionState):
            if s.phase == Phase.ASSESSMENT:
                _render_quiz(
                    state,
                    s.diagnostic_questions,
                    heading=f"## Initial test\n_{len(s.diagnostic_questions)} questions across broad subtopics._",
                    submit_label="Submit answers",
                    on_submit=lambda st, ans: _orchestrator().submit_diagnostic_answers(st, ans),
                )

            elif s.phase == Phase.DIAGNOSTIC_REVIEW:
                _render_review(
                    state,
                    questions=s.diagnostic_questions,
                    user_answers=s.diagnostic_answers,
                    results=s.diagnostic_results,
                    score=s.diagnostic_score,
                    weak_topics=s.weak_topics,
                    heading="## Initial test — results",
                    continue_label=(
                        "Start practice on weak topics"
                        if s.weak_topics
                        else "Continue"
                    ),
                    on_continue=lambda st: _orchestrator().continue_after_diagnostic(st),
                )

            elif s.phase == Phase.PRACTICE:
                topics = sorted({q["topic"] for q in s.practice_questions})
                topic_chips = " ".join(f"`{_md_escape(t)}`" for t in topics)
                _render_quiz(
                    state,
                    s.practice_questions,
                    heading=(
                        f"## Practice round {s.iteration}\n"
                        f"_{len(s.practice_questions)} questions on:_ {topic_chips}"
                    ),
                    submit_label=f"Submit round {s.iteration}",
                    on_submit=lambda st, ans: _orchestrator().submit_practice_answers(st, ans),
                )

            elif s.phase == Phase.PRACTICE_REVIEW:
                will_loop = (
                    not s.passed
                    and s.iteration < config.MAX_PRACTICE_ROUNDS
                    and bool(s.pending_weak_topics)
                )
                _render_review(
                    state,
                    questions=s.practice_questions,
                    user_answers=s.practice_answers,
                    results=s.practice_results,
                    score=s.practice_score,
                    weak_topics=[],
                    heading=f"## Practice round {s.iteration} — results",
                    continue_label=(
                        f"Next practice round (round {s.iteration + 1})"
                        if will_loop
                        else "See final report"
                    ),
                    on_continue=lambda st: _orchestrator().continue_after_practice(st),
                )

            elif s.phase == Phase.DONE:
                if s.round_scores:
                    gr.HTML(_score_chart_html(s.round_scores))
                gr.Markdown(_format_report(s))

                with gr.Row():
                    restart = gr.Button("Start a new session", variant="primary")
                    gr.DownloadButton(
                        "Download session JSON",
                        value=_generate_export(s),
                        variant="secondary",
                    )

                def reset():
                    return SessionState(), gr.update(visible=True), ""

                restart.click(reset, inputs=None, outputs=[state, setup_group, status])

    return demo


def _render_quiz(
    state_var: gr.State,
    questions: list[dict],
    heading: str,
    submit_label: str,
    on_submit,
):
    gr.HTML(_KEYBOARD_NAV_JS)
    gr.Markdown(heading)
    radios: list[gr.Radio] = []
    conf_radios: list[gr.Radio] = []

    for i, q in enumerate(questions):
        radios.append(
            gr.Radio(
                choices=q["choices"],
                label=f"{i + 1}. [{q['topic']}]  {q['prompt']}",  # raw label, no markdown processing
            )
        )
        conf_radios.append(
            gr.Radio(
                choices=["Low", "Medium", "High"],
                value="Medium",
                label=f"Confidence on Q{i + 1}",
                elem_classes=["qm-confidence"],
            )
        )

    progress = gr.Markdown(
        f'<span class="qm-progress">0 / {len(questions)} answered</span>'
    )
    submit_btn = gr.Button(submit_label, variant="primary")
    inline_status = gr.Markdown("")

    def _on_answer_change(*answers):
        answered = sum(1 for a in answers if a)
        return f'<span class="qm-progress">{answered} / {len(questions)} answered</span>'

    for r in radios:
        r.change(_on_answer_change, inputs=radios, outputs=progress)

    _CONF_MAP = {"Low": 1, "Medium": 2, "High": 3}

    def submit_handler(current_state, *all_inputs):
        answers_list = [a or "" for a in all_inputs[:len(questions)]]
        conf_list = list(all_inputs[len(questions):])

        missing = [i + 1 for i, a in enumerate(answers_list) if not a]
        if missing:
            yield (
                current_state,
                f"_Please answer all questions. Missing: `{missing}`_",
            )
            return

        # Merge confidence ratings into state before calling on_submit.
        current_state.confidence_ratings.update({
            questions[i]["id"]: _CONF_MAP.get(conf_list[i] or "Medium", 2)
            for i in range(len(questions))
        })

        yield current_state, '<span class="qm-loading">Grading and analyzing your answers.</span>'
        try:
            new_state = on_submit(current_state, answers_list)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            yield current_state, f"_Something went wrong while grading: `{exc}`_"
            return
        yield _fresh(new_state), ""

    submit_btn.click(
        submit_handler,
        inputs=[state_var, *radios, *conf_radios],
        outputs=[state_var, inline_status],
    )


def _render_review(
    state_var: gr.State,
    questions: list[dict],
    user_answers: list[str],
    results: list[dict],
    score: float | None,
    weak_topics: list[dict],
    heading: str,
    continue_label: str,
    on_continue,
):
    correct_by_id = {r["question_id"]: r.get("correct", False) for r in results}

    lines = [heading]
    if score is not None:
        lines.append(f"\n**Score:** `{score:.0%}` "
                     f"({sum(correct_by_id.values())}/{len(questions)} correct)\n")
    if weak_topics:
        chips = ", ".join(
            f"`{_md_escape(w['topic'])}` ({w['accuracy']:.0%})" for w in weak_topics
        )
        lines.append(f"**Weak topics flagged:** {chips}\n")

    for i, q in enumerate(questions):
        user_ans = user_answers[i] if i < len(user_answers) else ""
        is_correct = correct_by_id.get(q["id"], False)
        verdict_class = "correct" if is_correct else "incorrect"
        verdict_label = "Correct" if is_correct else "Incorrect"
        rationales = q.get("distractor_rationales", {}) or {}
        safe_topic = _md_escape(q["topic"])
        safe_prompt = _md_escape(q["prompt"])
        lines.append(
            f'\n---\n<span class="qm-verdict {verdict_class}">{verdict_label}</span>'
            f' **{i+1}. [{safe_topic}]** {safe_prompt}\n'
        )
        for choice in q["choices"]:
            is_right = choice == q.get("correct_answer")
            is_chosen = choice == user_ans
            tags = ""
            if is_right:
                tags += '<span class="qm-tag correct">Correct answer</span>'
            if is_chosen:
                tags += '<span class="qm-tag chosen">Your answer</span>'
            choice_class = ""
            if is_right:
                choice_class = "qm-choice-correct"
            elif is_chosen:
                choice_class = "qm-choice-chosen"
            line = f'- <span class="{choice_class}">{choice}</span>{tags}'
            if not is_right and (reason := rationales.get(choice)):
                line += f'<div class="qm-distractor">{reason}</div>'
            lines.append(line)
        if explanation := q.get("explanation", ""):
            lines.append(f'\n<div class="qm-explanation">{explanation}</div>')

    gr.Markdown("\n".join(lines))
    continue_btn = gr.Button(continue_label, variant="primary")
    inline_status = gr.Markdown("")

    def handler(current_state):
        yield current_state, '<span class="qm-loading">Generating next questions — usually 20–30 seconds.</span>'
        try:
            next_state = on_continue(current_state)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            yield current_state, f"_Something went wrong: `{exc}`_"
            return
        yield _fresh(next_state), ""

    continue_btn.click(
        handler, inputs=[state_var], outputs=[state_var, inline_status]
    )
