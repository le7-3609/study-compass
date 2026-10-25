"""Whole scenario.json through the API harness with a scripted fake model.

Proves the scenario, the runner and all checks fit together before spending money
on a real run: if the "model" calls the right tools, every check passes.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from conftest import CFG, FakeClient, fake_fetch, text_resp, tool_resp

from API.agent import StudyAgent
from shared.scenario_runner import run_scenario

ROOT = Path(__file__).resolve().parent.parent

SCRIPT = [
    # session 1, turn 1: save prefs
    tool_resp(("a", "remember", {"key": "day_end", "value": "22:00"}),
              ("b", "remember", {"key": "day_start", "value": "08:00"}),
              ("c", "remember", {"key": "days_off", "value": "sat"})), text_resp("שמרתי."),
    # turn 2: add 3 tasks
    tool_resp(("d", "add_task", {"title": "קריאה לסמינר המחקר", "course": "סמינר", "due": "2026-11-02", "hours": 2}),
              ("e", "add_task", {"title": "תרגיל 3", "course": "אלגוריתמים", "due": "2026-11-03", "hours": 6}),
              ("f", "add_task", {"title": "פרויקט", "course": "סטטיסטיקה", "due": "2026-11-05", "hours": 4})),
    text_resp("הוספתי."),
    # turn 3: plan
    tool_resp(("g", "read_calendar", {"start": "2026-11-01", "end": "2026-11-07"})),
    tool_resp(("h", "plan_week", {"week_start": "2026-11-01"})), text_resp("התוכנית מוכנה."),
    # session 2, turn 1: recall (memory is in context, no tool needed)
    text_resp("שמרת: לא אחרי 22:00, מתחילים ב-08:00, שבת חופש. הכי דחוף: הקריאה לסמינר."),
    # turn 2: web + add task
    tool_resp(("i", "lookup_topic", {"topic": "dynamic programming"})),
    tool_resp(("j", "add_task", {"title": "חזרה על תכנות דינמי", "course": "אלגוריתמים", "due": "2026-11-03", "hours": 2})),
    text_resp("הסבר + משימה."),
    # turn 3: contradiction + replan
    tool_resp(("k", "remember", {"key": "day_end", "value": "23:00"})),
    tool_resp(("l", "plan_week", {"week_start": "2026-11-01"})), text_resp("עודכן."),
    # turn 4: complete
    tool_resp(("m", "complete_task", {"task_id": "T1"})), text_resp("סומן."),
]


def test_full_scenario_all_checks_pass(tmp_path):
    client = FakeClient(SCRIPT)
    out = tmp_path / "api.json"
    factory = lambda s, t, n: StudyAgent(client, s, CFG, t, fetch=fake_fetch)  # noqa: E731
    asyncio.run(run_scenario(ROOT / "scenario.json", out, tmp_path / "state", factory, "API-fake", {}, {}))
    r = json.loads(out.read_text(encoding="utf-8"))
    failed = [c for c in r["checks"] if not c["passed"]]
    assert not failed, failed
    assert len(r["turns"]) == 7 and not client.script
