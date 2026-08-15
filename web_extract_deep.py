"""web_extract_deep — deep web extraction tool (JS rendering / anti-bot).

Standalone tool registered by this plugin (appears in the deferred
catalog; discover via ``tool_search`` then call). Use it when the plain
``web_extract`` returns incomplete content:

- pages rendered client-side (React / Vue / SPA) where the HTML is
  empty or has no real content, or
- sites behind Cloudflare / anti-bot challenges.

Two modes:

- ``mode="dynamic"``  → scrapling DynamicFetcher (renders JavaScript)
- ``mode="stealthy"`` → scrapling StealthyFetcher (additionally evades
  Cloudflare-style challenges)

Content is returned directly in memory — no intermediate files.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from tools.registry import tool_error, tool_result

from _scrapling_runner import fetch_html, is_scrapling_available

logger = logging.getLogger(__name__)

VALID_MODES = ("dynamic", "stealthy")

WEB_EXTRACT_DEEP_SCHEMA: Dict[str, Any] = {
    "name": "web_extract_deep",
    "description": (
        "Deep web extraction with JavaScript rendering and anti-bot bypass. "
        "Use this tool when web_extract returns incomplete or empty content — "
        "e.g. the page is rendered client-side (React/Vue/SPA, empty HTML), "
        "or the site is protected by Cloudflare / anti-bot challenges. "
        "mode='dynamic' renders JavaScript; mode='stealthy' additionally "
        "evades Cloudflare-style challenges. Returns content directly "
        "(no files written)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to extract.",
            },
            "mode": {
                "type": "string",
                "enum": ["dynamic", "stealthy"],
                "default": "dynamic",
                "description": (
                    "dynamic (default): render JavaScript via scrapling "
                    "DynamicFetcher. stealthy: evade Cloudflare/anti-bot via "
                    "scrapling StealthyFetcher (slower, needs browser)."
                ),
            },
            "css_selector": {
                "type": "string",
                "description": "Optional CSS selector to extract only a region of the page.",
            },
            "wait_selector": {
                "type": "string",
                "description": "Optional CSS selector to wait for before extracting (dynamic/stealthy).",
            },
            "timeout_ms": {
                "type": "integer",
                "default": 30000,
                "minimum": 5000,
                "description": "Fetch timeout in milliseconds.",
            },
            "output_format": {
                "type": "string",
                "enum": ["html", "markdown", "text"],
                "default": "html",
                "description": "Output format: html (raw HTML), text (extracted text), or markdown (best-effort text).",
            },
        },
        "required": ["url"],
    },
}


async def _handle_web_extract_deep(args: Dict[str, Any], **kwargs: Any) -> str:
    """Handler — async, runs the blocking scrapling call in a thread."""
    url = args.get("url")
    if not url or not isinstance(url, str) or not url.strip():
        return tool_error("web_extract_deep requires a non-empty 'url'.")

    if not is_scrapling_available():
        return tool_error(
            "scrapling is not installed in the Hermes environment. "
            "Run: uv pip install --python <hermes-venv-python> 'scrapling[all]'"
        )

    mode = str(args.get("mode", "dynamic") or "dynamic").strip().lower()
    if mode not in VALID_MODES:
        return tool_error(
            f"mode must be one of {', '.join(VALID_MODES)} (got {mode!r})."
        )

    css_selector = args.get("css_selector") or None
    wait_selector = args.get("wait_selector") or None
    timeout_ms = int(args.get("timeout_ms", 30000) or 30000)
    timeout_ms = max(5000, min(timeout_ms, 180000))
    output_format = str(args.get("output_format", "html") or "html").lower()

    try:
        fetched = await asyncio.to_thread(
            fetch_html,
            url,
            mode=mode,
            timeout_ms=timeout_ms,
            css_selector=css_selector,
            wait_selector=wait_selector,
        )
    except Exception as exc:
        logger.warning("web_extract_deep failed for %s: %s", url, exc)
        return tool_error(f"web_extract_deep failed: {exc}")

    if output_format == "text":
        content = fetched["text"] or fetched["html"]
    else:  # html / markdown (markdown falls back to text/html best-effort)
        content = fetched["html"]

    payload = {
        "success": True,
        "url": fetched["url"],
        "title": fetched["title"],
        "status": fetched["status"],
        "mode": fetched["mode"],
        "output_format": output_format,
        "content": content,
        "content_length": len(content),
        "provider": "scrapling",
    }
    return tool_result(payload)