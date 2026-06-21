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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root, .dark, .gradio-container {
  /* Page & Layout backgrounds */
  --background-fill-primary: #ffffff !important;
  --background-fill-primary-dark: #ffffff !important;
  --background-fill-secondary: #f8f9fa !important;
  --background-fill-secondary-dark: #f8f9fa !important;
  --body-background-fill: #ffffff !important;
  --body-background-fill-dark: #ffffff !important;

  /* Block & Container backgrounds */
  --block-background-fill: #ffffff !important;
  --block-background-fill-dark: #ffffff !important;
  --block-border-color: #e5e7eb !important;
  --block-border-color-dark: #e5e7eb !important;
  --border-color-primary: #e5e7eb !important;
  --border-color-primary-dark: #e5e7eb !important;
  --border-color-secondary: #f3f4f6 !important;
  --border-color-secondary-dark: #f3f4f6 !important;

  /* Inputs */
  --input-background-fill: #ffffff !important;
  --input-background-fill-dark: #ffffff !important;
  --input-border-color: #e5e7eb !important;
  --input-border-color-dark: #e5e7eb !important;

  /* Text & Labels */
  --body-text-color: #374151 !important;
  --body-text-color-dark: #374151 !important;
  --block-label-text-color: #6b7280 !important;
  --block-label-text-color-dark: #6b7280 !important;
  --input-text-color: #111111 !important;
  --input-text-color-dark: #111111 !important;
  --block-title-text-color: #111111 !important;
  --block-title-text-color-dark: #111111 !important;

  /* Buttons & Accent Color */
  --primary-500: #111111 !important;
  --primary-500-dark: #111111 !important;
  --primary-600: #242424 !important;
  --primary-600-dark: #242424 !important;
  --button-primary-background-fill: #111111 !important;
  --button-primary-background-fill-dark: #111111 !important;
  --button-primary-text-color: #ffffff !important;
  --button-primary-text-color-dark: #ffffff !important;
  --button-secondary-background-fill: #ffffff !important;
  --button-secondary-background-fill-dark: #ffffff !important;
  --button-secondary-text-color: #111111 !important;
  --button-secondary-text-color-dark: #111111 !important;
  --button-secondary-border-color: #e5e7eb !important;
  --button-secondary-border-color-dark: #e5e7eb !important;

  /* Radio / checkbox option pills (Level, confidence, quiz choices).
     Selected uses a soft blue tint (brand accent) — readable, not black. */
  --checkbox-label-background-fill: #ffffff !important;
  --checkbox-label-background-fill-dark: #ffffff !important;
  --checkbox-label-background-fill-selected: #eff6ff !important;
  --checkbox-label-background-fill-selected-dark: #eff6ff !important;
  --checkbox-label-background-fill-hover: #f8f9fa !important;
  --checkbox-label-background-fill-hover-dark: #f8f9fa !important;
  --checkbox-label-text-color: #374151 !important;
  --checkbox-label-text-color-dark: #374151 !important;
  --checkbox-label-text-color-selected: #1d4ed8 !important;
  --checkbox-label-text-color-selected-dark: #1d4ed8 !important;
  --checkbox-background-color: #ffffff !important;
  --checkbox-background-color-dark: #ffffff !important;
  --checkbox-background-color-selected: #3b82f6 !important;
  --checkbox-background-color-selected-dark: #3b82f6 !important;
  --checkbox-border-color: #e5e7eb !important;
  --checkbox-border-color-dark: #e5e7eb !important;
  --checkbox-border-color-selected: #3b82f6 !important;
  --checkbox-border-color-selected-dark: #3b82f6 !important;
  --checkbox-border-color-hover: #3b82f6 !important;
  --checkbox-border-color-hover-dark: #3b82f6 !important;
  --checkbox-border-color-focus: #3b82f6 !important;
  --checkbox-border-color-focus-dark: #3b82f6 !important;

  /* QuizMind tokens — Cal.com palette */
  --qm-bg-gradient: #ffffff;
  --qm-bg: #ffffff;
  --qm-surface: #ffffff;
  --qm-surface-2: #f5f5f5;
  --qm-surface-soft: #f8f9fa;
  --qm-border: #e5e7eb;
  --qm-border-soft: #f3f4f6;
  --qm-border-hover: #111111;
  --qm-ink: #111111;
  --qm-text: #374151;
  --qm-muted: #6b7280;
  --qm-muted-soft: #898989;
  /* accent = ink black (primary action layer is monochrome) */
  --qm-accent-gradient: #111111;
  --qm-accent: #111111;
  --qm-accent-dim: #f5f5f5;
  /* blue reserved for the "your/chosen answer" affordance only */
  --qm-blue: #3b82f6;
  --qm-blue-dim: #eff6ff;
  --qm-good: #10b981;
  --qm-good-dim: #ecfdf5;
  --qm-bad: #ef4444;
  --qm-bad-dim: #fef2f2;
  --qm-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  --qm-shadow-lg: 0 4px 12px rgba(0, 0, 0, 0.08);
}

html, body, .gradio-container, .gradio-container * {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
}

code, pre, .qm-code, .gr-markdown code {
  font-family: 'JetBrains Mono', ui-monospace, monospace !important;
}

body, .gradio-container {
  background: var(--qm-bg) !important;
  color: var(--qm-text) !important;
}

.gradio-container {
  max-width: 860px !important;
  margin: 0 auto !important;
  padding: 40px 24px !important;
  font-size: 14px !important;
  line-height: 1.6 !important;
}

/* Display headlines: Cal Sans signature (falls back to Inter 600 + neg tracking) */
h1, h2, h3, h4, h5, h6 {
  font-family: 'Cal Sans', 'Inter', -apple-system, sans-serif !important;
  color: var(--qm-ink) !important;
  font-weight: 600 !important;
  letter-spacing: -0.03em !important;
}

