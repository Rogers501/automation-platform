# ruff: noqa: E501
"""Self-contained HTML performance report generator (JMeter-style).

Produces a single HTML file with embedded CSS and SVG charts -- no external
dependencies, no server needed. Just open the file in a browser.

The report includes:
- Summary dashboard (total requests, failures, throughput, duration)
- Per-request statistics table (samples, avg, min, max, p50-p99, error%)
- APDEX score table (satisfied / tolerating / frustrated)
- Error details table
- SLA assertions table
- SVG charts: response time / throughput / active users over time,
  response time percentiles bar chart, distribution histogram
"""

from __future__ import annotations

import html
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

from framework.testing.load.assertions import AssertionResult

__all__ = [
    "LoadReportData",
    "ReportEntry",
    "TimeSeriesPoint",
    "generate_html_report",
]

# APDEX thresholds (milliseconds).
_APDEX_T = 500  # Satisfied: <= T
_APDEX_4T = 2000  # Tolerating: <= 4T


@dataclass
class ReportEntry:
    """Per-request-type aggregated stats for the report."""

    name: str
    method: str
    num_requests: int
    num_failures: int
    response_times: dict[int, int] = field(default_factory=dict)  # ms -> count
    total_content_length: int = 0

    @property
    def error_rate(self) -> float:
        if self.num_requests == 0:
            return 0.0
        return self.num_failures / self.num_requests

    @property
    def avg_ms(self) -> float:
        total = sum(k * v for k, v in self.response_times.items())
        return total / self.num_requests if self.num_requests else 0.0

    @property
    def min_ms(self) -> float:
        return min(self.response_times) if self.response_times else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.response_times) if self.response_times else 0.0

    def percentile(self, pct: float) -> float:
        """Return the *pct*-th percentile response time (ms)."""
        if not self.response_times:
            return 0.0
        total = sum(self.response_times.values())
        rank = max(1, math.ceil(total * pct / 100.0))
        cumulative = 0
        for ms in sorted(self.response_times):
            cumulative += self.response_times[ms]
            if cumulative >= rank:
                return float(ms)
        return float(max(self.response_times))

    def apdex(self, t: float = _APDEX_T) -> tuple[float, int, int, int]:
        """Return (score, satisfied, tolerating, frustrated)."""
        satisfied = sum(c for ms, c in self.response_times.items() if ms <= t)
        tolerating = sum(c for ms, c in self.response_times.items() if t < ms <= 4 * t)
        frustrated = sum(c for ms, c in self.response_times.items() if ms > 4 * t)
        total = satisfied + tolerating + frustrated
        if total == 0:
            return 0.0, 0, 0, 0
        score = (satisfied + tolerating / 2) / total
        return score, satisfied, tolerating, frustrated


@dataclass
class TimeSeriesPoint:
    """A single time-series sample (collected every second during the test)."""

    elapsed_seconds: float
    active_users: int
    rps: float
    avg_response_time_ms: float
    error_rate: float


@dataclass
class LoadReportData:
    """All data needed to generate the HTML report."""

    test_name: str
    start_time: str
    duration_seconds: float
    host: str
    entries: list[ReportEntry] = field(default_factory=list)
    timeline: list[TimeSeriesPoint] = field(default_factory=list)
    assertions: list[AssertionResult] = field(default_factory=list)

    @property
    def total_requests(self) -> int:
        return sum(e.num_requests for e in self.entries) if self.entries else 0

    @property
    def total_failures(self) -> int:
        return sum(e.num_failures for e in self.entries) if self.entries else 0

    @property
    def total_error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_failures / self.total_requests

    @property
    def avg_throughput(self) -> float:
        if self.duration_seconds <= 0:
            return 0.0
        return self.total_requests / self.duration_seconds

    @property
    def avg_response_time_ms(self) -> float:
        if not self.entries or self.total_requests == 0:
            return 0.0
        total_rt = sum(e.avg_ms * e.num_requests for e in self.entries)
        return total_rt / self.total_requests


