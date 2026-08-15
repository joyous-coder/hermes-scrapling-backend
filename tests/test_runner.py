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

class TestProxyConfig:
    def test_no_proxy_default(self, monkeypatch):
        from _scrapling_runner import clear_proxy_cache, get_proxy_config

        monkeypatch.delenv("EXTRACT_PROXY", raising=False)
        monkeypatch.delenv("EXTRACT_PROXY_AUTH", raising=False)
        clear_proxy_cache()
        assert get_proxy_config() == ("", None)

    def test_proxy_from_env(self, monkeypatch):
        from _scrapling_runner import clear_proxy_cache, get_proxy_config

        monkeypatch.setenv("EXTRACT_PROXY", "http://127.0.0.1:7890")
        monkeypatch.delenv("EXTRACT_PROXY_AUTH", raising=False)
        clear_proxy_cache()
        proxy, auth = get_proxy_config()
        assert proxy == "http://127.0.0.1:7890"
        assert auth is None

    def test_proxy_with_inline_auth(self, monkeypatch):
        from _scrapling_runner import clear_proxy_cache, get_proxy_config

        monkeypatch.setenv("EXTRACT_PROXY", "http://user:pass@127.0.0.1:7890")
        monkeypatch.delenv("EXTRACT_PROXY_AUTH", raising=False)
        clear_proxy_cache()
        proxy, auth = get_proxy_config()
        assert proxy == "http://user:pass@127.0.0.1:7890"
        assert auth == ("user", "pass")

    def test_proxy_auth_separate_env(self, monkeypatch):
        from _scrapling_runner import clear_proxy_cache, get_proxy_config

        monkeypatch.setenv("EXTRACT_PROXY", "http://127.0.0.1:7890")
        monkeypatch.setenv("EXTRACT_PROXY_AUTH", "user:pass")
        clear_proxy_cache()
        proxy, auth = get_proxy_config()
        assert proxy == "http://127.0.0.1:7890"
        assert auth == ("user", "pass")


class TestFetchWithProxy:
    def test_static_passes_proxy_and_auth(self, monkeypatch, fake_response):
        """With EXTRACT_PROXY set, static fetch passes proxy + proxy_auth."""
        captured = {}
        fake_resp = fake_response("<html><body>ok</body></html>", status=200)

        class FakeFetcher:
            @staticmethod
            def get(url, **kwargs):
                captured["kwargs"] = kwargs
                return fake_resp

        import _scrapling_runner as _runner_mod
        monkeypatch.setattr(_runner_mod, "_import_fetcher", lambda kind: FakeFetcher)
        monkeypatch.setenv("EXTRACT_PROXY", "http://user:pass@127.0.0.1:7890")
        monkeypatch.delenv("EXTRACT_PROXY_AUTH", raising=False)
        _runner_mod.clear_proxy_cache()

        fetch_html("https://example.com", mode="static", timeout_ms=30000)
        assert captured["kwargs"]["proxy"] == "http://user:pass@127.0.0.1:7890"
        assert captured["kwargs"]["proxy_auth"] == ("user", "pass")

    def test_dynamic_passes_proxy(self, monkeypatch, fake_response):
        captured = {}
        fake_resp = fake_response("<html><body>ok</body></html>", status=200)

        class FakeFetcher:
            @staticmethod
            def fetch(url, **kwargs):
                captured["kwargs"] = kwargs
                return fake_resp

        import _scrapling_runner as _runner_mod
        monkeypatch.setattr(_runner_mod, "_import_fetcher", lambda kind: FakeFetcher)
        monkeypatch.setenv("EXTRACT_PROXY", "http://127.0.0.1:7890")
        monkeypatch.delenv("EXTRACT_PROXY_AUTH", raising=False)
        _runner_mod.clear_proxy_cache()

        fetch_html("https://example.com", mode="dynamic", timeout_ms=30000)
        assert captured["kwargs"]["proxy"] == "http://127.0.0.1:7890"

    def test_no_proxy_no_kwargs(self, monkeypatch, fake_response):
        captured = {}
        fake_resp = fake_response("<html><body>ok</body></html>", status=200)

        class FakeFetcher:
            @staticmethod
            def get(url, **kwargs):
                captured["kwargs"] = kwargs
                return fake_resp

        import _scrapling_runner as _runner_mod
        monkeypatch.setattr(_runner_mod, "_import_fetcher", lambda kind: FakeFetcher)
        monkeypatch.delenv("EXTRACT_PROXY", raising=False)
        monkeypatch.delenv("EXTRACT_PROXY_AUTH", raising=False)
        _runner_mod.clear_proxy_cache()

        fetch_html("https://example.com", mode="static", timeout_ms=30000)
        assert "proxy" not in captured["kwargs"]
        assert "proxy_auth" not in captured["kwargs"]

    def test_explicit_extra_proxy_wins(self, monkeypatch, fake_response):
        captured = {}
        fake_resp = fake_response("<html><body>ok</body></html>", status=200)

        class FakeFetcher:
            @staticmethod
            def get(url, **kwargs):
                captured["kwargs"] = kwargs
                return fake_resp

        import _scrapling_runner as _runner_mod
        monkeypatch.setattr(_runner_mod, "_import_fetcher", lambda kind: FakeFetcher)
        monkeypatch.setenv("EXTRACT_PROXY", "http://env-proxy:8080")
        monkeypatch.delenv("EXTRACT_PROXY_AUTH", raising=False)
        _runner_mod.clear_proxy_cache()

        fetch_html(
            "https://example.com", mode="static", timeout_ms=30000,
            extra={"proxy": "http://explicit-proxy:8080"},
        )
        assert captured["kwargs"]["proxy"] == "http://explicit-proxy:8080"


