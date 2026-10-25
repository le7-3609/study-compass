"""Tool layer: JSON schemas for the API, dispatch to the domain, errors as is_error."""
from __future__ import annotations

from shared.domain import TOOL_SPECS, StudyDomain
from shared.store import DomainError

from API.harness import logger

log = logger(__file__)
MAX_RESULT_CHARS = 2000  # hard cap so one tool can never flood the context


def schemas() -> list[dict]:
    return [{"name": name, "description": spec["description"], "input_schema": spec["schema"]}
            for name, spec in TOOL_SPECS.items()]


class Toolbox:
    def __init__(self, domain: StudyDomain):
        self.domain = domain
        self.called: list[str] = []

    def execute(self, block: dict) -> dict:
        """One tool_use block -> one tool_result block (never raises)."""
        name, args, tid = block["name"], block.get("input") or {}, block["id"]
        self.called.append(name)
        try:
            text = self.domain.call(name, args)
            is_error = False
        except DomainError as e:
            text, is_error = f"error: {e}", True
        except Exception as e:  # bug in a tool: still give the model something to react to
            text, is_error = f"internal error in {name}: {type(e).__name__}: {e}", True
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + f"\n…[truncated {len(text) - MAX_RESULT_CHARS} chars]"
        log(f"{name}({_short(args)}) -> {'ERROR ' if is_error else ''}{len(text)} chars")
        result = {"type": "tool_result", "tool_use_id": tid, "content": text}
        if is_error:
            result["is_error"] = True
        return result


def _short(args: dict) -> str:
    s = ", ".join(f"{k}={v!r}" for k, v in args.items())
    return s if len(s) < 80 else s[:77] + "..."
