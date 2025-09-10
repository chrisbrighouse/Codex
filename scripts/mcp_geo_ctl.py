#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

PIDFILE = Path(".mcp_geo.pid")


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start(host: str, port: int, user_agent: str, min_interval: float) -> int:
    if PIDFILE.exists():
        try:
            pid = int(PIDFILE.read_text().strip())
        except Exception:
            pid = None
        if pid and is_running(pid):
            print(f"MCP Geo server already running (pid {pid}).")
            return 0
        else:
            try:
                PIDFILE.unlink()
            except Exception:
                pass

    server = Path(__file__).with_name("mcp_geo_server.py").resolve()
    if not server.exists():
        print("mcp_geo_server.py not found next to this script")
        return 1

    cmd = [sys.executable, str(server), "--host", host, "--port", str(port), "--user-agent", user_agent, "--min-interval", str(min_interval)]

    kwargs = {}
    if os.name == "nt":
        kwargs.update(creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    else:
        kwargs.update(start_new_session=True)

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
    PIDFILE.write_text(str(proc.pid))
    print(f"Started MCP Geo server pid {proc.pid} on http://{host}:{port}")
    return 0


def stop() -> int:
    if not PIDFILE.exists():
        print("No PID file found; server not running?")
        return 1
    try:
        pid = int(PIDFILE.read_text().strip())
    except Exception:
        print("PID file unreadable; remove .mcp_geo.pid manually if needed.")
        return 1
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception as e:
        print(f"Failed to signal pid {pid}: {e}")
        return 1
    try:
        PIDFILE.unlink()
    except Exception:
        pass
    print(f"Stopped MCP Geo server pid {pid}.")
    return 0


def status() -> int:
    if not PIDFILE.exists():
        print("MCP Geo server is not running.")
        return 1
    try:
        pid = int(PIDFILE.read_text().strip())
    except Exception:
        print("PID file unreadable.")
        return 1
    if is_running(pid):
        print(f"MCP Geo server running (pid {pid}).")
        return 0
    else:
        print("MCP Geo server not running (stale PID file).")
        return 1


def main() -> int:
    p = argparse.ArgumentParser(description="Control the MCP Geo server (start/stop/status)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("start", help="Start the server in background")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8081)
    sp.add_argument("--user-agent", default="codex-mcp-geo/0.1 (+you@example.com)")
    sp.add_argument("--min-interval", type=float, default=1.0)

    sub.add_parser("stop", help="Stop the server")
    sub.add_parser("status", help="Show server status")

    args = p.parse_args()
    if args.cmd == "start":
        return start(args.host, args.port, args.user_agent, args.min_interval)
    if args.cmd == "stop":
        return stop()
    if args.cmd == "status":
        return status()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

