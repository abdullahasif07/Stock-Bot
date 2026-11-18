"""Request-level protection for the public demo: optional access code and
per-IP sliding-window rate limits. In-memory, which is right for a single
instance; swap for Redis if you ever scale out."""
import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status

from .config import DEMO_ACCESS_CODE, TRUSTED_PROXY_HOPS


def client_ip(request: Request) -> str:
    """Resolve the caller's IP. Proxies append to X-Forwarded-For, so the
    trustworthy entry is the one added by our own proxy (counting from the
    right); anything to its left is client-controlled."""
    if TRUSTED_PROXY_HOPS > 0:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if parts:
                return parts[max(0, len(parts) - TRUSTED_PROXY_HOPS)]
    return request.client.host if request.client else "unknown"


def require_access_code(request: Request) -> None:
    if not DEMO_ACCESS_CODE:
        return
    supplied = request.headers.get("x-access-code", "")
    if not hmac.compare_digest(supplied.encode(), DEMO_ACCESS_CODE.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "access_code_required", "message": "This demo requires an access code."},
        )


class SlidingWindowLimiter:
    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_prune = time.monotonic()

    def hit(self, key: str, limit: int, window: float) -> float:
        """Record a hit. Returns 0 if allowed, else seconds until retry."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] >= window:
                q.popleft()
            if len(q) >= limit:
                return window - (now - q[0])
            q.append(now)
            if now - self._last_prune > 600:
                self._prune(now)
            return 0.0

    def _prune(self, now: float):
        for k in [k for k, q in self._hits.items() if not q or now - q[-1] > 86400]:
            del self._hits[k]
        self._last_prune = now

    def reset(self):
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def rate_limit(scope: str, per_minute: int | None = None, per_day: int | None = None):
    """FastAPI dependency factory: ``Depends(rate_limit("chat", 6, 40))``."""

    def dependency(request: Request, _=Depends(require_access_code)):
        ip = client_ip(request)
        for limit, window, label in ((per_minute, 60, "minute"), (per_day, 86400, "day")):
            if not limit:
                continue
            retry = limiter.hit(f"{scope}:{label}:{ip}", limit, window)
            if retry:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "code": "rate_limited",
                        "message": f"Demo limit reached ({limit} {scope} requests per {label}). "
                                   f"Try again in {int(retry) + 1}s.",
                    },
                    headers={"Retry-After": str(int(retry) + 1)},
                )

    return dependency
