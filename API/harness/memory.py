"""Long-term memory: where it lives and how it is retrieved.

Storage: prefs.json in the state dir (via shared.store), so it survives restarts.
Retrieval: the 4 scheduling preferences are tiny and always relevant, so they are
always included. Free-text notes grow over time, so only notes that share words
with the current message are included (max 3); the rest are reachable via `recall`.
"""
from __future__ import annotations

import re

from shared.store import DEFAULT_PREFS, StudyStore

from API.harness import logger

log = logger(__file__)
MAX_NOTES = 3
_WORD = re.compile(r"\w{3,}", re.UNICODE)


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text)}


class Memory:
    def __init__(self, store: StudyStore):
        self.store = store
        log(f"memory file: {store.root.name}/prefs.json ({len(store.prefs())} keys on disk)")

    def digest(self, user_text: str) -> str:
        prefs = self.store.prefs()
        core = []
        for k in DEFAULT_PREFS:
            if k in prefs:
                e = prefs[k]
                prev = f" (was {e['history'][-1]['value']})" if e.get("history") else ""
                core.append(f"{k}={e['value']}{prev}")
            else:
                core.append(f"{k}={DEFAULT_PREFS[k] or '-'}(default)")
        notes = prefs.get("note", {}).get("value", [])
        q = _words(user_text)
        scored = sorted(((len(q & _words(n)), i, n) for i, n in enumerate(notes)), reverse=True)
        picked = [n for score, _, n in scored if score > 0][:MAX_NOTES]
        lines = ["saved preferences: " + "; ".join(core)]
        lines += [f"note: {n}" for n in picked]
        if len(notes) > len(picked):
            lines.append(f"({len(notes) - len(picked)} other notes saved - use `recall` if needed)")
        log(f"retrieved {len(core)} prefs + {len(picked)}/{len(notes)} notes by keyword match")
        return "\n".join(lines)
