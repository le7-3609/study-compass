"""The same 8 domain tools, exposed to Claude Code as an in-process MCP server.

Each @tool wraps one shared StudyDomain method. Errors become is_error results,
exactly like API/harness/tools.py - but the dispatch and the tool_result plumbing
are done by the SDK.
"""
from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server, tool

from shared.domain import TOOL_SPECS, StudyDomain
from shared.store import DEFAULT_PREFS, StudyStore

SERVER = "study"
ALLOWED = [f"mcp__{SERVER}__{name}" for name in TOOL_SPECS]  # replaces: tools (restricted tool list)


def render_claude_md(store: StudyStore, path: Path) -> None:
    """Long-term memory file that Claude Code loads at session start."""
    prefs = store.prefs()  # replaces: memory
    lines = ["# Study Compass - saved memory", "",  # replaces: memory
             f"Today (use this date, not the system date): {store.today.isoformat()}", "",  # replaces: context
             "## Preferences (from prefs.json, kept up to date by `remember`)"]  # replaces: memory
    for k in DEFAULT_PREFS:  # replaces: memory
        e = prefs.get(k)  # replaces: memory
        prev = f" (previously {e['history'][-1]['value']})" if e and e.get("history") else ""  # replaces: memory
        lines.append(f"- {k}: {e['value'] if e else (DEFAULT_PREFS[k] or '-') + ' (default)'}{prev}")  # replaces: memory
    for n in prefs.get("note", {}).get("value", []):  # replaces: memory
        lines.append(f"- note: {n}")  # replaces: memory
    lines += ["", "Tasks and the timetable are NOT listed here: use list_tasks / read_calendar."]  # replaces: context
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")  # replaces: memory


def make_tools(domain: StudyDomain, claude_md: Path) -> list:
    def run(name: str, args: dict) -> dict:
        try:  # replaces: tools
            text = domain.call(name, args)  # replaces: tools
        except Exception as e:  # replaces: tools
            return {"content": [{"type": "text", "text": f"error: {e}"}], "is_error": True}  # replaces: tools
        if name == "remember":
            render_claude_md(domain.store, claude_md)  # replaces: memory
        return {"content": [{"type": "text", "text": text}]}  # replaces: tools

    def spec(name):
        return name, TOOL_SPECS[name]["description"], TOOL_SPECS[name]["schema"]

    @tool(*spec("add_task"))  # replaces: tools
    async def add_task(args):
        return run("add_task", args)

    @tool(*spec("list_tasks"))  # replaces: tools
    async def list_tasks(args):
        return run("list_tasks", args)

    @tool(*spec("complete_task"))  # replaces: tools
    async def complete_task(args):
        return run("complete_task", args)

    @tool(*spec("read_calendar"))  # replaces: tools
    async def read_calendar(args):
        return run("read_calendar", args)

    @tool(*spec("plan_week"))  # replaces: tools
    async def plan_week(args):
        return run("plan_week", args)

    @tool(*spec("lookup_topic"))  # replaces: tools
    async def lookup_topic(args):
        return run("lookup_topic", args)

    @tool(*spec("remember"))  # replaces: tools, memory
    async def remember(args):
        return run("remember", args)

    @tool(*spec("recall"))  # replaces: tools, memory
    async def recall(args):
        return run("recall", args)

    return [add_task, list_tasks, complete_task, read_calendar, plan_week, lookup_topic, remember, recall]


def build_server(domain: StudyDomain, claude_md: Path):
    return create_sdk_mcp_server(SERVER, "1.0.0", tools=make_tools(domain, claude_md))  # replaces: tools
