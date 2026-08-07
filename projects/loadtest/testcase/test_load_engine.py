"""Unit tests for load engine primitives (no Locust needed).

Covers LoadProfile shapes, SLA assertion evaluation, and DataProvider
template resolution. All tests are pure Python with no network/DB/external
dependencies (rule 14).
"""

from __future__ import annotations

import csv
import uuid as uuid_mod
from pathlib import Path

import pytest

from framework.testing.load import (
    AssertionOperator,
    DataProvider,
    DataProviderError,
    LoadAssertion,
    LoadProfile,
    LoadProfileError,
    RampStage,
    evaluate_assertions,
    load_profile,
    resolve_templates,
)

# ---------------------------------------------------------------------------
# LoadProfile / shapes
# ---------------------------------------------------------------------------


def _make_profile() -> LoadProfile:
    """Build a 3-stage profile: ramp_up(30s) -> hold(60s) -> ramp_down(10s)."""
    return LoadProfile(
        stages=[
            RampStage(name="ramp_up", target_users=50, spawn_rate=5, duration=30),
            RampStage(name="hold", target_users=50, spawn_rate=0, duration=60),
            RampStage(name="ramp_down", target_users=0, spawn_rate=10, duration=10),
        ]
    )


class TestLoadProfile:
    """LoadProfile.tick() stage transitions and interpolation."""

    def test_ramp_up_start(self) -> None:
        """At t=0 ramp-up begins from 0 users."""
        prof = _make_profile()
        users, rate = prof.tick(0)
        assert users == 0
        assert rate == 5

    def test_ramp_up_midpoint(self) -> None:
        """Halfway through ramp-up, users are ~50% of target."""
        prof = _make_profile()
        users, rate = prof.tick(15)
        assert users == 25
        assert rate == 5

    def test_hold_stage(self) -> None:
        """During hold, users stay at target with spawn_rate 0."""
        prof = _make_profile()
        users, rate = prof.tick(60)
        assert users == 50
        assert rate == 0

    def test_ramp_down_midpoint(self) -> None:
        """Halfway through ramp-down, users are ~50% of peak."""
        prof = _make_profile()
        users, rate = prof.tick(95)
        assert users == 25
        assert rate == 10

    def test_stop_after_last_stage(self) -> None:
        """After the final stage, tick returns None to signal stop."""
        prof = _make_profile()
        assert prof.tick(100) is None

    def test_total_duration(self) -> None:
        """Total duration is the sum of all stage durations."""
        prof = _make_profile()
        assert prof.total_duration == 100

    def test_empty_profile_stops_immediately(self) -> None:
        """An empty profile signals stop on the first tick."""
        prof = LoadProfile(stages=[])
        assert prof.tick(0) is None

    def test_stop_after_last_false(self) -> None:
        """When stop_after_last is False, holds at last target indefinitely."""
        prof = LoadProfile(
            stages=[RampStage(name="up", target_users=10, spawn_rate=1, duration=5)],
            stop_after_last=False,
        )
        users, rate = prof.tick(999)
        assert users == 10
        assert rate == 0.0


class TestLoadProfileLoader:
    """load_profile() YAML dict -> LoadProfile validation."""

    def test_load_from_dict_with_profile_key(self) -> None:
        """Profile nested under 'profile' key loads correctly."""
        data = {
            "profile": {
                "stages": [
                    {"name": "up", "target_users": 10, "spawn_rate": 2, "duration": 5},
                ],
            }
        }
        prof = load_profile(data)
        assert len(prof.stages) == 1
        assert prof.stages[0].target_users == 10

    def test_load_from_dict_top_level_stages(self) -> None:
        """Top-level 'stages' key (no 'profile' wrapper) loads correctly."""
        data = {
            "stages": [
                {"target_users": 5, "spawn_rate": 1, "duration": 3},
            ],
        }
        prof = load_profile(data)
        assert prof.stages[0].target_users == 5

    def test_load_invalid_raises(self) -> None:
        """Non-dict input raises LoadProfileError."""
        with pytest.raises(LoadProfileError):
            load_profile([])  # type: ignore[arg-type]

    def test_load_empty_stages_raises(self) -> None:
        """Empty stages list raises LoadProfileError."""
        with pytest.raises(LoadProfileError):
            load_profile({"stages": []})


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------


