"""Unit tests for the per-user rate limiter service (T040)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from src.services.rate_limiter import RateLimiter


class TestRateLimiter:
    """Rate limiter unit tests."""

    @pytest.mark.asyncio
    async def test_allows_requests_under_limit(self) -> None:
        """Requests within the limit should succeed."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            remaining = await limiter.check_rate_limit("user-1")
            assert remaining >= 0

    @pytest.mark.asyncio
    async def test_blocks_requests_over_limit(self) -> None:
        """21st request within the window should raise."""
        limiter = RateLimiter(max_requests=20, window_seconds=60)
        for _ in range(20):
            await limiter.check_rate_limit("user-1")

        with pytest.raises(Exception, match="rate.limit"):
            await limiter.check_rate_limit("user-1")

    @pytest.mark.asyncio
    async def test_sliding_window_reset(self) -> None:
        """Requests outside the time window should be discarded."""
        limiter = RateLimiter(max_requests=2, window_seconds=1)
        await limiter.check_rate_limit("user-1")
        await limiter.check_rate_limit("user-1")

        # Simulate window expiry
        import time

        with patch("time.time", return_value=time.time() + 2):
            remaining = await limiter.check_rate_limit("user-1")
            assert remaining >= 0

    @pytest.mark.asyncio
    async def test_per_user_isolation(self) -> None:
        """Each user has an independent rate limit bucket."""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        await limiter.check_rate_limit("user-a")

        # user-a is exhausted
        with pytest.raises(Exception, match="rate.limit"):
            await limiter.check_rate_limit("user-a")

        # user-b is fine
        remaining = await limiter.check_rate_limit("user-b")
        assert remaining >= 0

    @pytest.mark.asyncio
    async def test_concurrent_access_safety(self) -> None:
        """Concurrent calls should not exceed the limit."""
        limiter = RateLimiter(max_requests=10, window_seconds=60)

        results: list[bool] = []

        async def try_request() -> None:
            try:
                await limiter.check_rate_limit("user-concurrent")
                results.append(True)
            except Exception:
                results.append(False)

        # Launch 15 concurrent requests (limit is 10)
        await asyncio.gather(*[try_request() for _ in range(15)])

        assert results.count(True) == 10
        assert results.count(False) == 5
