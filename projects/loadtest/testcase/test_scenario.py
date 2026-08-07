"""Unit tests for scenario loading and metrics (no Locust needed)."""

from __future__ import annotations

from framework.testing.load import LatencyStats, LoadMetrics, load_scenarios


def test_load_scenarios_from_test_env() -> None:
    """Scenarios load from scenarios/test/login.yaml and validate."""
    scenarios = load_scenarios("scenarios/test/login.yaml")
    assert len(scenarios) == 2
    assert scenarios[0].name == "login_page_view"
    assert scenarios[0].weight == 5
    assert len(scenarios[0].steps) == 1
    assert scenarios[1].name == "login_submit"
    assert len(scenarios[1].steps) == 2


def test_load_scenarios_from_uat_env() -> None:
    """Scenarios load from scenarios/uat/login.yaml and validate."""
    scenarios = load_scenarios("scenarios/uat/login.yaml")
    assert len(scenarios) == 2
    assert scenarios[1].steps[1].method == "POST"


def test_load_scenarios_from_cost_env() -> None:
    """Cost calculation scenario loads from scenarios/cost/cost_calculate.yaml."""
    scenarios = load_scenarios("scenarios/cost/cost_calculate.yaml")
    assert len(scenarios) == 1
    assert scenarios[0].name == "cost_calculate"
    assert scenarios[0].weight == 1
    assert len(scenarios[0].steps) == 1
    step = scenarios[0].steps[0]
    assert step.method == "POST"
    assert "comCostAndWeight" in step.url
    assert scenarios[0].headers.get("authtoken") == "17f718ef5e0d4f108a66cc57c239dd01"
    # JSON body should have CSV templates with type casts.
    assert step.json_body is not None
    assert step.json_body["waybillId"] == "{{csv.cost_data.waybillId}}"
    assert step.json_body["productTypeId"] == "{{int:csv.cost_data.productTypeId}}"
    assert step.json_body["number"] == "{{float:csv.cost_data.number}}"
    # Fixed values.
    assert step.json_body["serviceMethodCode"] == "01"
    assert step.json_body["customerId"] == 1965
    assert step.json_body["smMode"] == 2


def test_latency_stats_percentiles() -> None:
    """LatencyStats computes p50/p90/p99 correctly."""
    stats = LatencyStats()
    for i in range(100):
        stats.record(float(i) / 1000.0)  # 0.000 to 0.099
    assert stats.count == 100
    assert 0.04 <= stats.p50 <= 0.051
    assert 0.089 <= stats.p90 <= 0.091
    assert 0.097 <= stats.p99 <= 0.099  # nearest-rank: ceil(100*0.99)=99 -> idx 98


def test_load_metrics_aggregation() -> None:
    """LoadMetrics tracks requests, errors, and computes rates."""
    metrics = LoadMetrics(scenario_name="test")
    metrics.record(0.1, is_error=False)
    metrics.record(0.2, is_error=False)
    metrics.record(0.3, is_error=True)
    metrics.duration_seconds = 6.0
    assert metrics.total_requests == 3
    assert metrics.total_errors == 1
    assert abs(metrics.error_rate - 1 / 3) < 0.01
    assert abs(metrics.rps - 0.5) < 0.01
    d = metrics.to_dict()
    assert d["latency_ms"]["p50"] > 0
