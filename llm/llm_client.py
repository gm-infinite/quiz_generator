"""Single chokepoint for every LLM call.

Provider-agnostic via OpenAI-compatible APIs. Default is OpenRouter + Qwen,
but the same code works with DashScope, Ollama, Hugging Face, or any other
OpenAI-compat endpoint by changing LLM_API_BASE + LLM_MODEL in core/config.

If you need retries, caching, rate limiting, or a model swap, change it here.
Agents must NOT import the openai SDK directly.
"""
from __future__ import annotations

import json
import os
import time
from typing import TypeVar

from dotenv import load_dotenv
from openai import OpenAI, APIError, APIStatusError
from pydantic import BaseModel, ValidationError

from core import config
from llm import prompts
from tools import web_search

T = TypeVar("T", bound=BaseModel)

load_dotenv()
load_dotenv(".env.example", override=False)

# Retry settings for transient errors (5xx, 429 rate limit).
_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY = 1.0  # seconds; doubles each attempt


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
            or os.environ.get("DASHSCOPE_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("LLM_API_KEY")
        )
        if not key:
            raise RuntimeError(
                "DASHSCOPE_API_KEY is not set. Add it to .env or export it."
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
        if config.USE_STRICT_PARSE:
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

        # JSON mode + manual Pydantic validation.
        # Used when a model doesn't fully support strict json_schema.
        # On schema/semantic validation failure (e.g. correct_answer not in
        # choices), re-prompt the model with its own bad output + the error
        # so it can fix itself.
        messages = list(kwargs.pop("messages"))
        last_err: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            resp = self._chat(
                messages=messages,
                response_format={"type": "json_object"},
                **kwargs,
            )
            text = resp.choices[0].message.content or ""
            try:
                return schema.model_validate_json(text)
            except ValidationError as exc:
                last_err = exc
                if attempt == _RETRY_ATTEMPTS - 1:
                    break
                print(
                    f"[llm] validation failed (attempt {attempt + 1}/{_RETRY_ATTEMPTS}); "
                    f"asking model to fix: {str(exc)[:200]}"
                )
                messages = messages + [
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": (
                            "Your previous JSON failed validation with this error:\n"
                            f"{exc}\n\n"
                            "Return a corrected JSON object that exactly matches the "
                            "schema. Make sure `correct_answer` is one of the strings "
                            "in `choices`, and that `distractor_rationales` keys match "
                            "the incorrect choice strings exactly."
                        ),
                    },
                ]
        assert last_err is not None
        raise last_err

    def generate_structured(self, prompt: str, schema: type[T]) -> T:
        """Call the model and return a validated Pydantic instance."""
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        system = (
            "You are a structured-data generator. Respond with a single JSON "
            "object that EXACTLY matches this JSON schema — including all "
            "required field names. Do NOT return a bare array; the top-level "
            "value must be an object.\n\n"
            f"SCHEMA:\n{schema_json}"
        )
        return self._chat_parsed(
            schema=schema,
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )

    def generate_with_search(
        self, prompt: str, schema: type[T], search_query: str | None = None
    ) -> T:
        """generate_structured with web-search grounding prepended.

        Runs `search_query` through tools/web_search (Tavily or Serper,
        auto-detected from the API key present) and injects the snippets
        above the prompt. Degrades to plain generate_structured when no
        query is given, no key is configured, or the search fails — so
        this is always safe to call.
        """
        if search_query:
            snippets = web_search.search_snippets(search_query)
            if snippets:
                prompt = prompts.search_grounding_block(snippets) + prompt
        return self.generate_structured(prompt, schema)
