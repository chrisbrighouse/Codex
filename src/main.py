#!/usr/bin/env python3
"""
Simple CLI chatbot entrypoint with geocode intent via MCP.
"""
from __future__ import annotations

import sys
from typing import List

from src.config import Config
from src.chat.session import ChatSession
from src.providers.echo import EchoProvider
from src.providers.openai_provider import OpenAIProvider
from src.connectors.mcp_client import MCPClient
from src.connectors.a2a_client import A2AClient
from src.utils.intent import detect_geocode_query, detect_timetable_intent


def get_provider(name: str):
    name = (name or "").strip().lower()
    if name in ("", "echo"):
        return EchoProvider()
    if name in ("openai", "oa"):
        return OpenAIProvider()
    raise ValueError(f"Unknown provider: {name}")


def print_help():
    print(
        """Commands:
  /help
  /exit | /quit
  /provider <name>         (echo|openai)
  /mcp connect [endpoint]  connect MCP client
  /mcp send <text>         send a payload via MCP
  /mcp close               close MCP connection
  /a2a connect [endpoint]  connect A2A client
  /a2a send <text>         send a payload via A2A
  /a2a close               close A2A connection
"""
    )


def main(argv: List[str] | None = None) -> int:
    cfg = Config.from_env()
    provider_name = cfg.provider or "echo"
    provider = get_provider(provider_name)
    mcp: MCPClient | None = None
    mcp_tt: MCPClient | None = None
    a2a: A2AClient | None = None

    session = ChatSession()
    print("CLI Chatbot (provider: %s). Type /help for commands." % provider_name)

    # Auto-connect Geo MCP at startup (uses env or local default)
    try:
        mcp_endpoint = cfg.mcp_endpoint or "http://127.0.0.1:8081/mcp"
        mcp = MCPClient(mcp_endpoint)
        mcp.connect()
        print(f"Geo MCP connected ({mcp_endpoint}).")
    except Exception as e:
        mcp = None
        print(f"Geo MCP not connected: {e} (start geo server or set MCP_ENDPOINT)")

    # Auto-connect Timetable MCP
    try:
        tt_endpoint = cfg.timetable_endpoint or "http://127.0.0.1:8082/mcp"
        mcp_tt = MCPClient(tt_endpoint)
        mcp_tt.connect()
        print(f"Timetable MCP connected ({tt_endpoint}).")
    except Exception as e:
        mcp_tt = None
        print(f"Timetable MCP not connected: {e} (start timetable server or set TIMETABLE_ENDPOINT)")

    try:
        while True:
            try:
                user = input("you> ").strip()
            except EOFError:
                print()
                break

            if not user:
                continue
            if user in ("/exit", "/quit"):
                break
            if user == "/help":
                print_help()
                continue
            if user.startswith("/mcp "):
                cmd = user.split(maxsplit=2)
                sub = cmd[1] if len(cmd) > 1 else ""
                if sub == "connect":
                    endpoint = cmd[2] if len(cmd) > 2 else cfg.mcp_endpoint
                    mcp = MCPClient(endpoint)
                    try:
                        mcp.connect()
                        print(f"MCP connected ({endpoint or 'default'}).")
                    except Exception as e:
                        print(f"MCP error: {e}")
                elif sub == "send":
                    if not mcp:
                        print("MCP not connected. Use /mcp connect")
                    else:
                        payload = cmd[2] if len(cmd) > 2 else ""
                        try:
                            resp = mcp.send({"text": payload})
                            print(f"mcp> {resp}")
                        except Exception as e:
                            print(f"MCP error: {e}")
                elif sub == "close":
                    if mcp:
                        mcp.close()
                        mcp = None
                        print("MCP closed.")
                    else:
                        print("MCP not connected.")
                else:
                    print("Usage: /mcp connect [endpoint] | /mcp send <text> | /mcp close")
                continue
            if user.startswith("/a2a "):
                cmd = user.split(maxsplit=2)
                sub = cmd[1] if len(cmd) > 1 else ""
                if sub == "connect":
                    endpoint = cmd[2] if len(cmd) > 2 else cfg.a2a_endpoint
                    a2a = A2AClient(endpoint)
                    try:
                        a2a.connect()
                        print(f"A2A connected ({endpoint or 'default'}).")
                    except Exception as e:
                        print(f"A2A error: {e}")
                elif sub == "send":
                    if not a2a:
                        print("A2A not connected. Use /a2a connect")
                    else:
                        payload = cmd[2] if len(cmd) > 2 else ""
                        try:
                            resp = a2a.send({"text": payload})
                            print(f"a2a> {resp}")
                        except Exception as e:
                            print(f"A2A error: {e}")
                elif sub == "close":
                    if a2a:
                        a2a.close()
                        a2a = None
                        print("A2A closed.")
                    else:
                        print("A2A not connected.")
                else:
                    print("Usage: /a2a connect [endpoint] | /a2a send <text> | /a2a close")
                continue
            if user.startswith("/provider "):
                _, _, new_name = user.partition(" ")
                try:
                    provider = get_provider(new_name)
                    provider_name = new_name
                    print(f"Switched provider to: {provider_name}")
                except Exception as e:
                    print(f"Error: {e}")
                continue

            # Intent: timetable (auto-call timetable MCP if available)
            tt_intent = detect_timetable_intent(user)
            if tt_intent:
                if not mcp_tt:
                    endpoint = cfg.timetable_endpoint or "http://127.0.0.1:8082/mcp"
                    mcp_tt = MCPClient(endpoint)
                    try:
                        mcp_tt.connect()
                    except Exception as e:
                        print(f"[timetable mcp unavailable] {e}")
                        mcp_tt = None
                if mcp_tt:
                    # helper: adjust date to match week hint if provided
                    def _adjust_date_for_week_hint(d0):
                        if not tt_intent.week_hint or not d0:
                            return d0
                        check = {"method": "timetable.weekType", "params": {"date": d0.isoformat()}}
                        r = mcp_tt.send(check)
                        wk = None
                        if isinstance(r, dict) and r.get("ok"):
                            wk = (r.get("result") or {}).get("week")
                        if wk and wk != tt_intent.week_hint:
                            try:
                                from datetime import timedelta as _td
                                return d0 + _td(days=7)
                            except Exception:
                                return d0
                        return d0
                    def _subject_matches(name: str, query: str) -> bool:
                        ns = " ".join((name or "").strip().lower().split())
                        nq = " ".join((query or "").strip().lower().split())
                        return nq in ns if nq else True

                    if tt_intent.kind == "day" and tt_intent.date:
                        dd = _adjust_date_for_week_hint(tt_intent.date)
                        payload = {"method": "timetable.day", "params": {"date": dd.isoformat()}}
                        resp = mcp_tt.send(payload)
                        if isinstance(resp, dict) and resp.get("ok"):
                            pr = resp.get("result") or {}
                            lessons = pr.get("lessons") or []
                            lines = ["MCP: Timetable", f"Week {pr.get('week')} schedule for {dd.isoformat()}"]
                            for les in lessons:
                                lines.append(f"{les.get('start')}-{les.get('end')}: {les.get('subject')} ({les.get('room')})")
                            reply = "\n".join(lines if lines else ["MCP: Timetable", "No lessons found."])
                            session.add_user(user)
                            session.add_assistant(reply)
                            print(f"bot> {reply}")
                            continue
                    elif tt_intent.kind == "at" and tt_intent.date is not None:
                        dd = _adjust_date_for_week_hint(tt_intent.date)
                        hh = tt_intent.time_h or 0
                        mm = tt_intent.time_m or 0
                        iso = f"{dd.isoformat()}T{hh:02d}:{mm:02d}"
                        payload = {"method": "timetable.at", "params": {"datetime": iso}}
                        resp = mcp_tt.send(payload)
                        if isinstance(resp, dict) and resp.get("ok"):
                            pr = resp.get("result") or {}
                            les = pr.get("lesson")
                            if les:
                                reply = "\n".join([
                                    "MCP: Timetable",
                                    f"At {iso} (Week {pr.get('week')}): {les.get('subject')} in {les.get('room')} ({les.get('start')}-{les.get('end')})",
                                ])
                            else:
                                reply = "\n".join(["MCP: Timetable", f"At {iso}: no lesson."])
                            session.add_user(user)
                            session.add_assistant(reply)
                            print(f"bot> {reply}")
                            continue
                    elif tt_intent.kind == "period" and tt_intent.date is not None:
                        dd = _adjust_date_for_week_hint(tt_intent.date)
                        payload = {"method": "timetable.day", "params": {"date": dd.isoformat()}}
                        resp = mcp_tt.send(payload)
                        if isinstance(resp, dict) and resp.get("ok"):
                            pr = resp.get("result") or {}
                            lessons = pr.get("lessons") or []
                            if lessons:
                                if tt_intent.period_last:
                                    target = lessons[-1]
                                else:
                                    idx = max(1, tt_intent.period_ordinal or 1) - 1
                                    target = lessons[idx] if idx < len(lessons) else None
                                if target:
                                    reply = "\n".join([
                                        "MCP: Timetable",
                                        f"{('Last' if tt_intent.period_last else f'Period {idx+1}')} on {dd.isoformat()} (Week {pr.get('week')}): {target.get('subject')} in {target.get('room')} ({target.get('start')}-{target.get('end')})",
                                    ])
                                else:
                                    reply = "\n".join(["MCP: Timetable", f"No such period on {dd.isoformat()} (has only {len(lessons)} lessons)."])
                            else:
                                reply = "\n".join(["MCP: Timetable", f"No lessons on {dd.isoformat()}."])
                            session.add_user(user)
                            session.add_assistant(reply)
                            print(f"bot> {reply}")
                            continue
                    elif tt_intent.kind == "next":
                        payload = {"method": "timetable.next", "params": {}}
                        resp = mcp_tt.send(payload)
                        if isinstance(resp, dict) and resp.get("ok"):
                            pr = resp.get("result") or {}
                            les = pr.get("lesson")
                            if les:
                                reply = "\n".join([
                                    "MCP: Timetable",
                                    f"Next lesson (Week {pr.get('week')}): {les.get('subject')} in {les.get('room')} at {les.get('start')} ({les.get('start')}-{les.get('end')})",
                                ])
                            else:
                                reply = "\n".join(["MCP: Timetable", "No upcoming lesson found soon."])
                            session.add_user(user)
                            session.add_assistant(reply)
                            print(f"bot> {reply}")
                            continue
                    elif tt_intent.kind == "subject" and tt_intent.date is not None:
                        dd = _adjust_date_for_week_hint(tt_intent.date)
                        subj = tt_intent.subject or ""
                        payload = {"method": "timetable.find", "params": {"date": dd.isoformat(), "subject": subj}}
                        resp = mcp_tt.send(payload)
                        if isinstance(resp, dict) and resp.get("ok"):
                            pr = resp.get("result") or {}
                            lessons = pr.get("lessons") or []
                            if lessons:
                                lines = [
                                    "MCP: Timetable",
                                    f"{subj} on {dd.isoformat()} (Week {pr.get('week')}):",
                                ]
                                for les in lessons:
                                    lines.append(f"{les.get('start')}-{les.get('end')}: {les.get('subject')} ({les.get('room')})")
                                reply = "\n".join(lines)
                            else:
                                reply = "\n".join(["MCP: Timetable", f"No {subj} on {dd.isoformat()}."])
                            session.add_user(user)
                            session.add_assistant(reply)
                            print(f"bot> {reply}")
                            continue
                    elif tt_intent.kind == "weekType" and tt_intent.date is not None:
                        payload = {"method": "timetable.weekType", "params": {"date": tt_intent.date.isoformat()}}
                        resp = mcp_tt.send(payload)
                        if isinstance(resp, dict) and resp.get("ok"):
                            pr = resp.get("result") or {}
                            reply = "\n".join(["MCP: Timetable", f"Week type for {tt_intent.date.isoformat()}: {pr.get('week')}"])
                            session.add_user(user)
                            session.add_assistant(reply)
                            print(f"bot> {reply}")
                            continue

            # Intent: geocode (auto-call MCP if available)
            geo_q = detect_geocode_query(user)
            if geo_q:
                if not mcp:
                    # Try to connect automatically using config/default endpoint
                    endpoint = cfg.mcp_endpoint or "http://127.0.0.1:8081/mcp"
                    mcp = MCPClient(endpoint)
                    try:
                        mcp.connect()
                    except Exception as e:
                        print(f"[mcp unavailable] {e}")
                        mcp = None
                if mcp:
                    payload = {"method": "geocode", "params": {"q": geo_q, "limit": 1}}
                    resp = mcp.send(payload)
                    if isinstance(resp, dict) and resp.get("ok") and isinstance(resp.get("result"), dict):
                        result = resp["result"]
                        lat = result.get("lat")
                        lon = result.get("lon")
                        name = result.get("display_name") or geo_q
                        session.add_user(user)
                        reply = "\n".join([
                            "MCP: Geolocate",
                            f"Coordinates for {name}: {lat}, {lon}",
                        ])
                        session.add_assistant(reply)
                        print(f"bot> {reply}")
                        continue
                    else:
                        detail = None
                        if isinstance(resp, dict):
                            detail = resp.get("error") or resp.get("raw")
                        msg = "[mcp error] could not geocode"
                        if detail:
                            msg += f": {detail}"
                        msg += " (try /mcp connect or start the MCP geo server)"
                        print(msg)

            # Default: use chat provider
            session.add_user(user)
            try:
                reply = provider.generate(session.history, user)
            except Exception as e:
                reply = f"[provider error] {e}"
            session.add_assistant(reply)
            print(f"bot> {reply}")

    except KeyboardInterrupt:
        print("\nInterrupted.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
