import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    """In-process, in-memory limiter. Good enough for a single-process deployment
    and closes the "no rate limiting on login" gap documented in
    docs/threat-model.md — but it does NOT survive a process restart and does NOT
    coordinate across multiple server processes/replicas. A production multi-replica
    deployment needs a shared store (e.g. Redis) instead; that's a real gap, not
    silently claimed to be solved here."""

    def __init__(self, *, max_events: int, window_seconds: float):
        self._max_events = max_events
        self._window_seconds = window_seconds
        self._lock = threading.Lock()
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] > self._window_seconds:
                events.popleft()
            if len(events) >= self._max_events:
                return False
            events.append(now)
            return True


# 10 attempts per 5 minutes per (ip, email) pair — generous enough for a real user
# who mistypes a password a few times, tight enough to blunt credential stuffing.
login_rate_limiter = SlidingWindowRateLimiter(max_events=10, window_seconds=300)
