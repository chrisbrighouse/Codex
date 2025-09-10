# Next Steps

A lightweight checklist to resume work quickly next session.

- Timetable intents: extend phrasing (e.g., "period after lunch", "first class", "what's on this afternoon").
- Timetable server: add basic unit tests (CSV parsing, weekType math, at/next lookups) and sample fixture.
- Chat UX: default to OpenAI when `OPENAI_API_KEY` is present; show active model in banner.
- Config: allow overriding both MCP endpoints via `.env` (supports `TIMETABLE_ENDPOINT`, `MCP_ENDPOINT`).
- CI: make Ruff blocking; optionally add Black `--check` and a minimal `ruff.toml`.
- Docs: add examples for Windows usage (`.ps1` execution policy notes already included).
- A2A: design a small protocol for calling the timetable server via A2A once the connector is implemented.
- Geo server: optional caching (in-memory, short TTL) to reduce repeated lookups.

When ready, convert items into GitHub issues and link them here.

