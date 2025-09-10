from __future__ import annotations

import json
from typing import Any, Optional


class MCPClient:
    """Very small HTTP-based MCP client.

    Expects an HTTP endpoint that accepts POST /mcp with a JSON body.
    If `send` is invoked with a dict containing a "text" key, it will try:
      1) parse the text as JSON ({"method":..., "params":...})
      2) otherwise, treat the text as a geocode query: {"method":"geocode","params":{"q": text}}
    """

    def __init__(self, endpoint: Optional[str] = None) -> None:
        self.endpoint = (endpoint or "").strip()
        self._connected = False

    def connect(self) -> None:
        # For HTTP, mark as connected if an endpoint is present.
        if not self.endpoint:
            raise RuntimeError("MCP endpoint is not set")
        self._connected = True

    def send(self, payload: Any) -> Any:
        if not self._connected:
            raise RuntimeError("MCPClient is not connected")

        import urllib.request
        from urllib.parse import urlparse

        # Determine request body
        body: dict
        if isinstance(payload, dict) and isinstance(payload.get("text"), str):
            text = payload.get("text") or ""
            try:
                body = json.loads(text)
                if not isinstance(body, dict):
                    raise ValueError
            except Exception:
                # Fallback: assume it's a geocode query string
                body = {"method": "geocode", "params": {"q": text}}
        elif isinstance(payload, dict):
            body = payload
        else:
            raise ValueError("Unsupported payload; provide a dict or /mcp send <json>")

        # Default path to /mcp if no path provided
        parsed = urlparse(self.endpoint)
        target = self.endpoint
        if not parsed.path or parsed.path == "/":
            target = self.endpoint.rstrip("/") + "/mcp"

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            target,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # nosec - user-provided endpoint
                raw = resp.read()
        except Exception as e:
            return {"ok": False, "error": str(e)}
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {"ok": False, "error": "Invalid JSON response", "raw": raw[:2000].decode("utf-8", "ignore")}

    def close(self) -> None:
        self._connected = False

