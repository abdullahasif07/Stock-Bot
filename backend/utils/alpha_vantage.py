"""Alpha Vantage client: daily budget, 1 req/s throttle, disk cache."""
import threading
import time

import requests

from ..config import ALPHA_VANTAGE_API_KEY as API_KEY, ALPHA_VANTAGE_BASE_URL as BASE_URL
from . import cache
from .quota import alpha_vantage_budget

_throttle_lock = threading.Lock()
_last_call = 0.0
MIN_INTERVAL = 1.1  # free tier also enforces a burst limit


PREMIUM_MEMORY = 7 * 86400


def _premium_key(function: str) -> str:
    return f"av-premium:{function}"


def _check_response(data: dict, label: str, function: str) -> bool:
    for key in ("Note", "Information", "Error Message"):
        if key in data:
            print(f"[ALPHA VANTAGE] {label} -> {key}: {data[key]}")
            # Only the endpoint-specific message; the daily-limit note also mentions premium plans.
            if "premium endpoint" in str(data[key]).lower():
                # Free keys can't use this endpoint — stop spending budget on it.
                cache.put(_premium_key(function), True)
            return False
    return True


def raw_request(params: dict, label: str) -> requests.Response | None:
    """Low-level call. Consumes one unit of the daily budget."""
    global _last_call
    if not API_KEY:
        return None
    if cache.get(_premium_key(params.get("function", "")), PREMIUM_MEMORY):
        return None
    if not alpha_vantage_budget.try_consume():
        print(f"[ALPHA VANTAGE] Daily budget exhausted, skipping {label}")
        return None
    with _throttle_lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
    try:
        resp = requests.get(BASE_URL, params={**params, "apikey": API_KEY}, timeout=15)
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        print(f"[ALPHA VANTAGE] {label} failed: {e}")
        return None


def fetch(params: dict, label: str | None = None) -> dict | None:
    """JSON request; returns parsed dict or None on any failure / limit."""
    tag = label or params.get("function", "UNKNOWN")
    resp = raw_request(params, tag)
    if resp is None:
        return None
    try:
        data = resp.json()
    except ValueError:
        print(f"[ALPHA VANTAGE] {tag} returned non-JSON")
        return None
    return data if _check_response(data, tag, params.get("function", "")) else None


def cached_fetch(params: dict, ttl: float, label: str | None = None) -> dict | None:
    key = "av:" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return cache.get_or_fetch(key, ttl, lambda: fetch(params, label))
