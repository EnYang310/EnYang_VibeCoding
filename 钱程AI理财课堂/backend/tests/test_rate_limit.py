from app.rate_limit import SlidingWindowLimiter


def test_chat_rate_limiter_blocks_only_after_the_configured_window_is_full():
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
    assert limiter.allow("visitor", now=100.0) is True
    assert limiter.allow("visitor", now=101.0) is True
    assert limiter.allow("visitor", now=102.0) is False
    assert limiter.allow("another", now=102.0) is True
    assert limiter.allow("visitor", now=161.1) is True


def test_chat_rate_limiter_prunes_stale_visitors():
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60, max_keys=2)
    assert limiter.allow("old-a", now=0.0) is True
    assert limiter.allow("old-b", now=0.0) is True
    assert limiter.allow("current", now=61.0) is True
    assert set(limiter._events) == {"current"}