class TestAssertionOperator:
    """AssertionOperator.compare() for all six operators."""

    def test_all_operators(self) -> None:
        """Each operator returns the expected boolean for given operands."""
        assert AssertionOperator.EQ.compare(5, 5)
        assert not AssertionOperator.EQ.compare(5, 6)
        assert AssertionOperator.NE.compare(5, 6)
        assert not AssertionOperator.NE.compare(5, 5)
        assert AssertionOperator.LT.compare(4, 5)
        assert not AssertionOperator.LT.compare(5, 5)
        assert AssertionOperator.LE.compare(5, 5)
        assert not AssertionOperator.LE.compare(6, 5)
        assert AssertionOperator.GT.compare(6, 5)
        assert not AssertionOperator.GT.compare(5, 5)
        assert AssertionOperator.GE.compare(5, 5)
        assert not AssertionOperator.GE.compare(4, 5)


class TestEvaluateAssertions:
    """evaluate_assertions() against a metrics dict."""

    @staticmethod
    def _metrics_dict(
        p99: float = 300.0, error_rate: float = 0.005, rps: float = 50.0
    ) -> dict[str, object]:
        return {
            "scenario": "test",
            "total_requests": 1000,
            "total_errors": 5,
            "error_rate": error_rate,
            "rps": rps,
            "duration_seconds": 20.0,
            "latency_ms": {
                "min": 10.0,
                "avg": 200.0,
                "p50": 180.0,
                "p90": 280.0,
                "p95": 320.0,
                "p99": p99,
                "max": 500.0,
            },
        }

    def test_p99_pass(self) -> None:
        """P99 below threshold passes."""
        assertions = [LoadAssertion(metric="p99_ms", operator=AssertionOperator.LT, threshold=500)]
        results = evaluate_assertions(assertions, self._metrics_dict(p99=300))
        assert len(results) == 1
        assert results[0].passed
        assert results[0].actual_value == 300.0

    def test_p99_fail(self) -> None:
        """P99 above threshold fails."""
        assertions = [LoadAssertion(metric="p99_ms", operator=AssertionOperator.LT, threshold=500)]
        results = evaluate_assertions(assertions, self._metrics_dict(p99=600))
        assert not results[0].passed

    def test_error_rate_pass(self) -> None:
        """Error rate below threshold passes."""
        assertions = [
            LoadAssertion(metric="error_rate", operator=AssertionOperator.LT, threshold=0.01)
        ]
        results = evaluate_assertions(assertions, self._metrics_dict(error_rate=0.005))
        assert results[0].passed

    def test_error_rate_fail(self) -> None:
        """Error rate above threshold fails."""
        assertions = [
            LoadAssertion(metric="error_rate", operator=AssertionOperator.LT, threshold=0.01)
        ]
        results = evaluate_assertions(assertions, self._metrics_dict(error_rate=0.05))
        assert not results[0].passed

    def test_rps_gt_pass(self) -> None:
        """RPS above threshold passes."""
        assertions = [LoadAssertion(metric="rps", operator=AssertionOperator.GT, threshold=10)]
        results = evaluate_assertions(assertions, self._metrics_dict(rps=50))
        assert results[0].passed

    def test_multiple_assertions(self) -> None:
        """Multiple assertions evaluated together return one result each."""
        assertions = [
            LoadAssertion(metric="p99_ms", operator=AssertionOperator.LT, threshold=500),
            LoadAssertion(metric="error_rate", operator=AssertionOperator.LT, threshold=0.01),
            LoadAssertion(metric="rps", operator=AssertionOperator.GT, threshold=10),
        ]
        results = evaluate_assertions(assertions, self._metrics_dict())
        assert len(results) == 3
        assert all(r.passed for r in results)

    def test_unknown_metric_raises(self) -> None:
        """Unknown metric name raises KeyError."""
        assertions = [
            LoadAssertion(metric="unknown_metric", operator=AssertionOperator.LT, threshold=1)
        ]
        with pytest.raises(KeyError):
            evaluate_assertions(assertions, self._metrics_dict())

    def test_latency_sub_metric_extraction(self) -> None:
        """Latency sub-metrics (avg_ms, p50_ms) extract correctly from nested dict."""
        assertions = [
            LoadAssertion(metric="avg_ms", operator=AssertionOperator.LT, threshold=300),
            LoadAssertion(metric="p50_ms", operator=AssertionOperator.LT, threshold=200),
        ]
        results = evaluate_assertions(assertions, self._metrics_dict())
        assert results[0].actual_value == 200.0
        assert results[1].actual_value == 180.0


