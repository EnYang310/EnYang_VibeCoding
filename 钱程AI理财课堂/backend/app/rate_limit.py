from __future__ import annotations

from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, *, limit: int, window_seconds: int, max_keys: int = 1024) -> None:
        self.limit = max(1, limit)
        self.window_seconds = max(1, window_seconds)
        self.max_keys = max(1, max_keys)
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def _prune_stale_keys(self, *, now: float) -> None:
        cutoff = now - self.window_seconds
        for existing_key, existing_events in list(self._events.items()):
            while existing_events and existing_events[0] <= cutoff:
                existing_events.popleft()
            if not existing_events:
                self._events.pop(existing_key, None)

    def allow(self, key: str, *, now: float) -> bool:
        if key not in self._events and len(self._events) >= self.max_keys:
            self._prune_stale_keys(now=now)
            if len(self._events) >= self.max_keys:
                return False
        events = self._events[key]
        cutoff = now - self.window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= self.limit:
            return False
        events.append(now)
        return True
