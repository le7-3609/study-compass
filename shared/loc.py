"""Count lines of code per harness part, for results/*.json and REPORT.md.

API: non-blank, non-comment lines of each file in API/harness/.
SDK: lines tagged `# replaces: <part>` in SDK/*.py (the line that does that job).
"""
from __future__ import annotations

import re
from pathlib import Path

PARTS = ["loop", "tools", "history", "memory", "context", "compaction", "caching", "tokens"]
ROOT = Path(__file__).resolve().parent.parent


def _code_lines(path: Path) -> int:
    n, in_doc = 0, False
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith(('"""', "'''")):
            if not (len(s) > 3 and s.endswith(('"""', "'''"))):
                in_doc = not in_doc
            continue
        if in_doc or not s or s.startswith("#"):
            continue
        n += 1
    return n


def api_loc() -> dict:
    return {p: _code_lines(ROOT / "API" / "harness" / f"{p}.py") for p in PARTS}


def sdk_loc() -> dict:
    counts = {p: 0 for p in PARTS}
    pat = re.compile(r"#\s*replaces:\s*([\w,\s.]+)")
    for f in (ROOT / "SDK").glob("*.py"):
        for line in f.read_text(encoding="utf-8").splitlines():
            m = pat.search(line)
            if m:
                for part in re.split(r"[,\s]+", m.group(1).strip()):
                    part = part.removesuffix(".py")
                    if part in counts:
                        counts[part] += 1
    return counts
