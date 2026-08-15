"""Pytest config for hermes-scrapling-backend tests.

Runs against the user's hermes-agent install (real agent.* ABCs and
tools.registry helpers), so the provider contract is exercised with the
real base classes. We only need the plugin directory importable.

The ``fake_response`` fixture builds a scrapling-like Response stub
(no network) so the runner tests don't hit the internet.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(html: str) -> str:
    return _TAG_RE.sub(" ", html).strip()


class FakeElement:
    """A single element; holds its own HTML fragment."""

    def __init__(self, html: str):
        self._html = html

    def get_all_text(self) -> str:
        return _strip_tags(self._html)

    def __str__(self) -> str:
        return self._html


class FakeResponse:
    """Minimal stand-in for scrapling's Response object.

    Implements a tiny CSS-selector matcher good enough for tests:
      - ``title``            → element wrapping the <title> text
      - ``.class`` or ``tag``→ element wrapping the matching tag's text
    """

    def __init__(self, html: str, status: int = 200):
        self._html = html
        self.status = status
        self.body = html.encode("utf-8")

    def get_all_text(self) -> str:
        return _strip_tags(self._html)

    def css(self, selector: str) -> list:
        selector = selector.strip()
        # title selector
        if selector == "title":
            m = re.search(r"<title[^>]*>(.*?)</title>", self._html, re.S)
            if m:
                return [FakeElement(m.group(0))]
            return []
        # .class selector
        if selector.startswith("."):
            cls = selector[1:]
            m = re.search(
                rf'<[^>]+class="[^"]*\b{cls}\b[^"]*"[^>]*>(.*?)</[^>]+>',
                self._html, re.S,
            )
            if m:
                return [FakeElement(m.group(0))]
            return []
        # bare tag selector
        m = re.search(rf"<{selector}[^>]*>(.*?)</{selector}>", self._html, re.S)
        if m:
            return [FakeElement(m.group(0))]
        return []


@pytest.fixture
def fake_response():
    def _make(html: str, status: int = 200) -> FakeResponse:
        return FakeResponse(html, status=status)

    return _make