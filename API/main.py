"""Run Study Compass (API version).

  python API/main.py --scenario scenario.json --out results/api.json
  python API/main.py                       # interactive chat, new conversation
  python API/main.py --resume <conv-id>    # continue a saved conversation

Needs ANTHROPIC_API_KEY in the environment (never in code or git).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.loc import api_loc  # noqa: E402
from shared.scenario_runner import run_scenario  # noqa: E402

from API.agent import StudyAgent  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario")
    ap.add_argument("--out", default=str(ROOT / "results" / "api.json"))
    ap.add_argument("--state", default=str(ROOT / "state" / "api"))
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--compact-at", type=int, default=12000, help="compaction threshold in prompt tokens")
    ap.add_argument("--resume", help="conversation id to continue (interactive mode)")
    ap.add_argument("--today", help="YYYY-MM-DD, defaults to the real date")
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Export it in your terminal (not in code).")
    import anthropic
    client = anthropic.Anthropic()
    cfg = {"model": args.model, "effort": args.effort, "compact_at": args.compact_at}

    if args.scenario:
        settings = {**cfg, "thinking": "adaptive", "max_tokens": 4000}
        factory = lambda state, today, _s: StudyAgent(client, state, cfg, today)  # noqa: E731
        asyncio.run(run_scenario(args.scenario, args.out, args.state, factory, "API", settings, api_loc()))
        return

    agent = StudyAgent(client, args.state, cfg, args.today, conversation=args.resume)
    print(f"conversation id: {agent.conversation}  (Ctrl-D to quit)")
    while True:
        try:
            text = input("\nyou> ").strip()
        except EOFError:
            break
        if text:
            r = agent.ask(text)
            print(f"\ncompass> {r['answer']}\n   (${r['cost_usd']:.4f}, {r['tokens']})")


if __name__ == "__main__":
    main()
