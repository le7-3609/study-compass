"""Notional USD per million tokens at paid-tier rates (introductory prices valid through 2026-12-31).

The free tier bills nothing; the cost column answers "what would this run cost on the paid tier".
Gemini implicit caching has no write charge, so cache_write is 0.
"""

PRICES = {
    "gemini-3.6-flash": {"input": 0.75, "cache_write": 0.0, "cache_read": 0.075, "output": 3.75},
    "gemini-3.5-flash-lite": {"input": 0.30, "cache_write": 0.0, "cache_read": 0.03, "output": 2.50},
    "gemini-3.8-flash": {"input": 0.75, "cache_write": 0.0, "cache_read": 0.075, "output": 3.75},
    "gemini-3-flash-preview": {"input": 0.50, "cache_write": 0.0, "cache_read": 0.05, "output": 3.00},
    "gemini-2.5-flash": {"input": 0.30, "cache_write": 0.0, "cache_read": 0.03, "output": 2.50},
}


def cost(tokens: dict, model: str) -> float:
    p = PRICES.get(model)
    if p is None:
        return 0.0
    return sum(tokens[k] * p[k] for k in ("input", "cache_write", "cache_read", "output")) / 1_000_000
