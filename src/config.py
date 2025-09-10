from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from src.utils.dotenv import load_dotenv


@dataclass
class Config:
    provider: str | None = None
    mcp_endpoint: str | None = None
    a2a_endpoint: str | None = None

    @classmethod
    def from_env(cls) -> "Config":
        # Load .env from project root if present
        load_dotenv(Path(".env"))
        return cls(
            provider=os.getenv("CHAT_PROVIDER"),
            mcp_endpoint=os.getenv("MCP_ENDPOINT"),
            a2a_endpoint=os.getenv("A2A_ENDPOINT"),
        )