# ---------------------------------------------------------------------------
# SVG chart generators (pure string building, no external deps)
# ---------------------------------------------------------------------------


def _svg_line_chart(
    series: list[tuple[float, float]],
    title: str,
    y_label: str,
    color: str = "#4A90D9",
    width: int = 800,
    height: int = 280,
) -> str:
    """Generate an SVG line chart from (x, y) data points."""
    if not series:
        return f'<div class="chart-placeholder">{title} (no data)</div>'
    margin_l, margin_r, margin_t, margin_b = 60, 20, 30, 40
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b

    x_vals = [p[0] for p in series]
    y_vals = [p[1] for p in series]
    x_min, x_max = min(x_vals), max(x_vals)
    y_min, y_max = min(y_vals), max(y_vals)
    if y_max == y_min:
        y_max = y_min + 1
    if x_max == x_min:
        x_max = x_min + 1

    def sx(x: float) -> float:
        return margin_l + (x - x_min) / (x_max - x_min) * plot_w

    def sy(y: float) -> float:
        return margin_t + plot_h - (y - y_min) / (y_max - y_min) * plot_h

    points_str = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in series)
    grid_lines = ""
    for i in range(5):
        gy = margin_t + plot_h * i / 4
        val = y_max - (y_max - y_min) * i / 4
        grid_lines += f'<line x1="{margin_l}" y1="{gy:.1f}" x2="{width - margin_r}" y2="{gy:.1f}" stroke="#e8e8e8" stroke-width="1"/>'
        grid_lines += f'<text x="{margin_l - 8}" y="{gy + 3:.1f}" text-anchor="end" font-size="10" fill="#888">{val:.1f}</text>'
    for i in range(5):
        gx = margin_l + plot_w * i / 4
        val = x_min + (x_max - x_min) * i / 4
        grid_lines += f'<text x="{gx:.1f}" y="{height - margin_b + 15}" text-anchor="middle" font-size="10" fill="#888">{val:.0f}</text>'

    return (
        f'<svg viewBox="0 0 {width} {height}" class="chart">'
        f'<text x="{width // 2}" y="15" text-anchor="middle" font-size="13" font-weight="bold" fill="#333">{html.escape(title)}</text>'
        f"{grid_lines}"
        f'<line x1="{margin_l}" y1="{margin_t}" x2="{margin_l}" y2="{margin_t + plot_h}" stroke="#ccc"/>'
        f'<line x1="{margin_l}" y1="{margin_t + plot_h}" x2="{width - margin_r}" y2="{margin_t + plot_h}" stroke="#ccc"/>'
        f'<polyline points="{points_str}" fill="none" stroke="{color}" stroke-width="2"/>'
        f'<text x="15" y="{height // 2}" transform="rotate(-90 15 {height // 2})" text-anchor="middle" font-size="11" fill="#666">{html.escape(y_label)}</text>'
        f'<text x="{width // 2}" y="{height - 5}" text-anchor="middle" font-size="11" fill="#666">Time (s)</text>'
        f"</svg>"
    )


