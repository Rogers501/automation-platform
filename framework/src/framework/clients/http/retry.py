"""Retry policy for HTTP requests (pure decisions + delay computation).

The execution loop lives in the client, where it has full httpx context; this
module holds the declarative policy so it is trivially unit-testable.
"""

from __future__ import annotations

import random

from pydantic import BaseModel

__all__ = ["RetryPolicy"]


class RetryPolicy(BaseModel):
    """Declarative retry policy.

    Attributes:
        max_attempts: Maximum number of attempts (including the first).
        backoff_factor: Base multiplier for exponential backoff.
        max_backoff: Upper bound for any single delay.
        retry_statuses: HTTP status codes eligible for retry.
        retry_methods: HTTP methods eligible for retry (idempotent verbs).
    """

    max_attempts: int = 3
    backoff_factor: float = 0.5
    max_backoff: float = 30.0
    retry_statuses: frozenset[int] = frozenset({429, 500, 502, 503, 504})
    retry_methods: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})

    def should_retry_method(self, method: str) -> bool:
        """Whether ``method`` (case-insensitive) is eligible for retry."""
        return method.upper() in self.retry_methods

    def should_retry_status(self, status_code: int) -> bool:
        """Whether ``status_code`` is eligible for retry."""
        return status_code in self.retry_statuses

    def attempts_exhausted(self, attempt: int) -> bool:
        """Whether ``attempt`` (1-based) is the last allowed attempt."""
        return attempt >= self.max_attempts

    def compute_delay(self, attempt: int, retry_after: float | None = None) -> float:
        """Compute the sleep delay before the next attempt (seconds).

        Honors a server-provided ``Retry-After`` (clamped to ``max_backoff``);
        otherwise uses exponential backoff with up to 10% jitter.

        Args:
            attempt: The 1-based number of the attempt just completed.
            retry_after: Optional ``Retry-After`` header value in seconds.
        """
        if retry_after is not None:
            return float(min(max(retry_after, 0.0), self.max_backoff))
        base: float = self.backoff_factor * (2 ** (attempt - 1))
        capped: float = min(base, self.max_backoff)
        jitter: float = random.uniform(0.0, capped * 0.1) if capped > 0 else 0.0
        return capped + jitter
