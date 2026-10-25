"""Prompt caching on Gemini is implicit: the server caches the longest repeated prefix by itself.

Nothing to mark. What we control is keeping the prefix stable: tools, system prompt and history are
sent in the same order every call, and the per-turn context is attached to the newest user message
(see context.py). Hits are reported as cachedContentTokenCount (see tokens.py).
"""
from __future__ import annotations

from API.harness import logger

log = logger(__file__)


def apply(tools: list[dict], system: str, contents: list[dict]) -> tuple[list, str, list]:
    log(f"implicit caching: stable prefix = tools + system + {max(len(contents) - 1, 0)} earlier messages")
    return tools, system, contents
