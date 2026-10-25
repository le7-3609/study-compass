"""What enters each turn.

The static system prompt and tool schemas never change (so they stay cached). The
dynamic part is built per turn and attached to the *user message* rather than the
system prompt - that keeps the cached prefix stable across turns.

Included: today's date, memory digest (see memory.py), open tasks due in the next
14 days (max 8, one line each). Left out on purpose: the timetable (fetched with
read_calendar only when planning), done tasks, far-future tasks, the full plan.
"""
from __future__ import annotations

from shared.domain import task_line, upcoming_tasks
from shared.store import WEEKDAYS, StudyStore

from API.harness import logger
from API.harness.memory import Memory

log = logger(__file__)


class ContextBuilder:
    def __init__(self, store: StudyStore, memory: Memory, horizon_days: int = 14, max_tasks: int = 8):
        self.store, self.memory = store, memory
        self.horizon_days, self.max_tasks = horizon_days, max_tasks

    def build_user_content(self, user_text: str) -> list[dict]:
        today = self.store.today
        tasks, left_out = upcoming_tasks(self.store, self.horizon_days, self.max_tasks)
        parts = [f"today: {WEEKDAYS[today.weekday()]} {today.isoformat()}", self.memory.digest(user_text)]
        if tasks:
            parts.append(f"open tasks due within {self.horizon_days} days:\n" + "\n".join(task_line(t) for t in tasks))
        else:
            parts.append("open tasks due soon: none")
        if left_out:
            parts.append(f"({left_out} more open tasks not shown - use list_tasks)")
        plan = self.store.plan()
        if plan:
            parts.append(f"a saved plan exists for week {plan['week_start']} ({len(plan['blocks'])} blocks)")
        ctx = "<context>\n" + "\n".join(parts) + "\n</context>"
        log(f"injected {len(ctx)} chars (~{len(ctx) // 4} tokens): date, prefs, {len(tasks)} tasks"
            f"{', plan pointer' if plan else ''}; excluded: calendar, {left_out} tasks, done tasks")
        return [{"type": "text", "text": ctx}, {"type": "text", "text": user_text}]