def _svg_bar_chart(
    labels: list[str],
    values: list[float],
    title: str,
    y_label: str,
    color: str = "#4A90D9",
    width: int = 800,
    height: int = 280,
) -> str:
    """Generate an SVG bar chart."""
    if not values:
        return f'<div class="chart-placeholder">{title} (no data)</div>'
    margin_l, margin_r, margin_t, margin_b = 60, 20, 30, 50
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b
    y_max = max(values) if max(values) > 0 else 1
    bar_w = min(80, plot_w / len(values) * 0.6)
    gap = (plot_w - bar_w * len(values)) / (len(values) + 1)

    bars = ""
    grid = ""
    for i in range(5):
        gy = margin_t + plot_h * i / 4
        val = y_max - y_max * i / 4
        grid += f'<line x1="{margin_l}" y1="{gy:.1f}" x2="{width - margin_r}" y2="{gy:.1f}" stroke="#e8e8e8" stroke-width="1"/>'
        grid += f'<text x="{margin_l - 8}" y="{gy + 3:.1f}" text-anchor="end" font-size="10" fill="#888">{val:.1f}</text>'

    for i, (label, val) in enumerate(zip(labels, values, strict=True)):
        bx = margin_l + gap + i * (bar_w + gap)
        bh = (val / y_max) * plot_h if y_max > 0 else 0
        by = margin_t + plot_h - bh
        bars += f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" fill="{color}" rx="3"/>'
        bars += f'<text x="{bx + bar_w / 2:.1f}" y="{by - 4:.1f}" text-anchor="middle" font-size="10" fill="#555">{val:.1f}</text>'
        bars += f'<text x="{bx + bar_w / 2:.1f}" y="{height - margin_b + 15}" text-anchor="middle" font-size="10" fill="#888">{html.escape(label)}</text>'

    return (
        f'<svg viewBox="0 0 {width} {height}" class="chart">'
        f'<text x="{width // 2}" y="15" text-anchor="middle" font-size="13" font-weight="bold" fill="#333">{html.escape(title)}</text>'
        f"{grid}"
        f'<line x1="{margin_l}" y1="{margin_t + plot_h}" x2="{width - margin_r}" y2="{margin_t + plot_h}" stroke="#ccc"/>'
        f"{bars}"
        f'<text x="15" y="{height // 2}" transform="rotate(-90 15 {height // 2})" text-anchor="middle" font-size="11" fill="#666">{html.escape(y_label)}</text>'
        f"</svg>"
    )


def _svg_histogram(
    response_times: dict[int, int],
    title: str,
    color: str = "#67B168",
    width: int = 800,
    height: int = 280,
) -> str:
    """Generate a response-time distribution histogram."""
    if not response_times:
        return f'<div class="chart-placeholder">{title} (no data)</div>'
    bins: dict[str, int] = {}
    for ms, count in response_times.items():
        bucket = f"{(ms // 100) * 100}-{(ms // 100) * 100 + 99}"
        bins[bucket] = bins.get(bucket, 0) + count
    sorted_bins = sorted(bins.items(), key=lambda x: int(x[0].split("-")[0]))
    return _svg_bar_chart(
        [b[0] for b in sorted_bins],
        [float(b[1]) for b in sorted_bins],
        title,
        "Count",
        color=color,
        width=width,
        height=height,
    )


# ---------------------------------------------------------------------------
# HTML report generator
# ---------------------------------------------------------------------------

