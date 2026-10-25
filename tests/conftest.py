"""Offline test helpers: a scripted fake Gemini client - no API key, no network."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import API.harness as harness  # noqa: E402

harness.QUIET = True


def usage(inp=100, read=0, write=0, out=20):
    """Gemini usageMetadata: promptTokenCount includes the cached part."""
    return {"promptTokenCount": inp + read, "cachedContentTokenCount": read, "candidatesTokenCount": out}


def text_resp(text, **u):
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": usage(**u)}


def tool_resp(*calls, **u):
    """calls: (id, name, args) tuples -> one reply with several functionCall parts."""
    parts = [{"functionCall": {"id": i, "name": n, "args": a}, "thoughtSignature": "sig"} for i, n, a in calls]
    return {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP"}],
            "usageMetadata": usage(**u)}


class FakeClient:
    """Scripted stand-in for GeminiClient: no key, no network."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def generate(self, **kw):
        self.requests.append(kw)
        if not self.script:
            raise AssertionError("fake model ran out of scripted responses")
        return self.script.pop(0)


def fake_fetch(url):
    if "opensearch" in url:
        return ["dynamic programming", ["Dynamic programming"], [""], ["https://en.wikipedia.org/wiki/Dynamic_programming"]]
    return {"title": "Dynamic programming",
            "extract": "Dynamic programming is both a mathematical optimization method and an algorithmic paradigm. " * 20,
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Dynamic_programming"}}}


CFG = {"model": "gemini-3.6-flash", "effort": "medium", "compact_at": 12000}


@pytest.fixture
def state(tmp_path):
    return tmp_path / "state"
