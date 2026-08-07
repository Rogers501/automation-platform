"""Post-run SLA assertions for load tests.

Evaluate threshold conditions against :class:`LoadMetrics` after a run.
Each assertion has a metric name, a comparison operator, and a threshold
value. Results are collected and can be attached to Allure.

YAML example::

    assertions:
      - metric: p99_ms
        operator: lt
        threshold: 500
        description: "P99 latency under 500ms"
      - metric: error_rate
        operator: lt
        threshold: 0.01
        description: "Error rate under 1%"
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from framework.reporting.allure import attach_json

__all__ = [
    "AssertionOperator",
    "AssertionResult",
    "LoadAssertion",
    "evaluate_assertions",
    "report_assertions",
]


class AssertionOperator(StrEnum):
    """Supported comparison operators."""

    EQ = "eq"
    NE = "ne"
    LT = "lt"
    LE = "le"
    GT = "gt"
    GE = "ge"

    def compare(self, actual: float, threshold: float) -> bool:
        """Return True if actual <op> threshold holds."""
        match self:
            case AssertionOperator.EQ:
                return actual == threshold
            case AssertionOperator.NE:
                return actual != threshold
            case AssertionOperator.LT:
                return actual < threshold
            case AssertionOperator.LE:
                return actual <= threshold
            case AssertionOperator.GT:
                return actual > threshold
            case AssertionOperator.GE:
                return actual >= threshold


_METRIC_KEYS = {
    "total_requests",
    "total_errors",
    "error_rate",
    "rps",
    "duration_seconds",
}

_LATENCY_KEYS = {
    "min_ms",
    "avg_ms",
    "p50_ms",
    "p90_ms",
    "p95_ms",
    "p99_ms",
    "max_ms",
}


class LoadAssertion(BaseModel):
    """A single SLA assertion.

    Attributes:
        metric: Metric name (e.g. p99_ms, error_rate, rps).
        operator: Comparison operator (eq/ne/lt/le/gt/ge).
        threshold: Threshold value to compare against.
        description: Human-readable description.
    """

    model_config = ConfigDict(extra="ignore")

    metric: str
    operator: AssertionOperator = AssertionOperator.LT
    threshold: float
    description: str = ""


class AssertionResult(BaseModel):
    """Result of evaluating one assertion against actual metrics.

    Attributes:
        assertion: The original assertion spec.
        actual_value: The extracted metric value.
        passed: Whether the assertion passed.
    """

    model_config = ConfigDict(extra="ignore")

    assertion: LoadAssertion
    actual_value: float
    passed: bool


def _extract_metric(metrics_dict: dict[str, Any], metric_name: str) -> float:
    """Extract a metric value from a LoadMetrics.to_dict() output.

    Supports top-level metrics (error_rate, rps, ...) and latency sub-metrics
    (p99_ms, avg_ms, ...) which are nested under latency_ms.
    """
    if metric_name in _METRIC_KEYS:
        return float(metrics_dict.get(metric_name, 0.0))
    if metric_name in _LATENCY_KEYS:
        latency = metrics_dict.get("latency_ms", {})
        return float(latency.get(metric_name.replace("_ms", ""), 0.0))
    raise KeyError(f"unknown metric: {metric_name}")


def evaluate_assertions(
    assertions: list[LoadAssertion],
    metrics_dict: dict[str, Any],
) -> list[AssertionResult]:
    """Evaluate all assertions against a metrics dict.

    Args:
        assertions: List of LoadAssertion to evaluate.
        metrics_dict: Output of LoadMetrics.to_dict().

    Returns:
        List of AssertionResult, one per assertion.
    """
    results: list[AssertionResult] = []
    for assertion in assertions:
        actual = _extract_metric(metrics_dict, assertion.metric)
        passed = assertion.operator.compare(actual, assertion.threshold)
        results.append(
            AssertionResult(
                assertion=assertion,
                actual_value=actual,
                passed=passed,
            )
        )
    return results


def report_assertions(results: list[AssertionResult]) -> None:
    """Attach assertion results as a JSON Allure attachment (no-op w/o allure)."""
    data = [
        {
            "metric": r.assertion.metric,
            "operator": r.assertion.operator.value,
            "threshold": r.assertion.threshold,
            "actual": r.actual_value,
            "passed": r.passed,
            "description": r.assertion.description,
        }
        for r in results
    ]
    attach_json("Load Assertions", data)
