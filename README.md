# hermes-scrapling-backend

[Hermes Agent](https://hermes-agent.nousresearch.com/) plugin that
replaces the built-in `web_extract` backend with
[scrapling](https://github.com/d4vinci/scrapling) and adds
`web_extract_deep`, a deep-extraction tool for pages that need
JavaScript rendering or anti-bot bypass.

## What you get

| Capability | How to enable |
|---|---|
| Replace `web_extract` | `web.extract_backend: "scrapling"` in `config.yaml` |
| Deep extraction tool | `web_extract_deep` (auto-registered; in deferred catalog, discover via `tool_search`) |

## Why scrapling?

- **No API key** — scrapling is a local Python library.
- **Anti-bot** — `StealthyFetcher` evades Cloudflare-style challenges
  out of the box (no solver services, no credentials).
- **JS rendering** — `DynamicFetcher` runs a real browser.
- **No intermediate files** — content is returned directly in memory
  (unlike the scrapling CLI, which writes `OUTPUT_FILE`).

## Prerequisites

The plugin imports scrapling **inside the Hermes environment**, so it
must be installed into Hermes' venv (not just a separate uv tool):

```bash
# Find hermes' venv python (usually):
#   C:\Users\<you>\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe
uv pip install --python "C:/Users/<you>/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe" "scrapling[all]"
```

The `[all]` extra is required — it pulls in `playwright`, `patchright`
and `nodriver` used by `DynamicFetcher` / `StealthyFetcher`. (On this
machine the browsers were already downloaded via `scrapling install`
+ `python -m patchright install chromium`.)

## Install

```bash
hermes plugins install https://github.com/joyous-coder/hermes-scrapling-backend.git
# or shorthand
hermes plugins install joyous-coder/hermes-scrapling-backend
# pin to a commit
hermes plugins install joyous-coder/hermes-scrapling-backend --ref <40-char-sha>
```

## Configure

In `~/.hermes/config.yaml`:

```yaml
web:
  extract_backend: "scrapling"     # route web_extract through scrapling Fetcher
```

## Tool: `web_extract_deep`

Use it when the plain `web_extract` returns incomplete content:

- pages rendered client-side (React / Vue / SPA — empty HTML), or
- sites behind Cloudflare / anti-bot challenges.

```json
{
  "url": "https://example.com/",
  "mode": "dynamic",            // "dynamic" (default) | "stealthy"
  "css_selector": null,         // optional — extract only a region
  "wait_selector": null,        // optional — wait for an element (dynamic/stealthy)
  "timeout_ms": 30000,
  "output_format": "html"       // "html" | "markdown" | "text"
}
```

- `mode="dynamic"` → scrapling `DynamicFetcher` (renders JavaScript)
- `mode="stealthy"` → scrapling `StealthyFetcher` (evades CF/anti-bot)

Content is returned directly — no files written.

## Architecture

```
hermes-scrapling-backend/
├── plugin.yaml            # kind: backend, provides_web_providers + provides_tools
├── __init__.py            # register(ctx): provider + web_extract_deep
├── _scrapling_runner.py   # fetch_html() — Fetcher/DynamicFetcher/StealthyFetcher
├── extract_provider.py    # ScraplingExtractProvider (extract-only)
├── web_extract_deep.py    # web_extract_deep tool (async, to_thread)
└── tests/                 # 22 tests
```

**Flat layout** (no sub-packages): the Hermes plugin loader imports only
`__init__.py` as a single file via `spec_from_file_location`; sibling
modules are loaded explicitly and cached in `sys.modules`. A
`providers/` sub-package would collide with hermes-agent's own
`providers/` package (see hermes-mmx-backend for the same fix).

## Notes on deferral

`web_extract_deep` is a non-core plugin tool, so by default it lives in
the **deferred catalog** (discoverable via `tool_search` →
`tool_describe` → `tool_call`). This is decided by hermes'
`tools.tool_search` config (`auto` by default), not by the plugin —
`register_tool` has no eager/deferred switch. Setting
`tools.tool_search: off` in config.yaml makes ALL plugin tools eager
(including this one and mmx's tools), at the cost of a larger tool
schema on every API call.

## Development

```bash
uv venv .testvenv --python 3.11
source .testvenv/Scripts/activate
uv pip install pytest
python -m pytest tests/ -v     # 22 tests, no network
```

## License

MIT — see [LICENSE](LICENSE).