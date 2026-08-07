"""Latency and throughput metrics for load tests.

Collects per-request latencies and computes percentiles (p50/p90/p95/p99),
error rate, and throughput (RPS). Designed to be fed into Allure or any
reporting layer. Pure Python, no Locust dependency (rule 11).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from framework.reporting.allure import attach_json

__all__ = ["LatencyStats", "LoadMetrics"]


@dataclass
class LatencyStats:
    """Accumulates latency samples and computes percentiles on demand.

    Call :meth:`record` for each completed request, then read
    :attr:`p50` / :attr:`p90` / :attr:`p99` etc. after the run.
    """

    _samples: list[float] = field(default_factory=list)

    def record(self, latency_seconds: float) -> None:
        """Record a single request latency (seconds)."""
        self._samples.append(latency_seconds)

    def percentile(self, pct: float) -> float:
        """Return the *pct*-th percentile latency (0-100).

        Returns 0.0 when no samples have been recorded.
        """
        if not self._samples:
            return 0.0
        sorted_samples = sorted(self._samples)
        # Nearest-rank method (inclusive).
        rank = max(1, math.ceil(len(sorted_samples) * pct / 100.0))
        return sorted_samples[rank - 1]

    @property
    def p50(self) -> float:
        """Median latency (seconds)."""
        return self.percentile(50)

    @property
    def p90(self) -> float:
        """90th-percentile latency (seconds)."""
        return self.percentile(90)

    @property
    def p95(self) -> float:
        """95th-percentile latency (seconds)."""
        return self.percentile(95)

    @property
    def p99(self) -> float:
        """99th-percentile latency (seconds)."""
        return self.percentile(99)

    @property
    def avg(self) -> float:
        """Mean latency (seconds); 0.0 when empty."""
        if not self._samples:
            return 0.0
        return sum(self._samples) / len(self._samples)

    @property
    def min(self) -> float:
        """Minimum latency (seconds); 0.0 when empty."""
        return min(self._samples) if self._samples else 0.0

    @property
    def max(self) -> float:
        """Maximum latency (seconds); 0.0 when empty."""
        return max(self._samples) if self._samples else 0.0

    @property
    def count(self) -> int:
        """Total number of recorded samples."""
        return len(self._samples)


@dataclass
class LoadMetrics:
    """Aggregated load-test metrics for a scenario or entire run.

    Tracks total requests, errors, and latency distribution. Use
    :meth:`report` to emit an Allure JSON attachment.
    """

    scenario_name: str = ""
    total_requests: int = 0
    total_errors: int = 0
    latency: LatencyStats = field(default_factory=LatencyStats)
    duration_seconds: float = 0.0

    def record(self, latency_seconds: float, *, is_error: bool = False) -> None:
        """Record a completed request."""
        self.total_requests += 1
        if is_error:
            self.total_errors += 1
        self.latency.record(latency_seconds)

    @property
    def error_rate(self) -> float:
        """Fraction of requests that errored (0.0-1.0)."""
        if self.total_requests == 0:
            return 0.0
        return self.total_errors / self.total_requests

    @property
    def rps(self) -> float:
        """Requests per second over the run duration."""
        if self.duration_seconds <= 0:
            return 0.0
        return self.total_requests / self.duration_seconds

    def to_dict(self) -> dict[str, object]:
        """Serialize all metrics to a plain dict (for JSON / Allure)."""
        lat = self.latency
        return {
            "scenario": self.scenario_name,
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "error_rate": round(self.error_rate, 4),
            "rps": round(self.rps, 2),
            "duration_seconds": round(self.duration_seconds, 2),
            "latency_ms": {
                "min": round(lat.min * 1000, 1),
                "avg": round(lat.avg * 1000, 1),
                "p50": round(lat.p50 * 1000, 1),
                "p90": round(lat.p90 * 1000, 1),
                "p95": round(lat.p95 * 1000, 1),
                "p99": round(lat.p99 * 1000, 1),
                "max": round(lat.max * 1000, 1),
            },
        }

    def report(self, *, name: str | None = None) -> None:
        """Attach metrics as a JSON Allure attachment (no-op without allure)."""
        attach_json(name or f"Load Metrics: {self.scenario_name}", self.to_dict())
