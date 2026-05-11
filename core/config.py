"""Centralized constants. Tune here, not inline."""

GEMINI_MODEL = "gemini-2.5-flash"

DIAGNOSTIC_QUESTION_COUNT = 10
PRACTICE_QUESTIONS_PER_TOPIC = 5

WEAK_TOPIC_THRESHOLD = 0.60      # accuracy below this flags a topic
PASS_ABSOLUTE_THRESHOLD = 0.70   # practice score that ends the loop outright
PASS_IMPROVEMENT_DELTA = 0.20    # improvement over diagnostic that ends the loop

MAX_PRACTICE_ROUNDS = 3

LEVELS = ("beginner", "intermediate", "advanced")
