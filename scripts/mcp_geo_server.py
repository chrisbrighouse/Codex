#!/usr/bin/env python3
from __future__ import annotations

"""Minimal MCP-style geolocation server using OpenStreetMap Nominatim.
Respect Nominatim's policy: set a descriptive User-Agent with contact email
and keep to ~1 request/second. Endpoints:
  - POST /mcp {method: geocode|reverse, params: {...}}
  - GET /geocode?q=...&limit=1
  - GET /reverse?lat=..&lon=..
"""

import argparse
import json
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

NOMINATIM_BASE = "https://nominatim.openstreetmap.org"


class RateLimiter:
    def __init__(self, min_interval: float = 1.0) -> None:
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delta = now - self._last
            if delta < self.min_interval:
                time.sleep(self.min_interval - delta)
                now = time.monotonic()
            self._last = now


class GeoHandler(BaseHTTPRequestHandler):
    server_version = "MCPGeo/0.1"

    user_agent: str = "codex-mcp-geo/0.1 (+you@example.com)"
    limiter: RateLimiter

    def _send_json(self, obj: dict, status: int = 200) -> None:
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _fetch_json(self, url: str) -> dict:
        self.limiter.wait()
        req = Request(url, headers={"User-Agent": self.user_agent})
        with urlopen(req, timeout=20) as resp:  # nosec
            raw = resp.read()
        return json.loads(raw.decode("utf-8"))

    def _do_geocode(self, query: str, limit: int = 1) -> dict:
        from urllib.parse import quote_plus
        url = f"{NOMINATIM_BASE}/search?q={quote_plus(query)}&format=json&limit={limit}"
        arr = self._fetch_json(url)
        if not isinstance(arr, list) or not arr:
            return {"matches": 0}
        top = arr[0]
        return {
            "matches": len(arr),
            "lat": float(top.get("lat", 0.0)),
            "lon": float(top.get("lon", 0.0)),
            "display_name": top.get("display_name"),
            "raw": top,
        }

    def _do_reverse(self, lat: float, lon: float) -> dict:
        from urllib.parse import quote_plus
        url = (
            f"{NOMINATIM_BASE}/reverse?lat={quote_plus(str(lat))}"
            f"&lon={quote_plus(str(lon))}&format=json"
        )
        obj = self._fetch_json(url)
        return {
            "lat": lat,
            "lon": lon,
            "display_name": obj.get("display_name"),
            "address": obj.get("address"),
            "raw": obj,
        }

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/geocode":
                qs = parse_qs(parsed.query)
                q = (qs.get("q") or [""])[0]
                limit = int((qs.get("limit") or ["1"])[0])
                if not q:
                    self._send_json({"ok": False, "error": "missing q"}, HTTPStatus.BAD_REQUEST)
                    return
                result = self._do_geocode(q, limit)
                self._send_json({"ok": True, "result": result})
                return
            if parsed.path == "/reverse":
                qs = parse_qs(parsed.query)
                try:
                    lat = float((qs.get("lat") or [""])[0])
                    lon = float((qs.get("lon") or [""])[0])
                except ValueError:
                    self._send_json({"ok": False, "error": "invalid lat/lon"}, HTTPStatus.BAD_REQUEST)
                    return
                result = self._do_reverse(lat, lon)
                self._send_json({"ok": True, "result": result})
                return
            self._send_json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            if parsed.path != "/mcp":
                self._send_json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "invalid JSON"}, HTTPStatus.BAD_REQUEST)
                return
            method = (body.get("method") or "").lower()
            params = body.get("params") or {}
            if method == "geocode":
                q = params.get("q") or ""
                limit = int(params.get("limit") or 1)
                if not q:
                    self._send_json({"ok": False, "error": "missing params.q"}, HTTPStatus.BAD_REQUEST)
                    return
                result = self._do_geocode(q, limit)
                self._send_json({"ok": True, "result": result})
                return
            if method == "reverse":
                try:
                    lat = float(params.get("lat"))
                    lon = float(params.get("lon"))
                except Exception:
                    self._send_json({"ok": False, "error": "invalid params.lat/lon"}, HTTPStatus.BAD_REQUEST)
                    return
                result = self._do_reverse(lat, lon)
                self._send_json({"ok": True, "result": result})
                return
            self._send_json({"ok": False, "error": "unknown method"}, HTTPStatus.BAD_REQUEST)
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)


class ThreadingHTTPServer(ThreadingMixIn, __import__("http.server").server.HTTPServer):
    daemon_threads = True


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal MCP Geo server (Nominatim)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--user-agent", default="codex-mcp-geo/0.1 (+you@example.com)")
    parser.add_argument("--min-interval", type=float, default=1.0)
    args = parser.parse_args()

    GeoHandler.user_agent = args.user_agent
    GeoHandler.limiter = RateLimiter(min_interval=args.min_interval)

    addr = (args.host, args.port)
    httpd = ThreadingHTTPServer(addr, GeoHandler)
    print(f"MCP Geo Server listening on http://{args.host}:{args.port}")
    print("Endpoints: POST /mcp | GET /geocode | GET /reverse")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

