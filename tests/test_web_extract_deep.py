"""Tests for web_extract_deep tool."""

from __future__ import annotations

import asyncio
import json

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