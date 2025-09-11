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
import logging
import threading
import time
import sys
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
        self._logger = logging.getLogger("mcp.timetable")

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
        # Debug summary per (week, day)
        try:
            by_key = {key: len(v) for key, v in self._index.items()}
            self._logger.debug("index summary: %s", by_key)
        except Exception:
            pass
        return len(self.lessons)

    def week_type_for(self, d: date) -> str:
        # Week A on the reference week; alternate each 7 days
        delta = (d - self.week_a_start).days
        weeks = delta // 7
        wk = "A" if weeks % 2 == 0 else "B"
        self._logger.debug("week_type_for d=%s delta=%d weeks=%d -> %s", d.isoformat(), delta, weeks, wk)
        return wk

    def day_lessons(self, d: date) -> Dict[str, Any]:
        week = self.week_type_for(d)
        key = (week, d.weekday())
        items = self._index.get(key, [])
        self._logger.debug("day_lessons d=%s week=%s weekday=%d count=%d", d.isoformat(), week, d.weekday(), len(items))
        lessons = [l.to_public() for l in items]
        return {"week": week, "lessons": lessons}

    def at(self, dt: datetime) -> Dict[str, Any]:
        # Use timezone if available
        if self._tz and dt.tzinfo is None:
            dt = dt.replace(tzinfo=self._tz)
        d = dt.date()
        m = dt.hour * 60 + dt.minute
        week = self.week_type_for(d)
        key = (week, d.weekday())
        self._logger.debug("at dt=%s (m=%d) week=%s weekday=%d candidates=%d", dt.isoformat(), m, week, d.weekday(), len(self._index.get(key, []) or []))
        for les in self._index.get(key, []):
            self._logger.debug(
                "consider window %s-%s (%d-%d) subj=%s",
                minutes_to_hhmm(les.start_min),
                minutes_to_hhmm(les.end_min),
                les.start_min,
                les.end_min,
                les.subject,
            )
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
            items = self._index.get(key, [])
            self._logger.debug("next from=%s (m=%d) week=%s weekday=%d candidates=%d", cur.isoformat(), m, week, d.weekday(), len(items))
            for les in items:
                if les.start_min >= m:
                    return {"week": week, "lesson": les.to_public()}
            # move to next day at 00:00
            cur = (datetime.combine(d, datetime.min.time()) + timedelta(days=1)).replace(tzinfo=dt.tzinfo)
        return {"week": self.week_type_for(dt.date()), "lesson": None}


def _first_param(params: dict, *names: str) -> Optional[str]:
    """Return the first matching param value among `names` (case-insensitive).
    Accepts both exact and case-variant keys; ignores non-string values.
    """
    if not isinstance(params, dict):
        return None
    lower_map = {str(k).lower(): v for k, v in params.items()}
    for name in names:
        v = lower_map.get(name.lower())
        if v is None:
            continue
        if isinstance(v, str):
            s = v.strip()
            if s:
                return s
        else:
            try:
                s = str(v).strip()
                if s:
                    return s
            except Exception:
                pass
    return None


def _norm_subject(s: Optional[str]) -> str:
    try:
        return " ".join((s or "").strip().lower().split())
    except Exception:
        return (s or "").strip().lower()


def _subject_matches(subj: str, query: Optional[str]) -> bool:
    if not query:
        return True
    ns = _norm_subject(subj)
    nq = _norm_subject(query)
    return nq in ns if nq else True