h1 { font-size: 28px !important; line-height: 1.2 !important; margin-bottom: 8px !important; }
h2 { font-size: 20px !important; margin-bottom: 16px !important; border-bottom: 1px solid var(--qm-border) !important; padding-bottom: 8px !important; }
h3 { font-size: 16px !important; margin-bottom: 12px !important; letter-spacing: -0.01em !important; }
h4 { font-size: 14px !important; letter-spacing: -0.01em !important; }

p, span, label, .prose, .markdown-text, .gr-markdown {
  color: var(--qm-text) !important;
}

/* Custom Cards — white surface, hairline border, soft drop shadow */
.qm-card {
  background: var(--qm-surface) !important;
  border: 1px solid var(--qm-border) !important;
  border-radius: 12px !important;
  padding: 24px !important;
  box-shadow: var(--qm-shadow);
  margin-bottom: 24px !important;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.qm-card:hover {
  box-shadow: var(--qm-shadow-lg);
}

/* Quiz question cards: tighter than default cards. Spacing between cards is
   driven by the parent flex column's gap (below), not card margins. */
.qm-quiz-card {
  margin-bottom: 0 !important;
  padding: 18px 20px !important;
}

/* Gradio wraps each quiz card in its own flex column and stacks them with a
   16px gap at several nesting levels. Tighten every column that contains a
   quiz card (any depth) so the questions sit closer together. */
.column:has(.qm-quiz-card) {
  gap: 10px !important;
}

/* Strip Gradio's chunky panels when custom card class is used */
.block, .form, .panel, .group, .gr-block, .gr-form, .gr-panel, .gr-group, fieldset {
  background: transparent !important;
  background-color: transparent !important;
  border: none !important;
  box-shadow: none !important;
}

/* Inputs */
input[type="text"], textarea, .dropdown {
  background: var(--qm-surface) !important;
  color: var(--qm-ink) !important;
  border: 1px solid var(--qm-border) !important;
  border-radius: 8px !important;
  padding: 10px 14px !important;
  font-size: 13.5px !important;
  transition: all 0.2s ease !important;
}

input[type="text"]:focus, textarea:focus, .dropdown:focus {
  border-color: var(--qm-ink) !important;
  box-shadow: 0 0 0 2px rgba(17, 17, 17, 0.08) !important;
  outline: none !important;
}

/* Buttons */
button {
  border-radius: 8px !important;
  font-weight: 600 !important;
  font-size: 13.5px !important;
  padding: 10px 20px !important;
  transition: all 0.15s ease !important;
  cursor: pointer !important;
}

button.primary, button[variant="primary"], .primary, .lg.primary {
  background: var(--qm-accent) !important;
  color: #ffffff !important;
  border: none !important;
  box-shadow: var(--qm-shadow) !important;
}

button.primary:hover:not(:disabled) {
  background: var(--qm-primary-active, #242424) !important;
  box-shadow: var(--qm-shadow-lg) !important;
}

button.secondary, button:not(.primary) {
  background: var(--qm-surface) !important;
  color: var(--qm-ink) !important;
  border: 1px solid var(--qm-border) !important;
}

button.secondary:hover:not(:disabled), button:not(.primary):hover:not(:disabled) {
  background: var(--qm-surface-soft) !important;
  border-color: var(--qm-muted) !important;
}

button:disabled {
  background: var(--qm-surface-2) !important;
  color: var(--qm-muted) !important;
  border-color: var(--qm-border) !important;
  cursor: not-allowed !important;
  box-shadow: none !important;
  transform: none !important;
}

/* Radio groups (quiz choices) */
.gr-radio, [data-testid="radio"] {
  gap: 12px !important;
  display: flex !important;
  flex-direction: column !important;
  margin-top: 8px !important;
}

.gr-radio label, .gr-radio > div > label {
  background: var(--qm-surface) !important;
  border: 1px solid var(--qm-border) !important;
  border-radius: 8px !important;
  padding: 14px 18px !important;
  color: var(--qm-text) !important;
  cursor: pointer !important;
  transition: all 0.15s ease !important;
  display: flex !important;
  align-items: center !important;
  gap: 12px !important;
}

.gr-radio label:hover {
  border-color: var(--qm-blue) !important;
  background: var(--qm-blue-dim) !important;
}

.gr-radio input:checked + span,
.gr-radio label:has(input:checked) {
  background: var(--qm-blue-dim) !important;
  border-color: var(--qm-blue) !important;
}

.gr-radio label input[type="radio"] {
  accent-color: var(--qm-blue) !important;
}

/* Question labels */
.gr-form > label > span:first-child,
.label-wrap span {
  color: var(--qm-ink) !important;
  font-weight: 600 !important;
  font-size: 15px !important;
  margin-bottom: 12px !important;
  display: block !important;
}

/* Markdown blocks */
.gr-markdown h2 {
  border-bottom: 1px solid var(--qm-border) !important;
  padding-bottom: 8px !important;
  margin-top: 24px !important;
}

.gr-markdown code {
  background: var(--qm-surface-2) !important;
  color: var(--qm-ink) !important;
  padding: 2px 6px !important;
  border-radius: 4px !important;
  font-size: 13px !important;
}

footer { display: none !important; }

/* Loading indicator */
.qm-loading {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  color: var(--qm-ink) !important;
  font-weight: 600;
  font-size: 13.5px;
  padding: 12px 18px;
  background: var(--qm-surface-2);
  border: 1px solid var(--qm-border);
  border-radius: 8px;
  margin: 16px 0;
  width: 100%;
  box-sizing: border-box;
}

.qm-loading::before {
  content: "";
  width: 16px;
  height: 16px;
  border: 2.5px solid var(--qm-border);
  border-top-color: var(--qm-ink);
  border-radius: 50%;
  animation: qm-spin 0.8s linear infinite;
  display: inline-block;
}

@keyframes qm-spin {
  to { transform: rotate(360deg); }
}

/* Review details */
.qm-verdict {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 4px 10px;
  border-radius: 9999px;
}

.qm-verdict.correct {
  background: var(--qm-good-dim);
  color: var(--qm-good) !important;
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.qm-verdict.incorrect {
  background: var(--qm-bad-dim);
  color: var(--qm-bad) !important;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.qm-tag {
  display: inline-block;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 9999px;
  margin-left: 10px;
}

.qm-tag.correct { background: var(--qm-good-dim); color: var(--qm-good) !important; border: 1px solid rgba(16, 185, 129, 0.2); }
.qm-tag.chosen  { background: var(--qm-blue-dim); color: var(--qm-blue) !important; border: 1px solid rgba(59, 130, 246, 0.25); }

.qm-choice-correct { font-weight: 600; color: var(--qm-good) !important; }
.qm-choice-chosen  { font-weight: 600; color: var(--qm-blue) !important; }

/* Progress bar */
.qm-progress-container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 20px 0;
  padding: 12px 18px;
  background: var(--qm-surface-soft);
  border-radius: 8px;
  border: 1px solid var(--qm-border);
}

.qm-progress-bar-bg {
  flex-grow: 1;
  height: 6px;
  background: var(--qm-surface-strong, #e5e7eb);
  border-radius: 9999px;
  margin: 0 16px;
  overflow: hidden;
}

.qm-progress-bar-fill {
  height: 100%;
  background: var(--qm-accent);
  width: 0%;
  transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  border-radius: 9999px;
}

.qm-progress-text {
  font-size: 11px;
  font-weight: 700;
  color: var(--qm-ink);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* Distractors and explanations */
.qm-distractor {
  margin: 6px 0 10px 16px;
  padding: 8px 12px;
  border-left: 3px solid var(--qm-bad);
  background: var(--qm-bad-dim);
  color: var(--qm-muted) !important;
  font-size: 12.5px;
  border-radius: 0 6px 6px 0;
}

.qm-explanation {
  margin-top: 14px;
  padding: 12px 16px;
  border-left: 3px solid var(--qm-good);
  background: var(--qm-good-dim);
  color: var(--qm-text) !important;
  font-size: 13px;
  border-radius: 0 8px 8px 0;
}

/* Confidence radios */
.qm-confidence {
  margin-top: 10px !important;
  margin-bottom: 10px !important;
}

.qm-confidence .gr-radio, .qm-confidence [data-testid="radio-group"] {
  flex-direction: row !important;
  gap: 10px !important;
}

.qm-confidence label, .qm-confidence [data-testid="radio-group"] label {
  padding: 6px 14px !important;
  font-size: 11px !important;
  border-radius: 9999px !important;
  background: var(--qm-surface-soft) !important;
}

.qm-confidence label:hover {
  transform: none !important;
  background: var(--qm-surface-2) !important;
  border-color: var(--qm-border) !important;
}

.qm-confidence label {
  cursor: pointer !important;
}

.qm-confidence label.selected,
.qm-confidence label:has(input:checked) {
  background: var(--qm-blue-dim) !important;
  border-color: var(--qm-blue) !important;
  color: var(--qm-blue) !important;
}

.qm-confidence .label-wrap span {
  font-size: 10px !important;
  color: var(--qm-muted) !important;
  text-transform: uppercase;
  letter-spacing: 0.06em !important;
}

/* Timeline components */
.qm-timeline-container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 8px 0 32px 0;
  padding: 14px 20px;
  background: var(--qm-surface);
  border: 1px solid var(--qm-border);
  border-radius: 12px;
  box-shadow: var(--qm-shadow);
}

.qm-timeline-step {
  display: flex;
  align-items: center;
  gap: 10px;
  z-index: 2;
}

.qm-timeline-circle {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--qm-surface);
  border: 1.5px solid var(--qm-border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 13px;
  color: var(--qm-muted);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.qm-timeline-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--qm-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  transition: all 0.3s ease;
}

.qm-timeline-step.active .qm-timeline-circle {
  background: var(--qm-accent);
  border-color: transparent;
  color: #ffffff;
}

.qm-timeline-step.active .qm-timeline-label {
  color: var(--qm-ink);
}

.qm-timeline-step.completed .qm-timeline-circle {
  background: var(--qm-good-dim);
  border-color: var(--qm-good);
  color: var(--qm-good);
}

.qm-timeline-step.completed .qm-timeline-label {
  color: var(--qm-ink);
}

.qm-timeline-line {
  height: 2px;
  background: var(--qm-border);
  flex-grow: 1;
  margin: 0 12px;
  z-index: 1;
}

/* Topic badges inside questions */
.qm-topic-badge {
  background: var(--qm-surface-2);
  color: var(--qm-ink);
  border: 1px solid var(--qm-border);
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 9999px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  display: inline-block;
}

/* Card classes for reviews */
.qm-review-card h4 {
  font-size: 16px !important;
  font-weight: 600 !important;
  margin-top: 0 !important;
  margin-bottom: 14px !important;
}

.qm-choices-list {
  list-style: none;
  padding-left: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.qm-choices-list li {
  padding: 10px 14px;
  background: var(--qm-surface-soft);
  border: 1px solid var(--qm-border);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.qm-choices-list li.qm-choice-correct {
  background: var(--qm-good-dim);
  border-color: var(--qm-good);
}

.qm-choices-list li.qm-choice-chosen {
  background: var(--qm-blue-dim);
  border-color: var(--qm-blue);
}

/* Dashboard Report styling */
.qm-report-dashboard {
  background: var(--qm-surface) !important;
  border: 1px solid var(--qm-border) !important;
  padding: 24px !important;
}

.qm-dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--qm-border);
  padding-bottom: 16px;
  margin-bottom: 20px;
}

.qm-dashboard-header h3 {
  margin: 0 !important;
  font-size: 20px !important;
}

.qm-metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

@media (max-width: 600px) {
  .qm-metrics-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .qm-columns-grid {
    grid-template-columns: 1fr !important;
  }
  .qm-judge-grid {
    grid-template-columns: 1fr !important;
  }
}

.qm-metric-box {
  background: var(--qm-surface-2);
  border: 1px solid var(--qm-border);
  border-radius: 12px;
  padding: 14px 10px;
  text-align: center;
}

.qm-metric-lbl {
  display: block;
  font-size: 10px;
  color: var(--qm-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 6px;
}

.qm-metric-val {
  display: block;
  font-size: 18px;
  font-weight: 700;
  color: var(--qm-ink);
}

.qm-prose-block {
  background: var(--qm-surface-soft);
  border: 1px solid var(--qm-border);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
  line-height: 1.6;
}

.qm-columns-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-top: 20px;
}

.qm-column-card {
  border-radius: 12px;
  padding: 20px;
  border: 1px solid var(--qm-border);
}

.qm-column-card h4 {
  margin-top: 0;
  margin-bottom: 14px;
  font-size: 15px;
  font-weight: 700;
}

.qm-column-card.correct {
  background: var(--qm-good-dim);
  border-color: rgba(16, 185, 129, 0.2);
}

.qm-column-card.correct h4 {
  color: var(--qm-good);
}

.qm-column-card.incorrect {
  background: var(--qm-bad-dim);
  border-color: rgba(239, 68, 68, 0.2);
}

.qm-column-card.incorrect h4 {
  color: var(--qm-bad);
}

.qm-column-card ul {
  padding-left: 0;
  list-style: none;
  margin: 0;
}

.qm-column-card li {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
}

.qm-bullet-green { color: var(--qm-good); font-weight: bold; }
.qm-bullet-red { color: var(--qm-bad); font-weight: bold; }

.qm-ordered-list {
  padding-left: 20px;
  margin: 0;
}

.qm-ordered-list li {
  margin-bottom: 8px;
  line-height: 1.5;
}

.qm-judge-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.qm-judge-scorecard {
  background: var(--qm-surface-2);
  border: 1px solid var(--qm-border);
  border-radius: 12px;
  padding: 16px;
}

.qm-judge-score-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.qm-judge-score-name {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--qm-muted);
}

.qm-judge-score-value {
  font-size: 13px;
  font-weight: 700;
  color: #ffffff;
  background: var(--qm-accent);
  padding: 2px 8px;
  border-radius: 9999px;
}

.qm-judge-score-just {
  font-size: 12px;
  color: var(--qm-text);
  line-height: 1.5;
  margin: 0;
}

.qm-judge-overall {
  border-top: 1px dashed var(--qm-border);
  padding-top: 14px;
  margin-top: 14px;
  color: var(--qm-muted);
  font-size: 12.5px;
}

.qm-wrong-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.qm-wrong-round-header {
  font-weight: 700;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--qm-ink);
  padding: 8px 0;
  border-bottom: 1px solid var(--qm-border);
  margin-top: 16px;
}

.qm-wrong-item {
  padding: 16px 0;
  border-bottom: 1px dashed var(--qm-border);
}

.qm-wrong-item:last-child {
  border-bottom: none;
}

.qm-wrong-meta {
  font-size: 10px;
  font-weight: bold;
  text-transform: uppercase;
  color: var(--qm-muted);
  margin-bottom: 6px;
}

.qm-wrong-prompt {
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--qm-ink);
}

.qm-wrong-answers {
  display: flex;
  gap: 16px;
  font-size: 12.5px;
}

.qm-wrong-stud { color: var(--qm-bad); }
.qm-wrong-corr { color: var(--qm-good); }

.qm-wrong-exp {
  margin-top: 8px;
  font-size: 12px;
  color: var(--qm-muted);
  padding: 6px 10px;
  background: var(--qm-surface-soft);
  border-radius: 6px;
}

.qm-title-container h1 {
  color: var(--qm-ink) !important;
  font-size: 36px !important;
  font-weight: 600 !important;
  letter-spacing: -0.04em !important;
  display: block !important;
  margin: 0 0 8px 0 !important;
}

.qm-title-container p {
  color: var(--qm-muted) !important;
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


def _render_timeline(s: SessionState) -> str:
    phase = s.phase
    
    setup_status = "active" if phase == Phase.INIT else "completed"
    
    if phase in (Phase.ASSESSMENT, Phase.DIAGNOSTIC_REVIEW):
        diag_status = "active"
    elif phase in (Phase.PRACTICE, Phase.PRACTICE_REVIEW, Phase.DONE):
        diag_status = "completed"
    else:
        diag_status = ""
        
    if phase in (Phase.PRACTICE, Phase.PRACTICE_REVIEW):
        practice_status = "active"
    elif phase == Phase.DONE:
        practice_status = "completed"
    else:
        practice_status = ""
        
    done_status = "active" if phase == Phase.DONE else ""
    
    return f"""
    <div class="qm-timeline-container">
      <div class="qm-timeline-step {setup_status}">
        <div class="qm-timeline-circle">1</div>
        <div class="qm-timeline-label">Setup</div>
      </div>
      <div class="qm-timeline-line"></div>
      <div class="qm-timeline-step {diag_status}">
        <div class="qm-timeline-circle">2</div>
        <div class="qm-timeline-label">Diagnostic</div>
      </div>
      <div class="qm-timeline-line"></div>
      <div class="qm-timeline-step {practice_status}">
        <div class="qm-timeline-circle">3</div>
        <div class="qm-timeline-label">Practice</div>
      </div>
      <div class="qm-timeline-line"></div>
      <div class="qm-timeline-step {done_status}">
        <div class="qm-timeline-circle">4</div>
        <div class="qm-timeline-label">Report</div>
      </div>
    </div>
    """


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
        color = "#10b981" if score >= PASS else "#ef4444"
        bars.append(
            f'<div style="margin:4px 0">'
            f'<div style="font-size:11px;color:#6b7280;margin-bottom:2px">{label}</div>'
            f'<div style="display:flex;align-items:center;gap:8px">'
            f'<div style="background:{color};width:{pct}%;height:18px;'
            f'border-radius:9999px;min-width:4px;transition:width .3s"></div>'
            f'<span style="font-size:12px;color:#111111;min-width:32px">{pct}%</span>'
            f'</div></div>'
        )

    return (
        '<div style="padding:16px;background:#f5f5f5;border-radius:12px;'
        'border:1px solid #e5e7eb;margin-bottom:16px">'
        '<div style="font-size:11px;text-transform:uppercase;letter-spacing:.08em;'
        'color:#6b7280;margin-bottom:10px">Score progression</div>'
        + "".join(bars)
        + f'<div style="margin-top:10px;font-size:10px;color:#6b7280">'
        f'<span style="color:#ef4444">■</span> below 70% pass threshold &nbsp;'
        f'<span style="color:#10b981">■</span> passing</div>'
        "</div>"
    )


def _pdf_safe(text: object, has_unicode: bool = False) -> str:
    """fpdf's core fonts only handle latin-1; replace anything they can't render
    so generation never crashes on LLM-produced unicode (math symbols, etc.)."""
    if has_unicode:
        return str(text)
    return str(text).encode("latin-1", "replace").decode("latin-1")


def _collect_wrong(s: SessionState) -> list[tuple[str, dict, dict]]:
    """(round label, question, result) for every incorrect answer, all rounds."""
    wrong: list[tuple[str, dict, dict]] = []
    qmap = {q["id"]: q for q in s.diagnostic_questions}
    for r in s.diagnostic_results:
        if not r["correct"] and r["question_id"] in qmap:
            wrong.append(("Initial test", qmap[r["question_id"]], r))
    for hist in s.practice_history:
        qm = {q["id"]: q for q in hist["questions"]}
        for r in hist["results"]:
            if not r["correct"] and r["question_id"] in qm:
                wrong.append((f"Practice round {hist['iteration']}", qm[r["question_id"]], r))
    return wrong


def _generate_pdf(s: SessionState) -> str:
    """Render the final report to a temp PDF and return its path."""
    import datetime
    import tempfile
    import os
    import urllib.request

    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    # Download DejaVuSans family fonts to enable full Unicode/Turkish rendering in report PDFs
    font_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "fonts")
    os.makedirs(font_dir, exist_ok=True)
    
    font_urls = {
        "DejaVuSans.ttf": "https://raw.githubusercontent.com/pyfpdf/fpdf2/master/test/fonts/DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf": "https://raw.githubusercontent.com/pyfpdf/fpdf2/master/test/fonts/DejaVuSans-Bold.ttf",
        "DejaVuSans-Oblique.ttf": "https://raw.githubusercontent.com/pyfpdf/fpdf2/master/test/fonts/DejaVuSans-Oblique.ttf",
    }
    
    has_dejavu = True
    for filename, url in font_urls.items():
        filepath = os.path.join(font_dir, filename)
        if not os.path.exists(filepath):
            try:
                # 5-second timeout for offline safety and custom user agent to prevent blocks
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=5) as response, open(filepath, "wb") as out_file:
                    out_file.write(response.read())
            except Exception:
                has_dejavu = False
        if not os.path.exists(filepath):
            has_dejavu = False

    report = s.final_report or {}
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    if has_dejavu:
        pdf.add_font("DejaVuSans", "", os.path.join(font_dir, "DejaVuSans.ttf"))
        pdf.add_font("DejaVuSans", "B", os.path.join(font_dir, "DejaVuSans-Bold.ttf"))
        pdf.add_font("DejaVuSans", "I", os.path.join(font_dir, "DejaVuSans-Oblique.ttf"))
        font_family = "DejaVuSans"
    else:
        font_family = "Helvetica"

    pdf.add_page()

    def line(txt: str, h: float) -> None:
        # full-width line that always resets the cursor to the left margin,
        # otherwise the next multi_cell has zero usable width and fpdf raises.
        pdf.multi_cell(0, h, _pdf_safe(txt, has_unicode=has_dejavu), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def heading(txt: str, size: int = 13) -> None:
        pdf.ln(2)
        pdf.set_font(font_family, "B", size)
        line(txt, size * 0.55)

    def body(txt: str, size: int = 11, style: str = "") -> None:
        pdf.set_font(font_family, style, size)
        line(txt, 5.5)

    pdf.set_font(font_family, "B", 20)
    line("QuizMind - Learning Report", 10)
    pdf.set_font(font_family, "", 10)
    pdf.set_text_color(110)
    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    line(f"{s.subject} ({s.level})  -  {date}", 6)
    pdf.set_text_color(0)

    def pct(x: float | None) -> str:
        return f"{x:.0%}" if x is not None else "-"

    mins, secs = divmod(int(s.elapsed_seconds or 0), 60)
    heading("Result", 14)
    body(f"Status: {'PASSED' if s.passed else 'NOT PASSED'}", style="B")
    body(f"Diagnostic score: {pct(s.diagnostic_score)}")
    body(f"Practice score: {pct(s.practice_score)}")
    body(f"Practice rounds: {s.iteration}")
    body(f"Time: {mins}m {secs}s")

    if r := report.get("evaluator_rationale"):
        heading("Evaluator"); body(r)
    if sm := report.get("summary"):
        heading("Summary"); body(sm)
    if m := report.get("mastered_topics"):
        heading("Mastered topics")
        for t in m:
            body(f"- {t}")
    if w := report.get("still_needs_work"):
        heading("Still needs work")
        for t in w:
            body(f"- {t}")
    if steps := report.get("recommended_next_steps"):
        heading("Recommended next steps")
        for i, x in enumerate(steps, 1):
            body(f"{i}. {x}")

    if s.judge_scores:
        heading("Judge scores")
        for key in ("relevance", "difficulty_calibration", "improvement_validity"):
            e = s.judge_scores.get(key, {}) or {}
            body(f"{key.replace('_', ' ').title()}: {e.get('score', '?')}/10", style="B")
            if j := e.get("justification"):
                body(j)
        if oc := s.judge_scores.get("overall_comment"):
            body(oc, style="I")

    if wrong := _collect_wrong(s):
        heading("Questions to review")
        cur = None
        for rnd, q, r in wrong:
            if rnd != cur:
                cur = rnd
                body(rnd, style="B")
            body(f"[{q['topic']}] {q['prompt']}")
            body(f"   Your answer: {r['student_answer']}   Correct: {r['correct_answer']}", size=10)
            if ex := q.get("explanation"):
                body(f"   {ex}", size=10, style="I")

    subject_slug = s.subject.lower().replace(" ", "_")[:20] or "session"
    tmp = tempfile.NamedTemporaryFile(
        suffix=".pdf", prefix=f"quizmind_{subject_slug}_", delete=False
    )
    tmp.close()
    pdf.output(tmp.name)
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


def _format_report_html(s: SessionState) -> str:
    report = s.final_report or {}
    evaluator_rationale = report.get("evaluator_rationale", "")
    summary = report.get("summary", "")
    mastered = report.get("mastered_topics", [])
    still = report.get("still_needs_work", [])
    steps = report.get("recommended_next_steps", [])
    
    # Format time
    time_str = "—"
    if s.elapsed_seconds is not None:
        mins, secs = divmod(int(s.elapsed_seconds), 60)
        time_str = f"{mins}m {secs}s"
        
    diag_score_str = f"{s.diagnostic_score:.0%}" if s.diagnostic_score is not None else "—"
    prac_score_str = f"{s.practice_score:.0%}" if s.practice_score is not None else "—"
    
    pass_badge = '<span class="qm-verdict correct">Passed</span>' if s.passed else '<span class="qm-verdict incorrect">Not Passed</span>'
    
    # Build Mastered / Needs Work HTML
    mastered_html = ""
    if mastered:
        items = "".join(f"<li><span class='qm-bullet-green'>✓</span> {m}</li>" for m in mastered)
        mastered_html = f"""
        <div class="qm-column-card correct">
          <h4>Mastered Topics</h4>
          <ul>{items}</ul>
        </div>
        """
        
    needs_work_html = ""
    if still:
        items = "".join(f"<li><span class='qm-bullet-red'>✗</span> {s_}</li>" for s_ in still)
        needs_work_html = f"""
        <div class="qm-column-card incorrect">
          <h4>Needs Focus</h4>
          <ul>{items}</ul>
        </div>
        """
        
    # Build Next Steps HTML
    next_steps_html = ""
    if steps:
        items = "".join(f"<li>{x}</li>" for x in steps)
        next_steps_html = f"""
        <div class="qm-card" style="margin-top: 24px;">
          <h4 style="margin-top: 0; margin-bottom: 12px; font-size: 16px;">Recommended Next Steps</h4>
          <ol class="qm-ordered-list">{items}</ol>
        </div>
        """
        
    # Build Judge Scores HTML
    judge_html = ""
    if s.judge_scores:
        cards = []
        for key in ("relevance", "difficulty_calibration", "improvement_validity"):
            entry = s.judge_scores.get(key, {}) or {}
            score = entry.get("score", "?")
            just = entry.get("justification", "")
            cards.append(f"""
            <div class="qm-judge-scorecard">
              <div class="qm-judge-score-header">
                <span class="qm-judge-score-name">{key.replace('_', ' ')}</span>
                <span class="qm-judge-score-value">{score}/10</span>
              </div>
              <p class="qm-judge-score-just">{just}</p>
            </div>
            """)
        overall = s.judge_scores.get("overall_comment", "")
        overall_html = f'<p class="qm-judge-overall"><em>{overall}</em></p>' if overall else ""
        judge_html = f"""
        <div class="qm-card" style="margin-top: 24px;">
          <h4 style="margin-top: 0; margin-bottom: 16px; font-size: 16px;">LLM-as-a-Judge Session Review</h4>
          <div class="qm-judge-grid">
            {"".join(cards)}
          </div>
          {overall_html}
        </div>
        """
        
    # Wrong answers section in HTML
    wrong_html = ""
    wrong_list = []
    
    # Diagnostic wrongs
    qmap = {q["id"]: q for q in s.diagnostic_questions}
    for r in s.diagnostic_results:
        if not r["correct"] and r["question_id"] in qmap:
            wrong_list.append({"round": "Initial test", "q": qmap[r["question_id"]], "r": r})
            
    # Practice round wrongs
    for hist in s.practice_history:
        label = f"Practice round {hist['iteration']}"
        qmap_p = {q["id"]: q for q in hist["questions"]}
        for r in hist["results"]:
            if not r["correct"] and r["question_id"] in qmap_p:
                wrong_list.append({"round": label, "q": qmap_p[r["question_id"]], "r": r})
                
    if wrong_list:
        items_html = []
        current_round = None
        for entry in wrong_list:
            if entry["round"] != current_round:
                current_round = entry["round"]
                items_html.append(f'<li class="qm-wrong-round-header">{current_round}</li>')
            q = entry["q"]
            r = entry["r"]
            exp = f'<div class="qm-wrong-exp"><em>{q.get("explanation", "")}</em></div>' if q.get("explanation") else ""
            items_html.append(f"""
            <li class="qm-wrong-item">
              <div class="qm-wrong-meta">[{q['topic']}]</div>
              <div class="qm-wrong-prompt">{q['prompt']}</div>
              <div class="qm-wrong-answers">
                <span class="qm-wrong-stud">Your answer: <code>{r['student_answer']}</code></span>
                <span class="qm-wrong-corr">Correct: <code>{r['correct_answer']}</code></span>
              </div>
              {exp}
            </li>
            """)
        wrong_html = f"""
        <div class="qm-card" style="margin-top: 24px;">
          <h4 style="margin-top: 0; margin-bottom: 16px; font-size: 16px;">Incorrect Questions Review</h4>
          <ul class="qm-wrong-list">
            {"".join(items_html)}
          </ul>
        </div>
        """

    dashboard_html = f"""
    <div class="qm-card qm-report-dashboard" style="margin-bottom: 0px !important;">
      <div class="qm-dashboard-header">
        <h3 style="margin-top: 0px !important;">Final Learning Report</h3>
        {pass_badge}
      </div>
      <div class="qm-metrics-grid">
        <div class="qm-metric-box">
          <span class="qm-metric-lbl">Diagnostic Score</span>
          <span class="qm-metric-val">{diag_score_str}</span>
        </div>
        <div class="qm-metric-box">
          <span class="qm-metric-lbl">Practice Score</span>
          <span class="qm-metric-val">{prac_score_str}</span>
        </div>
        <div class="qm-metric-box">
          <span class="qm-metric-lbl">Practice Rounds</span>
          <span class="qm-metric-val">{s.iteration}</span>
        </div>
        <div class="qm-metric-box">
          <span class="qm-metric-lbl">Time Elapsed</span>
          <span class="qm-metric-val">{time_str}</span>
        </div>
      </div>
      
      {f'<div class="qm-prose-block"><strong>Evaluator:</strong> {evaluator_rationale}</div>' if evaluator_rationale else ''}
      {f'<div class="qm-prose-block"><strong>Summary:</strong> {summary}</div>' if summary else ''}
      
      <div class="qm-columns-grid">
        {mastered_html}
        {needs_work_html}
      </div>
    </div>
    
    {next_steps_html}
    {judge_html}
    {wrong_html}
    """
    return dashboard_html


CSS = CUSTOM_CSS  # re-export so app.py can pass it to launch()


def build_blocks() -> gr.Blocks:
    with gr.Blocks(title="QuizMind") as demo:
        state = gr.State(SessionState())

        @gr.render(inputs=state)
        def render_timeline_header(s: SessionState):
            gr.HTML(_render_timeline(s))

        gr.HTML(
            '<div class="qm-title-container">'
            '<h1>QuizMind</h1>'
            '<p>Adaptive multi-agent quiz system. We test you, find weak spots, and target them until you improve.</p>'
            '</div>'
            '<script>'
            '  (function() {'
            '    document.documentElement.classList.remove("dark");'
            '    document.body.classList.remove("dark");'
            '    const observer = new MutationObserver((mutations) => {'
            '      mutations.forEach((mutation) => {'
            '        if (mutation.type === "attributes" && mutation.attributeName === "class") {'
            '          if (document.documentElement.classList.contains("dark")) {'
            '            document.documentElement.classList.remove("dark");'
            '          }'
            '          if (document.body.classList.contains("dark")) {'
            '            document.body.classList.remove("dark");'
            '          }'
            '        }'
            '      });'
            '    });'
            '    observer.observe(document.documentElement, { attributes: true });'
            '    observer.observe(document.body, { attributes: true });'
            '  })();'
            '</script>'
        )

        with gr.Group(elem_classes=["qm-card"]) as setup_group:
            gr.HTML('<h3 style="margin-top: 0; margin-bottom: 20px; font-size: 18px; border-bottom: 1px solid var(--qm-border); padding-bottom: 10px;">Configure Learning Session</h3>')
            category_in = gr.Dropdown(
                choices=[*config.SUBJECT_CATEGORIES, "Custom..."],
                value=config.SUBJECT_CATEGORIES[0],
                label="Category",
                elem_id="category-dropdown",
            )
            custom_subject_in = gr.Textbox(
                label="Custom subject",
                placeholder="e.g. Ottoman architecture",
                visible=False,
                elem_id="custom-subject-textbox",
            )
            level_in = gr.Radio(
                choices=list(config.LEVELS),
                value="beginner",
                label="Level",
                elem_id="level-radio",
            )
            question_count_in = gr.Slider(
                minimum=5,
                maximum=20,
                step=5,
                value=10,
                label="Questions in initial test",
                elem_id="question-count-slider",
            )
            max_rounds_in = gr.Slider(
                minimum=1,
                maximum=config.MAX_PRACTICE_ROUNDS_LIMIT,
                step=1,
                value=config.MAX_PRACTICE_ROUNDS,
                label="Max practice rounds",
                elem_id="max-rounds-slider",
            )
            file_in = gr.File(
                label="Optional: upload a file to generate questions from (.txt, .md, .pdf)",
                file_types=[".txt", ".md", ".pdf"],
                file_count="single",
                elem_id="file-uploader",
            )
            start_btn = gr.Button("Start test", variant="primary", elem_id="start-session-button")

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

        def start_session(category: str, custom_subject: str, level: str, question_count: int, max_rounds: int, file_obj):
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
                    max_rounds=int(max_rounds),
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
            inputs=[category_in, custom_subject_in, level_in, question_count_in, max_rounds_in, file_in],
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
                    loading_msg="Generating practice questions — usually 20–30 seconds.",
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
                    and s.iteration < s.max_rounds
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
                    loading_msg=(
                        "Generating next questions — usually 20–30 seconds."
                        if will_loop
                        else "Preparing your final report…"
                    ),
                )

            elif s.phase == Phase.DONE:
                if s.round_scores:
                    gr.HTML(_score_chart_html(s.round_scores))
                gr.HTML(_format_report_html(s))

                with gr.Row():
                    restart = gr.Button("Start a new session", variant="primary", elem_id="restart-session-button")
                    gr.DownloadButton(
                        "Download report PDF",
                        value=_generate_pdf(s),
                        variant="secondary",
                        elem_id="download-pdf-button",
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
    
    # Render heading in styled HTML
    clean_heading = heading.replace("## ", "").replace("\n", "<br/>").replace("_", "")
    gr.HTML(f'<div style="margin-bottom: 24px;"><h3>{clean_heading}</h3></div>')
    
    radios: list[gr.Radio] = []
    conf_radios: list[gr.Radio] = []

    for i, q in enumerate(questions):
        with gr.Group(elem_classes=["qm-card", "qm-quiz-card"]):
            gr.HTML(f'<span class="qm-topic-badge" style="margin-bottom: 12px; display: inline-block;">Topic: {q["topic"]}</span>')
            radios.append(
                gr.Radio(
                    choices=q["choices"],
                    label=f"{i + 1}. {q['prompt']}",  # raw label, no markdown processing
                )
            )
            conf_radios.append(
                gr.Radio(
                    choices=["Low", "Medium", "High"],
                    value="Medium",
                    label="Confidence level on this question:",
                    elem_classes=["qm-confidence"],
                    # Wired only as a submit input inside @gr.render; Gradio
                    # then infers it non-interactive. Force it clickable.
                    interactive=True,
                )
            )

    progress = gr.HTML(
        f"""
        <div class="qm-progress-container">
          <span class="qm-progress-text">0 / {len(questions)} Answered</span>
          <div class="qm-progress-bar-bg">
            <div class="qm-progress-bar-fill" style="width: 0%"></div>
          </div>
          <span class="qm-progress-text">0%</span>
        </div>
        """
    )
    submit_btn = gr.Button(submit_label, variant="primary", elem_id="submit-answers-button")
    inline_status = gr.Markdown("")

    def _on_answer_change(*answers):
        answered = sum(1 for a in answers if a)
        total = len(answers)
        pct = int((answered / total) * 100) if total > 0 else 0
        return f"""
        <div class="qm-progress-container">
          <span class="qm-progress-text">{answered} / {total} Answered</span>
          <div class="qm-progress-bar-bg">
            <div class="qm-progress-bar-fill" style="width: {pct}%"></div>
          </div>
          <span class="qm-progress-text">{pct}%</span>
        </div>
        """

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
    loading_msg: str = "Generating next questions — usually 20–30 seconds.",
):
    correct_by_id = {r["question_id"]: r.get("correct", False) for r in results}

    # Summary Card HTML
    summary_html = f"""
    <div class="qm-card qm-summary-header">
      <h3 style="margin-top: 0; margin-bottom: 16px; font-size: 18px;">{heading}</h3>
      <div class="qm-metrics-grid" style="grid-template-columns: repeat(2, 1fr) !important; max-width: 400px; margin-bottom: 0;">
        <div class="qm-metric-box">
          <span class="qm-metric-lbl">Score</span>
          <span class="qm-metric-val">{f"{score:.0%}" if score is not None else '—'}</span>
        </div>
        <div class="qm-metric-box">
          <span class="qm-metric-lbl">Correct Answers</span>
          <span class="qm-metric-val">{sum(correct_by_id.values())} / {len(questions)}</span>
        </div>
      </div>
    """
    
    if weak_topics:
        chips = "".join(f"<code>{_md_escape(w['topic'])}</code> ({w['accuracy']:.0%}) &nbsp;" for w in weak_topics)
        summary_html += f"""
        <div style="margin-top: 16px; border-top: 1px dashed var(--qm-border); padding-top: 12px; font-size: 13px;">
          <strong>Weak topics flagged:</strong> &nbsp;{chips}
        </div>
        """
        
    summary_html += "</div>"
    gr.HTML(summary_html)

    q_htmls = []
    for i, q in enumerate(questions):
        user_ans = user_answers[i] if i < len(user_answers) else ""
        is_correct = correct_by_id.get(q["id"], False)
        verdict_class = "correct" if is_correct else "incorrect"
        verdict_label = "Correct" if is_correct else "Incorrect"
        rationales = q.get("distractor_rationales", {}) or {}
        
        choices_html = []
        for choice in q["choices"]:
            is_right = choice == q.get("correct_answer")
            is_chosen = choice == user_ans
            
            tags = ""
            if is_right:
                tags += '<span class="qm-tag correct">Correct Answer</span>'
            if is_chosen:
                tags += '<span class="qm-tag chosen">Your Answer</span>'
                
            choice_class = ""
            if is_right:
                choice_class = "qm-choice-correct"
            elif is_chosen:
                choice_class = "qm-choice-chosen"
                
            choice_item = f'<li class="{choice_class}"><span>{choice}</span>{tags}</li>'
            if not is_right and (reason := rationales.get(choice)):
                choice_item += f'<div class="qm-distractor">{reason}</div>'
            choices_html.append(choice_item)
            
        exp_html = ""
        if explanation := q.get("explanation", ""):
            exp_html = f'<div class="qm-explanation">{explanation}</div>'
            
        card_html = f"""
        <div class="qm-card qm-review-card">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
            <span class="qm-verdict {verdict_class}">{verdict_label}</span>
            <span class="qm-topic-badge">Topic: {q['topic']}</span>
          </div>
          <h4>{i+1}. {q['prompt']}</h4>
          <ul class="qm-choices-list">
            {"".join(choices_html)}
          </ul>
          {exp_html}
        </div>
        """
        q_htmls.append(card_html)

    gr.HTML("\n".join(q_htmls))
    
    continue_btn = gr.Button(continue_label, variant="primary", elem_id="continue-button")
    inline_status = gr.Markdown("")

    def handler(current_state):
        yield current_state, f'<span class="qm-loading">{loading_msg}</span>'
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
