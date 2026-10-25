"""Run Study Compass (SDK version: google-genai Chat + automatic function calling).

  python SDK/main.py --scenario scenario.json --out results/sdk.json
  python SDK/main.py                  # interactive chat
  python SDK/main.py --resume         # continue the saved chat history

Needs GEMINI_API_KEY (environment or git-ignored .env). Never put the key in code.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.env import gemini_key  # noqa: E402
from shared.loc import sdk_loc  # noqa: E402
from shared.scenario_runner import run_scenario  # noqa: E402

from SDK.agent import StudyAgentSDK  # noqa: E402


def chat(args, cfg, key) -> None:
    agent = StudyAgentSDK(key, args.state, cfg, args.today, resume=args.resume)
    print("(Ctrl-D to quit)")
    while True:
        try:
            text = input("\nyou> ").strip()
        except EOFError:
            break
        if text:
            r = agent.ask(text)
            print(f"\ncompass> {r['answer']}\n   (${r['cost_usd']:.4f}, {r['tokens']})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario")
    ap.add_argument("--out", default=str(ROOT / "results" / "sdk.json"))
    ap.add_argument("--state", default=str(ROOT / "state" / "sdk"))
    ap.add_argument("--model", default="gemini-3.6-flash")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--today")
    args = ap.parse_args()

    key = gemini_key(ROOT)
    cfg = {"model": args.model, "effort": args.effort}

    if args.scenario:
        settings = {**cfg, "thinking": f"level {args.effort}", "max_remote_calls": 10, "max_tokens": 8000}
        factory = lambda state, today, _s: StudyAgentSDK(key, state, cfg, today)  # noqa: E731
        asyncio.run(run_scenario(args.scenario, args.out, args.state, factory, "SDK", settings, sdk_loc()))
    else:
        chat(args, cfg, key)


if __name__ == "__main__":
    main()
