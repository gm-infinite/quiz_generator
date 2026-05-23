"""Centralized constants. Tune here, not inline."""

# LLM provider config
LLM_API_BASE = "https://openrouter.ai/api/v1"   # OpenRouter (default)
# Alternatives:
#   "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"   # Alibaba DashScope
#   "http://localhost:11434/v1"                                # Ollama (local)
#   "https://api-inference.huggingface.co/v1"                  # Hugging Face

LLM_MODEL = "qwen/qwen3.6-plus:free"
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

MAX_PRACTICE_ROUNDS = 3

LEVELS = ("beginner", "intermediate", "advanced")
