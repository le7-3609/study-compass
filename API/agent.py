"""Study Compass on the raw Gemini REST API: wires the hand-written harness together."""
from __future__ import annotations

import uuid
from pathlib import Path

from shared.domain import DEFAULT_CALENDAR, StudyDomain
from shared.prompt import SYSTEM_PROMPT
from shared.store import StudyStore

from API.harness import compaction, logger
from API.harness.context import ContextBuilder
from API.harness.history import History
from API.harness.loop import run_turn
from API.harness.memory import Memory
from API.harness.tokens import TurnMeter
from API.harness.tools import Toolbox, schemas

log = logger(__file__)


class StudyAgent:
    def __init__(self, client, state_dir: str | Path, cfg: dict, today: str | None = None,
                 conversation: str | None = None, fetch=None):
        self.client, self.cfg = client, cfg
        self.store = StudyStore(state_dir, today)
        self.conversation = conversation or uuid.uuid4().hex[:8]
        self.history = History(Path(state_dir) / "conversations" / f"{self.conversation}.jsonl")
        self.context = ContextBuilder(self.store, Memory(self.store))
        self.toolbox = Toolbox(StudyDomain(self.store, cfg.get("calendar", DEFAULT_CALENDAR), fetch))
        self.tool_schemas = schemas()
        self.last_prompt_tokens = 0
        log(f"agent ready: conversation={self.conversation}, {len(self.tool_schemas)} tools")

    def ask(self, text: str) -> dict:
        meter = TurnMeter(self.cfg["model"])
        compaction.maybe_compact(self.client, self.cfg["model"], self.history, meter,
                                 self.last_prompt_tokens, self.cfg.get("compact_at", 12000))
        self.toolbox.called = []
        answer = run_turn(self.client, self.cfg, SYSTEM_PROMPT, self.tool_schemas, self.history,
                          self.toolbox, meter, self.context.build_user_content(text))
        self.last_prompt_tokens = meter.last_prompt_tokens
        return {"answer": answer, "tools": list(self.toolbox.called), **meter.summary()}
