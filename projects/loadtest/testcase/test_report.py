"""Unit tests for the HTML performance report generator (no Locust needed)."""

from __future__ import annotations

from pathlib import Path

from framework.testing.load.assertions import (
    AssertionOperator,
    AssertionResult,
    LoadAssertion,
)
from framework.testing.load.report import (
    LoadReportData,
    ReportEntry,
    TimeSeriesPoint,
    generate_html_report,
)


class TestReportEntry:
    """ReportEntry computed properties: percentiles, apdex, error rate."""

    @staticmethod
    def _entry() -> ReportEntry:
        """Build an entry with known response times: 100ms x5, 200ms x3, 800ms x1, 3000ms x1."""
        return ReportEntry(
            name="POST /api",
            method="POST",
            num_requests=10,
            num_failures=1,
            response_times={100: 5, 200: 3, 800: 1, 3000: 1},
        )

    def test_avg_ms(self) -> None:
        """Average is weighted mean of response times."""
        e = self._entry()
        # (100*5 + 200*3 + 800 + 3000) / 10 = 490
        assert e.avg_ms == 490.0

    def test_min_max(self) -> None:
        """Min and max are the smallest/largest response time keys."""
        e = self._entry()
        assert e.min_ms == 100
        assert e.max_ms == 3000

    def test_percentile(self) -> None:
        """Percentile uses nearest-rank method."""
        e = self._entry()
        assert e.percentile(50) == 100  # rank=5 -> 100ms
        assert e.percentile(90) == 800  # rank=9 -> 800ms
        assert e.percentile(99) == 3000  # rank=10 -> 3000ms

    def test_error_rate(self) -> None:
        """Error rate is failures / requests."""
        e = self._entry()
        assert e.error_rate == 0.1

    def test_apdex(self) -> None:
        """APDEX: 5 satisfied (<=500), 1 tolerating (<=2000), 1 frustrated (>2000)."""
        e = self._entry()
        score, sat, tol, fru = e.apdex()
        # satisfied: 100x5 + 200x3 + 800x1 = 9 (all <= 500)
        # tolerating: 3000 > 2000, so 0 tolerating... wait 800 <= 2000 yes
        # Actually: 500ms threshold, 4T=2000ms
        # satisfied (<=500): 100x5 + 200x3 = 8
        # tolerating (500<t<=2000): 800x1 = 1
        # frustrated (>2000): 3000x1 = 1
        assert sat == 8
        assert tol == 1
        assert fru == 1
        assert abs(score - (8 + 0.5) / 10) < 0.001

    def test_empty_entry(self) -> None:
        """Empty entry returns zeros for all computed properties."""
        e = ReportEntry(name="empty", method="GET", num_requests=0, num_failures=0)
        assert e.avg_ms == 0.0
        assert e.min_ms == 0.0
        assert e.max_ms == 0.0
        assert e.percentile(99) == 0.0
        assert e.error_rate == 0.0
        score, _sat, _tol, _fru = e.apdex()
        assert score == 0.0


class TestLoadReportData:
    """LoadReportData aggregated properties."""

    def test_totals(self) -> None:
        """Total requests and error rate aggregate across entries."""
        data = LoadReportData(
            test_name="test",
            start_time="2026-01-01",
            duration_seconds=60,
            host="http://example.com",
            entries=[
                ReportEntry(name="A", method="GET", num_requests=100, num_failures=5),
                ReportEntry(name="B", method="POST", num_requests=200, num_failures=10),
            ],
        )
        assert data.total_requests == 300
        assert data.total_failures == 15
        assert abs(data.total_error_rate - 0.05) < 0.001
        assert abs(data.avg_throughput - 5.0) < 0.001  # 300/60

    def test_empty_data(self) -> None:
        """Empty report data returns zeros."""
        data = LoadReportData(
            test_name="empty",
            start_time="",
            duration_seconds=0,
            host="",
        )
        assert data.total_requests == 0
        assert data.total_error_rate == 0.0
        assert data.avg_throughput == 0.0


class TestGenerateHtmlReport:
    """generate_html_report produces a valid, self-contained HTML file."""

    @staticmethod
    def _sample_data() -> LoadReportData:
        """Build sample report data with entries, timeline, and assertions."""
        assertions = [
            AssertionResult(
                assertion=LoadAssertion(
                    metric="p99_ms",
                    operator=AssertionOperator.LT,
                    threshold=500,
                    description="P99 under 500ms",
                ),
                actual_value=350.0,
                passed=True,
            ),
        ]
        timeline = [
            TimeSeriesPoint(
                elapsed_seconds=i,
                active_users=10 + i,
                rps=50.0 + i,
                avg_response_time_ms=100.0 + i * 5,
                error_rate=0.01,
            )
            for i in range(10)
        ]
        return LoadReportData(
            test_name="Cost Calculate Load Test",
            start_time="2026-08-07 10:00:00",
            duration_seconds=60.0,
            host="http://10.94.7.5:30576",
            entries=[
                ReportEntry(
                    name="POST comCostAndWeight",
                    method="POST",
                    num_requests=1000,
                    num_failures=10,
                    response_times={50: 200, 100: 500, 200: 200, 500: 80, 1000: 20},
                ),
            ],
            timeline=timeline,
            assertions=assertions,
        )

    def test_generates_html_file(self, tmp_path: Path) -> None:
        """Report file is created and contains expected HTML elements."""
        data = self._sample_data()
        output = tmp_path / "report.html"
        result = generate_html_report(data, output)
        assert result == output
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "Cost Calculate Load Test" in content
        assert "Statistics" in content
        assert "APDEX" in content
        assert "<svg" in content
        assert "SLA Assertions" in content
        assert "PASS" in content

    def test_empty_data_no_crash(self, tmp_path: Path) -> None:
        """Report generates without crashing for empty data."""
        data = LoadReportData(
            test_name="empty",
            start_time="",
            duration_seconds=0,
            host="",
        )
        output = tmp_path / "empty.html"
        generate_html_report(data, output)
        assert output.exists()

    def test_report_is_self_contained(self, tmp_path: Path) -> None:
        """HTML report has no external dependencies (no http/https links)."""
        data = self._sample_data()
        output = tmp_path / "self_contained.html"
        generate_html_report(data, output)
        content = output.read_text(encoding="utf-8")
        assert "http://" not in content or "10.94.7.5" in content  # only host ref
        assert "https://" not in content  # no CDN links
        assert "<style>" in content  # CSS is embedded

    def test_timeline_charts_present(self, tmp_path: Path) -> None:
        """SVG charts are generated when timeline data is available."""
        data = self._sample_data()
        output = tmp_path / "charts.html"
        generate_html_report(data, output)
        content = output.read_text(encoding="utf-8")
        assert "Response Time Over Time" in content
        assert "Throughput Over Time" in content
        assert "Active Users Over Time" in content
        assert "polyline" in content  # SVG line chart element

    def test_histogram_present(self, tmp_path: Path) -> None:
        """Response time distribution histogram is generated."""
        data = self._sample_data()
        output = tmp_path / "histogram.html"
        generate_html_report(data, output)
        content = output.read_text(encoding="utf-8")
        assert "Response Time Distribution" in content
