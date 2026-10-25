"""The HTTP call to the Gemini REST API (generateContent). No SDK: urllib + JSON.

Retries 429/5xx with a short backoff (the free tier is rate limited).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from API.harness import logger

log = logger(__file__)
BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiClient:
    def __init__(self, api_key: str, retries: int = 4):
        self.api_key, self.retries = api_key, retries

    def generate(self, model: str, contents: list[dict], system: str | None = None,
                 tools: list[dict] | None = None, thinking_level: str | None = None,
                 max_tokens: int = 8000) -> dict:
        body: dict = {"contents": contents, "generationConfig": {"maxOutputTokens": max_tokens}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = tools
        if thinking_level:
            body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": thinking_level}
        req = urllib.request.Request(
            f"{BASE}/{model}:generateContent", data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key})
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                if e.code in (429, 500, 503) and attempt < self.retries:
                    wait = 5 * 2 ** attempt
                    log(f"HTTP {e.code}, retry in {wait}s")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"Gemini API error {e.code}: {detail}") from None
