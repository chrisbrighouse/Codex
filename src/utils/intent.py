from __future__ import annotations

import re
from typing import Optional


_GEO_PATTERNS = [
    re.compile(r"\bcoordinates of\s+(?P<q>.+)", re.IGNORECASE),
    re.compile(r"\bcoords of\s+(?P<q>.+)", re.IGNORECASE),
    re.compile(r"\bwhat are the coordinates of\s+(?P<q>.+)", re.IGNORECASE),
    re.compile(r"\btell me the coordinates of\s+(?P<q>.+)", re.IGNORECASE),
    re.compile(r"\blat(?:itude)?\s*(?:,|and)?\s*lon(?:gitude)?\s*(?:for|of)?\s+(?P<q>.+)", re.IGNORECASE),
]


def detect_geocode_query(text: str) -> Optional[str]:
    s = (text or "").strip()
    if not s:
        return None
    for pat in _GEO_PATTERNS:
        m = pat.search(s)
        if m:
            q = (m.group("q") or "").strip().rstrip("?.! ")
            return q or None
    return None

