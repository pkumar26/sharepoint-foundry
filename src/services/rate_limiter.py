"""Per-user sliding-window rate limiter (T042).

Uses an in-memory ``asyncio.Lock`` + ``collections.deque`` per user to
enforce a configurable request limit within a rolling time window.
"""

from __future__ import annotations

import logging
import time
from asyncio import Lock
from collections import deque

logger = logging.getLogger(__name__)


class RateLimitExceededError(Exception):
    """Raised when a user exceeds their rate limit."""

    def __init__(self, user_id: str, retry_after: float) -> None:
        self.user_id = user_id
        self.retry_after = retry_after
        super().__init__(f"rate limit exceeded for user {user_id}; retry after {retry_after:.0f}s")


class RateLimiter:
    """Sliding-window rate limiter backed by per-user timestamp deques.

    Args:
        max_requests: Maximum number of requests allowed per window.
        window_seconds: Rolling window duration in seconds.
    """

    def __init__(
        self,
        max_requests: int = 20,
        window_seconds: int = 60,
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque[float]] = {}
        self._locks: dict[str, Lock] = {}

    def _get_lock(self, user_id: str) -> Lock:
        if user_id not in self._locks:
            self._locks[user_id] = Lock()
        return self._locks[user_id]

    async def check_rate_limit(self, user_id: str) -> int:
        """Check and record a request for the given user.

        Args:
            user_id: Entra object-id of the requesting user.

        Returns:
            Number of remaining requests in the current window.

        Raises:
            RateLimitExceeded: When the limit has been reached.
        """
        lock = self._get_lock(user_id)
        async with lock:
            now = time.time()
            if user_id not in self._buckets:
                self._buckets[user_id] = deque()

            bucket = self._buckets[user_id]

            # Evict timestamps outside the window
            cutoff = now - self.window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= self.max_requests:
                retry_after = bucket[0] + self.window_seconds - now
                logger.warning(
                    "Rate limit exceeded",
                    extra={
                        "user_id": user_id,
                        "requests_in_window": len(bucket),
                        "retry_after_seconds": retry_after,
                    },
                )
                raise RateLimitExceededError(user_id, retry_after)

            bucket.append(now)
            remaining = self.max_requests - len(bucket)
            return remaining
