"""The report PDF generator must produce a valid file and survive unicode."""
from core.session_state import Phase, SessionState
from ui.views import _generate_pdf


def _state() -> SessionState:
    s = SessionState(subject="Calculus — Bahçeşehir ∑", level="intermediate", phase=Phase.DONE)
    s.iteration = 2
    s.diagnostic_score = 0.5
    s.practice_score = 0.8
    s.passed = True
    s.elapsed_seconds = 372
    s.diagnostic_questions = [
        {"id": "d-0", "topic": "Chain rule", "prompt": "d/dx sin(x²)?",
         "correct_answer": "2x·cos(x²)", "explanation": "Chain rule."},
    ]
    s.diagnostic_results = [
        {"question_id": "d-0", "correct": False,
         "student_answer": "cos(x²)", "correct_answer": "2x·cos(x²)"},
    ]
    s.final_report = {
        "summary": "Good recovery.",
        "mastered_topics": ["Chain rule"],
        "still_needs_work": ["Integration"],
        "recommended_next_steps": ["Drill integration by parts."],
    }
    s.judge_scores = {
        "relevance": {"score": 9, "justification": "On target."},
        "overall_comment": "Solid session.",
    }
    return s


def test_generate_pdf_writes_valid_file():
    path = _generate_pdf(_state())
    with open(path, "rb") as f:
        head = f.read(5)
    assert head == b"%PDF-", f"not a PDF: {head!r}"


def test_generate_pdf_handles_empty_state():
    # A bare DONE state (no report/judge/questions) must not crash.
    path = _generate_pdf(SessionState(subject="", phase=Phase.DONE))
    with open(path, "rb") as f:
        assert f.read(5) == b"%PDF-"
