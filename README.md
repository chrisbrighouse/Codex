# Codex Chat + MCP Servers

This repo contains a simple CLI chatbot (`scripts/chatty`) and MCP servers for geolocation and a school timetable.

## Quick Start
- Run chat: `scripts/chatty` (Windows: `scripts\chatty.bat` or `scripts\chatty.ps1`)
- Note: the chat launcher auto-starts the Timetable MCP if it's not running.
- MCP Geo server control: `python3 scripts/mcp_geo_ctl.py start|status|stop`
- Short geo control: `scripts/gmcp start|status|stop` (Windows: `scripts\\gmcp.bat`/`.ps1`)
- MCP Timetable server control: `scripts/ttmcp start|status|stop`

## Short Launcher
- Unix/macOS: `scripts/chatty` (optionally add `scripts/` to `PATH`)
- Windows (CMD): `scripts\chatty.bat`
- Windows (PowerShell): `scripts\chatty.ps1`
  - If needed: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` or `Unblock-File scripts\chatty.ps1`

## MCP Geo Server (Nominatim)
- Start: `python3 scripts/mcp_geo_ctl.py start`
- Status: `python3 scripts/mcp_geo_ctl.py status`
- Stop: `python3 scripts/mcp_geo_ctl.py stop`
- Manual run: `python3 scripts/mcp_geo_server.py --host 127.0.0.1 --port 8081 --user-agent "codex-mcp-geo/0.1 (+you@example.com)"`
- Endpoints: `POST /mcp`, `GET /geocode`, `GET /reverse`

## MCP Timetable Server (Week A/B)
Loads `assets/timetable.csv` and answers timetable questions with alternating Week A/B logic.

- Control commands:
  - Start: `scripts/ttmcp start` (defaults: host `127.0.0.1`, port `8082`, path `Assets/timetable.csv`, week A `2025-09-08`, TZ `Europe/London`)
  - Status: `scripts/ttmcp status`
  - Stop: `scripts/ttmcp stop`
  - Windows: use `scripts\ttmcp.bat` or `scripts\ttmcp.ps1`

- Manual run:
  - `python3 scripts/mcp_timetable_server.py --path Assets/timetable.csv --weeka-start 2025-09-08 --tz Europe/London --host 127.0.0.1 --port 8082`

- Endpoints:
  - `POST /mcp` methods: `timetable.weekType`, `timetable.day`, `timetable.at`, `timetable.next`
  - Helper GETs: `/status`, `/day?date=YYYY-MM-DD`
  - New: `timetable.find` — subject search (case-insensitive)
    - Params: `subject` (required; accepts `subject|subj|lesson|class`), optional `date` (ISO date or `today|tomorrow|yesterday|Mon..Sun`) or `from`/`datetime`
    - Behavior:
      - With `date` only: returns lessons matching the subject on that date: `{week, date, lessons:[...]}`
      - With `from`/`datetime` or none: finds the next matching lesson: `{week, lesson|null}`

- Example chat queries handled automatically:
  - "what lessons on Tuesday week A?"
  - "first period tomorrow"
  - "3rd period on Friday week B"
  - "what lesson at 10:15 on Monday?"

- Logging
  - Log file: `.mcp_timetable.log` in the repo root.
  - Start with log level (DEBUG recommended while testing):
    - Unix/macOS: `scripts/ttmcp start --log-level DEBUG`
    - Windows: `scripts\ttmcp.bat start --log-level DEBUG` or `scripts\ttmcp.ps1 start --log-level DEBUG`
  - Stop: `scripts/ttmcp stop`
  - Tail logs (Unix/macOS): `tail -f .mcp_timetable.log`
  - View logs (Windows CMD): `type .mcp_timetable.log`
  - View logs (PowerShell): `Get-Content .mcp_timetable.log -Wait`
