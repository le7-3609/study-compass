"""The same 8 domain tools as plain Python functions; the google-genai SDK turns them into
function declarations and runs them itself (automatic function calling).

The docstring of each function is the tool description, built from the same TOOL_SPECS the API
version sends. Errors become an "error: ..." string, like API/harness/tools.py.
"""

# no `from __future__ import annotations` here: google-genai resolves the real type objects to build schemas
from pathlib import Path

from shared.domain import TOOL_SPECS, StudyDomain
from shared.store import DEFAULT_PREFS, StudyStore


def render_memory(store: StudyStore) -> str:
    """Long-term memory block appended to the system instruction at session start."""
    prefs = store.prefs()  # replaces: memory
    lines = ["Saved memory (from prefs.json, kept up to date by `remember`):",  # replaces: memory
             f"Today (use this date, not the system date): {store.today.isoformat()}"]  # replaces: context
    for k in DEFAULT_PREFS:  # replaces: memory
        e = prefs.get(k)  # replaces: memory
        prev = f" (previously {e['history'][-1]['value']})" if e and e.get("history") else ""  # replaces: memory
        lines.append(f"- {k}: {e['value'] if e else (DEFAULT_PREFS[k] or '-') + ' (default)'}{prev}")  # replaces: memory
    for n in prefs.get("note", {}).get("value", []):  # replaces: memory
        lines.append(f"- note: {n}")  # replaces: memory
    lines.append("Tasks and the timetable are NOT listed here: use list_tasks / read_calendar.")  # replaces: context
    return "\n".join(lines)  # replaces: memory


def _doc(name: str) -> str:
    spec = TOOL_SPECS[name]
    args = "\n".join(f"    {k}: {v['description']}" for k, v in spec["schema"]["properties"].items()
                     if v.get("description"))
    return spec["description"] + (f"\n\nArgs:\n{args}" if args else "")


def make_tools(domain: StudyDomain, called: list[str]) -> list:
    def run(name: str, **args) -> str:
        called.append(name)
        try:  # replaces: tools
            return domain.call(name, {k: v for k, v in args.items() if v not in (None, "")})  # replaces: tools
        except Exception as e:  # replaces: tools
            return f"error: {e}"  # replaces: tools

    def add_task(title: str, course: str, due: str, hours: float) -> str:  # replaces: tools
        return run("add_task", title=title, course=course, due=due, hours=hours)

    def list_tasks(status: str = "open", course: str = "") -> str:  # replaces: tools
        return run("list_tasks", status=status, course=course)

    def complete_task(task_id: str) -> str:  # replaces: tools
        return run("complete_task", task_id=task_id)

    def read_calendar(start: str, end: str) -> str:  # replaces: tools
        return run("read_calendar", start=start, end=end)

    def plan_week(week_start: str) -> str:  # replaces: tools
        return run("plan_week", week_start=week_start)

    def lookup_topic(topic: str, lang: str = "en") -> str:  # replaces: tools
        return run("lookup_topic", topic=topic, lang=lang)

    def remember(key: str, value: str) -> str:  # replaces: tools, memory
        return run("remember", key=key, value=value)

    def recall() -> str:  # replaces: tools, memory
        return run("recall")

    fns = [add_task, list_tasks, complete_task, read_calendar, plan_week, lookup_topic, remember, recall]
    for f in fns:
        f.__doc__ = _doc(f.__name__)  # replaces: tools
    return fns
