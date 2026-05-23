"""Extract plain text from an uploaded file.

Supports .txt / .md natively and .pdf via `pypdf` (optional). Unknown
extensions are read as utf-8 text on a best-effort basis. Output is
truncated to `SOURCE_TEXT_MAX_CHARS` so we don't blow the prompt budget.
"""
from __future__ import annotations

import os

from core import config


def extract_text(path: str) -> str:
    if not path:
        return ""
    ext = os.path.splitext(path)[1].lower()

    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError(
                "PDF upload requires `pypdf`. Install it with: pip install pypdf"
            ) from exc
        reader = PdfReader(path)
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    else:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()

    text = text.strip()
    if len(text) > config.SOURCE_TEXT_MAX_CHARS:
        text = text[: config.SOURCE_TEXT_MAX_CHARS] + "\n...[truncated]"
    return text
