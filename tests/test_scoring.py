from tools import scoring


Q = lambda qid, topic, correct: {  # noqa: E731
    "id": qid, "topic": topic, "correct_answer": correct,
    "prompt": "?", "choices": ["A", "B"], "explanation": "",
}


def test_grade_answers_marks_correct_and_wrong():
    qs = [Q("1", "math", "A"), Q("2", "math", "B")]
    graded = scoring.grade_answers(qs, ["A", "C"])
    assert graded[0]["correct"] is True
    assert graded[1]["correct"] is False
    assert graded[1]["student_answer"] == "C"


def test_grade_answers_length_mismatch_raises():
    import pytest
    with pytest.raises(ValueError):
        scoring.grade_answers([Q("1", "x", "A")], [])


def test_overall_accuracy_empty_is_zero():
    assert scoring.overall_accuracy([]) == 0.0


def test_per_topic_accuracy_buckets_by_topic():
    graded = [
        {"topic": "a", "correct": True},
        {"topic": "a", "correct": False},
        {"topic": "b", "correct": True},
    ]
    per = scoring.per_topic_accuracy(graded)
    assert per["a"] == 0.5
    assert per["b"] == 1.0


def test_weak_topics_threshold_and_ordering():
    per = {"a": 0.4, "b": 0.9, "c": 0.2}
    weak = scoring.weak_topics(per, threshold=0.6)
    assert weak == ["c", "a"]  # sorted by accuracy ascending


def test_weak_topics_strict_inequality():
    # exactly at threshold is NOT weak
    per = {"a": 0.6}
    assert scoring.weak_topics(per, threshold=0.6) == []
