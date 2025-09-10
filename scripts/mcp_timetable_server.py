#!/usr/bin/env python3
from __future__ import annotations

"""
Minimal MCP-style server for a school timetable with alternating Week A/B.

CSV schema (header row required):
  week,day,start,end,subject,teacher,room,notes
    - week: A|B
    - day: Monday|Mon|0..6 (0=Mon)
    - start,end: HH:MM (24h)
    - subject/teacher/room/notes: free text (optional)

Methods (POST /mcp):
  - {"method":"timetable.weekType","params":{"date":"YYYY-MM-DD"}}
      -> {ok: true, result: {week: "A"|"B"}}
  - {"method":"timetable.day","params":{"date":"YYYY-MM-DD"}}
      -> {ok: true, result: {week: "A|B", lessons: [...]}}
  - {"method":"timetable.at","params":{"datetime":"YYYY-MM-DDTHH:MM"}}
      -> {ok: true, result: {week: "A|B", lesson: {...}|null}}
  - {"method":"timetable.next","params":{"from":"YYYY-MM-DDTHH:MM"}}
      -> {ok: true, result: {week: "A|B", lesson: {...}|null}}

GET helpers:
  - /status -> JSON with counts and configuration
  - /day?date=YYYY-MM-DD -> lessons for that date

Env/config:
  - --path CSV file path (required)
  - --weeka-start YYYY-MM-DD (Week A Monday reference; required)
  - --tz IANA timezone (default Europe/London)
"""

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


