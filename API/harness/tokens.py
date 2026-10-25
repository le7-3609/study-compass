"""Token usage and cost per turn.

A turn may take several model calls (tool loop, compaction). The meter sums the
`usage` of every call and prices it. usage.input_tokens is only the uncached part;
cache reads/writes are reported separately by the API.
"""
from __future__ import annotations

import time

from shared.pricing import cost

from API.harness import logger

log = logger(__file__)


def _get(usage, name: str) -> int:
    v = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, 0)
    return int(v or 0)


class TurnMeter:
    def __init__(self, model: str):
        self.model = model
        self.tokens = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0}
        self.calls = 0
        self.last_prompt_tokens = 0
        self._t0 = time.perf_counter()

    def add(self, usage, purpose: str = "turn") -> None:
        call = {"input": _get(usage, "input_tokens"),
                "cache_read": _get(usage, "cache_read_input_tokens"),
                "cache_write": _get(usage, "cache_creation_input_tokens"),
                "output": _get(usage, "output_tokens")}
        for k, v in call.items():
            self.tokens[k] += v
        self.calls += 1
        if purpose == "turn":
            self.last_prompt_tokens = call["input"] + call["cache_read"] + call["cache_write"]
        log(f"call #{self.calls} ({purpose}): in={call['input']} cache_read={call['cache_read']} "
            f"cache_write={call['cache_write']} out={call['output']} ${cost(call, self.model):.4f}")

    def summary(self) -> dict:
        out = {"tokens": dict(self.tokens), "model_calls": self.calls,
               "cost_usd": round(cost(self.tokens, self.model), 6),
               "seconds": round(time.perf_counter() - self._t0, 2)}
        log(f"turn total: {out['tokens']} calls={out['model_calls']} ${out['cost_usd']:.4f}")
        return out
