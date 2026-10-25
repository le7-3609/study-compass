"""Print the REPORT.md tables from results/api.json and results/sdk.json.

  python report_tables.py > results/tables.md
"""
import json
from pathlib import Path

from shared.loc import PARTS

R = Path(__file__).parent / "results"


def load(name):
    p = R / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


api, sdk = load("api"), load("sdk")
if not (api and sdk):
    raise SystemExit("run both versions first (results/api.json and results/sdk.json)")

rows = [("input (uncached)", "input"), ("cache read", "cache_read"), ("cache write", "cache_write"),
        ("output", "output"), ("cache hit %", "cache_hit_pct"), ("model calls", "model_calls"),
        ("cost USD", "cost_usd"), ("seconds", "seconds")]
print("| metric | API | SDK |\n|---|---:|---:|")
for label, k in rows:
    print(f"| {label} | {api['totals'][k]} | {sdk['totals'][k]} |")
print(f"| checks passed | {api['checks_passed']} | {sdk['checks_passed']} |\n")

print("| turn | API in / read / write / out | API calls | API $ | SDK in / read / write / out | SDK calls | SDK $ |")
print("|---|---|---:|---:|---|---:|---:|")
for a, s in zip(api["turns"], sdk["turns"]):
    ta, ts = a["tokens"], s["tokens"]
    print(f"| {a['session']}.{a['turn']} | {ta['input']} / {ta['cache_read']} / {ta['cache_write']} / {ta['output']} "
          f"| {a['model_calls']} | {a['cost_usd']:.4f} | {ts['input']} / {ts['cache_read']} / {ts['cache_write']} / "
          f"{ts['output']} | {s['model_calls']} | {s['cost_usd']:.4f} |")
print()

print("| harness part | API lines | SDK lines |\n|---|---:|---:|")
for p in PARTS:
    print(f"| {p} | {api['loc'][p]} | {sdk['loc'][p]} |")
print(f"| **total** | {sum(api['loc'].values())} | {sum(sdk['loc'].values())} |\n")

print("| check | API | SDK |\n|---|:-:|:-:|")
for a, s in zip(api["checks"], sdk["checks"]):
    print(f"| {a['id']} | {'✅' if a['passed'] else '❌'} | {'✅' if s['passed'] else '❌'} |")
