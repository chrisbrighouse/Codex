from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _parse_line(line: str) -> Optional[tuple[str, str]]:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if s.startswith("export "):
        s = s[len("export "):].lstrip()
    if "=" not in s:
        return None
    key, value = s.split("=", 1)
    key = key.strip()
    value = value.strip()
    if (value.startswith("'") and value.endswith("'")) or (
        value.startswith('"') and value.endswith('"')
    ):
        value = value[1:-1]
    return key, value


def load_dotenv(path: str | os.PathLike = ".env", override: bool = False) -> int:
    """Load KEY=VALUE lines from a .env file into os.environ.

    Returns number of variables set. Does nothing if the file is missing.
    """
    p = Path(path)
    if not p.exists():
        return 0
    count = 0
    for raw in p.read_text(encoding="utf-8").splitlines():
        parsed = _parse_line(raw)
        if not parsed:
            continue
        key, value = parsed
        if not override and key in os.environ:
            continue
        os.environ[key] = value
        count += 1
    return count