class TimetableHandler(BaseHTTPRequestHandler):
    server_version = "MCPTimetable/0.1"
    timetable: Timetable
    logger = logging.getLogger("mcp.timetable")

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
            req_id = f"g{int(time.time()*1000)}-{threading.get_ident()}"
            self.logger.info("[%s] GET %s from %s", req_id, parsed.path, getattr(self, 'client_address', None))
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
                self.logger.debug("[%s] status path=%s tz=%s weeka=%s lessons=%d", req_id, self.timetable.csv_path, self.timetable.tz, self.timetable.week_a_start.isoformat(), len(self.timetable.lessons))
                self._send_json(payload)
                return
            if parsed.path == "/day":
                qs = parse_qs(parsed.query)
                ds = (qs.get("date") or [""])[0].strip()
                if not ds:
                    self._send_json({"ok": False, "error": "missing date"}, HTTPStatus.BAD_REQUEST)
                    return
                try:
                    d = date.fromisoformat(ds)
                except Exception:
                    self._send_json({"ok": False, "error": f"invalid date: {ds}"}, HTTPStatus.BAD_REQUEST)
                    return
                out = self.timetable.day_lessons(d)
                self.logger.info("[%s] GET /day date=%s week=%s count=%d", req_id, ds, out.get("week"), len(out.get("lessons") or []))
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
            if not isinstance(params, dict):
                params = {}
            req_id = f"p{int(time.time()*1000)}-{threading.get_ident()}"
            self.logger.info("[%s] POST /mcp method=%s from %s", req_id, method, getattr(self, 'client_address', None))
            self.logger.debug("[%s] raw params=%s", req_id, params)
            if method == "timetable.weektype":
                ds = _first_param(params, "date", "day", "on")
                if ds:
                    try:
                        d = date.fromisoformat(ds)
                    except Exception:
                        self._send_json({"ok": False, "error": f"invalid date: {ds}"}, HTTPStatus.BAD_REQUEST)
                        return
                else:
                    d = date.today()
                self._send_json({"ok": True, "result": {"week": self.timetable.week_type_for(d)}})
                wk = self.timetable.week_type_for(d)
                self.logger.info("[%s] weekType date=%s -> %s", req_id, (ds or d.isoformat()), wk)
                return
            if method == "timetable.day":
                ds = _first_param(params, "date", "day", "on")
                subj_q = _first_param(params, "subject", "subj", "lesson", "class")
                if ds:
                    try:
                        d = date.fromisoformat(ds)
                    except Exception:
                        self._send_json({"ok": False, "error": f"invalid date: {ds}"}, HTTPStatus.BAD_REQUEST)
                        return
                else:
                    d = date.today()
                self.logger.debug("[%s] resolve timetable.day ds=%s -> d=%s", req_id, ds, d.isoformat())
                res = self.timetable.day_lessons(d)
                if subj_q:
                    before = len(res.get("lessons") or [])
                    filtered = [les for les in (res.get("lessons") or []) if _subject_matches(les.get("subject") or "", subj_q)]
                    res = {**res, "lessons": filtered}
                    self.logger.debug("[%s] subject filter '%s' reduced %d -> %d", req_id, subj_q, before, len(filtered))
                self._send_json({"ok": True, "result": res})
                self.logger.info("[%s] day date=%s week=%s count=%d", req_id, (ds or d.isoformat()), res.get("week"), len(res.get("lessons") or []))
                return
            if method == "timetable.at":
                ts = _first_param(params, "datetime", "dateTime", "at", "time", "timestamp")
                subj_q = _first_param(params, "subject", "subj", "lesson", "class")
                if not ts:
                    self._send_json({"ok": False, "error": "missing datetime"}, HTTPStatus.BAD_REQUEST)
                    return
                try:
                    dt = datetime.fromisoformat(ts)
                except Exception:
                    self._send_json({"ok": False, "error": f"invalid datetime: {ts}"}, HTTPStatus.BAD_REQUEST)
                    return
                self.logger.debug("[%s] resolve timetable.at ts=%s -> dt=%s", req_id, ts, dt.isoformat())
                res = self.timetable.at(dt)
                if subj_q:
                    les = res.get("lesson")
                    if les and not _subject_matches(les.get("subject") or "", subj_q):
                        self.logger.debug("[%s] subject filter '%s' excludes current lesson '%s'", req_id, subj_q, (les.get("subject") or ""))
                        res = {**res, "lesson": None}
                self._send_json({"ok": True, "result": res})
                self.logger.info("[%s] at datetime=%s week=%s hit=%s", req_id, ts, res.get("week"), bool(res.get("lesson")))
                return
            if method == "timetable.next":
                ts = _first_param(params, "from", "start", "since", "datetime", "dateTime", "at", "time")
                subj_q = _first_param(params, "subject", "subj", "lesson", "class")
                if ts:
                    try:
                        dt = datetime.fromisoformat(ts)
                    except Exception:
                        self._send_json({"ok": False, "error": f"invalid datetime: {ts}"}, HTTPStatus.BAD_REQUEST)
                        return
                else:
                    dt = datetime.now(self.timetable._tz) if self.timetable._tz else datetime.now()
                self.logger.debug("[%s] resolve timetable.next ts=%s -> dt=%s", req_id, (ts or ""), dt.isoformat())
                # If subject filter provided, search forward with subject match
                if subj_q:
                    cur = dt
                    res = None
                    for _ in range(14):
                        d = cur.date()
                        m = cur.hour * 60 + cur.minute
                        week = self.timetable.week_type_for(d)
                        key = (week, d.weekday())
                        items = self.timetable._index.get(key, [])
                        for les in items:
                            if les.start_min >= m and _subject_matches(les.subject, subj_q):
                                res = {"week": week, "lesson": les.to_public()}
                                break
                        if res:
                            break
                        cur = (datetime.combine(d, datetime.min.time()) + timedelta(days=1)).replace(tzinfo=dt.tzinfo)
                    if not res:
                        res = {"week": self.timetable.week_type_for(dt.date()), "lesson": None}
                else:
                    res = self.timetable.next(dt)
                self._send_json({"ok": True, "result": res})
                self.logger.info("[%s] next from=%s week=%s found=%s", req_id, (ts or dt.isoformat()), res.get("week"), bool(res.get("lesson")))
                return
            if method == "timetable.find":
                subj_q = _first_param(params, "subject", "subj", "lesson", "class")
                if not subj_q:
                    self._send_json({"ok": False, "error": "missing subject"}, HTTPStatus.BAD_REQUEST)
                    return
                ds = _first_param(params, "date", "day", "on")
                ts = _first_param(params, "from", "start", "since", "datetime", "dateTime", "at", "time")
                self.logger.debug("[%s] resolve timetable.find subj='%s' ds=%s ts=%s", req_id, subj_q, ds, ts)
                # If only a date is provided (and no time), return all matching lessons on that date
                if ds and not ts:
                    # Accept ISO date or simple day words
                    try:
                        d = date.fromisoformat(ds)
                    except Exception:
                        # try relative words
                        w = ds.strip().lower()
                        today = date.today()
                        if w == "today":
                            d = today
                        elif w == "tomorrow":
                            d = today + timedelta(days=1)
                        elif w == "yesterday":
                            d = today - timedelta(days=1)
                        elif w in DAY_MAP:
                            # next occurrence of weekday
                            dow = DAY_MAP[w]
                            delta = (dow - today.weekday()) % 7
                            d = today + timedelta(days=delta)
                        else:
                            self._send_json({"ok": False, "error": f"invalid date: {ds}"}, HTTPStatus.BAD_REQUEST)
                            return
                    res = self.timetable.day_lessons(d)
                    before = len(res.get("lessons") or [])
                    filtered = [les for les in (res.get("lessons") or []) if _subject_matches(les.get("subject") or "", subj_q)]
                    out = {**res, "lessons": filtered, "date": d.isoformat()}
                    self._send_json({"ok": True, "result": out})
                    self.logger.info("[%s] find(date) subj='%s' date=%s week=%s %d->%d", req_id, subj_q, d.isoformat(), res.get("week"), before, len(filtered))
                    return
                # Otherwise, search forward from a datetime (if provided) or now
                if ts:
                    try:
                        dt = datetime.fromisoformat(ts)
                    except Exception:
                        self._send_json({"ok": False, "error": f"invalid datetime: {ts}"}, HTTPStatus.BAD_REQUEST)
                        return
                else:
                    dt = datetime.now(self.timetable._tz) if self.timetable._tz else datetime.now()
                cur = dt
                found = None
                for _ in range(14):
                    d = cur.date()
                    m = cur.hour * 60 + cur.minute
                    week = self.timetable.week_type_for(d)
                    key = (week, d.weekday())
                    items = self.timetable._index.get(key, [])
                    self.logger.debug("[%s] find scan d=%s week=%s m=%d candidates=%d", req_id, d.isoformat(), week, m, len(items))
                    for les in items:
                        if les.start_min >= m and _subject_matches(les.subject, subj_q):
                            found = {"week": week, "lesson": les.to_public()}
                            break
                    if found:
                        break
                    cur = (datetime.combine(d, datetime.min.time()) + timedelta(days=1)).replace(tzinfo=dt.tzinfo)
                if not found:
                    found = {"week": self.timetable.week_type_for(dt.date()), "lesson": None}
                self._send_json({"ok": True, "result": found})
                self.logger.info("[%s] find(next) subj='%s' from=%s week=%s hit=%s", req_id, subj_q, (ts or dt.isoformat()), found.get("week"), bool(found.get("lesson")))
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
    ap.add_argument("--log-level", default="INFO", help="Log level (DEBUG, INFO, WARNING, ERROR)")
    args = ap.parse_args()

    # Configure logging: file + stdout
    logger = logging.getLogger("mcp.timetable")
    level = getattr(logging, str(args.log_level).upper(), logging.INFO)
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    try:
        fh = logging.FileHandler(".mcp_timetable.log", encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    tt = Timetable(csv_path=args.path, week_a_start=date.fromisoformat(args.weeka_start), tz=args.tz)
    count = tt.load()
    TimetableHandler.timetable = tt
    TimetableHandler.logger = logger

    addr = (args.host, args.port)
    httpd = ThreadingHTTPServer(addr, TimetableHandler)
    logger.info("MCP Timetable Server listening on http://%s:%d", args.host, args.port)
    logger.info("Loaded %d lessons from %s; Week A start %s; TZ %s", count, args.path, args.weeka_start, args.tz)
    logger.info("Endpoints: POST /mcp | GET /status | GET /day?date=YYYY-MM-DD")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
