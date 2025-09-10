Title: feat(mcp): timetable server + geo auto-start + chat intents

Summary

- Add MCP Timetable server that serves Week A/B lessons from CSV and answers:
  - timetable.weekType, timetable.day, timetable.at, timetable.next
- Integrate timetable intents in chat:
  - “what lessons on Tuesday (week A|B)?”, “first/2nd/last period …”, “what lesson at 10:15 on Monday?”, “next lesson”, “what week is YYYY-MM-DD?”
- Restore/solidify MCP Geo server and add auto-start for both MCPs in chat launchers.
- Add short control wrappers:
  - Timetable: scripts/ttmcp (start|status|stop), plus .bat/.ps1
  - Geo: scripts/gmcp (start|status|stop), plus .bat/.ps1
- Chat launchers (chatty/.bat/.ps1) now:
  - Auto-start Timetable MCP (127.0.0.1:8082) and Geo MCP (127.0.0.1:8081) if not running
  - Print “Timetable MCP connected (…)” / “Geo MCP connected (…)”
- Config: support TIMETABLE_ENDPOINT in src/config.py
- Docs: README with quick usage for chat + MCP servers
- CI: GitHub Actions running unit tests and Ruff lint (non-blocking)
- Git hygiene: ignore .env and MCP PID files

Changes

- scripts/:
  - mcp_timetable_server.py, mcp_timetable_ctl.py, ttmcp, ttmcp.bat, ttmcp.ps1
  - mcp_geo_server.py, mcp_geo_ctl.py, gmcp, gmcp.bat, gmcp.ps1
  - chatty, chatty.bat, chatty.ps1 (with MCP auto-start)
- src/:
  - main.py (timetable + geocode intent routing, MCP auto-connect with labels)
  - config.py (TIMETABLE_ENDPOINT)
  - utils/intent.py (timetable + geocode intent detection)
  - utils/dotenv.py
  - chat/session.py
  - connectors/{mcp_client.py,a2a_client.py}
  - providers/{echo.py,openai_provider.py}
- .gitignore: add .mcp_timetable.pid
- README.md: usage docs for chat + servers
- .github/workflows/ci.yml: unit tests + Ruff (non-blocking)

Test Plan

- Launch chat: scripts/chatty (Windows: scripts\\chatty.bat or scripts\\chatty.ps1)
  - Expect: “Timetable MCP connected (…)” and “Geo MCP connected (…)”
- Try:
  - “tell me the coordinates of paris, france” → “MCP: Geolocate …”
  - “what lessons on Tuesday week A?” → “MCP: Timetable Week A schedule …”
  - “first period tomorrow”, “3rd period on Friday week B”
  - “what lesson at 10:15 on Monday?”
  - “next lesson”
  - “what week is 2025-09-09?”
- Direct server checks:
  - scripts/ttmcp status | start | stop
  - scripts/gmcp status | start | stop
  - curl http://127.0.0.1:8082/status (timetable)
  - curl "http://127.0.0.1:8081/geocode?q=paris%2C%20france" (geo)

