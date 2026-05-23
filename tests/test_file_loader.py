"""Tests for tools.file_loader (no real PDFs — keep it deterministic)."""
from __future__ import annotations

from core import config
from tools.file_loader import extract_text


def test_empty_path_returns_empty_string():
    assert extract_text("") == ""


def test_txt_file_is_read_verbatim(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("Photosynthesis converts light into chemical energy.\n")
    out = extract_text(str(p))
    assert "Photosynthesis" in out


def test_markdown_file_treated_as_text(tmp_path):
    p = tmp_path / "notes.md"
    p.write_text("# Title\n\nbody text")
    out = extract_text(str(p))
    assert "body text" in out


def test_truncation_at_max_chars(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SOURCE_TEXT_MAX_CHARS", 50)
    p = tmp_path / "big.txt"
    p.write_text("A" * 500)
    out = extract_text(str(p))
    assert len(out) <= 50 + len("\n...[truncated]")
    assert out.endswith("[truncated]")


def test_unknown_extension_falls_back_to_text(tmp_path):
    p = tmp_path / "data.log"
    p.write_text("line one\nline two")
    out = extract_text(str(p))
    assert "line one" in out and "line two" in out


def test_non_utf8_bytes_do_not_crash(tmp_path):
    p = tmp_path / "weird.txt"
    p.write_bytes(b"valid \xff\xfe bytes")  # invalid utf-8 mid-string
    out = extract_text(str(p))
    assert "valid" in out  # errors='ignore' keeps readable parts