_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; background: #f5f6fa; color: #333; padding: 20px; }
h1 { color: #1a3a5c; margin-bottom: 4px; }
h2 { color: #1a3a5c; margin: 24px 0 12px; border-bottom: 2px solid #e0e6ed; padding-bottom: 6px; }
.meta { color: #888; font-size: 13px; margin-bottom: 20px; }
.dashboard { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
.card { background: #fff; border-radius: 8px; padding: 20px; min-width: 180px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
.card .label { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }
.card .value { font-size: 28px; font-weight: 700; margin-top: 4px; }
.card .value.ok { color: #27ae60; }
.card .value.warn { color: #e67e22; }
.card .value.err { color: #e74c3c; }
table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.08); margin-bottom: 20px; }
th { background: #1a3a5c; color: #fff; padding: 10px 14px; text-align: left; font-size: 13px; }
td { padding: 8px 14px; border-bottom: 1px solid #eee; font-size: 13px; }
tr:hover td { background: #f8f9fb; }
.pass { color: #27ae60; font-weight: 700; }
.fail { color: #e74c3c; font-weight: 700; }
.chart-container { background: #fff; border-radius: 8px; padding: 16px; margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
.chart { width: 100%; height: auto; }
.chart-placeholder { padding: 40px; text-align: center; color: #aaa; }
.charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
@media (max-width: 900px) { .charts-grid { grid-template-columns: 1fr; } }
"""


def _fmt(v: float, unit: str = "", decimals: int = 1) -> str:
    """Format a value with unit."""
    return f"{v:.{decimals}f}{unit}"


def generate_html_report(data: LoadReportData, output_path: str | Path) -> Path:
    """Generate a self-contained HTML report file.

    Args:
        data: All report data (entries, timeline, assertions).
        output_path: Where to write the HTML file.

    Returns:
        The path to the generated file.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    parts: list[str] = []
    parts.append("<!DOCTYPE html><html lang='zh'><head><meta charset='UTF-8'>")
    parts.append("<meta name='viewport' content='width=device-width, initial-scale=1.0'>")
    parts.append(f"<title>{html.escape(data.test_name)} - Load Test Report</title>")
    parts.append(f"<style>{_CSS}</style></head><body>")
    parts.append(f"<h1>{html.escape(data.test_name)}</h1>")
    parts.append(
        f"<div class='meta'>Host: {html.escape(data.host)} | Start: {html.escape(data.start_time)} | Duration: {_fmt(data.duration_seconds, 's', 0)}</div>"
    )

    # Dashboard cards
    err_class = (
        "ok"
        if data.total_error_rate < 0.01
        else ("warn" if data.total_error_rate < 0.05 else "err")
    )
    parts.append("<div class='dashboard'>")
    parts.append(
        f"<div class='card'><div class='label'>Total Requests</div><div class='value'>{data.total_requests:,}</div></div>"
    )
    parts.append(
        f"<div class='card'><div class='label'>Failures</div><div class='value {err_class}'>{data.total_failures:,}</div></div>"
    )
    parts.append(
        f"<div class='card'><div class='label'>Error Rate</div><div class='value {err_class}'>{_fmt(data.total_error_rate * 100, '%', 2)}</div></div>"
    )
    parts.append(
        f"<div class='card'><div class='label'>Avg Throughput</div><div class='value'>{_fmt(data.avg_throughput, ' RPS')}</div></div>"
    )
    parts.append(
        f"<div class='card'><div class='label'>Avg Response</div><div class='value'>{_fmt(data.avg_response_time_ms, ' ms')}</div></div>"
    )
    parts.append(
        f"<div class='card'><div class='label'>Duration</div><div class='value'>{_fmt(data.duration_seconds, 's', 0)}</div></div>"
    )
    parts.append("</div>")

    # Statistics table
    parts.append(
        "<h2>Statistics</h2><table><tr><th>Name</th><th>Method</th><th>Samples</th><th>Failures</th><th>Error %</th><th>Avg (ms)</th><th>Min (ms)</th><th>Max (ms)</th><th>P50</th><th>P90</th><th>P95</th><th>P99</th><th>Throughput</th></tr>"
    )
    for e in data.entries:
        throughput = e.num_requests / data.duration_seconds if data.duration_seconds > 0 else 0
        err_cls = "pass" if e.error_rate < 0.01 else "fail"
        parts.append(
            f"<tr><td>{html.escape(e.name)}</td><td>{e.method}</td>"
            f"<td>{e.num_requests:,}</td><td>{e.num_failures:,}</td>"
            f"<td class='{err_cls}'>{_fmt(e.error_rate * 100, '%', 2)}</td>"
            f"<td>{_fmt(e.avg_ms, ' ms')}</td>"
            f"<td>{_fmt(e.min_ms, ' ms', 0)}</td><td>{_fmt(e.max_ms, ' ms', 0)}</td>"
            f"<td>{_fmt(e.percentile(50), ' ms', 0)}</td>"
            f"<td>{_fmt(e.percentile(90), ' ms', 0)}</td>"
            f"<td>{_fmt(e.percentile(95), ' ms', 0)}</td>"
            f"<td>{_fmt(e.percentile(99), ' ms', 0)}</td>"
            f"<td>{_fmt(throughput, ' RPS')}</td></tr>"
        )
    parts.append("</table>")

    # APDEX table
    parts.append(
        "<h2>APDEX (Application Performance Index)</h2><table><tr><th>Name</th><th>Score</th><th>Rating</th><th>Satisfied</th><th>Tolerating</th><th>Frustrated</th></tr>"
    )
    for e in data.entries:
        score, sat, tol, fru = e.apdex()
        rating = (
            "Excellent"
            if score >= 0.94
            else (
                "Good"
                if score >= 0.85
                else ("Fair" if score >= 0.7 else ("Poor" if score >= 0.5 else "Unacceptable"))
            )
        )
        parts.append(
            f"<tr><td>{html.escape(e.name)}</td>"
            f"<td class='{'pass' if score >= 0.85 else 'fail'}'>{_fmt(score, '', 3)}</td>"
            f"<td>{rating}</td><td>{sat:,}</td><td>{tol:,}</td><td>{fru:,}</td></tr>"
        )
    parts.append("</table>")

    # Charts
    parts.append("<h2>Charts</h2>")
    parts.append('<div class="charts-grid">')
    if data.timeline:
        rt_series = [(p.elapsed_seconds, p.avg_response_time_ms) for p in data.timeline]
        rps_series = [(p.elapsed_seconds, p.rps) for p in data.timeline]
        users_series = [(p.elapsed_seconds, float(p.active_users)) for p in data.timeline]
        parts.append(
            f'<div class="chart-container">{_svg_line_chart(rt_series, "Response Time Over Time", "ms", "#e74c3c")}</div>'
        )
        parts.append(
            f'<div class="chart-container">{_svg_line_chart(rps_series, "Throughput Over Time", "RPS", "#27ae60")}</div>'
        )
        parts.append(
            f'<div class="chart-container">{_svg_line_chart(users_series, "Active Users Over Time", "Users", "#3498db")}</div>'
        )
    # Percentile bar chart (per entry)
    if data.entries:
        pct_labels = [e.name for e in data.entries]
        for pct, color in [(99, "#e74c3c"), (95, "#e67e22"), (90, "#f1c40f"), (50, "#27ae60")]:
            pct_values = [e.percentile(pct) for e in data.entries]
            parts.append(
                f'<div class="chart-container">{_svg_bar_chart(pct_labels, pct_values, f"P{pct} Response Time by Request", "ms", color)}</div>'
            )
        # Distribution histogram for first entry
        parts.append(
            f'<div class="chart-container">{_svg_histogram(data.entries[0].response_times, "Response Time Distribution", "#8e44ad")}</div>'
        )
    parts.append("</div>")

    # SLA assertions
    if data.assertions:
        parts.append(
            "<h2>SLA Assertions</h2><table><tr><th>Metric</th><th>Operator</th><th>Threshold</th><th>Actual</th><th>Result</th><th>Description</th></tr>"
        )
        for r in data.assertions:
            cls = "pass" if r.passed else "fail"
            parts.append(
                f"<tr><td>{html.escape(r.assertion.metric)}</td>"
                f"<td>{r.assertion.operator.value}</td>"
                f"<td>{r.assertion.threshold}</td>"
                f"<td>{r.actual_value}</td>"
                f"<td class='{cls}'>{'PASS' if r.passed else 'FAIL'}</td>"
                f"<td>{html.escape(r.assertion.description)}</td></tr>"
            )
        parts.append("</table>")

    # Footer
    parts.append(
        f"<div class='meta' style='margin-top:24px'>Generated by automation-platform load test engine at {time.strftime('%Y-%m-%d %H:%M:%S')}</div>"
    )
    parts.append("</body></html>")

    path.write_text("\n".join(parts), encoding="utf-8")
    return path
