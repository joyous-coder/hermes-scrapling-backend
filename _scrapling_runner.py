"""scrapling runner — thin wrapper around the scrapling Python API.

All fetch functions return content directly in memory (str HTML or str
text) — NO intermediate files are ever written. This is the key
difference from the scrapling CLI (`scrapling extract fetch URL out.html`),
which forces file output; here we use the Python API and serialize the
response object's HTML/text to a string.

Three modes:

- static   → ``scrapling.Fetcher.get(url)``            — plain HTTP, fastest
- dynamic  → ``scrapling.DynamicFetcher.fetch(url)``   — renders JavaScript
- stealthy → ``scrapling.StealthyFetcher.fetch(url)``  — evades CF/anti-bot

Each returns a scrapling ``Response`` object. Verified API surface
(scrapling 0.4.14):

- ``response.body``            → bytes (the raw HTML)
- ``response.get_all_text()``  → str (extracted text)
- ``response.css(sel)``        → list of elements (NOT ``css_first``)
- ``response.status``          → int HTTP status

Note: ``str(response)`` is NOT the HTML — it renders a debug repr like
``<200 https://...>``. Always decode ``.body``.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Proxy configuration
#
# The plugin reads proxy settings from environment variables (set them in
# Hermes' .env file, e.g. ~/AppData/Local/hermes/.env):
#
#   EXTRACT_PROXY=http://host:port
#   # or with credentials inline:
#   EXTRACT_PROXY=http://user:pass@host:port
#   # optional explicit auth for the static fetcher:
#   EXTRACT_PROXY_AUTH=user:pass
#
# When neither is set, requests go direct (no proxy). The resolved value
# is memoized per-process — restart the gateway after changing .env.
# ---------------------------------------------------------------------------

_PROXY_ENV = "EXTRACT_PROXY"
_PROXY_AUTH_ENV = "EXTRACT_PROXY_AUTH"

_proxy_cache: Optional[Tuple[str, Tuple[str, str] | None]] = None


def get_proxy_config() -> Tuple[str, Tuple[str, str] | None]:
    """Return (proxy_url, proxy_auth) resolved from EXTRACT_PROXY env.

    Returns ("", None) when no proxy is configured (direct connection).
    Result is memoized — restart the gateway after changing .env.
    """
    global _proxy_cache
    if _proxy_cache is not None:
        return _proxy_cache

    proxy = os.environ.get(_PROXY_ENV, "").strip()
    auth: Tuple[str, str] | None = None

    # Credentials can be inline in the URL (http://user:pass@host) or in a
    # separate EXTRACT_PROXY_AUTH=user:pass variable.
    if proxy:
        # Split inline user:pass@ from the URL for the static fetcher's
        # proxy_auth parameter; dynamic/stealthy accept it inline instead.
        try:
            from urllib.parse import urlparse

            parsed = urlparse(proxy)
            if parsed.username and parsed.password:
                auth = (parsed.username, parsed.password)
        except Exception:
            pass

    raw_auth = os.environ.get(_PROXY_AUTH_ENV, "").strip()
    if not auth and raw_auth and ":" in raw_auth:
        user, _, pwd = raw_auth.partition(":")
        auth = (user, pwd)

    _proxy_cache = (proxy, auth)
    return _proxy_cache


def clear_proxy_cache() -> None:
    """Reset memoized proxy config (used by tests)."""
    global _proxy_cache
    _proxy_cache = None


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


def is_scrapling_available() -> bool:
    """Return True when the scrapling package is importable.

    Cheap check used by the provider's ``is_available()`` — no network,
    no browser launch.
    """
    try:
        import scrapling  # noqa: F401

        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------


def _import_fetcher(kind: str):
    """Import and return the scrapling fetcher class for *kind*."""
    import scrapling

    if kind == "dynamic":
        return scrapling.DynamicFetcher
    if kind == "stealthy":
        return scrapling.StealthyFetcher
    return scrapling.Fetcher


def _html_from_response(response: Any) -> str:
    """Extract HTML str from a scrapling Response (bytes .body → utf-8)."""
    body = getattr(response, "body", None)
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    # Fallback: repr of the object (only reached on exotic responses).
    return str(response)


def fetch_html(
    url: str,
    *,
    mode: str = "static",
    timeout_ms: int = 30000,
    css_selector: Optional[str] = None,
    wait_selector: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Fetch a URL and return in-memory content.

    Returns a dict::

        {
            "url": str,
            "mode": str,
            "html": str,          # full HTML (or selector-matched HTML)
            "text": str,          # extracted text (or selector-matched text)
            "status": int|None,   # HTTP status if available
            "title": str,         # <title> if available
        }

    Raises RuntimeError on any fetch failure — callers convert to the
    hermes tool_error / per-URL error shape.
    """
    fetcher_cls = _import_fetcher(mode)

    # scrapling's `timeout` is passed straight to playwright's
    # set_default_navigation_timeout / set_default_timeout, whose unit is
    # MILLISECONDS. Do NOT divide by 1000.
    kwargs: Dict[str, Any] = {"timeout": timeout_ms}
    if wait_selector:
        kwargs["wait_selector"] = wait_selector
    if extra:
        kwargs.update(extra)

    # Apply proxy from EXTRACT_PROXY env (if configured). Explicit per-call
    # proxy in `extra` wins; otherwise we use the env-configured value.
    if "proxy" not in kwargs:
        proxy, proxy_auth = get_proxy_config()
        if proxy:
            if mode == "static":
                kwargs["proxy"] = proxy
                if proxy_auth:
                    kwargs["proxy_auth"] = proxy_auth
            else:
                # dynamic/stealthy accept str URL or playwright dict.
                kwargs["proxy"] = proxy

    try:
        if mode == "static":
            response = fetcher_cls.get(url, **kwargs)
        else:
            response = fetcher_cls.fetch(url, **kwargs)
    except Exception as exc:
        logger.warning("scrapling %s fetch failed for %s: %s", mode, url, exc)
        raise RuntimeError(f"scrapling {mode} fetch failed: {exc}") from exc

    html = _html_from_response(response)
    status = getattr(response, "status", None)
    try:
        status = int(status) if status is not None else None
    except (TypeError, ValueError):
        status = None

    # Title via css('title') — returns a list (no css_first in 0.4.14).
    title = ""
    try:
        title_els = response.css("title")
        if title_els:
            title = title_els[0].get_all_text().strip()
    except Exception:
        title = ""

    if css_selector:
        try:
            matched = response.css(css_selector)
            html = "\n".join(str(el) for el in matched)
            text = "\n".join(el.get_all_text() for el in matched)
        except Exception as exc:
            logger.warning("css_selector %r failed: %s", css_selector, exc)
            text = response.get_all_text() if response is not None else ""
    else:
        text = response.get_all_text() if response is not None else ""

    return {
        "url": url,
        "mode": mode,
        "html": html,
        "text": text,
        "status": status,
        "title": title,
    }