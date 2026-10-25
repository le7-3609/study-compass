"""Token usage and cost per turn.

A turn may take several model calls (tool loop, compaction). The meter sums the
usageMetadata of every call and prices it. Gemini reports promptTokenCount INCLUDING
the cached part, so input = prompt - cached. Thinking tokens (thoughtsTokenCount) are
billed as output. Implicit caching has no write charge, so cache_write stays 0.
"""
from __future__ import annotations

import time

from shared.pricing import cost

from API.harness import logger

log = logger(__file__)


def _get(usage: dict, name: str) -> int:
    return int((usage or {}).get(name) or 0)


class TurnMeter:
    def __init__(self, model: str):
        self.model = model
        self.tokens = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0}
        self.calls = 0
        self.last_prompt_tokens = 0
        self._t0 = time.perf_counter()

    def add(self, usage: dict, purpose: str = "turn") -> None:
        cached = _get(usage, "cachedContentTokenCount")
        call = {"input": _get(usage, "promptTokenCount") - cached, "cache_read": cached, "cache_write": 0,
                "output": _get(usage, "candidatesTokenCount") + _get(usage, "thoughtsTokenCount")}
        for k, v in call.items():
            self.tokens[k] += v
        self.calls += 1
        if purpose == "turn":
            self.last_prompt_tokens = call["input"] + call["cache_read"]
        log(f"call #{self.calls} ({purpose}): in={call['input']} cache_read={call['cache_read']} "
            f"out={call['output']} ${cost(call, self.model):.4f}")

    def summary(self) -> dict:
        out = {"tokens": dict(self.tokens), "model_calls": self.calls,
               "cost_usd": round(cost(self.tokens, self.model), 6),
               "seconds": round(time.perf_counter() - self._t0, 2)}
        log(f"turn total: {out['tokens']} calls={out['model_calls']} ${out['cost_usd']:.4f}")
        return out
