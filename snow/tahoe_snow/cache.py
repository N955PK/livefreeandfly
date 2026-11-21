"""Fetch with an on-disk cache, so nothing is requested twice."""
import hashlib
import json
import time
from pathlib import Path

import requests

from tahoe_snow.config import RAW, USER_AGENT

_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = USER_AGENT
# Every request that went over the network in this process: (url, params, "ok" or "limited", cost), where cost is
# what the service says it charged for the request (its X-RateLimit-Cost header), or None when it does not say.
REQUESTS: list = []


def _path(kind: str, url: str, params: dict | None, suffix: str) -> Path:
    key = hashlib.sha1((url + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()[:20]
    return RAW / kind / f"{key}{suffix}"


def get_text(kind: str, url: str, params: dict | None = None, max_age_h: float | None = None,
             timeout: float = 120, retries: int = 4, suffix: str = ".txt") -> str:
    """Return the response body, from cache when present and fresh.

    ``max_age_h=None`` means a cached copy never expires (archived data).
    When the fetch fails and a stale copy exists, the stale copy is returned.
    """
    path = _path(kind, url, params, suffix)
    if path.exists():
        age_h = (time.time() - path.stat().st_mtime) / 3600
        if max_age_h is None or age_h <= max_age_h:
            return path.read_text()
    error = None
    for attempt in range(retries):
        try:
            resp = _SESSION.get(url, params=params, timeout=timeout)
            if resp.status_code == 429:
                REQUESTS.append((url, params, "limited", None))
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} from {url}")
            resp.raise_for_status()
            cost = resp.headers.get("X-RateLimit-Cost")
            REQUESTS.append((url, params, "ok", float(cost) if cost else None))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(resp.text)
            return resp.text
        except requests.RequestException as exc:
            error = exc
            time.sleep(2 ** attempt * 2)
    if path.exists():
        return path.read_text()
    raise RuntimeError(f"fetch failed: {url} {params}: {error}")


def get_json(kind: str, url: str, params: dict | None = None, max_age_h: float | None = None, **kw):
    """The reply as JSON. A reply that is not JSON (an error page, half a body) is thrown out of the cache and asked
    for once more: kept, it would be handed back on every run until it aged out."""
    for attempt in (1, 2):
        text = get_text(kind, url, params, max_age_h, suffix=".json", **kw)
        try:
            return json.loads(text)
        except ValueError:
            _path(kind, url, params, ".json").unlink(missing_ok=True)
            if attempt == 2:
                raise