# ---------------------------------------------------------------------------
# DataProvider
# ---------------------------------------------------------------------------


class TestDataProvider:
    """DataProvider template resolution."""

    def test_uuid_template(self) -> None:
        """{{uuid}} produces a valid UUID4 string."""
        provider = DataProvider()
        result = provider.resolve("{{uuid}}")
        # Should be a valid UUID.
        parsed = uuid_mod.UUID(str(result))
        assert parsed.version == 4

    def test_timestamp_template(self) -> None:
        """{{timestamp}} produces a positive integer."""
        provider = DataProvider()
        result = provider.resolve("{{timestamp}}")
        assert isinstance(result, int)
        assert result > 0

    def test_random_int_in_range(self) -> None:
        """{{random.int(min,max)}} produces a value within [min, max]."""
        provider = DataProvider(random_seed=42)
        for _ in range(100):
            result = provider.resolve("{{random.int(1,100)}}")
            assert 1 <= result <= 100

    def test_random_float_in_range(self) -> None:
        """{{random.float(min,max)}} produces a value within [min, max)."""
        provider = DataProvider(random_seed=42)
        for _ in range(100):
            result = provider.resolve("{{random.float(0,1)}}")
            assert 0 <= result < 1.0

    def test_random_choice(self) -> None:
        """{{random.choice(a,b,c)}} picks one of the listed values."""
        provider = DataProvider(random_seed=42)
        result = provider.resolve("{{random.choice(red,green,blue)}}")
        assert result in {"red", "green", "blue"}

    def test_csv_template(self, tmp_path: Path) -> None:
        """{{csv.file.column}} reads sequentially from a CSV file."""
        csv_file = tmp_path / "users.csv"
        with csv_file.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["username", "password"])
            writer.writeheader()
            writer.writerow({"username": "alice", "password": "pass1"})
            writer.writerow({"username": "bob", "password": "pass2"})

        provider = DataProvider(csv_dir=tmp_path)
        # Sequential rows, wrapping around.
        assert provider.resolve("{{csv.users.username}}") == "alice"
        assert provider.resolve("{{csv.users.username}}") == "bob"
        assert provider.resolve("{{csv.users.username}}") == "alice"

    def test_csv_missing_file_raises(self, tmp_path: Path) -> None:
        """Missing CSV file raises DataProviderError."""
        provider = DataProvider(csv_dir=tmp_path)
        with pytest.raises(DataProviderError):
            provider.resolve("{{csv.nonexistent.col}}")

    def test_csv_missing_column_raises(self, tmp_path: Path) -> None:
        """Missing column in CSV raises DataProviderError."""
        csv_file = tmp_path / "data.csv"
        with csv_file.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["a"])
            writer.writeheader()
            writer.writerow({"a": "1"})

        provider = DataProvider(csv_dir=tmp_path)
        with pytest.raises(DataProviderError):
            provider.resolve("{{csv.data.b}}")

    def test_resolve_nested_dict(self) -> None:
        """resolve() handles nested dict structures."""
        provider = DataProvider(random_seed=42)
        data = {
            "name": "{{uuid}}",
            "count": "{{random.int(1,10)}}",
            "nested": {"id": "{{uuid}}"},
        }
        result = provider.resolve(data)
        assert isinstance(result["name"], str)
        assert isinstance(result["count"], int)
        assert isinstance(result["nested"]["id"], str)

    def test_resolve_list(self) -> None:
        """resolve() handles list structures."""
        provider = DataProvider(random_seed=42)
        data = ["{{uuid}}", "{{random.int(1,5)}}"]
        result = provider.resolve(data)
        assert isinstance(result[0], str)
        assert isinstance(result[1], int)

    def test_resolve_plain_string(self) -> None:
        """Plain strings without templates are returned unchanged."""
        provider = DataProvider()
        assert provider.resolve("hello world") == "hello world"

    def test_resolve_non_string(self) -> None:
        """Non-string values (int, bool, None) are returned as-is."""
        provider = DataProvider()
        assert provider.resolve(42) == 42
        assert provider.resolve(True) is True
        assert provider.resolve(None) is None

    def test_inline_template_substitution(self) -> None:
        """Templates embedded in a larger string are substituted in place."""
        provider = DataProvider(random_seed=42)
        result = provider.resolve("order-{{random.int(100,999)}}-x")
        assert result.startswith("order-")
        assert result.endswith("-x")

    def test_unknown_template_raises(self) -> None:
        """Unknown template expression raises DataProviderError."""
        provider = DataProvider()
        with pytest.raises(DataProviderError):
            provider.resolve("{{unknown.thing}}")

    def test_reproducible_with_seed(self) -> None:
        """Same random_seed produces same sequence of random values."""
        p1 = DataProvider(random_seed=99)
        p2 = DataProvider(random_seed=99)
        assert p1.resolve("{{random.int(1,1000)}}") == p2.resolve("{{random.int(1,1000)}}")

    def test_resolve_templates_convenience(self) -> None:
        """resolve_templates() convenience function works without explicit provider."""
        result = resolve_templates({"id": "{{uuid}}"})
        assert isinstance(result["id"], str)

    def test_csv_loads_from_project_data(self) -> None:
        """CSV template reads from the loadtest project data/ directory."""
        provider = DataProvider(csv_dir=Path("data"))
        result = provider.resolve("{{csv.users.username}}")
        assert result == "01943936"


