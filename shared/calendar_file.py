"""Read the student's timetable from an .ics file (the external file source).

Supports the subset a university timetable export uses: DTSTART/DTEND in local
floating time, SUMMARY, and RRULE:FREQ=WEEKLY with an optional UNTIL.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from shared.store import DomainError


def _dt(value: str) -> datetime:
    value = value.rstrip("Z")
    return datetime.strptime(value, "%Y%m%dT%H%M%S" if "T" in value else "%Y%m%d")


def parse_ics(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise DomainError(f"calendar file not found: {p.name}")
    events, cur = [], None
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT" and cur is not None:
            if "start" in cur and "end" in cur:
                events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            name, value = line.split(":", 1)
            name = name.split(";")[0]
            if name == "SUMMARY":
                cur["title"] = value
            elif name == "DTSTART":
                cur["start"] = _dt(value)
            elif name == "DTEND":
                cur["end"] = _dt(value)
            elif name == "RRULE":
                parts = dict(kv.split("=", 1) for kv in value.split(";") if "=" in kv)
                if parts.get("FREQ") == "WEEKLY":
                    cur["weekly_until"] = _dt(parts["UNTIL"]).date() if "UNTIL" in parts else date.max
    return events


def busy_between(path: str | Path, start: date, end: date) -> list[dict]:
    """Expand events into concrete occurrences with start <= day <= end, sorted."""
    if end < start:
        raise DomainError("end is before start")
    if (end - start).days > 31:
        raise DomainError("range too long; ask for at most 31 days")
    out = []
    for ev in parse_ics(path):
        length = ev["end"] - ev["start"]
        occ = ev["start"]
        until = ev.get("weekly_until")
        while occ.date() <= end:
            if occ.date() >= start:
                out.append({"title": ev.get("title", "busy"), "start": occ, "end": occ + length})
            if not until:
                break
            occ += timedelta(days=7)
            if occ.date() > until:
                break
    return sorted(out, key=lambda e: e["start"])
