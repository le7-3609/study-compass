"""Tool layer: function declarations for the API, dispatch to the domain, errors as error results."""
from __future__ import annotations

from shared.domain import TOOL_SPECS, StudyDomain
from shared.store import DomainError

from API.harness import logger

log = logger(__file__)
MAX_RESULT_CHARS = 2000  # hard cap so one tool can never flood the context


def schemas() -> list[dict]:
    decls = []
    for name, spec in TOOL_SPECS.items():
        d = {"name": name, "description": spec["description"]}
        if spec["schema"]["properties"]:  # Gemini rejects an empty parameter object
            d["parametersJsonSchema"] = spec["schema"]
        decls.append(d)
    return [{"functionDeclarations": decls}]


class Toolbox:
    def __init__(self, domain: StudyDomain):
        self.domain = domain
        self.called: list[str] = []

    def execute(self, call: dict) -> dict:
        """One functionCall -> one functionResponse part (never raises)."""
        name, args = call["name"], call.get("args") or {}
        self.called.append(name)
        try:
            text, key = self.domain.call(name, args), "result"
        except DomainError as e:
            text, key = f"error: {e}", "error"
        except Exception as e:  # bug in a tool: still give the model something to react to
            text, key = f"internal error in {name}: {type(e).__name__}: {e}", "error"
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + f"\n…[truncated {len(text) - MAX_RESULT_CHARS} chars]"
        log(f"{name}({_short(args)}) -> {'ERROR ' if key == 'error' else ''}{len(text)} chars")
        resp = {"name": name, "response": {key: text}}
        if call.get("id"):
            resp["id"] = call["id"]
        return {"functionResponse": resp}


def _short(args: dict) -> str:
    s = ", ".join(f"{k}={v!r}" for k, v in args.items())
    return s if len(s) < 80 else s[:77] + "..."
