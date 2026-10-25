"""Persistent state on disk: tasks, preferences (long-term memory) and the weekly plan.

Everything lives as small JSON files under one state directory, so a fresh agent
instance (session 2) sees exactly what the previous one left behind.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

PREF_KEYS = {
    "day_start": "HH:MM - earliest time a study block may start",
    "day_end": "HH:MM - latest time a study block may end",
    "days_off": "comma list of weekdays with no studying, e.g. 'sat' or 'fri,sat'",
    "session_minutes": "length of one study block in minutes (30-180)",
    "note": "free-text fact worth remembering (goals, struggles, course info)",
}
DEFAULT_PREFS = {"day_start": "08:00", "day_end": "22:00", "days_off": "", "session_minutes": "90"}
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class DomainError(Exception):
    """A tool-level error that should be shown to the model (is_error)."""


class StudyStore:
    def __init__(self, root: str | Path, today: str | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.today = date.fromisoformat(today) if today else date.today()

    # ---------- raw json ----------
    def _read(self, name: str, default):
        p = self.root / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

    def _write(self, name: str, data) -> None:
        p = self.root / name
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)

    # ---------- tasks ----------
    def tasks(self) -> list[dict]:
        return self._read("tasks.json", [])

    def save_tasks(self, tasks: list[dict]) -> None:
        self._write("tasks.json", tasks)

    def add_task(self, title: str, course: str, due: str, hours: float) -> dict:
        title, course = title.strip(), course.strip()
        if not title:
            raise DomainError("title is empty")
        try:
            due_d = date.fromisoformat(due)
        except ValueError:
            raise DomainError(f"due must be YYYY-MM-DD, got {due!r}")
        if not 0 < float(hours) <= 40:
            raise DomainError("hours must be between 0 and 40")
        tasks = self.tasks()
        for t in tasks:
            if t["status"] == "open" and t["title"].lower() == title.lower():
                raise DomainError(f"open task already exists: {t['id']}")
        task = {"id": f"T{len(tasks) + 1}", "title": title, "course": course,
                "due": due_d.isoformat(), "hours": float(hours), "status": "open",
                "created": self.today.isoformat()}
        tasks.append(task)
        self.save_tasks(tasks)
        return task

    def complete_task(self, task_id: str) -> dict:
        tasks = self.tasks()
        for t in tasks:
            if t["id"].lower() == task_id.strip().lower():
                if t["status"] == "done":
                    raise DomainError(f"{t['id']} is already done")
                t["status"] = "done"
                t["done_on"] = self.today.isoformat()
                self.save_tasks(tasks)
                return t
        raise DomainError(f"no task {task_id!r}; ids: {', '.join(x['id'] for x in tasks) or 'none'}")

    # ---------- preferences / memory ----------
    def prefs(self) -> dict:
        return self._read("prefs.json", {})

    def pref(self, key: str) -> str:
        entry = self.prefs().get(key)
        return entry["value"] if entry else DEFAULT_PREFS[key]

    def remember(self, key: str, value: str) -> dict:
        key, value = key.strip(), str(value).strip()
        if key not in PREF_KEYS:
            raise DomainError(f"unknown key {key!r}; use one of {', '.join(PREF_KEYS)}")
        value = _validate(key, value)
        prefs = self.prefs()
        if key == "note":
            notes = prefs.setdefault("note", {"value": [], "history": []})
            if value not in notes["value"]:
                notes["value"].append(value)
            self._write("prefs.json", prefs)
            return {"key": key, "value": value, "replaced": None}
        old = prefs.get(key)
        replaced = None
        if old and old["value"] != value:
            replaced = old["value"]
            old.setdefault("history", []).append({"value": old["value"], "until": self.today.isoformat()})
            old["value"], old["updated"] = value, self.today.isoformat()
        elif not old:
            prefs[key] = {"value": value, "updated": self.today.isoformat(), "history": []}
        self._write("prefs.json", prefs)
        return {"key": key, "value": value, "replaced": replaced}

    # ---------- plan ----------
    def plan(self) -> dict | None:
        return self._read("plan.json", None)

    def save_plan(self, plan: dict) -> None:
        self._write("plan.json", plan)

    # ---------- web cache ----------
    def web_cache(self) -> dict:
        return self._read("web_cache.json", {})

    def save_web_cache(self, cache: dict) -> None:
        self._write("web_cache.json", cache)


def _validate(key: str, value: str) -> str:
    if key in ("day_start", "day_end"):
        if len(value) == 4 and value[1] == ":":
            value = "0" + value
        if not _TIME.match(value):
            raise DomainError(f"{key} must be HH:MM, got {value!r}")
    elif key == "days_off":
        days = [d.strip().lower()[:3] for d in value.split(",") if d.strip()]
        bad = [d for d in days if d not in WEEKDAYS]
        if bad:
            raise DomainError(f"unknown weekday(s) {bad}; use {WEEKDAYS}")
        value = ",".join(days)
    elif key == "session_minutes":
        if not value.isdigit() or not 30 <= int(value) <= 180:
            raise DomainError("session_minutes must be an integer 30-180")
    elif key == "note" and not value:
        raise DomainError("note is empty")
    return value
