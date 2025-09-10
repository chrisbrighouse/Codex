from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


Message = Dict[str, str]


@dataclass
class ChatSession:
    history: List[Message] = field(default_factory=list)

    def add_user(self, content: str) -> None:
        self.history.append({"role": "user", "content": content})

    def add_assistant(self, content: str) -> None:
        self.history.append({"role": "assistant", "content": content})

