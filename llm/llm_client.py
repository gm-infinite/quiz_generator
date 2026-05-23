"""Single chokepoint for every LLM call.

Provider-agnostic via OpenAI-compatible APIs. Default is OpenRouter + Qwen,
but the same code works with DashScope, Ollama, Hugging Face, or any other
OpenAI-compat endpoint by changing LLM_API_BASE + LLM_MODEL in core/config.

If you need retries, caching, rate limiting, or a model swap, change it here.
Agents must NOT import the openai SDK directly.
"""
from __future__ import annotations

import os
import time
from typing import TypeVar

from dotenv import load_dotenv
from openai import OpenAI, APIError, APIStatusError
from pydantic import BaseModel

from core import config

T = TypeVar("T", bound=BaseModel)

load_dotenv()
load_dotenv(".env.example", override=False)

# Retry settings for transient errors (5xx, 429 rate limit).
_RETRY_ATTEMPTS = 5
_RETRY_BASE_DELAY = 2.0  # seconds; doubles each attempt


def _is_transient(exc: Exception) -> bool:
    """Return True for errors worth retrying (5xx, 429)."""
    if isinstance(exc, APIStatusError):
        return exc.status_code >= 500 or exc.status_code == 429
    if isinstance(exc, APIError):
        return True  # generic transport errors
    return False


class LLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        key = (
            api_key
            or os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("LLM_API_KEY")
        )
        if not key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Add it to .env or export it."
            )
        self._client = OpenAI(
            api_key=key,
            base_url=base_url or config.LLM_API_BASE,
        )
        self._model = model or config.LLM_MODEL

    def _chat(self, **kwargs):
        """Wrap chat.completions.create with retry on transient errors."""
        last_exc: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                return self._client.chat.completions.create(**kwargs)
            except Exception as exc:
                if not _is_transient(exc):
                    raise
                last_exc = exc
                if attempt == _RETRY_ATTEMPTS - 1:
                    break
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                print(
                    f"[llm] transient error ({type(exc).__name__}); "
                    f"retrying in {delay:.0f}s (attempt {attempt + 1}/{_RETRY_ATTEMPTS})"
                )
                time.sleep(delay)
        assert last_exc is not None
        raise last_exc

    def _chat_parsed(self, schema: type[T], **kwargs) -> T:
        """Chat call that returns a validated Pydantic instance.

        Tries OpenAI's structured-output `parse()` first (sends a strict
        json_schema). If the model rejects strict schemas or returns no
        parsed payload, falls back to JSON-mode + manual Pydantic
        validation. Either way, callers get a validated Pydantic instance.
        """
        last_exc: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                resp = self._client.beta.chat.completions.parse(
                    response_format=schema, **kwargs,
                )
                parsed = resp.choices[0].message.parsed
                if parsed is None:
                    raise ValueError("parsed=None")
                return parsed  # type: ignore[return-value]
            except Exception as exc:
                if not _is_transient(exc):
                    # Non-transient — break out and try the JSON-mode fallback.
                    last_exc = exc
                    break
                last_exc = exc
                if attempt == _RETRY_ATTEMPTS - 1:
                    break
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                print(
                    f"[llm] transient error in parse ({type(exc).__name__}); "
                    f"retrying in {delay:.0f}s (attempt {attempt + 1}/{_RETRY_ATTEMPTS})"
                )
                time.sleep(delay)

        # Fallback: JSON mode + manual Pydantic validation.
        # Used when a model doesn't fully support strict json_schema.
        resp = self._chat(
            response_format={"type": "json_object"},
            **kwargs,
        )
        text = resp.choices[0].message.content or ""
        return schema.model_validate_json(text)

    def generate_structured(self, prompt: str, schema: type[T]) -> T:
        """Call the model and return a validated Pydantic instance."""
        return self._chat_parsed(
            schema=schema,
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a structured-data generator. Respond only "
                        "with JSON matching the requested schema."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )

    def generate_with_search(self, prompt: str, schema: type[T]) -> T:
        """Same as generate_structured. Search grounding dropped in Phase 1.

        TODO(phase-2): wire in an external search tool (Tavily/Serper) and
        inline results into the prompt before generation.
        """
        return self.generate_structured(prompt, schema)
