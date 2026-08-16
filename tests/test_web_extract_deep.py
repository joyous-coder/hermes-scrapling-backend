"""Tests for web_extract_deep tool."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from web_extract_deep import (
    WEB_EXTRACT_DEEP_SCHEMA,
    _handle_web_extract_deep,
)


class TestSchema:
    def test_schema_requires_url(self):
        assert "url" in WEB_EXTRACT_DEEP_SCHEMA["parameters"]["required"]

    def test_schema_modes(self):
        mode = WEB_EXTRACT_DEEP_SCHEMA["parameters"]["properties"]["mode"]
        assert mode["enum"] == ["dynamic", "stealthy"]
        assert mode["default"] == "dynamic"

    def test_schema_has_fallback_hint_in_description(self):
        desc = WEB_EXTRACT_DEEP_SCHEMA["description"]
        assert "web_extract" in desc
        assert "Cloudflare" in desc
        assert "JavaScript" in desc


class TestHandler:
    def test_missing_url(self):
        result = asyncio.run(_handle_web_extract_deep({}))
        parsed = json.loads(result)
        assert "url" in parsed["error"]

    def test_invalid_mode(self):
        result = asyncio.run(
            _handle_web_extract_deep({"url": "https://x.com", "mode": "bogus"})
        )
        parsed = json.loads(result)
        assert "mode must be one of" in parsed["error"]

    def test_routes_mode_to_fetcher(self, monkeypatch):
        """mode=dynamic routes through fetch_html with mode=dynamic."""
        import web_extract_deep as deep_mod

        captured = {}

        def fake_fetch(url, *, mode="static", timeout_ms=30000, css_selector=None,
                       wait_selector=None, extra=None):
            captured["url"] = url
            captured["mode"] = mode
            return {
                "url": url,
                "mode": mode,
                "html": "<html><p>Deep content</p></html>",
                "text": "Deep content",
                "status": 200,
                "title": "Deep",
            }

        monkeypatch.setattr(deep_mod, "fetch_html", fake_fetch)
        result = asyncio.run(
            _handle_web_extract_deep(
                {"url": "https://deep.example/", "mode": "dynamic", "output_format": "text"}
            )
        )
        parsed = json.loads(result)
        assert parsed["success"] is True
        assert captured["mode"] == "dynamic"
        assert parsed["content_length"] > 0

    def test_fetch_failure_returns_error(self, monkeypatch):
        import web_extract_deep as deep_mod

        def bad_fetch(url, **kwargs):
            raise RuntimeError("page crashed")

        monkeypatch.setattr(deep_mod, "fetch_html", bad_fetch)
        result = asyncio.run(
            _handle_web_extract_deep({"url": "https://bad.example/", "mode": "dynamic"})
        )
        parsed = json.loads(result)
        assert "failed" in parsed["error"]


class TestSpillToDisk:
    """Pages larger than the inline limit are written to disk and the
    response returns a path + head/tail preview."""

    def test_small_content_returns_inline(self, monkeypatch, tmp_path):
        """Under the inline limit, content is returned directly."""
        import web_extract_deep as deep_mod

        monkeypatch.setattr(deep_mod, "CACHE_DIR", tmp_path / "cache")

        def fake_fetch(url, **kwargs):
            return {
                "url": url,
                "mode": "dynamic",
                "html": "<p>small</p>",
                "markdown": "small content",
                "text": "small content",
                "status": 200,
                "title": "small",
            }

        monkeypatch.setattr(deep_mod, "fetch_html", fake_fetch)
        result = asyncio.run(
            _handle_web_extract_deep(
                {"url": "https://small.example/", "output_format": "markdown"}
            )
        )
        parsed = json.loads(result)
        assert parsed["success"] is True
        assert "truncated" not in parsed  # small → no spill flag
        assert "file_path" not in parsed
        assert "small content" in parsed["content"]

    def test_large_content_spills_to_disk(self, monkeypatch, tmp_path):
        """Over the inline limit, content is written to disk + preview returned."""
        import web_extract_deep as deep_mod

        monkeypatch.setattr(deep_mod, "CACHE_DIR", tmp_path / "cache")
        # Lower the threshold so we don't need a giant string in the test
        monkeypatch.setenv("WEB_EXTRACT_DEEP_INLINE_LIMIT", "100")

        def fake_fetch(url, **kwargs):
            # Build content larger than the 100-char inline limit
            big = "x" * 500
            return {
                "url": url,
                "mode": "dynamic",
                "html": big,
                "markdown": big,
                "text": big,
                "status": 200,
                "title": "big",
            }

        monkeypatch.setattr(deep_mod, "fetch_html", fake_fetch)
        result = asyncio.run(
            _handle_web_extract_deep(
                {"url": "https://big.example/", "output_format": "markdown"}
            )
        )
        parsed = json.loads(result)
        assert parsed["success"] is True
        assert parsed["truncated"] is True
        assert parsed["inline_limit"] == 100
        assert parsed["content_length"] == 500
        assert "file_path" in parsed
        assert "Use read_file" in parsed["note"]

        # Confirm file was actually written with full content
        file_path = Path(parsed["file_path"])
        assert file_path.exists()
        assert len(file_path.read_text()) == 500
        # Preview should be much shorter than full content. With 500-char
        # content the head/tail windows fully cover it, but the preview
        # still includes truncation marker text and is shorter than a
        # hypothetical 5000-char head alone would be.
        assert "[... middle omitted" in parsed["content"]
        assert "Full text saved to:" in parsed["content"]
        assert "[TRUNCATED]" in parsed["content"]
        assert len(parsed["content"]) < 5000

    def test_spill_failure_returns_truncated_inline(self, monkeypatch, tmp_path):
        """If disk write fails (e.g. permission denied), fall back to inline
        truncation rather than dropping the content entirely."""
        import web_extract_deep as deep_mod

        # Use a path that cannot be created (parent is a file, not a dir)
        blocker = tmp_path / "blocker"
        blocker.write_text("not a dir")
        monkeypatch.setattr(deep_mod, "CACHE_DIR", blocker / "cache")

        monkeypatch.setenv("WEB_EXTRACT_DEEP_INLINE_LIMIT", "50")

        def fake_fetch(url, **kwargs):
            big = "y" * 500
            return {
                "url": url,
                "mode": "dynamic",
                "html": big,
                "markdown": big,
                "text": big,
                "status": 200,
                "title": "big",
            }

        monkeypatch.setattr(deep_mod, "fetch_html", fake_fetch)
        result = asyncio.run(
            _handle_web_extract_deep(
                {"url": "https://nobuffer.example/", "output_format": "markdown"}
            )
        )
        parsed = json.loads(result)
        assert parsed["success"] is True
        assert parsed["truncated"] is True
        # Should have inline truncation but no file_path
        assert "file_path" not in parsed
        assert "spill_error" in parsed
        assert len(parsed["content"]) == 50