class TestDataProviderTypeCast:
    """Type-cast prefixes: int:, float:, str:."""

    def test_int_cast_csv(self, tmp_path: Path) -> None:
        """{{int:csv.file.col}} casts CSV string value to Python int."""
        csv_file = tmp_path / "data.csv"
        with csv_file.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "qty"])
            writer.writeheader()
            writer.writerow({"id": "100", "qty": "42"})

        provider = DataProvider(csv_dir=tmp_path)
        result = provider.resolve("{{int:csv.data.id}}")
        assert result == 100
        assert isinstance(result, int)

    def test_float_cast_csv(self, tmp_path: Path) -> None:
        """{{float:csv.file.col}} casts CSV string value to Python float."""
        csv_file = tmp_path / "weights.csv"
        with csv_file.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["weight"])
            writer.writeheader()
            writer.writerow({"weight": "0.5"})

        provider = DataProvider(csv_dir=tmp_path)
        result = provider.resolve("{{float:csv.weights.weight}}")
        assert result == 0.5
        assert isinstance(result, float)

    def test_int_cast_random(self) -> None:
        """{{int:random.int(1,100)}} is idempotent (already int)."""
        provider = DataProvider(random_seed=42)
        result = provider.resolve("{{int:random.int(1,100)}}")
        assert isinstance(result, int)

    def test_str_cast_uuid(self) -> None:
        """{{str:uuid}} explicitly casts to str."""
        provider = DataProvider()
        result = provider.resolve("{{str:uuid}}")
        assert isinstance(result, str)

    def test_float_cast_random_int(self) -> None:
        """{{float:random.int(1,10)}} converts int result to float."""
        provider = DataProvider(random_seed=42)
        result = provider.resolve("{{float:random.int(1,10)}}")
        assert isinstance(result, float)

    def test_type_cast_in_nested_dict(self, tmp_path: Path) -> None:
        """Type-cast templates resolve correctly inside nested dict structures."""
        csv_file = tmp_path / "records.csv"
        with csv_file.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "weight"])
            writer.writeheader()
            writer.writerow({"id": "999", "weight": "1.5"})

        provider = DataProvider(csv_dir=tmp_path)
        data = {
            "productTypeId": "{{int:csv.records.id}}",
            "weight": "{{float:csv.records.weight}}",
            "label": "{{csv.records.id}}",
        }
        result = provider.resolve(data)
        assert result["productTypeId"] == 999
        assert isinstance(result["productTypeId"], int)
        assert result["weight"] == 1.5
        assert isinstance(result["weight"], float)
        assert result["label"] == "999"
        assert isinstance(result["label"], str)
