"""Pass/fail checks declared in scenario.json, evaluated mostly on the saved state.

Each check is {"id", "type", ...params}. State checks read the JSON files the agent
left on disk; only `answer_contains_any` looks at reply text.
"""
from __future__ import annotations

from datetime import date

from shared.calendar_file import busy_between
from shared.store import WEEKDAYS, StudyStore


def _pref(store, key):
    return store.prefs().get(key)


def _find_task(store, contains):
    return [t for t in store.tasks() if any(c.lower() in t["title"].lower() for c in contains)]


def check(c: dict, store: StudyStore, turns: list[dict], calendar_path) -> tuple[bool, str]:
    kind = c["type"]
    if kind == "pref_equals":
        e = _pref(store, c["key"])
        return (bool(e) and e["value"] == c["value"]), f"{c['key']}={e['value'] if e else None}"
    if kind == "pref_history_contains":
        e = _pref(store, c["key"]) or {}
        hist = [h["value"] for h in e.get("history", [])]
        return c["value"] in hist, f"history={hist}"
    if kind == "task_count":
        n = len([t for t in store.tasks() if c.get("status", "all") in ("all", t["status"])])
        return n >= c["min"], f"{n} tasks"
    if kind == "task_exists":
        hits = _find_task(store, c["title_contains"])
        if "due_on_or_before" in c:
            hits = [t for t in hits if t["due"] <= c["due_on_or_before"]]
        return bool(hits), f"matches={[t['id'] for t in hits]}"
    if kind == "task_status":
        hits = _find_task(store, c["title_contains"])
        return bool(hits) and all(t["status"] == c["status"] for t in hits), \
            f"{[(t['id'], t['status']) for t in hits]}"
    if kind == "plan_respects_prefs":
        plan = store.plan()
        if not plan or not plan["blocks"]:
            return False, "no plan"
        ds, de = store.pref("day_start"), store.pref("day_end")
        off = {d for d in store.pref("days_off").split(",") if d}
        bad = [b for b in plan["blocks"] if b["start"] < ds or b["end"] > de
               or WEEKDAYS[date.fromisoformat(b["date"]).weekday()] in off]
        # the saved plan must have been built with the *current* preferences (i.e. replanned after a change)
        stale = plan["rules"]["day_end"] != de or plan["rules"]["day_start"] != ds
        return (not bad and not stale), \
            f"violations={len(bad)} plan_window={plan['rules']['day_start']}-{plan['rules']['day_end']} prefs={ds}-{de}"
    if kind == "plan_no_calendar_overlap":
        plan = store.plan()
        if not plan:
            return False, "no plan"
        ws = date.fromisoformat(plan["week_start"])
        from datetime import datetime, timedelta
        busy = busy_between(calendar_path, ws, ws + timedelta(days=6))
        clashes = []
        for b in plan["blocks"]:
            s = datetime.fromisoformat(f"{b['date']}T{b['start']}")
            e = datetime.fromisoformat(f"{b['date']}T{b['end']}")
            clashes += [ev["title"] for ev in busy if s < ev["end"] and ev["start"] < e]
        return not clashes, f"{len(plan['blocks'])} blocks, clashes={clashes}"
    if kind == "plan_schedules_task_before_due":
        plan = store.plan() or {"blocks": []}
        hits = [t for t in _find_task(store, c["title_contains"]) if t["status"] == "open"]
        if not hits:
            return False, "task not found"
        t = hits[-1]
        blocks = [b for b in plan["blocks"] if b["task_id"] == t["id"]]
        ok = bool(blocks) and all(b["date"] < t["due"] for b in blocks)
        return ok, f"{t['id']} blocks={len(blocks)} due={t['due']}"
    if kind == "tool_called":
        sel = [x for x in turns if x["session"] == c["session"]]
        called = sorted({n for x in sel for n in x["tools"]})
        return c["tool"] in called, f"session {c['session']} tools={called}"
    if kind == "answer_contains_any":
        x = next((x for x in turns if x["session"] == c["session"] and x["turn"] == c["turn"]), None)
        text = (x or {}).get("answer", "")
        found = [s for s in c["any"] if s in text]
        return bool(found), f"found={found}"
    return False, f"unknown check type {kind}"


def run_checks(checks: list[dict], store: StudyStore, turns: list[dict], calendar_path) -> list[dict]:
    out = []
    for c in checks:
        try:
            ok, detail = check(c, store, turns, calendar_path)
        except Exception as e:  # a crashing check is a failing check
            ok, detail = False, f"error: {e}"
        out.append({"id": c["id"], "passed": ok, "detail": detail, "desc": c.get("desc", "")})
    return out
