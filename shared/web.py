"""External internet tool: a short topic explanation from Wikipedia.

Two requests: opensearch to resolve the best article title, then the REST summary.
Results are trimmed to a few hundred characters and cached in the state dir, so a
repeated question costs neither a network call nor extra tokens.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from shared.store import DomainError, StudyStore

UA = "study-compass/1.0 (course exercise; contact: student)"
MAX_CHARS = 600


def _get_json(url: str, timeout: float = 10.0):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def lookup(topic: str, lang: str = "en", fetch=_get_json) -> dict:
    topic = topic.strip()
    if not topic:
        raise DomainError("topic is empty")
    if lang not in ("en", "he"):
        raise DomainError("lang must be 'en' or 'he'")
    base = f"https://{lang}.wikipedia.org"
    try:
        hits = fetch(f"{base}/w/api.php?action=opensearch&limit=1&format=json&search="
                     + urllib.parse.quote(topic))
        if not hits or len(hits) < 2 or not hits[1]:
            raise DomainError(f"no article found for {topic!r} on {lang}.wikipedia")
        title = hits[1][0]
        page = fetch(f"{base}/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_")))
    except DomainError:
        raise
    except Exception as e:  # network, HTTP, JSON - reported to the model as is_error
        raise DomainError(f"web lookup failed: {type(e).__name__}: {e}")
    text = " ".join((page.get("extract") or "").split())
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rsplit(" ", 1)[0] + "…"
    url = page.get("content_urls", {}).get("desktop", {}).get("page", f"{base}/wiki/{title}")
    return {"title": page.get("title", title), "summary": text, "url": url}


def cached_lookup(store: StudyStore, topic: str, lang: str = "en", fetch=_get_json) -> tuple[dict, bool]:
    cache = store.web_cache()
    key = f"{lang}:{topic.strip().lower()}"
    if key in cache:
        return cache[key], True
    result = lookup(topic, lang, fetch)
    cache[key] = result
    store.save_web_cache(cache)
    return result, False
