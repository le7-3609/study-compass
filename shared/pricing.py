"""USD per million tokens (standard API rates, 5-minute cache writes)."""

PRICES = {
    "claude-opus-5-5": {"input": 4.00, "cache_write": 5.00, "cache_read": 0.20, "output": 20.00},
}


def cost(tokens: dict, model: str) -> float:
    p = PRICES.get(model)
    if p is None:
        return 0.0
    return sum(tokens[k] * p[k] for k in ("input", "cache_write", "cache_read", "output")) / 1_000_000
