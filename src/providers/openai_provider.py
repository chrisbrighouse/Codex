from __future__ import annotations

import json
import os
import urllib.request
from typing import Dict, List


class OpenAIProvider:
    """Minimal OpenAI Chat Completions provider using stdlib only.

    Env vars:
      - OPENAI_API_KEY (required)
      - OPENAI_MODEL (default: gpt-4o-mini)
      - OPENAI_BASE_URL (default: https://api.openai.com)
      - OPENAI_TEMPERATURE (default: 0.2)
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
        try:
            self.temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
        except ValueError:
            self.temperature = 0.2

    def generate(self, history: List[Dict[str, str]], prompt: str) -> str:
        messages: List[Dict[str, str]] = []
        for m in history:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role in ("user", "assistant", "system"):
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": prompt})

        url = f"{self.base_url.rstrip('/')}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:  # nosec - trusted URL configured by user
            raw = resp.read()
        obj = json.loads(raw.decode("utf-8"))
        try:
            return obj["choices"][0]["message"]["content"].strip()
        except Exception:
            return json.dumps(obj)[:2000]

