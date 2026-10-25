"""Run Study Compass (Agent SDK version).

  python SDK/main.py --scenario scenario.json --out results/sdk.json
  python SDK/main.py                  # interactive chat
  python SDK/main.py --resume         # continue the last saved session (resume=session_id)

Runs on your Claude Code login. ANTHROPIC_API_KEY must NOT be set, otherwise
billing moves to the key.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.loc import sdk_loc  # noqa: E402
from shared.scenario_runner import run_scenario  # noqa: E402

from SDK.agent import StudyAgentSDK  # noqa: E402


async def chat(args, cfg) -> None:
    resume = None
    sess = Path(args.state) / "sdk_session.json"
    if args.resume and sess.exists():
        resume = json.loads(sess.read_text())["session_id"]  # replaces: history
    agent = StudyAgentSDK(args.state, cfg, args.today, resume=resume)
    print("(Ctrl-D to quit)")
    try:
        while True:
            try:
                text = input("\nyou> ").strip()
            except EOFError:
                break
            if text:
                r = await agent.ask(text)
                print(f"\ncompass> {r['answer']}\n   (${r['cost_usd']:.4f}, {r['tokens']})")
    finally:
        await agent.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario")
    ap.add_argument("--out", default=str(ROOT / "results" / "sdk.json"))
    ap.add_argument("--state", default=str(ROOT / "state" / "sdk"))
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--today")
    args = ap.parse_args()

    if os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is set - run `unset ANTHROPIC_API_KEY` so the SDK uses your Claude Code login.")
    cfg = {"model": args.model, "effort": args.effort}

    if args.scenario:
        settings = {**cfg, "thinking": "adaptive", "max_turns": 10}
        factory = lambda state, today, _s: StudyAgentSDK(state, cfg, today)  # noqa: E731
        asyncio.run(run_scenario(args.scenario, args.out, args.state, factory, "SDK", settings, sdk_loc()))
    else:
        asyncio.run(chat(args, cfg))


if __name__ == "__main__":
    main()
