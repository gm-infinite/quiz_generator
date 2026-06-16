"""Web search grounding via Tavily or Serper.

Zero extra dependencies — stdlib urllib only. The provider is auto-detected
from whichever API key is set (TAVILY_API_KEY checked first, then
SERPER_API_KEY). A missing key, a disabled flag, or any network/parse
failure degrades gracefully to an empty string so question generation
proceeds ungrounded rather than crashing mid-session.
"""
from __future__ import annotations

import json
import os
import urllib.request

from core import config

_TAVILY_URL = "https://api.tavily.com/search"
_SERPER_URL = "https://google.serper.dev/search"


def _post_json(url: str, payload: dict, headers: dict[str, str]) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=config.SEARCH_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _search_tavily(query: str, max_results: int, api_key: str) -> list[dict]:
    data = _post_json(
        _TAVILY_URL,
        {"query": query, "max_results": max_results, "api_key": api_key},
        {},
    )
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("content", ""),
        }
        for r in data.get("results", [])
    ]


def _search_serper(query: str, max_results: int, api_key: str) -> list[dict]:
    data = _post_json(
        _SERPER_URL,
        {"q": query, "num": max_results},
        {"X-API-KEY": api_key},
    )
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("link", ""),
            "snippet": r.get("snippet", ""),
        }
        for r in data.get("organic", [])
    ]


def search_snippets(query: str, max_results: int | None = None) -> str:
    """Run a web search and return a numbered snippet block, or "".

    Empty string means "no grounding available" — callers must treat that
    as a signal to generate from model knowledge alone, never as an error.
    """
    if not config.SEARCH_ENABLED or not query:
        return ""
    max_results = max_results or config.SEARCH_MAX_RESULTS

    if key := os.environ.get("TAVILY_API_KEY"):
        provider, run = "tavily", lambda: _search_tavily(query, max_results, key)
    elif key := os.environ.get("SERPER_API_KEY"):
        provider, run = "serper", lambda: _search_serper(query, max_results, key)
    else:
        return ""

    try:
        results = run()
    except Exception as exc:
        print(
            f"[web_search] {provider} search failed "
            f"({type(exc).__name__}: {exc}); proceeding ungrounded"
        )
        return ""

    lines = []
    for i, r in enumerate(results[:max_results], 1):
        snippet = (r["snippet"] or "")[: config.SEARCH_SNIPPET_MAX_CHARS]
        lines.append(f"[{i}] {r['title']} ({r['url']})\n{snippet}")
    return "\n\n".join(lines)
