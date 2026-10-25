"""Context-window management: summarise the conversation once it passes a threshold.

Trigger: the prompt size of the previous model call (input + cache read + cache
write) is above `threshold` tokens. Everything before the start of the most recent
`keep_turns` turns is turned into a short summary by one extra model call, and a
compaction record is appended to the history (nothing is deleted from disk).
Cuts are made only at a turn start, so tool_use/tool_result pairs never split.
"""
from __future__ import annotations

import json

from API.harness import logger
from API.harness.history import History
from API.harness.tokens import TurnMeter

log = logger(__file__)

SUMMARY_PROMPT = ("Summarise this study-planner conversation for your own future use in at most 120 words: "
                  "decisions taken, preferences stated, tasks added/completed, open questions. "
                  "Facts only, no greetings.")


def _is_turn_start(msg: dict) -> bool:
    c = msg["content"]
    if msg["role"] != "user":
        return False
    return isinstance(c, str) or not any(b.get("type") == "tool_result" for b in c)


def _transcript(messages: list[dict], limit: int = 300) -> str:
    lines = []
    for m in messages:
        blocks = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
        for b in blocks:
            t = b.get("type")
            if t == "text":
                s = b["text"]
            elif t == "tool_use":
                s = f"[tool {b['name']} {json.dumps(b.get('input'), ensure_ascii=False)}]"
            elif t == "tool_result":
                s = f"[result {b['content'] if isinstance(b['content'], str) else b['content']}]"
            else:
                continue
            lines.append(f"{m['role']}: {s[:limit]}")
    return "\n".join(lines)


def maybe_compact(client, model: str, history: History, meter: TurnMeter, last_prompt_tokens: int,
                  threshold: int, keep_turns: int = 1) -> bool:
    if last_prompt_tokens <= threshold:
        log(f"no compaction: last prompt {last_prompt_tokens} <= threshold {threshold}")
        return False
    msgs = history.messages()
    starts = [i for i, m in enumerate(msgs) if _is_turn_start(m)]
    if len(starts) <= keep_turns:
        log("over threshold but only the current turns exist - nothing to compact")
        return False
    cut = starts[-keep_turns]
    log(f"compacting {cut} of {len(msgs)} messages (last prompt {last_prompt_tokens} > {threshold})")
    resp = client.messages.create(
        model=model, max_tokens=400,
        system="You compress conversation logs.",
        messages=[{"role": "user", "content": f"{SUMMARY_PROMPT}\n\n<log>\n{_transcript(msgs[:cut])}\n</log>"}],
    )
    meter.add(resp.usage, purpose="compaction")
    blocks = [b if isinstance(b, dict) else b.model_dump() for b in resp.content]
    summary = "".join(b["text"] for b in blocks if b.get("type") == "text").strip()
    history.append_compaction(summary, dropped=cut)
    return True
