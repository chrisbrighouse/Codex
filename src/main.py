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
from src.utils.intent import detect_geocode_query


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
    a2a: A2AClient | None = None

    session = ChatSession()
    print("CLI Chatbot (provider: %s). Type /help for commands." % provider_name)

    # Auto-connect MCP at startup (uses env or local default)
    try:
        mcp_endpoint = cfg.mcp_endpoint or "http://127.0.0.1:8081/mcp"
        mcp = MCPClient(mcp_endpoint)
        mcp.connect()
        print(f"MCP connected ({mcp_endpoint}).")
    except Exception as e:
        mcp = None
        print(f"MCP not connected: {e} (start server or set MCP_ENDPOINT)")

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

