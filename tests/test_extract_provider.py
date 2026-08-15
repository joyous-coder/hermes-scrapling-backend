"""Tests for ScraplingExtractProvider."""

from __future__ import annotations

from unittest import mock

from extract_provider import ScraplingExtractProvider


class TestScraplingExtractProvider:
    def _provider(self):
        return ScraplingExtractProvider()

    def test_name_and_display(self):
        p = self._provider()
        assert p.name == "scrapling"
        assert p.display_name == "scrapling (Python API)"

    def test_extract_only(self):
        p = self._provider()
        assert p.supports_search() is False
        assert p.supports_extract() is True

    def test_is_available(self):
        assert self._provider().is_available() is True

    def test_extract_returns_standard_shape(self, monkeypatch, fake_response):
        from _scrapling_runner import fetch_html as real_fetch

        fake_resp = fake_response(
            "<html><title>Quotes</title><p>Hello world</p></html>", status=200
        )

        class FakeFetcher:
            @staticmethod
            def get(url, **kwargs):
                return fake_resp

        import _scrapling_runner as _runner_mod
        monkeypatch.setattr(
            _runner_mod, "_import_fetcher", lambda kind: FakeFetcher
        )

        results = self._provider().extract(
            ["https://quotes.toscrape.com/"], format="markdown"
        )
        assert len(results) == 1
        r = results[0]
        assert r["url"] == "https://quotes.toscrape.com/"
        assert r["title"] == "Quotes"
        assert "Hello world" in r["content"]
        # raw_content is now markdown (clean text), not raw HTML
        assert "<html>" not in r["raw_content"]
        assert "Hello world" in r["raw_content"]
        assert r["metadata"]["status"] == 200
        assert r["metadata"]["output_format"] == "markdown"

    def test_extract_per_url_error(self, monkeypatch):
        class FakeFetcher:
            @staticmethod
            def get(url, **kwargs):
                raise RuntimeError("network down")

        import _scrapling_runner as _runner_mod
        monkeypatch.setattr(
            _runner_mod, "_import_fetcher", lambda kind: FakeFetcher
        )
        results = self._provider().extract(["https://bad.example/"])
        assert len(results) == 1
        assert "network down" in results[0]["error"]
        assert results[0]["content"] == ""

    def test_extract_max_chars(self, monkeypatch, fake_response):
        fake_resp = fake_response(
            "<html><body>" + "x" * 500 + "</body></html>", status=200
        )

        class FakeFetcher:
            @staticmethod
            def get(url, **kwargs):
                return fake_resp

        import _scrapling_runner as _runner_mod
        monkeypatch.setattr(
            _runner_mod, "_import_fetcher", lambda kind: FakeFetcher
        )
        results = self._provider().extract(
            ["https://example.com/"], max_chars=100
        )
        assert len(results[0]["content"]) <= 100

    def test_setup_schema(self):
        schema = self._provider().get_setup_schema()
        assert schema["name"] == "scrapling (Python API)"
        assert schema["badge"] == "local"