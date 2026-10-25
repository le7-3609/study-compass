"""Prompt-caching breakpoints (max 4 per request; we use 3).

1. last tool schema      -> caches all tool definitions
2. system prompt block   -> caches tools + system
3. last block of the last message -> rolling breakpoint: the next call (next tool
   iteration or next turn) reads the whole conversation so far from cache.

Copies are made so cache_control never leaks into the stored history.
"""
from __future__ import annotations

import copy

from API.harness import logger

log = logger(__file__)
EPHEMERAL = {"type": "ephemeral"}


def apply(tools: list[dict], system: str, messages: list[dict]) -> tuple[list, list, list]:
    tools = copy.deepcopy(tools)
    if tools:
        tools[-1]["cache_control"] = EPHEMERAL
    system_blocks = [{"type": "text", "text": system, "cache_control": EPHEMERAL}]
    messages = copy.deepcopy(messages)
    marked = False
    if messages:
        last = messages[-1]
        if isinstance(last["content"], str):
            last["content"] = [{"type": "text", "text": last["content"]}]
        for block in reversed(last["content"]):
            if block.get("type") not in ("thinking", "redacted_thinking"):
                block["cache_control"] = EPHEMERAL
                marked = True
                break
    log(f"breakpoints: tools[{len(tools) - 1}], system, {'last message' if marked else 'no message'}"
        f" ({len(messages)} msgs)")
    return tools, system_blocks, messages
