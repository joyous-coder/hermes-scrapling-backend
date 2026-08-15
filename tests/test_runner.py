"""Tests for the scrapling runner helpers."""

from __future__ import annotations

from unittest import mock

from _scrapling_runner import (
    _html_from_response,
    _import_fetcher,
    fetch_html,
    is_scrapling_available,
)


class TestIsScraplingAvailable:
    def test_true_when_importable(self):
        assert is_scrapling_available() is True

    def test_false_when_import_fails(self, monkeypatch):
        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "scrapling":
                raise ImportError("no scrapling")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fake_import)
        assert is_scrapling_available() is False


class TestImportFetcher:
    def test_maps_modes(self):
        from scrapling import DynamicFetcher, Fetcher, StealthyFetcher

        assert _import_fetcher("static") is Fetcher
        assert _import_fetcher("dynamic") is DynamicFetcher
        assert _import_fetcher("stealthy") is StealthyFetcher
        assert _import_fetcher("bogus") is Fetcher  # unknown → static


class TestHtmlFromResponse:
    def test_decodes_bytes_body(self, fake_response):
        resp = fake_response("<html><body>hi</body></html>")
        html = _html_from_response(resp)
        assert "<html>" in html
        assert "hi" in html


class TestFetchHtml:
    def test_static_returns_content(self, monkeypatch, fake_response):
        fake_resp = fake_response("<html><title>T</title><p>Hello</p></html>", status=200)

        class FakeFetcher:
            @staticmethod
            def get(url, **kwargs):
                return fake_resp

        import _scrapling_runner as _runner_mod
        monkeypatch.setattr(
            _runner_mod, "_import_fetcher", lambda kind: FakeFetcher
        )
        result = fetch_html("https://example.com", mode="static", timeout_ms=30000)

        assert result["url"] == "https://example.com"
        assert result["status"] == 200
        assert "Hello" in result["html"]
        assert "Hello" in result["text"]

    def test_timeout_passed_as_ms_not_seconds(self, monkeypatch, fake_response):
        """scrapling timeout is milliseconds — regression guard."""
        captured = {}
        fake_resp = fake_response("<p>x</p>")

        class FakeFetcher:
            @staticmethod
            def get(url, **kwargs):
                captured["kwargs"] = kwargs
                return fake_resp

        import _scrapling_runner as _runner_mod
        monkeypatch.setattr(
            _runner_mod, "_import_fetcher", lambda kind: FakeFetcher
        )
        fetch_html("https://example.com", mode="static", timeout_ms=30000)
        assert captured["kwargs"]["timeout"] == 30000  # NOT 30

    def test_css_selector_limits_content(self, monkeypatch, fake_response):
        fake_resp = fake_response(
            '<div class="a">AAA</div><div class="b">BBB</div>', status=200
        )

        class FakeFetcher:
            @staticmethod
            def get(url, **kwargs):
                return fake_resp

        import _scrapling_runner as _runner_mod
        monkeypatch.setattr(
            _runner_mod, "_import_fetcher", lambda kind: FakeFetcher
        )
        result = fetch_html(
            "https://example.com", mode="static", timeout_ms=30000,
            css_selector=".a",
        )
        assert "AAA" in result["html"]
        assert "BBB" not in result["html"]

    def test_fetch_failure_raises(self, monkeypatch):
        class FakeFetcher:
            @staticmethod
            def get(url, **kwargs):
                raise RuntimeError("boom")

        import _scrapling_runner as _runner_mod
        monkeypatch.setattr(
            _runner_mod, "_import_fetcher", lambda kind: FakeFetcher
        )
        import pytest

        with pytest.raises(RuntimeError, match="boom"):
            fetch_html("https://example.com", mode="static", timeout_ms=30000)