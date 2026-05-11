"""Single chokepoint for every Gemini call.

If you need retries, caching, rate limiting, or a model swap, change it here.
Agents must NOT import google.genai directly.
"""
from __future__ import annotations

import os
from typing import TypeVar

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

from core import config

T = TypeVar("T", bound=BaseModel)

load_dotenv()
load_dotenv(".env.example", override=False)


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to .env or export it."
            )
        self._client = genai.Client(api_key=key)
        self._model = model or config.GEMINI_MODEL

    def generate_structured(self, prompt: str, schema: type[T]) -> T:
        """Call the model and return a validated Pydantic instance."""
        resp = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        # The SDK populates `parsed` when response_schema is a Pydantic class.
        parsed = getattr(resp, "parsed", None)
        if parsed is not None:
            return parsed  # type: ignore[return-value]
        return schema.model_validate_json(resp.text)

    def generate_with_search(self, prompt: str, schema: type[T]) -> T:
        """Same as `generate_structured` but with Google Search grounding.

        Note: at time of writing, some Gemini versions don't allow combining
        a response_schema with the search tool. If that combination errors,
        we fall back to a free-form grounded call and parse JSON out of the
        text. Agents shouldn't care — they get a validated Pydantic object.
        """
        search_tool = types.Tool(google_search=types.GoogleSearch())
        try:
            resp = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[search_tool],
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
            parsed = getattr(resp, "parsed", None)
            if parsed is not None:
                return parsed  # type: ignore[return-value]
            return schema.model_validate_json(resp.text)
        except Exception:
            # Fallback: grounded text, then ask the model to reformat as JSON.
            grounded = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(tools=[search_tool]),
            )
            reformatted = self._client.models.generate_content(
                model=self._model,
                contents=(
                    "Reformat the following content into the requested JSON schema "
                    "exactly. Content:\n\n" + (grounded.text or "")
                ),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
            parsed = getattr(reformatted, "parsed", None)
            if parsed is not None:
                return parsed  # type: ignore[return-value]
            return schema.model_validate_json(reformatted.text)
