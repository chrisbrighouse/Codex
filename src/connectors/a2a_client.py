"""Agent-to-Agent (A2A) client placeholder."""
from __future__ import annotations

from typing import Any, Optional


class A2AClient:
    def __init__(self, endpoint: Optional[str] = None) -> None:
        self.endpoint = endpoint
        self._connected = False

    def connect(self) -> None:
        self._connected = True

    def send(self, payload: Any) -> Any:
        if not self._connected:
            raise RuntimeError("A2AClient is not connected")
        return {"ok": True, "relay": payload}

    def close(self) -> None:
        self._connected = False

