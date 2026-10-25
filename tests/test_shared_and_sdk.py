"""Domain code, checks, line counting and the SDK wiring - all offline."""
from __future__ import annotations

import asyncio

from conftest import CFG, fake_fetch

from shared import loc, planner
from shared.checks import run_checks
from shared.domain import DEFAULT_CALENDAR, StudyDomain
from shared.store import DomainError, StudyStore


def _week(state, day_end="22:00"):
    store = StudyStore(state, "2026-10-30")
    store.remember("day_end", day_end)
    store.remember("days_off", "sat")
    store.add_task("Seminar reading", "Seminar", "2026-11-02", 2)
    store.add_task("Algorithms HW3", "Algorithms", "2026-11-03", 6)
    store.add_task("Statistics project", "Statistics", "2026-11-05", 4)
    return store


def test_planner_respects_window_days_off_calendar_and_deadlines(state):
    store = _week(state)
    plan = planner.plan_week(store, DEFAULT_CALENDAR, "2026-11-01")
    assert plan["blocks"] and not plan["unscheduled_hours"]
    for b in plan["blocks"]:
        assert "08:00" <= b["start"] and b["end"] <= "22:00"
        assert b["date"] != "2026-11-07"  # Saturday
    due = {t["id"]: t["due"] for t in store.tasks()}
    assert all(b["date"] < due[b["task_id"]] for b in plan["blocks"])
    sunday = [b for b in plan["blocks"] if b["date"] == "2026-11-01"]
    assert not any(b["start"] < "12:15" and b["end"] > "09:45" for b in sunday)  # lecture 10-12 + buffer


def test_store_validation_errors():
    import tempfile
    store = StudyStore(tempfile.mkdtemp(), "2026-10-30")
    for bad in [("day_end", "25:00"), ("days_off", "funday"), ("colour", "red")]:
        try:
            store.remember(*bad)
            raise AssertionError("should fail")
        except DomainError:
            pass


def test_checks_pass_on_good_state_and_fail_on_stale_plan(state):
    store = _week(state)
    StudyDomain(store).plan_week("2026-11-01")
    store.remember("day_end", "23:00")  # contradiction saved, plan NOT rebuilt yet
    checks = [{"id": "a", "type": "pref_equals", "key": "day_end", "value": "23:00"},
              {"id": "b", "type": "pref_history_contains", "key": "day_end", "value": "22:00"},
              {"id": "c", "type": "plan_respects_prefs"},
              {"id": "d", "type": "plan_no_calendar_overlap"}]
    res = {r["id"]: r["passed"] for r in run_checks(checks, store, [], DEFAULT_CALENDAR)}
    assert res == {"a": True, "b": True, "c": False, "d": True}
    StudyDomain(store).plan_week("2026-11-01")  # replan with new prefs
    assert run_checks(checks[2:3], store, [], DEFAULT_CALENDAR)[0]["passed"]


def test_loc_counts_every_part():
    api, sdk = loc.api_loc(), loc.sdk_loc()
    assert set(api) == set(loc.PARTS) and all(v > 0 for v in api.values())
    assert sdk["tools"] > 0 and sdk["memory"] > 0 and sdk["loop"] > 0 and sdk["history"] > 0


def test_sdk_tools_run_offline_and_update_claude_md(state):
    from SDK.tools import make_tools, render_claude_md
    store = StudyStore(state, "2026-10-30")
    md = state / "CLAUDE.md"
    render_claude_md(store, md)
    tools = {t.name: t for t in make_tools(StudyDomain(store, fetch=fake_fetch), md)}
    assert len(tools) == 8
    ok = asyncio.run(tools["remember"].handler({"key": "day_end", "value": "22:00"}))
    assert not ok.get("is_error") and "day_end: 22:00" in md.read_text()
    bad = asyncio.run(tools["complete_task"].handler({"task_id": "T9"}))
    assert bad["is_error"] is True
    web = asyncio.run(tools["lookup_topic"].handler({"topic": "dynamic programming"}))
    assert "wikipedia.org" in web["content"][0]["text"]


def test_sdk_options_are_restricted(state):
    from SDK.agent import StudyAgentSDK
    from shared.prompt import SYSTEM_PROMPT
    a = StudyAgentSDK(state, CFG, "2026-10-30")
    o = a.options
    assert o.strict_mcp_config is True and o.tools == [] and o.system_prompt == SYSTEM_PROMPT
    assert o.setting_sources == ["project"] and o.effort == "medium" and o.model == "claude-opus-5-5"
    assert all(t.startswith("mcp__study__") for t in o.allowed_tools) and len(o.allowed_tools) == 8
    assert (state / "sdk_workspace" / "CLAUDE.md").exists()
