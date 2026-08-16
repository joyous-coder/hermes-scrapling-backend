"""hermes-scrapling-backend — scrapling web extraction for Hermes Agent.

Two capabilities:

1. **ScraplingExtractProvider** — replaces the built-in ``web_extract``
   backend when ``web.extract_backend: "scrapling"`` is set in
   config.yaml. Uses ``scrapling.Fetcher`` (plain HTTP, lightweight)
   and returns content directly in memory — no intermediate files.

2. **web_extract_deep** — standalone tool for pages the plain fetcher
   can't handle:
     - ``mode="dynamic"``  → ``scrapling.DynamicFetcher`` (renders JS)
     - ``mode="stealthy"`` → ``scrapling.StealthyFetcher`` (evades
       Cloudflare / anti-bot challenges)

Module layout: this plugin deliberately uses a FLAT directory layout
(same as hermes-mmx-backend). The Hermes plugin loader imports only
``__init__.py`` as a single file via ``spec_from_file_location`` — it
does NOT add the plugin directory to ``sys.path`` and does not expose
``__path__`` correctly for relative imports. We therefore load each
sibling module explicitly with ``importlib.util.spec_from_file_location``
and cache it in ``sys.modules`` under both its bare name and our
qualified name so that cross-imports between siblings resolve.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent


def _load(name: str):
    """Load a sibling module file by absolute path; cache in sys.modules."""
    path = _PLUGIN_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load sibling module {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    sys.modules.setdefault(f"{__name__}.{name}", module)
    spec.loader.exec_module(module)
    return module


_runner_mod = _load("_scrapling_runner")
_provider_mod = _load("extract_provider")
_deep_mod = _load("web_extract_deep")

ScraplingExtractProvider = _provider_mod.ScraplingExtractProvider
WEB_EXTRACT_DEEP_SCHEMA = _deep_mod.WEB_EXTRACT_DEEP_SCHEMA
_handle_web_extract_deep = _deep_mod._handle_web_extract_deep


def register(ctx) -> None:
    """Register the extract provider and the web_extract_deep tool."""
    # Provider — route via web.extract_backend: "scrapling"
    ctx.register_web_search_provider(ScraplingExtractProvider())

    # Standalone tool — grouped with the core web tools (web_search /
    # web_extract) so tool_search finds it in the web domain. It still
    # lives in the deferred catalog (non-core tools defer by default).
    ctx.register_tool(
        name="web_extract_deep",
        toolset="web",
        schema=WEB_EXTRACT_DEEP_SCHEMA,
        handler=_handle_web_extract_deep,
        is_async=True,
        emoji="🕷️",
    )