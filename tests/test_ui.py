"""Unit and integration tests for the Gradio UI and views in ui/views.py."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import gradio as gr
import pytest

from core.session_state import Phase, SessionState
from ui.views import (
    _fresh,
    _generate_pdf,
    _format_history,
    _format_report,
    _format_report_html,
    _format_wrong_answers,
    _md_escape,
    _render_quiz,
    _render_review,
    _render_timeline,
    _score_chart_html,
    build_blocks,
)


def test_fresh():
    s = SessionState(subject="math")
    s_fresh = _fresh(s)
    assert s_fresh is not s
    assert s_fresh.subject == s.subject


def test_md_escape():
    assert _md_escape("Normal Text") == "Normal Text"
    assert _md_escape("Topic_With_Underscores") == "Topic\\_With\\_Underscores"
    assert _md_escape("Math * Bold") == "Math \\* Bold"
    assert _md_escape("Code ` block") == "Code \\` block"
    assert _md_escape("Slash\\Backslash") == "Slash\\\\Backslash"


def test_render_timeline():
    # Phase.INIT
    s = SessionState(phase=Phase.INIT)
    html = _render_timeline(s)
    assert "qm-timeline-step active" in html
    assert "Setup" in html

    # Phase.ASSESSMENT
    s = SessionState(phase=Phase.ASSESSMENT)
    html = _render_timeline(s)
    assert "qm-timeline-step completed" in html
    assert "qm-timeline-step active" in html
    assert "Diagnostic" in html

    # Phase.PRACTICE
    s = SessionState(phase=Phase.PRACTICE)
    html = _render_timeline(s)
    assert "qm-timeline-step completed" in html
    assert "qm-timeline-step active" in html
    assert "Practice" in html

    # Phase.DONE
    s = SessionState(phase=Phase.DONE)
    html = _render_timeline(s)
    assert "qm-timeline-step completed" in html
    assert "qm-timeline-step active" in html
    assert "Report" in html


def test_score_chart_html():
    # Empty scores
    assert _score_chart_html([]) == ""

    # Progression scores
    html = _score_chart_html([0.5, 0.8])
    assert "Initial test" in html
    assert "Round 1" in html
    assert "50%" in html
    assert "80%" in html
    # Below threshold (70%): red color
    assert "#ef4444" in html
    # Passing: green color
    assert "#10b981" in html


def test_generate_pdf():
    s = SessionState(
        subject="Python Programming",
        level="intermediate",
        question_count=5,
        max_rounds=3,
        passed=True,
        diagnostic_score=0.8,
    )
    filepath = _generate_pdf(s)
    assert os.path.exists(filepath)
    try:
        with open(filepath, "rb") as f:
            assert f.read(5) == b"%PDF-"
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


@patch("tools.session_storage.load_sessions")
def test_format_history(mock_load):
    # Empty history
    mock_load.return_value = []
    assert _format_history() == "_No sessions recorded yet._"

    # History entries
    mock_load.return_value = [
        {
            "timestamp": 1718460000,
            "subject": "Ottoman architecture",
            "level": "beginner",
            "passed": True,
            "diagnostic_score": 0.6,
            "practice_score": 0.8,
            "elapsed_seconds": 150.0,
        }
    ]
    res = _format_history()
    assert "**Ottoman architecture**" in res
    assert "(beginner)" in res
    assert "init: `60%`" in res
    assert "final: `80%`" in res
    assert "✓" in res


def test_format_wrong_answers():
    # No wrong answers
    s = SessionState()
    assert _format_wrong_answers(s) == ""

    # Diagnostic wrong answers
    q1 = {"id": "d1", "topic": "topic_a", "prompt": "Prompt A", "explanation": "Explanation A"}
    q2 = {"id": "d2", "topic": "topic_b", "prompt": "Prompt B"}
    s = SessionState(
        diagnostic_questions=[q1, q2],
        diagnostic_results=[
            {"question_id": "d1", "correct": False, "student_answer": "X", "correct_answer": "Y"},
            {"question_id": "d2", "correct": True, "student_answer": "A", "correct_answer": "A"},
        ],
    )
    wrong = _format_wrong_answers(s)
    assert "Questions to review" in wrong
    assert "Initial test" in wrong
    assert "[topic\\_a]" in wrong
    assert "Prompt A" in wrong
    assert "Your answer: `X`" in wrong
    assert "Correct: `Y`" in wrong
    assert "Explanation A" in wrong
    assert "Prompt B" not in wrong  # correct answer


def test_format_report():
    s = SessionState(
        diagnostic_score=0.6,
        practice_score=0.9,
        passed=True,
        iteration=2,
        elapsed_seconds=125,
        final_report={
            "evaluator_rationale": "Improved significantly.",
            "summary": "Overall good performance.",
            "mastered_topics": ["topic_a"],
            "still_needs_work": ["topic_b"],
            "recommended_next_steps": ["Step 1", "Step 2"],
        },
        judge_scores={
            "relevance": {"score": 9, "justification": "Good relevance"},
            "overall_comment": "Excellent work!",
        },
    )
    report = _format_report(s)
    assert "Final report" in report
    assert "Initial test score:** `60%`" in report
    assert "Practice score:** `90%`" in report
    assert "Passed:** `True`" in report
    assert "rounds: `2`" in report
    assert "Time:** `2m 5s`" in report
    assert "Evaluator.** Improved significantly." in report
    assert "Summary.** Overall good performance." in report
    assert "Mastered:** `topic_a`" in report
    assert "Still needs work:** `topic_b`" in report
    assert "Next steps:" in report
    assert "- Step 1" in report
    assert "Judge scores" in report
    assert "relevance:** `9/10` — Good relevance" in report
    assert "_Excellent work!_" in report


def test_format_report_html():
    s = SessionState(
        diagnostic_score=0.6,
        practice_score=0.9,
        passed=True,
        iteration=2,
        elapsed_seconds=125,
        final_report={
            "evaluator_rationale": "Improved significantly.",
            "summary": "Overall good performance.",
            "mastered_topics": ["topic_a"],
            "still_needs_work": ["topic_b"],
            "recommended_next_steps": ["Step 1", "Step 2"],
        },
        judge_scores={
            "relevance": {"score": 9, "justification": "Good relevance"},
            "overall_comment": "Excellent work!",
        },
    )
    html = _format_report_html(s)
    assert "Final Learning Report" in html
    assert "Passed" in html
    assert "60%" in html
    assert "90%" in html
    assert "Mastered Topics" in html
    assert "topic_a" in html
    assert "Needs Focus" in html
    assert "topic_b" in html
    assert "Recommended Next Steps" in html
    assert "Step 1" in html
    assert "LLM-as-a-Judge Session Review" in html
    assert "relevance" in html
    assert "9/10" in html


def test_build_blocks_initial_state():
    demo = build_blocks()
    assert isinstance(demo, gr.Blocks)

    # Check component types constructed in build_blocks
    blocks_types = [type(b) for b in demo.blocks.values()]
    assert gr.Dropdown in blocks_types
    assert gr.Radio in blocks_types
    assert gr.Slider in blocks_types
    assert gr.File in blocks_types
    assert gr.Button in blocks_types

    dropdowns = [b for b in demo.blocks.values() if isinstance(b, gr.Dropdown)]
    assert len(dropdowns) >= 1
    category_dropdown = dropdowns[0]
    assert category_dropdown.label == "Category"

    from core import config
    choices_values = [c[1] for c in category_dropdown.choices]
    assert all(choice in choices_values for choice in config.SUBJECT_CATEGORIES)


def test_toggle_custom_handler():
    demo = build_blocks()
    toggle_fn = None
    for fn_obj in demo.fns.values():
        if fn_obj.fn.__name__ == "_toggle_custom":
            toggle_fn = fn_obj.fn
            break

    assert toggle_fn is not None

    # Selecting Custom... should show custom textbox
    res = toggle_fn("Custom...")
    assert isinstance(res, dict)
    assert res.get("visible") is True

    # Selecting predefined category should hide custom textbox
    res = toggle_fn("History")
    assert isinstance(res, dict)
    assert res.get("visible") is False


@patch("ui.views._orchestrator")
@patch("ui.views.extract_text")
def test_start_session_handler(mock_extract, mock_orch_get):
    demo = build_blocks()
    start_session_fn = None
    for fn_obj in demo.fns.values():
        if fn_obj.fn.__name__ == "start_session":
            start_session_fn = fn_obj.fn
            break

    assert start_session_fn is not None

    # Case 1: Empty subject when Custom category chosen
    gen = start_session_fn("Custom...", "   ", "beginner", 10, 3, None)
    res = list(gen)
    assert len(res) == 1
    state_upd, group_upd, status_msg = res[0]
    assert isinstance(state_upd, dict)
    assert "_Please pick or enter a subject._" in status_msg

    # Case 2: File reading exception
    mock_extract.side_effect = RuntimeError("PDF read error")
    gen = start_session_fn("History", "", "beginner", 10, 3, "fake_file.pdf")
    res = list(gen)
    assert len(res) == 1
    state_upd, group_upd, status_msg = res[0]
    assert isinstance(state_upd, dict)
    assert "Could not read file: PDF read error" in status_msg

    # Case 3: Empty file content
    mock_extract.side_effect = None
    mock_extract.return_value = ""
    gen = start_session_fn("History", "", "beginner", 10, 3, "empty.txt")
    res = list(gen)
    assert len(res) == 1
    state_upd, group_upd, status_msg = res[0]
    assert isinstance(state_upd, dict)
    assert "File appears empty." in status_msg

    # Case 4: Successful configuration and start
    mock_orchestrator = MagicMock()
    mock_orch_get.return_value = mock_orchestrator
    mock_state = SessionState(subject="History", level="beginner")
    mock_orchestrator.start.return_value = mock_state

    gen = start_session_fn("History", "", "beginner", 10, 3, None)
    res = list(gen)
    assert len(res) == 2

    # First yield should be loading state
    state_upd, group_upd, status_msg = res[0]
    assert isinstance(state_upd, dict)
    assert "Generating test questions" in status_msg
    assert group_upd.get("visible") is False

    # Second yield should be the new active state
    state_upd, group_upd, status_msg = res[1]
    assert isinstance(state_upd, SessionState)
    assert state_upd.subject == "History"
    assert status_msg == ""

    # Verify orchestrator.start was called with expected values
    mock_orchestrator.start.assert_called_once_with(
        "History", "beginner", source_text="", question_count=10, max_rounds=3
    )


def test_submit_handler_quiz():
    state_var = gr.State(SessionState())
    questions = [
        {"id": "q1", "topic": "math", "prompt": "1+1?", "choices": ["A", "B"]},
        {"id": "q2", "topic": "science", "prompt": "Sky color?", "choices": ["C", "D"]},
    ]
    mock_on_submit = MagicMock()

    with gr.Blocks() as temp_blocks:
        _render_quiz(
            state_var=state_var,
            questions=questions,
            heading="Test quiz",
            submit_label="Submit",
            on_submit=mock_on_submit,
        )

    submit_handler_fn = None
    for fn_obj in temp_blocks.fns.values():
        if fn_obj.fn.__name__ == "submit_handler":
            submit_handler_fn = fn_obj.fn
            break

    assert submit_handler_fn is not None

    # Case 1: Missing answers from the user
    state = SessionState()
    gen = submit_handler_fn(state, "", "", "Medium", "Medium")
    res = list(gen)
    assert len(res) == 1
    state_res, status_msg = res[0]
    assert "_Please answer all questions. Missing:" in status_msg

    # Case 2: Success submission
    updated_state = SessionState(phase=Phase.DIAGNOSTIC_REVIEW)
    mock_on_submit.return_value = updated_state

    state = SessionState()
    gen = submit_handler_fn(state, "A", "C", "High", "Low")
    res = list(gen)
    assert len(res) == 2

    # First yield is grading status
    state_res1, status_msg1 = res[0]
    assert "Grading and analyzing your answers" in status_msg1

    # Second yield is updated state
    state_res2, status_msg2 = res[1]
    assert state_res2.phase == Phase.DIAGNOSTIC_REVIEW
    assert status_msg2 == ""

    # Verify confidence ratings were captured
    assert state.confidence_ratings == {"q1": 3, "q2": 1}
    mock_on_submit.assert_called_once_with(state, ["A", "C"])


def test_continue_handler_review():
    state_var = gr.State(SessionState())
    questions = [{"id": "q1", "topic": "math", "prompt": "1+1?", "choices": ["2", "3"]}]
    user_answers = ["2"]
    results = [{"question_id": "q1", "correct": True}]
    mock_on_continue = MagicMock()

    with gr.Blocks() as temp_blocks:
        _render_review(
            state_var=state_var,
            questions=questions,
            user_answers=user_answers,
            results=results,
            score=1.0,
            weak_topics=[],
            heading="Review",
            continue_label="Continue",
            on_continue=mock_on_continue,
        )

    continue_handler_fn = None
    for fn_obj in temp_blocks.fns.values():
        if fn_obj.fn.__name__ == "handler":
            continue_handler_fn = fn_obj.fn
            break

    assert continue_handler_fn is not None

    state = SessionState()
    updated_state = SessionState(phase=Phase.PRACTICE)
    mock_on_continue.return_value = updated_state

    gen = continue_handler_fn(state)
    res = list(gen)
    assert len(res) == 2

    # First yield is loading state
    state_res1, status_msg1 = res[0]
    assert "Generating next questions" in status_msg1

    # Second yield is updated state
    state_res2, status_msg2 = res[1]
    assert state_res2.phase == Phase.PRACTICE
    assert status_msg2 == ""

    mock_on_continue.assert_called_once_with(state)


def test_active_renders():
    # Verify that all sub-renderers execute without raising exceptions under each phase.

    # Phase 1: ASSESSMENT
    with gr.Blocks():
        state_var = gr.State(SessionState())
        _render_quiz(
            state_var,
            [{"id": "d1", "topic": "math", "prompt": "1+1?", "choices": ["A"]}],
            heading="Test",
            submit_label="Submit",
            on_submit=lambda st, ans: st,
        )

    # Phase 2: DIAGNOSTIC_REVIEW
    with gr.Blocks():
        state_var = gr.State(SessionState())
        _render_review(
            state_var,
            questions=[{"id": "d1", "topic": "math", "prompt": "1+1?", "choices": ["A"]}],
            user_answers=["A"],
            results=[{"question_id": "d1", "correct": True}],
            score=1.0,
            weak_topics=[],
            heading="Review",
            continue_label="Continue",
            on_continue=lambda st: st,
        )

    # Phase 3: PRACTICE
    with gr.Blocks():
        state_var = gr.State(SessionState())
        _render_quiz(
            state_var,
            [{"id": "p1", "topic": "math", "prompt": "1+1?", "choices": ["A"]}],
            heading="Practice",
            submit_label="Submit",
            on_submit=lambda st, ans: st,
        )

    # Phase 4: PRACTICE_REVIEW
    with gr.Blocks():
        state_var = gr.State(SessionState())
        _render_review(
            state_var,
            questions=[{"id": "p1", "topic": "math", "prompt": "1+1?", "choices": ["A"]}],
            user_answers=["A"],
            results=[{"question_id": "p1", "correct": True}],
            score=1.0,
            weak_topics=[],
            heading="Review",
            continue_label="See report",
            on_continue=lambda st: st,
        )
