"""Offline test helpers: a scripted fake Messages client - no API key, no network."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import API.harness as harness  # noqa: E402

harness.QUIET = True


def usage(inp=100, read=0, write=0, out=20):
    return SimpleNamespace(input_tokens=inp, cache_read_input_tokens=read,
                           cache_creation_input_tokens=write, output_tokens=out)


def text_resp(text, **u):
    return SimpleNamespace(content=[{"type": "text", "text": text}], stop_reason="end_turn", usage=usage(**u))


def tool_resp(*calls, **u):
    """calls: (id, name, input) tuples -> one response with several tool_use blocks."""
    blocks = [{"type": "thinking", "thinking": "plan", "signature": "sig"}]
    blocks += [{"type": "tool_use", "id": i, "name": n, "input": a} for i, n, a in calls]
    return SimpleNamespace(content=blocks, stop_reason="tool_use", usage=usage(**u))


class FakeMessages:
    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def create(self, **kw):
        self.requests.append(kw)
        if not self.script:
            raise AssertionError("fake model ran out of scripted responses")
        return self.script.pop(0)


class FakeClient:
    def __init__(self, script):
        self.messages = FakeMessages(script)


def fake_fetch(url):
    if "opensearch" in url:
        return ["dynamic programming", ["Dynamic programming"], [""], ["https://en.wikipedia.org/wiki/Dynamic_programming"]]
    return {"title": "Dynamic programming",
            "extract": "Dynamic programming is both a mathematical optimization method and an algorithmic paradigm. " * 20,
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Dynamic_programming"}}}


CFG = {"model": "claude-opus-5-5", "effort": "medium", "compact_at": 12000}


@pytest.fixture
def state(tmp_path):
    return tmp_path / "state"