class TestMarkdownOutput:
    def test_fetch_html_defaults_to_markdown_content(self, monkeypatch, fake_response):
        """fetch_html returns markdown in content by default."""
        fake_resp = fake_response("<html><body><p>Hello <b>world</b></p></body></html>", status=200)

        class FakeFetcher:
            @staticmethod
            def get(url, **kwargs):
                return fake_resp

        import _scrapling_runner as _runner_mod
        monkeypatch.setattr(_runner_mod, "_import_fetcher", lambda kind: FakeFetcher)
        # FakeResponse isn't a real Selector → Convertor path falls back to
        # get_all_text, so content should contain the text.
        result = fetch_html("https://example.com", mode="static", timeout_ms=30000)
        assert result["content"]  # non-empty
        assert "Hello" in result["content"]
        assert "html" in result
        assert "markdown" in result

    def test_fetch_html_output_format_html(self, monkeypatch, fake_response):
        fake_resp = fake_response("<html><body><p>Hi</p></body></html>", status=200)

        class FakeFetcher:
            @staticmethod
            def get(url, **kwargs):
                return fake_resp

        import _scrapling_runner as _runner_mod
        monkeypatch.setattr(_runner_mod, "_import_fetcher", lambda kind: FakeFetcher)
        result = fetch_html(
            "https://example.com", mode="static", timeout_ms=30000,
            output_format="html",
        )
        assert "<html>" in result["content"]

    def test_fetch_html_output_format_text(self, monkeypatch, fake_response):
        fake_resp = fake_response("<html><body><p>Hi</p></body></html>", status=200)

        class FakeFetcher:
            @staticmethod
            def get(url, **kwargs):
                return fake_resp

        import _scrapling_runner as _runner_mod
        monkeypatch.setattr(_runner_mod, "_import_fetcher", lambda kind: FakeFetcher)
        result = fetch_html(
            "https://example.com", mode="static", timeout_ms=30000,
            output_format="text",
        )
        assert "Hi" in result["content"]
        assert "<" not in result["content"] or "Hi" in result["content"]
