"""Tiny disk-backed TTL cache with single-flight fetching and stale fallback.

Why: Alpha Vantage's free tier allows ~25 calls/day, so every response is
reused as long as possible and survives restarts. If a refresh fails (quota
exhausted, network error) the last good value is served instead of nothing.
"""
import hashlib
import json
import os
import threading
import time
from typing import Any, Callable, Optional

from ..config import CACHE_DIR

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_memory: dict[str, tuple[float, Any]] = {}
_failed_at: dict[str, float] = {}
FAILURE_BACKOFF = 15 * 60  # don't retry a failing upstream on every page load


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def _path(key: str) -> str:
    digest = hashlib.sha1(key.encode()).hexdigest()[:20]
    return os.path.join(CACHE_DIR, f"{digest}.json")


def _read(key: str) -> Optional[tuple[float, Any]]:
    if key in _memory:
        return _memory[key]
    try:
        with open(_path(key), "r", encoding="utf-8") as f:
            payload = json.load(f)
        entry = (payload["ts"], payload["value"])
        _memory[key] = entry
        return entry
    except (OSError, ValueError, KeyError):
        return None


def _write(key: str, value: Any) -> None:
    entry = (time.time(), value)
    _memory[key] = entry
    tmp = _path(key) + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"key": key, "ts": entry[0], "value": value}, f)
        os.replace(tmp, _path(key))
    except OSError as e:  # read-only FS etc. — memory cache still works
        print(f"[CACHE] Could not persist {key}: {e}")


def put(key: str, value: Any) -> None:
    _write(key, value)


def get(key: str, ttl: float) -> Optional[Any]:
    entry = _read(key)
    if entry and time.time() - entry[0] < ttl:
        return entry[1]
    return None


def get_or_fetch(key: str, ttl: float, fetch: Callable[[], Any], allow_stale: bool = True) -> Any:
    """Return a fresh cached value, or call ``fetch`` (once, even under
    concurrency). ``None``/empty results are not cached; the stale value is
    returned instead when ``allow_stale``."""
    fresh = get(key, ttl)
    if fresh is not None:
        return fresh
    with _lock_for(key):
        fresh = get(key, ttl)  # another thread may have filled it
        if fresh is not None:
            return fresh
        value = None
        if time.time() - _failed_at.get(key, 0) > FAILURE_BACKOFF:
            try:
                value = fetch()
            except Exception as e:
                print(f"[CACHE] fetch for {key} failed: {type(e).__name__}: {e}")
            if value:
                _failed_at.pop(key, None)
                _write(key, value)
                return value
            _failed_at[key] = time.time()
        if allow_stale:
            stale = _read(key)
            if stale:
                return stale[1]
        return value


def age_seconds(key: str) -> Optional[float]:
    entry = _read(key)
    return time.time() - entry[0] if entry else None
