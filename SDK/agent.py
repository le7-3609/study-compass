"""Study Compass on the Claude Agent SDK: Claude Code runs the harness, we configure it.

Lines tagged `# replaces: <part>` do the job of API/harness/<part>.py.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage,
                              TextBlock, ToolUseBlock)

from shared.domain import DEFAULT_CALENDAR, StudyDomain
from shared.pricing import cost
from shared.prompt import SYSTEM_PROMPT
from shared.store import StudyStore

from SDK.tools import ALLOWED, SERVER, build_server, render_claude_md


def log(msg: str) -> None:
    print(f"  [SDK/agent.py] {msg}")


class StudyAgentSDK:
    def __init__(self, state_dir: str | Path, cfg: dict, today: str | None = None,
                 resume: str | None = None, fetch=None):
        self.cfg = cfg
        self.store = StudyStore(state_dir, today)
        self.workspace = Path(state_dir) / "sdk_workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.session_file = Path(state_dir) / "sdk_session.json"
        claude_md = self.workspace / "CLAUDE.md"
        render_claude_md(self.store, claude_md)  # replaces: memory (state on disk -> CLAUDE.md)
        domain = StudyDomain(self.store, cfg.get("calendar", DEFAULT_CALENDAR), fetch)
        self.options = ClaudeAgentOptions(
            model=cfg["model"], effort=cfg["effort"], thinking={"type": "adaptive"},
            system_prompt=SYSTEM_PROMPT,  # replaces: context (our own prompt instead of Claude Code's)
            mcp_servers={SERVER: build_server(domain, claude_md)},  # replaces: tools
            strict_mcp_config=True,  # replaces: tools (ignore any other MCP config)
            tools=[],  # replaces: tools (no built-in Bash/Read/Edit...)
            allowed_tools=ALLOWED,  # replaces: tools
            permission_mode="dontAsk",  # replaces: tools (anything not allowed is denied, no prompt)
            setting_sources=["project"],  # replaces: memory (loads workspace/CLAUDE.md)
            cwd=str(self.workspace),  # replaces: memory
            resume=resume,  # replaces: history
            max_turns=10,  # replaces: loop (iteration guard)
        )
        # compaction: automatic in Claude Code   # replaces: compaction
        # caching: automatic in Claude Code      # replaces: caching
        self.client: ClaudeSDKClient | None = None
        self._prev_reported_cost = 0.0
        log(f"options ready: model={cfg['model']} effort={cfg['effort']} tools={len(ALLOWED)} resume={resume}")

    async def ask(self, text: str) -> dict:
        if self.client is None:
            self.client = ClaudeSDKClient(options=self.options)
            await self.client.connect()
        t0 = time.perf_counter()
        await self.client.query(text)  # replaces: loop
        tools, parts, result = [], [], None
        async for msg in self.client.receive_response():  # replaces: loop
            if isinstance(msg, AssistantMessage):
                for b in msg.content:
                    if isinstance(b, ToolUseBlock):
                        tools.append(b.name.removeprefix(f"mcp__{SERVER}__"))
                        log(f"tool call {tools[-1]}")
                    elif isinstance(b, TextBlock):
                        parts.append(b.text)
            elif isinstance(msg, ResultMessage):
                result = msg
        u = result.usage or {}  # replaces: tokens
        tokens = {"input": int(u.get("input_tokens", 0)),  # replaces: tokens
                  "cache_read": int(u.get("cache_read_input_tokens", 0)),  # replaces: tokens
                  "cache_write": int(u.get("cache_creation_input_tokens", 0)),  # replaces: tokens
                  "output": int(u.get("output_tokens", 0))}  # replaces: tokens
        self.session_file.write_text(json.dumps({"session_id": result.session_id}))  # replaces: history
        reported = float(result.total_cost_usd or 0.0)  # replaces: tokens
        turn_cost = self._turn_cost(reported, tokens)
        rec = {"answer": "\n".join(parts).strip() or (result.result or ""), "tools": tools,
               "tokens": tokens, "model_calls": int(result.num_turns or 0), "cost_usd": round(turn_cost, 6),
               "cost_usd_from_usage": round(cost(tokens, self.cfg["model"]), 6),
               "sdk_total_cost_usd_reported": reported, "model_usage": result.model_usage,
               "seconds": round(time.perf_counter() - t0, 2), "session_id": result.session_id}
        log(f"turn: {tokens} calls={rec['model_calls']} ${rec['cost_usd']:.4f}")
        return rec

    def _turn_cost(self, reported: float, tokens: dict) -> float:
        """total_cost_usd may be per-query or cumulative for the client; pick the reading that
        matches the usage-based estimate (the SDK figure also covers any helper-model calls)."""
        estimate = cost(tokens, self.cfg["model"])
        delta = reported - self._prev_reported_cost
        self._prev_reported_cost = reported
        if estimate and abs(delta - estimate) < abs(reported - estimate):
            return delta
        return reported

    async def close(self) -> None:
        if self.client is not None:
            await self.client.disconnect()
            self.client = None
