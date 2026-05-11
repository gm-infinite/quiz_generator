"""Gradio UI for QuizMind.

This file MUST NOT import agents directly. All state changes go through
the Orchestrator. The UI's only job is rendering SessionState and pushing
user inputs back into Orchestrator methods.
"""
from __future__ import annotations

import gradio as gr

from core import config
from core.orchestrator import Orchestrator
from core.session_state import Phase, SessionState

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
"""


def _format_report(s: SessionState) -> str:
    lines = ["## Final report\n"]
    if s.diagnostic_score is not None:
        lines.append(f"- **Initial test score:** `{s.diagnostic_score:.0%}`")
    if s.practice_score is not None:
        lines.append(f"- **Practice score:** `{s.practice_score:.0%}`")
    lines.append(f"- **Passed:** `{s.passed}`  rounds: `{s.iteration}`")

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
            subject_in = gr.Textbox(
                label="Subject",
                placeholder="e.g. geography of Turkey",
                value="geography of Turkey",
                show_label=True,
            )
            level_in = gr.Radio(
                choices=list(config.LEVELS),
                value="beginner",
                label="Level",
            )
            start_btn = gr.Button("Start test  →", variant="primary")

        status = gr.Markdown("")

        def start_session(subject: str, level: str):
            if not subject.strip():
                return gr.skip(), gr.update(), "_Please enter a subject._"
            new_state = _orchestrator().start(subject.strip(), level)
            return (
                new_state,
                gr.update(visible=False),
                f"_Generated `{len(new_state.diagnostic_questions)}` test questions._",
            )

        start_btn.click(
            start_session,
            inputs=[subject_in, level_in],
            outputs=[state, setup_group, status],
        )

        @gr.render(inputs=state)
        def render_active(s: SessionState):
            if s.phase == Phase.ASSESSMENT:
                _render_quiz(
                    state,
                    s.diagnostic_questions,
                    heading=f"## Initial test\n_{len(s.diagnostic_questions)} questions across broad subtopics._",
                    submit_label="Submit answers  →",
                    on_submit=lambda st, ans: _orchestrator().submit_diagnostic_answers(st, ans),
                )

            elif s.phase == Phase.PRACTICE:
                topics = sorted({q["topic"] for q in s.practice_questions})
                topic_chips = " ".join(f"`{t}`" for t in topics)
                _render_quiz(
                    state,
                    s.practice_questions,
                    heading=(
                        f"## Practice round {s.iteration}\n"
                        f"_{len(s.practice_questions)} questions on:_ {topic_chips}"
                    ),
                    submit_label=f"Submit round {s.iteration}  →",
                    on_submit=lambda st, ans: _orchestrator().submit_practice_answers(st, ans),
                )

            elif s.phase == Phase.DONE:
                gr.Markdown(_format_report(s))
                restart = gr.Button("Start a new session", variant="primary")

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
    gr.Markdown(heading)
    radios: list[gr.Radio] = []
    for i, q in enumerate(questions):
        radios.append(
            gr.Radio(
                choices=q["choices"],
                label=f"{i + 1}. [{q['topic']}]  {q['prompt']}",
            )
        )
    submit_btn = gr.Button(submit_label, variant="primary")
    inline_status = gr.Markdown("")

    def submit_handler(current_state, *answers):
        answers_list = [a or "" for a in answers]
        missing = [i + 1 for i, a in enumerate(answers_list) if not a]
        if missing:
            return (
                current_state,
                f"_Please answer all questions. Missing: `{missing}`_",
            )
        new_state = on_submit(current_state, answers_list)
        return new_state, ""

    submit_btn.click(
        submit_handler,
        inputs=[state_var, *radios],
        outputs=[state_var, inline_status],
    )
