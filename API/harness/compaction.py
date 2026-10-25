"""Context-window management: summarise the conversation once it passes a threshold.

Trigger: the prompt size of the previous model call (input + cache read) is above `threshold`
tokens. Everything before the start of the most recent
`keep_turns` turns is turned into a short summary by one extra model call, and a
compaction record is appended to the history (nothing is deleted from disk).
Cuts are made only at a turn start, so functionCall/functionResponse pairs never split.
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
    return msg["role"] == "user" and not any("functionResponse" in p for p in msg["parts"])


def _transcript(messages: list[dict], limit: int = 300) -> str:
    lines = []
    for m in messages:
        for p in m["parts"]:
            if p.get("thought"):
                continue
            if "text" in p:
                s = p["text"]
            elif "functionCall" in p:
                s = f"[tool {p['functionCall']['name']} {json.dumps(p['functionCall'].get('args'), ensure_ascii=False)}]"
            elif "functionResponse" in p:
                s = f"[result {next(iter(p['functionResponse']['response'].values()))}]"
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
    resp = client.generate(
        model=model, max_tokens=1500, system="You compress conversation logs.", thinking_level="low",
        contents=[{"role": "user", "parts": [{"text": f"{SUMMARY_PROMPT}\n\n<log>\n{_transcript(msgs[:cut])}\n</log>"}]}])
    meter.add(resp.get("usageMetadata", {}), purpose="compaction")
    parts = ((resp.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    summary = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    history.append_compaction(summary, dropped=cut)
    return True
