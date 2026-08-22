"""Simple in-memory fixed-window rate limiter (single-process).

Keyed by a caller string (e.g. "jd:123"). Window is 60 seconds. This is
adequate for the current --workers 1 deployment; a multi-process setup would
move to Redis.
"""
import time
from collections import defaultdict

_WINDOW_SECONDS = 60.0


class RateLimiter:
    def __init__(self):
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str, limit: int) -> bool:
        """Return True if the call is within the limit for the current window."""
        now = time.time()
        cutoff = now - _WINDOW_SECONDS
        hits = [t for t in self._hits[key] if t > cutoff]
        self._hits[key] = hits
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True


# Global singleton
rate_limiter = RateLimiter()
