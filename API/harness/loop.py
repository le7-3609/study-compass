"""The agent loop: call the model, run tools, repeat while the reply contains functionCall parts.

All functionResponse parts of one model reply go back together in ONE user message.
Every reply is appended to history before tools run, so a crash mid-turn still leaves
a consistent log. Model parts are stored exactly as received (thought signatures included).
"""
from __future__ import annotations

from API.harness import caching, logger
from API.harness.history import History
from API.harness.tokens import TurnMeter
from API.harness.tools import Toolbox

log = logger(__file__)
MAX_ITERATIONS = 10


def run_turn(client, cfg: dict, system: str, tool_schemas: list[dict], history: History,
             toolbox: Toolbox, meter: TurnMeter, user_parts: list[dict]) -> str:
    history.append("user", user_parts)
    for i in range(1, MAX_ITERATIONS + 1):
        tools, system_text, contents = caching.apply(tool_schemas, system, history.messages())
        log(f"iteration {i}: calling {cfg['model']} with {len(contents)} messages")
        resp = client.generate(model=cfg["model"], contents=contents, system=system_text, tools=tools,
                               thinking_level=cfg["effort"], max_tokens=cfg.get("max_tokens", 8000))
        meter.add(resp.get("usageMetadata", {}))
        cand = (resp.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts") or []
        log(f"finishReason={cand.get('finishReason')}")
        if not parts:
            return f"(no answer: finishReason={cand.get('finishReason')})"
        history.append("model", parts)
        calls = [p for p in parts if "functionCall" in p]
        if not calls:
            return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
        results = [toolbox.execute(p["functionCall"]) for p in calls]
        history.append("user", results)  # one message carrying every functionResponse
        log(f"returned {len(results)} functionResponse part(s) in one message")
    log(f"stopped after {MAX_ITERATIONS} iterations")
    return "(stopped: too many tool iterations)"
