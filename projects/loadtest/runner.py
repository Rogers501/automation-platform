"""Locust scenario runner: YAML scenarios -> Locust HttpUser tasks.

Bridges framework testing.load primitives (scenario models, metrics, load
profiles, data provider, SLA assertions) with Locust execution. Scenarios are
loaded from YAML at startup; each scenario becomes a @task on the generated
HttpUser subclass.

Key integrations:
- DataProvider: resolves {{uuid}}, {{random.int}}, {{csv.file.col}} templates
  in step fields (url/params/headers/json/data) before each request.
- LoadProfile -> LoadTestShape: YAML-driven ramp-up/hold/ramp-down stages.
- SLA assertions: evaluated against globally aggregated metrics on test_stop.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from framework.core.config import get_settings
from framework.testing.load import (
    DataProvider,
    LatencyStats,
    LoadAssertion,
    LoadMetrics,
    LoadProfile,
    LoadReportData,
    ReportEntry,
    TimeSeriesPoint,
    evaluate_assertions,
    generate_html_report,
    load_profile,
    load_scenarios,
    report_assertions,
)

# ---------------------------------------------------------------------------
# Global metrics collector (thread-safe across gevent greenlets).
# ---------------------------------------------------------------------------
_GLOBAL_LOCK = threading.Lock()
_GLOBAL_METRICS: dict[str, LoadMetrics] = {}
_EVENT_HOOKS_REGISTERED = False

# Time-series samples (collected every second during the test for charts).
_TIMELINE: list[TimeSeriesPoint] = []
_TIMELINE_RUNNING = False
_ASSERTION_RESULTS: list = []
_TEST_HOST = ""
_TEST_START_TIME = ""


def _env_base_url() -> str:
    """Resolve base_url from framework config (config/envs/<APP_ENV>.yaml)."""
    return get_settings().web.base_url or get_settings().http.base_url


def _load_profile_config() -> tuple[LoadProfile | None, list[LoadAssertion]]:
    """Load load profile and assertions from config/<LOAD_PROFILE>.yaml.

    LOAD_PROFILE env var selects the profile file (default: load_profile).
    Returns (profile, assertions). Profile is None if not configured.
    """
    profile_name = os.environ.get("LOAD_PROFILE", "load_profile")
    profile_path = Path("config") / f"{profile_name}.yaml"
    if not profile_path.exists():
        return None, []
    try:
        raw = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        logger.warning("load_profile.yaml is malformed, skipping shape")
        return None, []
    if not isinstance(raw, dict):
        return None, []

    profile: LoadProfile | None = None
    if "profile" in raw or "stages" in raw:
        try:
            profile = load_profile(raw)
        except Exception as exc:
            logger.warning(f"invalid load profile: {exc}")

    assertions = [LoadAssertion.model_validate(a) for a in raw.get("assertions", [])]
    return profile, assertions


def _merge_global_metrics(metrics: LoadMetrics) -> None:
    """Merge per-user metrics into the global collector for end-of-test assertions."""
    with _GLOBAL_LOCK:
        existing = _GLOBAL_METRICS.get(metrics.scenario_name)
        if existing is None:
            _GLOBAL_METRICS[metrics.scenario_name] = metrics
        else:
            existing.total_requests += metrics.total_requests
            existing.total_errors += metrics.total_errors
            existing.duration_seconds += metrics.duration_seconds
            for sample in metrics.latency._samples:
                existing.latency.record(sample)


# ---------------------------------------------------------------------------
# Scenario execution
# ---------------------------------------------------------------------------


def _run_scenario(self: Any, scenario: Any, provider: DataProvider) -> None:
    """Execute all steps in a scenario, collecting per-step latency.

    ``self`` is a Locust HttpUser instance with ``self.client`` (a
    Locust HttpSession that records request stats automatically).
    ``provider`` resolves {{...}} templates in step fields before sending.
    """
    metrics = LoadMetrics(scenario_name=scenario.name)
    run_start = time.perf_counter()
    step_headers = dict(scenario.headers)

    for step in scenario.steps:
        # Resolve data-provider templates in all dynamic fields.
        resolved_url = provider.resolve(step.url)
        resolved_params = provider.resolve(step.params)
        resolved_headers = provider.resolve(step.headers)
        resolved_json = provider.resolve(step.json_body)
        resolved_data = provider.resolve(step.data)

        merged_headers = {**step_headers, **(resolved_headers or {})}
        req_name = step.name or f"{step.method} {resolved_url}"
        start = time.perf_counter()
        is_error = False
        try:
            with self.client.request(
                step.method.upper(),
                resolved_url,
                name=req_name,
                params=resolved_params,
                headers=merged_headers or None,
                json=resolved_json,
                data=resolved_data,
                catch_response=True,
            ) as resp:
                elapsed = time.perf_counter() - start
                if step.expected_status and resp.status_code != step.expected_status:
                    is_error = True
                    resp.failure(f"expected {step.expected_status}, got {resp.status_code}")
                elif resp.status_code >= 400:
                    is_error = True
                    resp.failure(f"HTTP {resp.status_code}")
                else:
                    resp.success()
        except Exception:
            elapsed = time.perf_counter() - start
            is_error = True

        metrics.record(elapsed, is_error=is_error)

        if step.think_time > 0:
            time.sleep(step.think_time)
        elif scenario.think_time > 0:
            time.sleep(scenario.think_time)

    metrics.duration_seconds = time.perf_counter() - run_start
    # Merge into global collector for end-of-test SLA assertions.
    _merge_global_metrics(metrics)
    # Stash on self for on_stop() to collect per-user attachments.
    if not hasattr(self, "_metrics_list"):
        self._metrics_list = []
    self._metrics_list.append(metrics)


# ---------------------------------------------------------------------------
# Locust class builders
# ---------------------------------------------------------------------------


def build_user_class(scenario_file: str) -> type:
    """Build a Locust HttpUser subclass from a YAML scenario file.

    Each scenario becomes a @task weighted by ``scenario.weight``.
    A DataProvider is created per user class for template resolution.
    SLA assertions (if configured) are registered as event hooks.
    """
    from locust import HttpUser, between, task

    scenarios = load_scenarios(scenario_file)
    base_url = _env_base_url()
    provider = DataProvider(csv_dir=Path("data"))
    _profile, assertions = _load_profile_config()

    namespace: dict[str, Any] = {
        "host": base_url,
        "wait_time": between(1, 3),
        "_scenario_file": scenario_file,
        "on_stop": _make_on_stop(),
    }

    for scenario in scenarios:

        def make_task(scn: Any = scenario, prov: DataProvider = provider) -> Any:
            @task(scn.weight)
            def _task(self: Any) -> None:
                _run_scenario(self, scn, prov)

            return _task

        task_name = f"task_{scenario.name}"
        namespace[task_name] = make_task()

    user_class = type("JmsLoadUser", (HttpUser,), namespace)

    # Register event hooks for timeline, assertions, and HTML report.
    global _TEST_HOST
    _TEST_HOST = base_url
    _register_event_hooks(assertions)

    return user_class


def build_shape_class() -> type | None:
    """Build a Locust LoadTestShape from config/load_profile.yaml.

    Returns None if no load profile is configured (Locust falls back to
    --users / --spawn-rate CLI args).
    """
    profile, _assertions = _load_profile_config()
    if profile is None:
        return None

    from locust import LoadTestShape

    class YamlLoadTestShape(LoadTestShape):
        """Load shape driven by config/load_profile.yaml stages."""

        def tick(self) -> tuple[int, float] | None:
            """Return (user_count, spawn_rate) for current elapsed time."""
            return profile.tick(self.get_run_time())

    return YamlLoadTestShape


# ---------------------------------------------------------------------------
# Hooks: per-user Allure attachment + end-of-test SLA assertions
# ---------------------------------------------------------------------------


def _make_on_stop() -> Any:
    """Create an on_stop hook that emits Allure metrics per user."""

    def on_stop(self: Any) -> None:
        from framework.reporting.allure import attach_json

        metrics_list = getattr(self, "_metrics_list", [])
        if not metrics_list:
            return
        # Aggregate per-scenario metrics across this user run.
        per_scenario: dict[str, list[LoadMetrics]] = {}
        for m in metrics_list:
            per_scenario.setdefault(m.scenario_name, []).append(m)

        for name, runs in per_scenario.items():
            stats = LatencyStats()
            total_req = sum(r.total_requests for r in runs)
            total_err = sum(r.total_errors for r in runs)
            for r in runs:
                for sample in r.latency._samples:
                    stats.record(sample)
            agg = LoadMetrics(
                scenario_name=name,
                total_requests=total_req,
                total_errors=total_err,
                latency=stats,
                duration_seconds=sum(r.duration_seconds for r in runs),
            )
            attach_json(f"Load Metrics: {name}", agg.to_dict())

    return on_stop


def _start_timeline(environment: Any) -> None:
    """Start a gevent greenlet that samples stats every second for charts."""
    global _TIMELINE_RUNNING, _TEST_START_TIME
    _TIMELINE_RUNNING = True
    _TIMELINE.clear()
    _TEST_START_TIME = time.strftime("%Y-%m-%d %H:%M:%S")
    start = time.time()

    def _sample() -> None:
        while _TIMELINE_RUNNING:
            elapsed = time.time() - start
            total = environment.stats.total
            runner = environment.runner
            _TIMELINE.append(
                TimeSeriesPoint(
                    elapsed_seconds=elapsed,
                    active_users=runner.user_count if runner else 0,
                    rps=total.current_rps if total.num_requests > 0 else 0.0,
                    avg_response_time_ms=(
                        total.avg_response_time if total.num_requests > 0 else 0.0
                    ),
                    error_rate=total.fail_ratio,
                )
            )
            gevent.sleep(1)

    import gevent

    gevent.spawn(_sample)


def _generate_report(environment: Any, assertions: list[LoadAssertion]) -> None:
    """Build LoadReportData from Locust stats and generate HTML report."""
    global _TIMELINE_RUNNING
    _TIMELINE_RUNNING = False

    # Build per-request entries from Locust's stats.
    entries: list[ReportEntry] = []
    for (method, name), stat in environment.stats.entries.items():
        entries.append(
            ReportEntry(
                name=name,
                method=method,
                num_requests=stat.num_requests,
                num_failures=stat.num_failures,
                response_times=dict(stat.response_times),
                total_content_length=getattr(stat, "total_content_length", 0),
            )
        )

    # Evaluate assertions using Locust's aggregated stats.
    assertion_results: list = []
    if assertions:
        total = environment.stats.total
        latency = total.get_response_time_percentile
        metrics_dict: dict[str, Any] = {
            "scenario": "_aggregate_",
            "total_requests": total.num_requests,
            "total_errors": total.num_failures,
            "error_rate": total.fail_ratio,
            "rps": total.current_rps,
            "duration_seconds": _TIMELINE[-1].elapsed_seconds if _TIMELINE else 0.0,
            "latency_ms": {
                "min": total.min_response_time or 0,
                "avg": total.avg_response_time or 0,
                "p50": latency(50) if latency else 0,
                "p90": latency(90) if latency else 0,
                "p95": latency(95) if latency else 0,
                "p99": latency(99) if latency else 0,
                "max": total.max_response_time or 0,
            },
        }
        assertion_results = evaluate_assertions(assertions, metrics_dict)
        report_assertions(assertion_results)
        passed = sum(1 for r in assertion_results if r.passed)
        failed = len(assertion_results) - passed
        logger.info(f"SLA assertions: {passed} passed, {failed} failed")
        for r in assertion_results:
            status = "PASS" if r.passed else "FAIL"
            logger.info(
                f"  [{status}] {r.assertion.metric} "
                f"{r.assertion.operator.value} {r.assertion.threshold} "
                f"(actual: {r.actual_value})"
            )

    # Generate HTML report.
    duration = _TIMELINE[-1].elapsed_seconds if _TIMELINE else 0.0
    data = LoadReportData(
        test_name="Load Test Report",
        start_time=_TEST_START_TIME,
        duration_seconds=duration,
        host=_TEST_HOST,
        entries=entries,
        timeline=list(_TIMELINE),
        assertions=assertion_results,
    )

    report_path = generate_html_report(data, Path("reports/load_report.html"))
    logger.info(f"HTML report: {report_path.absolute()}")

    # Also attach to Allure.
    from framework.reporting.allure import attach_text

    attach_text("Load Test Report", str(report_path.absolute()))


def _register_event_hooks(assertions: list[LoadAssertion]) -> None:
    """Register Locust event hooks for timeline, assertions, and report.

    Hooks:
    - test_start: start time-series collector
    - quitting: evaluate assertions + generate HTML report

    Idempotent: only registers once per process (flag-guarded).
    """
    global _EVENT_HOOKS_REGISTERED
    if _EVENT_HOOKS_REGISTERED:
        return

    from locust import events

    def on_test_start(environment: Any, **kwargs: Any) -> None:
        _start_timeline(environment)

    def on_quitting(environment: Any, **kwargs: Any) -> None:
        _generate_report(environment, assertions)

    events.test_start.add_listener(on_test_start)
    events.quitting.add_listener(on_quitting)
    _EVENT_HOOKS_REGISTERED = True
