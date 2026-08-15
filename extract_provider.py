"""ScraplingExtractProvider — replaces web_extract via the scrapling API.

Subclasses :class:`agent.web_search_provider.WebSearchProvider` with
``supports_extract() == True`` and ``supports_search() == False``.
When ``web.extract_backend: "scrapling"`` is set in config.yaml, every
``web_extract`` tool call routes here.

Extraction uses ``scrapling.Fetcher`` (plain HTTP, lightweight, fast).
The returned content is built in memory — no intermediate files are
written. For pages that need JS rendering or anti-bot bypass, the
model should fall back to the separate ``web_extract_deep`` tool.

Response shape follows the provider contract (list of per-URL dicts)::

    [
        {
            "url": str,
            "title": str,
            "content": str,        # clean text (or selector-limited)
            "raw_content": str,    # full HTML
            "metadata": dict,      # status, mode
            "error": str,          # only on per-URL failure
        },
        ...
    ]
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agent.web_search_provider import WebSearchProvider

from _scrapling_runner import fetch_html, is_scrapling_available

logger = logging.getLogger(__name__)


class ScraplingExtractProvider(WebSearchProvider):
    """scrapling-backed web extraction provider (extract-only)."""

    @property
    def name(self) -> str:
        return "scrapling"

    @property
    def display_name(self) -> str:
        return "scrapling (Python API)"

    def is_available(self) -> bool:
        return is_scrapling_available()

    def supports_search(self) -> bool:
        return False

    def supports_extract(self) -> bool:
        return True

    def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        """Extract content from one or more URLs.

        ``kwargs`` may carry forward-compat fields (``format``,
        ``include_raw``, ``max_chars``, ``css_selector``, ``timeout_ms``)
        — we honor the ones we understand and ignore the rest.
        """
        format_hint = str(kwargs.get("format", "") or "").lower()
        include_raw = bool(kwargs.get("include_raw", True))
        max_chars = kwargs.get("max_chars")
        css_selector = kwargs.get("css_selector")
        timeout_ms = int(kwargs.get("timeout_ms", 30000) or 30000)

        results: List[Dict[str, Any]] = []
        for url in urls:
            try:
                fetched = fetch_html(
                    url,
                    mode="static",
                    timeout_ms=timeout_ms,
                    css_selector=css_selector,
                )
            except Exception as exc:
                logger.warning("scrapling extract failed for %s: %s", url, exc)
                results.append(
                    {
                        "url": url,
                        "title": "",
                        "content": "",
                        "raw_content": "",
                        "metadata": {"status": None, "mode": "static"},
                        "error": str(exc),
                    }
                )
                continue

            # Prefer clean text; fall back to HTML when asked for html.
            if format_hint in ("html", "raw"):
                content = fetched["html"]
            else:
                content = fetched["text"] or fetched["html"]

            if max_chars and isinstance(max_chars, int) and len(content) > max_chars:
                content = content[:max_chars]

            results.append(
                {
                    "url": fetched["url"],
                    "title": fetched["title"],
                    "content": content,
                    "raw_content": fetched["html"] if include_raw else "",
                    "metadata": {
                        "status": fetched["status"],
                        "mode": fetched["mode"],
                    },
                }
            )

        return results

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "scrapling (Python API)",
            "badge": "local",
            "tag": "Web extraction via scrapling — no API key, no files.",
            "env_vars": [],
        }