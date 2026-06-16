"""Centralized constants. Tune here, not inline."""

# LLM provider config
LLM_API_BASE = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"   # Alibaba DashScope (default)
# Alternatives:
#   "https://openrouter.ai/api/v1"                             # OpenRouter
#   "http://localhost:11434/v1"                                # Ollama (local)
#   "https://api-inference.huggingface.co/v1"                  # Hugging Face

LLM_MODEL = "qwen-plus"

# DashScope's OpenAI-compat endpoint doesn't reliably honor strict
# json_schema via `beta.chat.completions.parse`, so we go straight to
# JSON mode. Flip to True if you switch to a provider that supports it.
USE_STRICT_PARSE = False
# Free tier default as of May 2026. Verify at
# https://openrouter.ai/models?max_price=0 — OpenRouter's free catalog
# rotates as model providers add/remove free hosting. The Qwen 2.5 series
# (the original Phase 1 default) has been retired from the free tier.
#
# Other options:
#   "qwen/qwen3.6-plus-preview:free"   — newer preview; logs prompts/completions for training
#   "qwen/qwen3-coder:free"            — 480B MoE, code-tuned (overkill for general quizzes)
#   "qwen/qwen3.6-plus"                — paid version, no rate limits worth mentioning
#   "qwen/qwen3.6-27b"                 — paid smaller variant
#   "qwen3:8b"                         — if running locally via Ollama

# Quiz constants
DIAGNOSTIC_QUESTION_COUNT = 10
PRACTICE_QUESTIONS_PER_TOPIC = 5

WEAK_TOPIC_THRESHOLD = 0.60      # accuracy below this flags a topic
PASS_ABSOLUTE_THRESHOLD = 0.70   # practice score that ends the loop outright
PASS_IMPROVEMENT_DELTA = 0.20    # improvement over diagnostic that ends the loop

MAX_PRACTICE_ROUNDS = 3         # default round cap; user can override per session
MAX_PRACTICE_ROUNDS_LIMIT = 5   # hard ceiling for the per-session override

LEVELS = ("beginner", "intermediate", "advanced")

# Predefined subject categories surfaced in the UI dropdown.
SUBJECT_CATEGORIES = (
    "Geography of Turkey",
    "World History",
    "Python Programming",
    "JavaScript & Web Development",
    "Data Structures & Algorithms",
    "Machine Learning Basics",
    "Linear Algebra",
    "Calculus",
    "Statistics & Probability",
    "Biology",
    "Chemistry",
    "Physics",
    "English Grammar",
    "General Knowledge",
)

# Cap on how much uploaded-file text we forward to the LLM (chars).
SOURCE_TEXT_MAX_CHARS = 20_000

# Web search grounding (Phase 2). Active only when SEARCH_ENABLED is True
# AND a TAVILY_API_KEY or SERPER_API_KEY is present in the environment/.env.
# Without a key, generate_with_search silently falls back to ungrounded
# generation — nothing breaks.
SEARCH_ENABLED = True
SEARCH_MAX_RESULTS = 4
SEARCH_TIMEOUT_SECONDS = 8
SEARCH_SNIPPET_MAX_CHARS = 500   # per-result truncation before prompt injection
