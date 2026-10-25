"""The 8 study tools as plain Python, plus their JSON schemas.

Both harnesses expose exactly these functions with exactly these schemas, so any
token or behaviour difference between API/ and SDK/ comes from the harness only.
Every function returns a short string (token optimization: ids instead of
repeated titles, one line per item, no pretty JSON).
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from shared import planner, web
from shared.calendar_file import busy_between
from shared.store import PREF_KEYS, DEFAULT_PREFS, WEEKDAYS, DomainError, StudyStore

DEFAULT_CALENDAR = Path(__file__).parent / "data" / "calendar.ics"

TOOL_SPECS = {
    "add_task": {
        "description": "Add an assignment/exam/reading to the task list. Returns the new task id.",
        "schema": {"type": "object", "properties": {
            "title": {"type": "string", "description": "short name, e.g. 'Algorithms HW3'"},
            "course": {"type": "string"},
            "due": {"type": "string", "description": "YYYY-MM-DD"},
            "hours": {"type": "number", "description": "estimated study hours"}},
            "required": ["title", "course", "due", "hours"]},
    },
    "list_tasks": {
        "description": "List tasks, one compact line each. If an up-to-date task list is already in your context, "
                       "use it instead of calling this.",
        "schema": {"type": "object", "properties": {
            "status": {"type": "string", "enum": ["open", "done", "all"]},
            "course": {"type": "string", "description": "optional filter, substring match"}},
            "required": []},
    },
    "complete_task": {
        "description": "Mark a task as done by its id (e.g. 'T2').",
        "schema": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]},
    },
    "read_calendar": {
        "description": "Read the student's timetable file (.ics) and return busy events between two dates (max 31 days).",
        "schema": {"type": "object", "properties": {
            "start": {"type": "string", "description": "YYYY-MM-DD"},
            "end": {"type": "string", "description": "YYYY-MM-DD"}},
            "required": ["start", "end"]},
    },
    "plan_week": {
        "description": "Build and save a study plan for 7 days from week_start. Uses the timetable file, open tasks "
                       "and saved preferences (day_start, day_end, days_off, session_minutes). Save preferences with "
                       "`remember` BEFORE calling this. Returns one line per day with task ids.",
        "schema": {"type": "object", "properties": {"week_start": {"type": "string", "description": "YYYY-MM-DD"}},
                   "required": ["week_start"]},
    },
    "lookup_topic": {
        "description": "Fetch a short explanation of a study topic from Wikipedia (internet). Returns ~600 chars + URL.",
        "schema": {"type": "object", "properties": {
            "topic": {"type": "string", "description": "search phrase, preferably English"},
            "lang": {"type": "string", "enum": ["en", "he"]}},
            "required": ["topic"]},
    },
    "remember": {
        "description": "Save a long-term preference that persists across sessions. Keys: "
                       + "; ".join(f"{k} = {v}" for k, v in PREF_KEYS.items())
                       + ". Saving an existing key replaces it (old value kept in history).",
        "schema": {"type": "object", "properties": {
            "key": {"type": "string", "enum": list(PREF_KEYS)},
            "value": {"type": "string"}},
            "required": ["key", "value"]},
    },
    "recall": {
        "description": "Show all saved preferences and notes, including the history of replaced values.",
        "schema": {"type": "object", "properties": {}, "required": []},
    },
}


class StudyDomain:
    def __init__(self, store: StudyStore, calendar_path: str | Path = DEFAULT_CALENDAR, fetch=None):
        self.store = store
        self.calendar_path = Path(calendar_path)
        self.fetch = fetch or web._get_json

    def call(self, name: str, args: dict) -> str:
        if name not in TOOL_SPECS:
            raise DomainError(f"unknown tool {name!r}")
        missing = [k for k in TOOL_SPECS[name]["schema"]["required"] if k not in args]
        if missing:
            raise DomainError(f"missing argument(s): {', '.join(missing)}")
        try:
            return getattr(self, name)(**args)
        except TypeError as e:
            raise DomainError(f"bad arguments: {e}")

    # ---------- tools ----------
    def add_task(self, title, course, due, hours) -> str:
        t = self.store.add_task(title, course, due, hours)
        return f"added {t['id']} | {t['title']} | {t['course']} | due {t['due']} | {t['hours']:g}h"

    def list_tasks(self, status="open", course=None) -> str:
        rows = [t for t in self.store.tasks()
                if (status == "all" or t["status"] == status)
                and (not course or course.lower() in t["course"].lower())]
        if not rows:
            return f"no {status} tasks"
        return "\n".join(task_line(t, with_status=status == "all") for t in sorted(rows, key=lambda t: t["due"]))

    def complete_task(self, task_id) -> str:
        t = self.store.complete_task(task_id)
        return f"done {t['id']} ({t['title']})"

    def read_calendar(self, start, end) -> str:
        try:
            s, e = date.fromisoformat(start), date.fromisoformat(end)
        except ValueError:
            raise DomainError("start/end must be YYYY-MM-DD")
        evs = busy_between(self.calendar_path, s, e)
        if not evs:
            return "no events"
        return "\n".join(f"{WEEKDAYS[ev['start'].weekday()]} {ev['start']:%m-%d %H:%M}-{ev['end']:%H:%M} {ev['title']}"
                         for ev in evs)

    def plan_week(self, week_start) -> str:
        return planner.plan_summary(planner.plan_week(self.store, self.calendar_path, week_start))

    def lookup_topic(self, topic, lang="en") -> str:
        r, hit = web.cached_lookup(self.store, topic, lang, self.fetch)
        return f"{r['title']}{' (cached)' if hit else ''}: {r['summary']}\nsource: {r['url']}"

    def remember(self, key, value) -> str:
        r = self.store.remember(key, value)
        if r["replaced"] is not None:
            return f"updated {key}: {r['replaced']} -> {r['value']} (old value kept in history)"
        return f"saved {key} = {r['value']}"

    def recall(self) -> str:
        prefs = self.store.prefs()
        lines = []
        for k in DEFAULT_PREFS:
            e = prefs.get(k)
            if e:
                hist = ", ".join(h["value"] for h in e.get("history", []))
                lines.append(f"{k} = {e['value']}" + (f" (previously: {hist})" if hist else ""))
            else:
                lines.append(f"{k} = {DEFAULT_PREFS[k] or '-'} (default)")
        for n in prefs.get("note", {}).get("value", []):
            lines.append(f"note: {n}")
        return "\n".join(lines)


def task_line(t: dict, with_status: bool = False) -> str:
    s = f" [{t['status']}]" if with_status else ""
    return f"{t['id']}{s} | {t['title']} | {t['course']} | due {t['due']} | {t['hours']:g}h"


def upcoming_tasks(store: StudyStore, days: int = 14, limit: int = 8) -> tuple[list[dict], int]:
    """Open tasks due within `days` (overdue included), earliest first; also returns how many were left out."""
    horizon = store.today + timedelta(days=days)
    open_ = sorted((t for t in store.tasks() if t["status"] == "open"), key=lambda t: t["due"])
    near = [t for t in open_ if date.fromisoformat(t["due"]) <= horizon]
    return near[:limit], len(open_) - len(near[:limit])
