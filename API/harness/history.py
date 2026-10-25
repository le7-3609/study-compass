"""Conversation history: an append-only JSONL file per conversation.

Records are never rewritten. A `message` record adds one message; a `compaction`
record says "from here on, the first N messages of the current view are replaced
by this summary". messages() replays the file to rebuild what the model sees.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from API.harness import logger

log = logger(__file__)


class History:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            log(f"loaded {len(self.messages())} messages from {self.path.name}")
        else:
            self.path.touch()
            log(f"new conversation file {self.path.name}")

    def _append(self, record: dict) -> None:
        record["ts"] = datetime.now().isoformat(timespec="seconds")
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def append(self, role: str, content) -> None:
        self._append({"type": "message", "role": role, "content": content})
        kinds = [c.get("type") for c in content] if isinstance(content, list) else ["text"]
        log(f"append {role}: {','.join(kinds)}")

    def append_compaction(self, summary: str, dropped: int) -> None:
        self._append({"type": "compaction", "summary": summary, "dropped": dropped})
        log(f"compaction record: {dropped} messages -> summary of {len(summary)} chars")

    def records(self) -> list[dict]:
        with self.path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def messages(self) -> list[dict]:
        view: list[dict] = []
        for r in self.records():
            if r["type"] == "message":
                view.append({"role": r["role"], "content": r["content"]})
            elif r["type"] == "compaction":
                view = [{"role": "user", "content": f"<summary of earlier conversation>\n{r['summary']}\n</summary>"},
                        {"role": "assistant", "content": "Understood, I'll continue from that summary."}] \
                       + view[r["dropped"]:]
        return view
