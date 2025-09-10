from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
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


DAY_NAME = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}


def _next_weekday(from_date: date, dow: int) -> date:
    days_ahead = (dow - from_date.weekday()) % 7
    return from_date + timedelta(days=days_ahead)


@dataclass
class TimetableIntent:
    kind: str  # 'day' | 'at' | 'next' | 'weekType' | 'period'
    date: Optional[date] = None
    time_h: Optional[int] = None
    time_m: Optional[int] = None
    week_hint: Optional[str] = None  # 'A' | 'B'
    period_ordinal: Optional[int] = None  # 1-based index; None unless kind='period'
    period_last: bool = False


_TT_DAY = re.compile(r"\b(lessons?|timetable).*(?:on|for)\s+(?P<day>[A-Za-z]+|today|tomorrow)\b", re.IGNORECASE)
_TT_AT = re.compile(
    r"\b(lesson|class)\s+at\s+(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ampm>am|pm)?(?:\s+on\s+(?P<day>[A-Za-z]+|today|tomorrow))?",
    re.IGNORECASE,
)
_TT_NEXT = re.compile(r"\bnext\s+(lesson|class)\b", re.IGNORECASE)
_TT_WEEK = re.compile(r"\bwhat\s+week\b(?:.*\b(on|for)\s+(?P<date>\d{4}-\d{2}-\d{2}))?", re.IGNORECASE)

_TT_PERIOD = re.compile(
    r"\b(?P<ord>(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\d{1,2}(?:st|nd|rd|th)?|last))\s+period\b(?:\s+(?:on|for)\s+(?P<day>[A-Za-z]+|today|tomorrow))?",
    re.IGNORECASE,
)

_TT_WEEK_HINT = re.compile(r"\bweek\s+(?P<w>[ab])\b", re.IGNORECASE)


def detect_timetable_intent(text: str) -> Optional[TimetableIntent]:
    s = (text or "").strip()
    if not s:
        return None
    # week hint present anywhere in the string
    week_hint = None
    mwh = _TT_WEEK_HINT.search(s)
    if mwh:
        week_hint = mwh.group("w").upper()
    # day schedule
    m = _TT_DAY.search(s)
    if m:
        word = (m.group("day") or "").lower()
        today = date.today()
        if word == "today":
            return TimetableIntent(kind="day", date=today, week_hint=week_hint)
        if word == "tomorrow":
            return TimetableIntent(kind="day", date=today + timedelta(days=1), week_hint=week_hint)
        if word in DAY_NAME:
            d = _next_weekday(today, DAY_NAME[word])
            return TimetableIntent(kind="day", date=d, week_hint=week_hint)

    # lesson at time (optional day)
    m = _TT_AT.search(s)
    if m:
        h = int(m.group("h"))
        mm = m.group("m")
        mnt = int(mm) if mm else 0
        ampm = (m.group("ampm") or "").lower()
        if ampm == "pm" and 1 <= h <= 11:
            h += 12
        if ampm == "am" and h == 12:
            h = 0
        word = (m.group("day") or "").lower()
        today = date.today()
        if word == "today" or not word:
            dd = today
        elif word == "tomorrow":
            dd = today + timedelta(days=1)
        elif word in DAY_NAME:
            dd = _next_weekday(today, DAY_NAME[word])
        else:
            dd = today
        return TimetableIntent(kind="at", date=dd, time_h=h, time_m=mnt, week_hint=week_hint)

    # next lesson
    if _TT_NEXT.search(s):
        return TimetableIntent(kind="next")

    # week type
    m = _TT_WEEK.search(s)
    if m:
        ds = m.group("date")
        d = date.fromisoformat(ds) if ds else date.today()
        return TimetableIntent(kind="weekType", date=d)

    # Nth period
    m = _TT_PERIOD.search(s)
    if m:
        ord_word = (m.group("ord") or "").lower()
        word = (m.group("day") or "").lower()
        today = date.today()
        if word == "today" or not word:
            dd = today
        elif word == "tomorrow":
            dd = today + timedelta(days=1)
        elif word in DAY_NAME:
            dd = _next_weekday(today, DAY_NAME[word])
        else:
            dd = today
        # ordinal mapping
        ord_map = {
            "first": 1,
            "second": 2,
            "third": 3,
            "fourth": 4,
            "fifth": 5,
            "sixth": 6,
            "seventh": 7,
            "eighth": 8,
            "ninth": 9,
            "tenth": 10,
        }
        if ord_word == "last":
            return TimetableIntent(kind="period", date=dd, week_hint=week_hint, period_last=True)
        if ord_word in ord_map:
            return TimetableIntent(kind="period", date=dd, week_hint=week_hint, period_ordinal=ord_map[ord_word])
        # numeric forms like 1st, 2nd, 3rd, 4th
        import re as _re
        mnum = _re.match(r"^(\d+)", ord_word)
        if mnum:
            try:
                n = int(mnum.group(1))
                if n >= 1:
                    return TimetableIntent(kind="period", date=dd, week_hint=week_hint, period_ordinal=n)
            except Exception:
                pass
        # fallback ignored if cannot parse
        return None

    return None
