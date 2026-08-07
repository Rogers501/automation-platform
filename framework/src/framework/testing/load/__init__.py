"""Load-testing scenario, metrics, shapes, assertions, and data-provider primitives.

This module is Locust-agnostic: it provides serializable scenario models
(YAML-driven), latency percentile computation, load-profile shapes (ramp-up
patterns), SLA assertions, and a template-based data provider (Faker/CSV).
The actual Locust integration lives in a separate loadtest project that
imports these primitives (rule 11: framework does not depend on locust).
"""

from framework.testing.load.assertions import (
    AssertionOperator,
    AssertionResult,
    LoadAssertion,
    evaluate_assertions,
    report_assertions,
)
from framework.testing.load.data_provider import (
    DataProvider,
    DataProviderError,
    resolve_templates,
)
from framework.testing.load.metrics import LatencyStats, LoadMetrics
from framework.testing.load.report import (
    LoadReportData,
    ReportEntry,
    TimeSeriesPoint,
    generate_html_report,
)
from framework.testing.load.scenario import (
    LoadScenario,
    LoadStep,
    ScenarioError,
    load_scenarios,
)
from framework.testing.load.shapes import (
    LoadProfile,
    LoadProfileError,
    RampStage,
    load_profile,
)

__all__ = [
    "AssertionOperator",
    "AssertionResult",
    "DataProvider",
    "DataProviderError",
    "LatencyStats",
    "LoadAssertion",
    "LoadMetrics",
    "LoadProfile",
    "LoadProfileError",
    "LoadReportData",
    "LoadScenario",
    "LoadStep",
    "RampStage",
    "ReportEntry",
    "ScenarioError",
    "TimeSeriesPoint",
    "evaluate_assertions",
    "generate_html_report",
    "load_profile",
    "load_scenarios",
    "report_assertions",
    "resolve_templates",
]
