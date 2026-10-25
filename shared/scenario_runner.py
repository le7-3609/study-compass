"""Run scenario.json against any agent factory and write results/<x>.json.

Harness-agnostic: both API/main.py and SDK/main.py call `run_scenario` with their own
factory. Every run starts from a clean state directory (comparison rule).
"""
from __future__ import annotations

import inspect
import json
import platform
import shutil
from importlib import metadata
from pathlib import Path

from shared.checks import run_checks
from shared.domain import DEFAULT_CALENDAR
from shared.store import StudyStore


async def _maybe(x):
    return await x if inspect.isawaitable(x) else x


def clean_state(state_dir: Path) -> None:
    if state_dir.exists():
        shutil.rmtree(state_dir)
    state_dir.mkdir(parents=True)


def _versions() -> dict:
    out = {"python": platform.python_version()}
    for pkg in ("google-genai",):
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = None
    return out


def totals(turns: list[dict]) -> dict:
    t = {k: sum(x["tokens"][k] for x in turns) for k in ("input", "cache_read", "cache_write", "output")}
    prompt = t["input"] + t["cache_read"] + t["cache_write"]
    t["cache_hit_pct"] = round(100 * t["cache_read"] / prompt, 1) if prompt else 0.0
    t["model_calls"] = sum(x["model_calls"] for x in turns)
    t["cost_usd"] = round(sum(x["cost_usd"] for x in turns), 5)
    t["seconds"] = round(sum(x["seconds"] for x in turns), 1)
    return t


async def run_scenario(scenario_path, out_path, state_dir, factory, label, settings, loc) -> dict:
    scenario = json.loads(Path(scenario_path).read_text(encoding="utf-8"))
    state_dir = Path(state_dir)
    clean_state(state_dir)
    turns = []
    for s_no, session in enumerate(scenario["sessions"], 1):
        print(f"\n=== {label} session {s_no}: fresh agent instance, state loaded from disk ===")
        agent = factory(state_dir, scenario["today"], s_no)
        for t_no, prompt in enumerate(session["turns"], 1):
            print(f"\n--- user [{s_no}.{t_no}]: {prompt}")
            rec = await _maybe(agent.ask(prompt))
            rec.update({"session": s_no, "turn": t_no, "prompt": prompt})
            print(f"--- agent: {rec['answer']}")
            print(f"--- turn cost ${rec['cost_usd']:.4f} | {rec['tokens']} | calls={rec['model_calls']} "
                  f"| tools={rec['tools']} | {rec['seconds']}s")
            turns.append(rec)
        await _maybe(getattr(agent, "close", lambda: None)())
    store = StudyStore(state_dir, scenario["today"])
    checks = run_checks(scenario["checks"], store, turns, DEFAULT_CALENDAR)
    result = {"harness": label, "settings": settings, "versions": _versions(), "turns": turns,
              "totals": totals(turns), "checks": checks,
              "checks_passed": f"{sum(c['passed'] for c in checks)}/{len(checks)}",
              "loc": loc, "final_state": {"tasks": store.tasks(), "prefs": store.prefs(), "plan": store.plan()}}
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n=== checks {result['checks_passed']} ===")
    for c in checks:
        print(f"  {'PASS' if c['passed'] else 'FAIL'} {c['id']}: {c['detail']}")
    print(f"totals: {result['totals']}\nwritten: {out_path}")
    return result
