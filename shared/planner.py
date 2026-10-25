"""Deterministic weekly planner: fits open tasks into free time around the timetable.

Rules: blocks only between day_start and day_end, never on days_off, never on top of
a calendar event (with a 15-minute buffer), always finished before the task's due
day, earliest deadline first. The result is saved to plan.json.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from shared.calendar_file import busy_between
from shared.store import WEEKDAYS, DomainError, StudyStore

BUFFER = timedelta(minutes=15)
MAX_BLOCKS_PER_TASK_PER_DAY = 2


def _t(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def free_slots(day: date, start: time, end: time, busy: list[dict]) -> list[list[datetime]]:
    slots = [[datetime.combine(day, start), datetime.combine(day, end)]]
    for ev in busy:
        b0, b1 = ev["start"] - BUFFER, ev["end"] + BUFFER
        nxt = []
        for s0, s1 in slots:
            if b1 <= s0 or b0 >= s1:
                nxt.append([s0, s1])
                continue
            if b0 > s0:
                nxt.append([s0, b0])
            if b1 < s1:
                nxt.append([b1, s1])
        slots = nxt
    return [s for s in slots if s[1] - s[0] >= timedelta(minutes=30)]


def plan_week(store: StudyStore, calendar_path, week_start: str) -> dict:
    try:
        ws = date.fromisoformat(week_start)
    except ValueError:
        raise DomainError(f"week_start must be YYYY-MM-DD, got {week_start!r}")
    day_start, day_end = _t(store.pref("day_start")), _t(store.pref("day_end"))
    if day_end <= day_start:
        raise DomainError("day_end must be after day_start - fix the preference first")
    off = {d for d in store.pref("days_off").split(",") if d}
    session = timedelta(minutes=int(store.pref("session_minutes")))
    days = [ws + timedelta(days=i) for i in range(7)]
    busy = busy_between(calendar_path, days[0], days[-1])

    slots = {}
    for d in days:
        if d < store.today or WEEKDAYS[d.weekday()] in off:
            continue
        slots[d] = free_slots(d, day_start, day_end, [e for e in busy if e["start"].date() == d])

    tasks = sorted((t for t in store.tasks() if t["status"] == "open"), key=lambda t: (t["due"], -t["hours"]))
    blocks, unscheduled = [], {}
    for task in tasks:
        due = date.fromisoformat(task["due"])
        remaining = timedelta(hours=task["hours"])
        for d in sorted(slots):
            if d >= due or remaining <= timedelta(0):
                continue
            used_today = 0
            for slot in slots[d]:
                while remaining > timedelta(0) and used_today < MAX_BLOCKS_PER_TASK_PER_DAY:
                    length = min(session, remaining)
                    if slot[1] - slot[0] < length:
                        break
                    blocks.append({"task_id": task["id"], "date": d.isoformat(),
                                   "start": slot[0].strftime("%H:%M"),
                                   "end": (slot[0] + length).strftime("%H:%M")})
                    slot[0] = slot[0] + length + BUFFER
                    remaining -= length
                    used_today += 1
        if remaining > timedelta(0):
            unscheduled[task["id"]] = round(remaining.total_seconds() / 3600, 2)

    blocks.sort(key=lambda b: (b["date"], b["start"]))
    plan = {"week_start": ws.isoformat(), "created": store.today.isoformat(),
            "rules": {"day_start": day_start.strftime("%H:%M"), "day_end": day_end.strftime("%H:%M"),
                      "days_off": sorted(off), "session_minutes": int(session.total_seconds() // 60)},
            "blocks": blocks, "unscheduled_hours": unscheduled}
    store.save_plan(plan)
    return plan


def plan_summary(plan: dict) -> str:
    """Compact text: one line per day, task ids only (titles are already in context)."""
    by_day: dict[str, list[str]] = {}
    for b in plan["blocks"]:
        by_day.setdefault(b["date"], []).append(f"{b['start']}-{b['end']} {b['task_id']}")
    r = plan["rules"]
    lines = [f"plan {plan['week_start']} (window {r['day_start']}-{r['day_end']}, off={','.join(r['days_off']) or '-'})"]
    for d in sorted(by_day):
        wd = WEEKDAYS[date.fromisoformat(d).weekday()]
        lines.append(f"{wd} {d[5:]}: " + "; ".join(by_day[d]))
    if plan["unscheduled_hours"]:
        lines.append("UNSCHEDULED: " + ", ".join(f"{k} {v}h" for k, v in plan["unscheduled_hours"].items()))
    return "\n".join(lines)
