"""Simple in-memory fixed-window rate limiter (single-process).

Keyed by a caller string (e.g. "jd:123"). Window is 60 seconds. This is
adequate for the current --workers 1 deployment; a multi-process setup would
move to Redis.

The internal key table is swept so abandoned keys don't grow unbounded.
"""
import time
from collections import defaultdict

_WINDOW_SECONDS = 60.0
_SWEEP_THRESHOLD = 1024  # start amortized cleanup once this many keys exist


class RateLimiter:
    def __init__(self):
        self._hits: dict[str, list[float]] = defaultdict(list)

    def _sweep(self, now: float) -> None:
        cutoff = now - _WINDOW_SECONDS
        for k in list(self._hits):
            hits = self._hits[k]
            if not hits or hits[-1] <= cutoff:
                del self._hits[k]

    def allow(self, key: str, limit: int) -> bool:
        """Return True if the call is within the limit for the current window."""
        now = time.time()
        cutoff = now - _WINDOW_SECONDS
        hits = [t for t in self._hits.get(key, []) if t > cutoff]
        if not hits:
            # New key or expired window → start a fresh window and allow.
            self._hits[key] = [now]
            self._maybe_sweep(now)
            return True
        if len(hits) >= limit:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        self._maybe_sweep(now)
        return True

    def _maybe_sweep(self, now: float) -> None:
        if len(self._hits) > _SWEEP_THRESHOLD:
            self._sweep(now)


# Global singleton
rate_limiter = RateLimiter()
