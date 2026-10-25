"""The agent loop: call the model, run tools, repeat while stop_reason == "tool_use".

All tool_result blocks of one model response go back together in ONE user message.
Every response is appended to history before tools run, so a crash mid-turn still
leaves a consistent log.
"""
from __future__ import annotations

from API.harness import caching, logger
from API.harness.history import History
from API.harness.tokens import TurnMeter
from API.harness.tools import Toolbox

log = logger(__file__)
MAX_ITERATIONS = 10


def _dump(block) -> dict:
    return block if isinstance(block, dict) else block.model_dump(mode="json", exclude_none=True)


def run_turn(client, cfg: dict, system: str, tool_schemas: list[dict], history: History,
             toolbox: Toolbox, meter: TurnMeter, user_content) -> str:
    history.append("user", user_content)
    for i in range(1, MAX_ITERATIONS + 1):
        tools, system_blocks, messages = caching.apply(tool_schemas, system, history.messages())
        log(f"iteration {i}: calling {cfg['model']} with {len(messages)} messages")
        resp = client.messages.create(
            model=cfg["model"], max_tokens=cfg.get("max_tokens", 4000),
            system=system_blocks, tools=tools, messages=messages,
            thinking={"type": "adaptive"}, output_config={"effort": cfg["effort"]},
        )
        meter.add(resp.usage)
        content = [_dump(b) for b in resp.content]
        history.append("assistant", content)
        log(f"stop_reason={resp.stop_reason}")
        if resp.stop_reason != "tool_use":
            return "".join(b["text"] for b in content if b.get("type") == "text").strip()
        uses = [b for b in content if b.get("type") == "tool_use"]
        results = [toolbox.execute(b) for b in uses]
        history.append("user", results)  # one message carrying every tool_result
        log(f"returned {len(results)} tool_result(s) in one message")
    log(f"stopped after {MAX_ITERATIONS} iterations")
    return "(stopped: too many tool iterations)"
