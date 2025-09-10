from __future__ import annotations

from typing import Dict, List


class EchoProvider:
    name = "echo"

    def generate(self, history: List[Dict[str, str]], prompt: str) -> str:
        count = sum(1 for m in history if m.get("role") == "user")
        return f"(echo#{count}) You said: {prompt}"

