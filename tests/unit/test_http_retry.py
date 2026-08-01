"""Unit tests for the HTTP retry policy."""

from __future__ import annotations

import random

from framework.clients.http.retry import RetryPolicy


def test_defaults() -> None:
    """Defaults: 3 attempts, idempotent verbs, 5xx + 429."""
    p = RetryPolicy()
    assert p.max_attempts == 3
    assert "GET" in p.retry_methods
    assert "POST" not in p.retry_methods
    assert 503 in p.retry_statuses
    assert 200 not in p.retry_statuses


def test_should_retry_method_case_insensitive() -> None:
    """Method matching is case-insensitive."""
    p = RetryPolicy()
    assert p.should_retry_method("get") is True
    assert p.should_retry_method("GET") is True
    assert p.should_retry_method("post") is False


def test_should_retry_status() -> None:
    """Status matching checks membership."""
    p = RetryPolicy()
    assert p.should_retry_status(429) is True
    assert p.should_retry_status(503) is True
    assert p.should_retry_status(404) is False


def test_attempts_exhausted() -> None:
    """attempts_exhausted flags the last allowed attempt."""
    p = RetryPolicy(max_attempts=3)
    assert p.attempts_exhausted(1) is False
    assert p.attempts_exhausted(2) is False
    assert p.attempts_exhausted(3) is True
    assert p.attempts_exhausted(4) is True


def test_compute_delay_retry_after_honored() -> None:
    """A server Retry-After overrides backoff (clamped to max_backoff)."""
    p = RetryPolicy(max_backoff=30.0)
    assert p.compute_delay(1, retry_after=5.0) == 5.0
    assert p.compute_delay(1, retry_after=100.0) == 30.0
    assert p.compute_delay(1, retry_after=-1.0) == 0.0


def test_compute_delay_exponential_without_jitter() -> None:
    """Backoff doubles per attempt; jitter stays within 10% of the cap."""
    random.seed(0)
    p = RetryPolicy(backoff_factor=1.0, max_backoff=30.0)
    for attempt in range(1, 5):
        delay = p.compute_delay(attempt)
        base = min(1.0 * (2 ** (attempt - 1)), 30.0)
        assert base <= delay <= base + base * 0.1


def test_compute_delay_capped() -> None:
    """The computed delay never exceeds max_backoff."""
    random.seed(0)
    p = RetryPolicy(backoff_factor=100.0, max_backoff=5.0)
    assert p.compute_delay(10) <= 5.0 + 0.5


def test_compute_delay_zero_backoff() -> None:
    """A zero backoff factor yields a zero delay (fast retries in tests)."""
    p = RetryPolicy(backoff_factor=0.0)
    assert p.compute_delay(1) == 0.0


def test_custom_policy_from_lists() -> None:
    """RetryPolicy accepts frozenset construction for runtime overrides."""
    p = RetryPolicy(
        max_attempts=5,
        retry_statuses=frozenset({418}),
        retry_methods=frozenset({"POST"}),
    )
    assert p.max_attempts == 5
    assert p.should_retry_status(418) is True
    assert p.should_retry_method("POST") is True
    assert p.should_retry_method("GET") is False
