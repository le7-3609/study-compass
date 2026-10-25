"""Study Compass on the google-genai SDK: Chat + automatic function calling run the loop, we configure it.

Lines tagged `# replaces: <part>` do the job of API/harness/<part>.py.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from google import genai
from google.genai import types

from shared.domain import DEFAULT_CALENDAR, StudyDomain
from shared.pricing import cost
from shared.prompt import SYSTEM_PROMPT
from shared.store import StudyStore

from SDK.tools import make_tools, render_memory

MAX_REMOTE_CALLS = 10


def log(msg: str) -> None:
    print(f"  [SDK/agent.py] {msg}")


class UsageTap:
    """Collects usageMetadata of every generateContent response. The SDK's automatic function calling
    only returns the LAST call's usage, so we read each HTTP response ourselves."""  # replaces: tokens

    def __init__(self):
        self.calls: list[dict] = []  # replaces: tokens

    def __call__(self, response) -> None:  # replaces: tokens
        if "generateContent" in str(response.url) and response.status_code == 200:  # replaces: tokens
            response.read()  # replaces: tokens
            self.calls.append(response.json().get("usageMetadata", {}))  # replaces: tokens


class StudyAgentSDK:
    def __init__(self, api_key: str, state_dir: str | Path, cfg: dict, today: str | None = None,
                 resume: bool = False, fetch=None):
        self.cfg = cfg
        self.store = StudyStore(state_dir, today)
        self.history_file = Path(state_dir) / "sdk_history.json"
        self.tap, self.called = UsageTap(), []
        domain = StudyDomain(self.store, cfg.get("calendar", DEFAULT_CALENDAR), fetch)
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(
            client_args={"event_hooks": {"response": [self.tap]}},  # replaces: tokens
            retry_options=types.HttpRetryOptions(attempts=5, initial_delay=5.0, max_delay=60.0,  # replaces: loop
                                                 http_status_codes=[429, 500, 503])))
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT + "\n\n" + render_memory(self.store),  # replaces: memory, context
            tools=make_tools(domain, self.called),  # replaces: tools
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                maximum_remote_calls=MAX_REMOTE_CALLS),  # replaces: loop
            thinking_config=types.ThinkingConfig(thinking_level=cfg["effort"].upper()),
            max_output_tokens=cfg.get("max_tokens", 8000),
        )
        history = None
        if resume and self.history_file.exists():  # replaces: history
            history = [types.Content.model_validate(c) for c in
                       json.loads(self.history_file.read_text(encoding="utf-8"))]  # replaces: history
        self.chat = self.client.chats.create(model=cfg["model"], config=config, history=history)  # replaces: history
        # compaction: none in this SDK (history grows)   # replaces: compaction
        # caching: implicit on the server, same as API   # replaces: caching
        log(f"chat ready: model={cfg['model']} thinking={cfg['effort']} tools=8 resumed={history is not None}")

    def ask(self, text: str) -> dict:
        self.tap.calls.clear()
        self.called.clear()
        t0 = time.perf_counter()
        resp = self.chat.send_message(text)  # replaces: loop
        usage = self.tap.calls  # replaces: tokens
        tokens = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0}  # replaces: tokens
        for u in usage:  # replaces: tokens
            cached = int(u.get("cachedContentTokenCount") or 0)  # replaces: tokens
            tokens["input"] += int(u.get("promptTokenCount") or 0) - cached  # replaces: tokens
            tokens["cache_read"] += cached  # replaces: tokens
            tokens["output"] += int(u.get("candidatesTokenCount") or 0) + int(u.get("thoughtsTokenCount") or 0)  # replaces: tokens
        self.history_file.write_text(json.dumps(  # replaces: history
            [c.model_dump(mode="json", exclude_none=True) for c in self.chat.get_history()],  # replaces: history
            ensure_ascii=False), encoding="utf-8")  # replaces: history
        rec = {"answer": (resp.text or "").strip(), "tools": list(self.called), "tokens": tokens,
               "model_calls": len(usage), "cost_usd": round(cost(tokens, self.cfg["model"]), 6),
               "seconds": round(time.perf_counter() - t0, 2)}
        log(f"turn: {tokens} calls={rec['model_calls']} ${rec['cost_usd']:.4f} tools={rec['tools']}")
        return rec