DAY_MAP = {
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


def parse_day(value: str) -> int:
    s = (value or "").strip().lower()
    if s.isdigit():
        i = int(s)
        if 0 <= i <= 6:
            return i
    if s in DAY_MAP:
        return DAY_MAP[s]
    raise ValueError(f"invalid day: {value}")


def parse_hhmm(value: str) -> int:
    s = (value or "").strip()
    hh, mm = s.split(":", 1)
    h = int(hh)
    m = int(mm)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError
    return h * 60 + m


def minutes_to_hhmm(total: int) -> str:
    h, m = divmod(total, 60)
    return f"{h:02d}:{m:02d}"


@dataclass
class Lesson:
    week: str
    day: int  # 0=Mon
    start_min: int
    end_min: int
    subject: str
    teacher: str
    room: str
    notes: str

    def to_public(self) -> Dict[str, Any]:
        return {
            "week": self.week,
            "day": self.day,
            "start": minutes_to_hhmm(self.start_min),
            "end": minutes_to_hhmm(self.end_min),
            "subject": self.subject,
            "teacher": self.teacher,
            "room": self.room,
            "notes": self.notes,
        }


class Timetable:
    def __init__(self, csv_path: str, week_a_start: date, tz: Optional[str] = None) -> None:
        self.csv_path = csv_path
        self.week_a_start = week_a_start
        self.tz = tz or "Europe/London"
        self._tz = ZoneInfo(self.tz) if ZoneInfo else None
        self.lessons: List[Lesson] = []
        self._index: Dict[Tuple[str, int], List[Lesson]] = {}

    def load(self) -> int:
        self.lessons.clear()
        self._index.clear()
        with open(self.csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required = {"week", "day", "start", "end"}
            missing = [c for c in required if c not in reader.fieldnames]
            if missing:
                raise ValueError(f"CSV missing required columns: {missing}")
            for row in reader:
                week = (row.get("week") or "").strip().upper()
                if week not in ("A", "B"):
                    raise ValueError(f"invalid week: {week}")
                day = parse_day(row.get("day") or "")
                start_min = parse_hhmm(row.get("start") or "")
                end_min = parse_hhmm(row.get("end") or "")
                subj = (row.get("subject") or "").strip()
                teacher = (row.get("teacher") or "").strip()
                room = (row.get("room") or "").strip()
                notes = (row.get("notes") or "").strip()
                self.lessons.append(
                    Lesson(
                        week=week,
                        day=day,
                        start_min=start_min,
                        end_min=end_min,
                        subject=subj,
                        teacher=teacher,
                        room=room,
                        notes=notes,
                    )
                )
        # Build index
        for les in self.lessons:
            key = (les.week, les.day)
            self._index.setdefault(key, []).append(les)
        for key in self._index:
            self._index[key].sort(key=lambda x: x.start_min)
        return len(self.lessons)

    def week_type_for(self, d: date) -> str:
        # Week A on the reference week; alternate each 7 days
        delta = (d - self.week_a_start).days
        weeks = delta // 7
        return "A" if weeks % 2 == 0 else "B"

    def day_lessons(self, d: date) -> Dict[str, Any]:
        week = self.week_type_for(d)
        key = (week, d.weekday())
        lessons = [l.to_public() for l in self._index.get(key, [])]
        return {"week": week, "lessons": lessons}

    def at(self, dt: datetime) -> Dict[str, Any]:
        # Use timezone if available
        if self._tz and dt.tzinfo is None:
            dt = dt.replace(tzinfo=self._tz)
        d = dt.date()
        m = dt.hour * 60 + dt.minute
        week = self.week_type_for(d)
        key = (week, d.weekday())
        for les in self._index.get(key, []):
            if les.start_min <= m < les.end_min:
                return {"week": week, "lesson": les.to_public()}
        return {"week": week, "lesson": None}

    def next(self, dt: datetime) -> Dict[str, Any]:
        # Search forward within the same day, then next days until found (max 14 days)
        if self._tz and dt.tzinfo is None:
            dt = dt.replace(tzinfo=self._tz)
        cur = dt
        for _ in range(14):
            d = cur.date()
            m = cur.hour * 60 + cur.minute
            week = self.week_type_for(d)
            key = (week, d.weekday())
            for les in self._index.get(key, []):
                if les.start_min >= m:
                    return {"week": week, "lesson": les.to_public()}
            # move to next day at 00:00
            cur = (datetime.combine(d, datetime.min.time()) + timedelta(days=1)).replace(tzinfo=dt.tzinfo)
        return {"week": self.week_type_for(dt.date()), "lesson": None}


class TimetableHandler(BaseHTTPRequestHandler):
    server_version = "MCPTimetable/0.1"
    timetable: Timetable

    def _send_json(self, obj: dict, status: int = 200) -> None:
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/status":
                payload = {
                    "ok": True,
                    "result": {
                        "path": self.timetable.csv_path,
                        "tz": self.timetable.tz,
                        "weeka_start": self.timetable.week_a_start.isoformat(),
                        "lessons": len(self.timetable.lessons),
                    },
                }
                self._send_json(payload)
                return
            if parsed.path == "/day":
                qs = parse_qs(parsed.query)
                ds = (qs.get("date") or [""])[0]
                if not ds:
                    self._send_json({"ok": False, "error": "missing date"}, HTTPStatus.BAD_REQUEST)
                    return
                d = date.fromisoformat(ds)
                out = self.timetable.day_lessons(d)
                self._send_json({"ok": True, "result": out})
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
            if method == "timetable.weektype":
                ds = (params.get("date") or "").strip()
                d = date.fromisoformat(ds) if ds else date.today()
                self._send_json({"ok": True, "result": {"week": self.timetable.week_type_for(d)}})
                return
            if method == "timetable.day":
                ds = (params.get("date") or "").strip()
                d = date.fromisoformat(ds) if ds else date.today()
                self._send_json({"ok": True, "result": self.timetable.day_lessons(d)})
                return
            if method == "timetable.at":
                ts = (params.get("datetime") or "").strip()
                dt = datetime.fromisoformat(ts)
                self._send_json({"ok": True, "result": self.timetable.at(dt)})
                return
            if method == "timetable.next":
                ts = (params.get("from") or "").strip()
                dt = datetime.fromisoformat(ts) if ts else datetime.now(self.timetable._tz) if self.timetable._tz else datetime.now()
                self._send_json({"ok": True, "result": self.timetable.next(dt)})
                return
            self._send_json({"ok": False, "error": "unknown method"}, HTTPStatus.BAD_REQUEST)
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)


class ThreadingHTTPServer(ThreadingMixIn, __import__("http.server").server.HTTPServer):
    daemon_threads = True


def main() -> int:
    ap = argparse.ArgumentParser(description="MCP Timetable server (Week A/B)")
    ap.add_argument("--path", required=True, help="CSV file with timetable data")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8082)
    ap.add_argument("--weeka-start", required=True, help="Week A Monday reference (YYYY-MM-DD)")
    ap.add_argument("--tz", default="Europe/London", help="Timezone, e.g., Europe/London")
    args = ap.parse_args()

    tt = Timetable(csv_path=args.path, week_a_start=date.fromisoformat(args.weeka_start), tz=args.tz)
    count = tt.load()
    TimetableHandler.timetable = tt

    addr = (args.host, args.port)
    httpd = ThreadingHTTPServer(addr, TimetableHandler)
    print(f"MCP Timetable Server listening on http://{args.host}:{args.port}")
    print(f"Loaded {count} lessons from {args.path}; Week A start {args.weeka_start}; TZ {args.tz}")
    print("Endpoints: POST /mcp | GET /status | GET /day?date=YYYY-MM-DD")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

