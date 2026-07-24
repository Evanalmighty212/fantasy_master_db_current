"""
mfl_client.py  (ISOLATED DIAGNOSTIC -- not wired into any production code)

Rate-limited, cached, retrying HTTP client for MyFantasyLeague's public
API and report pages. Built specifically so this investigation can
NEVER repeatedly hammer MFL's servers -- an earlier ad hoc parallel
batch attempt during the prior diagnostic pass triggered what looked
like transient rate-limiting/timeouts. This client exists to make that
impossible by construction:

- Every response is cached to disk, keyed by the exact request URL.
  A re-run of any script using this client re-reads the cache for
  anything already fetched -- nothing is ever fetched twice, and the
  whole pipeline is resumable across separate runs for exactly that
  reason.
- Requests are strictly SERIAL (no parallelism anywhere in this
  pipeline).
- A minimum delay is enforced between real network requests
  (MIN_DELAY_SECONDS), regardless of how fast the caller loops.
- Failures retry with exponential backoff (bounded), then give up and
  record the failure rather than hanging or looping forever.
"""

import hashlib
import json
import time
from pathlib import Path

import requests

CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

MIN_DELAY_SECONDS = 1.5
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 3

_last_request_time = [0.0]


def _cache_path(url: str) -> Path:
    key = hashlib.sha256(url.encode()).hexdigest()[:24]
    return CACHE_DIR / f"{key}.json"


def _throttle():
    elapsed = time.monotonic() - _last_request_time[0]
    if elapsed < MIN_DELAY_SECONDS:
        time.sleep(MIN_DELAY_SECONDS - elapsed)


def get_json(url: str, force_refresh: bool = False) -> dict:
    """Cached, rate-limited, retrying GET for a JSON endpoint. Returns
    the parsed JSON body, or {"_error": "..."} on final failure after
    retries (never raises, so a batch loop can record and continue
    rather than aborting the whole run on one bad league)."""
    cache_path = _cache_path(url)
    if cache_path.exists() and not force_refresh:
        cached = json.loads(cache_path.read_text())
        if "_error" not in cached:
            return cached
        # A previously-cached failure is retried, not treated as permanent.

    last_error = None
    for attempt in range(MAX_RETRIES):
        _throttle()
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            _last_request_time[0] = time.monotonic()
            resp.raise_for_status()
            data = resp.json()
            cache_path.write_text(json.dumps(data))
            return data
        except Exception as e:
            last_error = str(e)
            _last_request_time[0] = time.monotonic()
            if attempt < MAX_RETRIES - 1:
                time.sleep(BACKOFF_BASE_SECONDS * (2 ** attempt))

    result = {"_error": last_error, "_url": url}
    cache_path.write_text(json.dumps(result))
    return result


def get_html(url: str, force_refresh: bool = False) -> str:
    """Same caching/throttling/retry contract as get_json, for the
    report HTML pages (which aren't JSON)."""
    cache_path = _cache_path(url + "::html")
    if cache_path.exists() and not force_refresh:
        cached = json.loads(cache_path.read_text())
        if "_error" not in cached:
            return cached["html"]

    last_error = None
    for attempt in range(MAX_RETRIES):
        _throttle()
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            _last_request_time[0] = time.monotonic()
            resp.raise_for_status()
            cache_path.write_text(json.dumps({"html": resp.text}))
            return resp.text
        except Exception as e:
            last_error = str(e)
            _last_request_time[0] = time.monotonic()
            if attempt < MAX_RETRIES - 1:
                time.sleep(BACKOFF_BASE_SECONDS * (2 ** attempt))

    cache_path.write_text(json.dumps({"_error": last_error, "_url": url}))
    raise RuntimeError(f"Failed to fetch {url} after {MAX_RETRIES} attempts: {last_error}")


def cache_stats() -> dict:
    files = list(CACHE_DIR.glob("*.json"))
    errors = 0
    for f in files:
        try:
            if "_error" in json.loads(f.read_text()):
                errors += 1
        except Exception:
            pass
    return {"total_cached": len(files), "cached_errors": errors}
