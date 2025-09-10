#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path


PIDFILE = Path(".mcp_timetable.pid")

# Defaults based on your earlier inputs
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8082
DEFAULT_PATH = str(Path("Assets/timetable.csv"))
DEFAULT_WEEKA = "2025-09-08"  # Monday 8 Sep 2025
DEFAULT_TZ = "Europe/London"


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start(host: str, port: int, path: str, weeka: str, tz: str) -> int:
    if PIDFILE.exists():
        try:
            pid = int(PIDFILE.read_text().strip())
        except Exception:
            pid = None
        if pid and is_running(pid):
            print(f"Timetable MCP already running (pid {pid}).")
            return 0
        else:
            try:
                PIDFILE.unlink()
            except Exception:
                pass

    server = Path(__file__).with_name("mcp_timetable_server.py").resolve()
    if not server.exists():
        print("mcp_timetable_server.py not found next to this script")
        return 1

    cmd = [
        sys.executable,
        str(server),
        "--host",
        host,
        "--port",
        str(port),
        "--path",
        path,
        "--weeka-start",
        weeka,
        "--tz",
        tz,
    ]

    kwargs = {}
    if os.name == "nt":
        kwargs.update(
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    else:
        kwargs.update(start_new_session=True)

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
    PIDFILE.write_text(str(proc.pid))
    print(f"Started Timetable MCP pid {proc.pid} on http://{host}:{port}")
    print(f"CSV: {path} | Week A: {weeka} | TZ: {tz}")
    return 0


def stop() -> int:
    if not PIDFILE.exists():
        print("No PID file found; timetable server not running?")
        return 1
    try:
        pid = int(PIDFILE.read_text().strip())
    except Exception:
        print("PID file unreadable; remove .mcp_timetable.pid manually if needed.")
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
    print(f"Stopped Timetable MCP pid {pid}.")
    return 0


def status() -> int:
    if not PIDFILE.exists():
        print("Timetable MCP is not running.")
        return 1
    try:
        pid = int(PIDFILE.read_text().strip())
    except Exception:
        print("PID file unreadable.")
        return 1
    if is_running(pid):
        print(f"Timetable MCP running (pid {pid}).")
        return 0
    else:
        print("Timetable MCP not running (stale PID file).")
        return 1


def main() -> int:
    p = argparse.ArgumentParser(description="Control the Timetable MCP server (start/stop/status)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("start", help="Start server in background with predefined settings")
    sp.add_argument("--host", default=DEFAULT_HOST)
    sp.add_argument("--port", type=int, default=DEFAULT_PORT)
    sp.add_argument("--path", default=DEFAULT_PATH)
    sp.add_argument("--weeka-start", default=DEFAULT_WEEKA)
    sp.add_argument("--tz", default=DEFAULT_TZ)

    sub.add_parser("stop", help="Stop the server")
    sub.add_parser("status", help="Show server status")

    args = p.parse_args()
    if args.cmd == "start":
        return start(args.host, args.port, args.path, args.weeka_start, args.tz)
    if args.cmd == "stop":
        return stop()
    if args.cmd == "status":
        return status()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
