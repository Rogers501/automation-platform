"""Locust 压测执行器: YAML 场景 -> Locust HttpUser 任务.

本模块是框架 testing.load 原语 (场景模型、指标、压测形状、数据驱动、SLA 断言)
与 Locust 执行引擎之间的桥梁. 启动时从 YAML 加载场景, 每个场景变成一个
Locust @task, 挂在动态生成的 HttpUser 子类上.

核心功能:
  - 数据驱动: DataProvider 解析 {{uuid}}, {{random.int}}, {{data.file.col}} 等模板
  - 压测形状: LoadProfile -> LoadTestShape, YAML 驱动 ramp-up/hold/ramp-down
  - 业务断言: assert_json 字段校验响应 JSON 体中的业务字段 (如 succ: true)
  - 首次报文: 自动打印第一个请求和响应的完整报文 (仅一次, 方便调试)
  - 失败诊断: 自动打印前 3 次失败的详细信息 (URL、状态码、响应体)
  - SLA 断言: 压测结束时对全局指标评估, 输出 PASS/FAIL 汇总
  - HTML 报告: 自动生成带 SVG 图表、APDEX、统计表的 HTML 报告
"""

from __future__ import annotations

import atexit
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
# 全局指标收集器 (线程安全, 跨 gevent 协程)
# ---------------------------------------------------------------------------
_GLOBAL_LOCK = threading.Lock()
_GLOBAL_METRICS: dict[str, LoadMetrics] = {}
_EVENT_HOOKS_REGISTERED = False

# 时间序列采样 (每秒采集一次, 用于 HTML 报告中的图表)
_TIMELINE: list[TimeSeriesPoint] = []
_TIMELINE_RUNNING = False
_ASSERTION_RESULTS: list = []
_TEST_HOST = ""
_TEST_START_TIME = ""
_FIRST_REQUEST_LOGGED = False
_FIRST_RESPONSE_LOGGED = False
_FAILURE_LOG_COUNT = 0
_PENDING_REPORT_ENV: Any = None
_PENDING_REPORT_ASSERTIONS: list[LoadAssertion] = []
_ATEXIT_REGISTERED = False


def _env_base_url() -> str:
    """从框架配置读取 base_url (config/envs/<APP_ENV>.yaml)."""
    return get_settings().web.base_url or get_settings().http.base_url


def _load_profile_config() -> tuple[LoadProfile | None, list[LoadAssertion]]:
    """加载压测形状和 SLA 断言配置.

    LOAD_PROFILE 环境变量选择形状文件 (默认 load_profile).
    返回 (形状, 断言列表). 形状为 None 表示未配置.

    文件位置: config/<LOAD_PROFILE>.yaml
    """
    profile_name = os.environ.get("LOAD_PROFILE", "load_profile")
    profile_path = Path("config") / f"{profile_name}.yaml"
    if not profile_path.exists():
        return None, []
    try:
        raw = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        logger.warning("压测形状文件格式错误, 跳过")
        return None, []
    if not isinstance(raw, dict):
        return None, []

    profile: LoadProfile | None = None
    if "profile" in raw or "stages" in raw:
        try:
            profile = load_profile(raw)
        except Exception as exc:
            logger.warning(f"压测形状配置无效: {exc}")

    assertions = [LoadAssertion.model_validate(a) for a in raw.get("assertions", [])]
    return profile, assertions


def _merge_global_metrics(metrics: LoadMetrics) -> None:
    """将单用户指标合并到全局收集器, 供压测结束时做 SLA 断言."""
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
# 场景执行
# ---------------------------------------------------------------------------


def _log_failure_detail(step: Any, resp: Any, reason: str, full_url: str = "") -> None:
    """打印前 3 次失败的详细信息 (URL、状态码、响应体), 方便定位问题."""
    global _FAILURE_LOG_COUNT
    with _GLOBAL_LOCK:
        if _FAILURE_LOG_COUNT >= 3:
            return
        _FAILURE_LOG_COUNT += 1
        idx = _FAILURE_LOG_COUNT
    snippet = ""
    status = "N/A"
    if resp is not None:
        status = resp.status_code
        try:
            snippet = resp.text[:500]
        except Exception:
            snippet = "<无法读取>"
    url_display = full_url or step.url
    logger.warning(
        f"=== 失败 #{idx} ===\n"
        f"  接口: {step.name}\n"
        f"  URL: {url_display}\n"
        f"  原因: {reason}\n"
        f"  状态码: {status}\n"
        f"  响应体: {snippet}"
    )


def _run_scenario(self: Any, scenario: Any, provider: DataProvider) -> None:
    """执行场景中的所有步骤, 采集每步的延迟指标.

    参数:
        self: Locust HttpUser 实例, 通过 self.client 发送请求
        scenario: LoadScenario 场景对象 (从 YAML 加载)
        provider: DataProvider 数据驱动引擎, 解析 {{...}} 模板
    """
    metrics = LoadMetrics(scenario_name=scenario.name)
    run_start = time.perf_counter()
    step_headers = dict(scenario.headers)

    for step in scenario.steps:
        # 数据驱动: 解析所有动态字段中的 {{...}} 模板
        resolved_url = provider.resolve(step.url)
        resolved_params = provider.resolve(step.params)
        resolved_headers = provider.resolve(step.headers)
        resolved_json = provider.resolve(step.json_body)
        resolved_data = provider.resolve(step.data)

        merged_headers = {**step_headers, **(resolved_headers or {})}
        req_name = step.name or f"{step.method} {resolved_url}"

        # 构建完整 URL 用于日志输出 (绝对 URL 直接用, 相对路径拼接 host)
        full_url = resolved_url if resolved_url.startswith("http") else f"{self.host}{resolved_url}"

        # 首次请求报文打印 (仅一次, 方便确认请求参数是否正确)
        global _FIRST_REQUEST_LOGGED
        if not _FIRST_REQUEST_LOGGED:
            with _GLOBAL_LOCK:
                if not _FIRST_REQUEST_LOGGED:
                    _FIRST_REQUEST_LOGGED = True
                    import json as _json

                    logger.info("=== 首次请求报文 ===")
                    logger.info(f"  {step.method.upper()} {full_url}")
                    logger.info(f"  请求头: {merged_headers or {}}")
                    logger.info(
                        f"  请求体: {_json.dumps(resolved_json, ensure_ascii=False, indent=2)}"
                    )
                    if resolved_params:
                        logger.info(f"  查询参数: {resolved_params}")
                    logger.info("=== 首次请求报文结束 ===")

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

                # 三级断言: HTTP 状态码 -> HTTP 4xx/5xx -> 业务 JSON 字段
                if step.expected_status and resp.status_code != step.expected_status:
                    # 预期状态码不匹配
                    is_error = True
                    resp.failure(f"expected {step.expected_status}, got {resp.status_code}")
                    _log_failure_detail(step, resp, f"状态码 {resp.status_code}", full_url)
                elif resp.status_code >= 400:
                    # HTTP 错误
                    is_error = True
                    resp.failure(f"HTTP {resp.status_code}")
                    _log_failure_detail(step, resp, f"HTTP {resp.status_code}", full_url)
                elif step.assert_json:
                    # 业务级 JSON 断言: 校验响应体中的业务字段 (如 succ: true)
                    # 只有 HTTP 2xx 才进入此分支
                    try:
                        body = resp.json()
                        mismatch = False
                        for key, expected in step.assert_json.items():
                            actual = body.get(key)
                            if actual != expected:
                                mismatch = True
                                resp.failure(
                                    f"assert_json: {key}={actual!r}, expected {expected!r}"
                                )
                                break
                        if mismatch:
                            is_error = True
                            _log_failure_detail(step, resp, "业务断言不匹配", full_url)
                        else:
                            resp.success()
                    except Exception:
                        is_error = True
                        resp.failure("assert_json: 响应体不是有效 JSON")
                        _log_failure_detail(step, resp, "JSON 解析失败", full_url)
                else:
                    resp.success()

                # 首次响应报文打印 (仅一次, 方便确认响应是否正确)
                global _FIRST_RESPONSE_LOGGED
                if not _FIRST_RESPONSE_LOGGED:
                    with _GLOBAL_LOCK:
                        if not _FIRST_RESPONSE_LOGGED:
                            _FIRST_RESPONSE_LOGGED = True
                            try:
                                resp_body = resp.text[:2000]
                            except Exception:
                                resp_body = "<无法读取>"
                            logger.info("=== 首次响应报文 ===")
                            logger.info(f"  状态码: {resp.status_code}")
                            logger.info(f"  响应体: {resp_body}")
                            logger.info("=== 首次响应报文结束 ===")
        except Exception as exc:
            elapsed = time.perf_counter() - start
            is_error = True
            _log_failure_detail(step, None, f"异常: {exc}", full_url)

        metrics.record(elapsed, is_error=is_error)

        # 思考时间: step 级别优先, 其次场景级别
        if step.think_time > 0:
            time.sleep(step.think_time)
        elif scenario.think_time > 0:
            time.sleep(scenario.think_time)

    metrics.duration_seconds = time.perf_counter() - run_start
    # 合并到全局收集器, 供压测结束时做 SLA 断言
    _merge_global_metrics(metrics)
    # 存到 self 上, on_stop 时采集 per-user 指标附件
    if not hasattr(self, "_metrics_list"):
        self._metrics_list = []
    self._metrics_list.append(metrics)


# ---------------------------------------------------------------------------
# Locust 类构建器
# ---------------------------------------------------------------------------


def build_user_class(scenario_file: str) -> type:
    """从 YAML 场景文件构建 Locust HttpUser 子类.

    每个场景变成一个 @task, 权重由 scenario.weight 决定.
    创建一个 DataProvider 实例用于模板解析.
    如果配置了 SLA 断言, 注册事件钩子.

    参数:
        scenario_file: 场景文件路径 (如 scenarios/jmsbr/waybill_get.yaml)
    """
    from locust import HttpUser, constant, task

    scenarios = load_scenarios(scenario_file)
    base_url = _env_base_url()
    provider = DataProvider(csv_dir=Path("data"))
    _profile, assertions = _load_profile_config()

    # wait_time=0: API 压测不需要用户思考时间, 最大化吞吐量
    namespace: dict[str, Any] = {
        "host": base_url,
        "wait_time": constant(0),
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

    # 注册事件钩子: 时间序列采集、SLA 断言、HTML 报告
    global _TEST_HOST
    _TEST_HOST = base_url
    _register_event_hooks(assertions)

    return user_class


_CACHED_SHAPE_CLASS: type | None = None


def build_shape_class() -> type | None:
    """从 config/<LOAD_PROFILE>.yaml 构建 Locust LoadTestShape.

    返回 None 表示未配置压测形状 (Locust 回退到 --users/--spawn-rate).
    使用缓存避免重复导入时报 "Duplicate shape classes" 错误.
    """
    global _CACHED_SHAPE_CLASS
    if _CACHED_SHAPE_CLASS is not None:
        return _CACHED_SHAPE_CLASS

    profile, _assertions = _load_profile_config()
    if profile is None:
        return None

    from locust import LoadTestShape

    class YamlLoadTestShape(LoadTestShape):
        """YAML 驱动的压测形状 (ramp-up/hold/ramp-down 阶段)."""

        def tick(self) -> tuple[int, float] | None:
            """根据已运行时间返回 (用户数, 拉起速率), None 表示结束."""
            return profile.tick(self.get_run_time())

    _CACHED_SHAPE_CLASS = YamlLoadTestShape
    return YamlLoadTestShape


# ---------------------------------------------------------------------------
# 事件钩子: per-user Allure 附件 + 压测结束 SLA 断言
# ---------------------------------------------------------------------------


def _make_on_stop() -> Any:
    """创建 on_stop 钩子, 在用户停止时输出 Allure 指标附件."""

    def on_stop(self: Any) -> None:
        from framework.reporting.allure import attach_json

        metrics_list = getattr(self, "_metrics_list", [])
        if not metrics_list:
            return
        # 按场景聚合该用户的指标
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
    """启动 gevent 协程, 每秒采集一次统计数据用于 HTML 报告图表."""
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
    """保存环境引用, 延迟到 Locust 统计表输出后再生成报告.

    quitting 事件在 Locust 打印统计表 *之前* 触发. 通过 atexit 延迟到
    sys.exit 之后 (即 Locust 统计表之后) 才生成报告, 控制台输出顺序为:
    Locust 统计表 -> SLA 断言汇总 -> HTML 报告路径.
    """
    global _PENDING_REPORT_ENV, _PENDING_REPORT_ASSERTIONS, _ATEXIT_REGISTERED
    _PENDING_REPORT_ENV = environment
    _PENDING_REPORT_ASSERTIONS = assertions
    if not _ATEXIT_REGISTERED:
        _ATEXIT_REGISTERED = True
        atexit.register(_atexit_generate_report)


def _atexit_generate_report() -> None:
    """在 Locust 统计表输出后生成 HTML 报告并打印 SLA 断言结果."""
    global _TIMELINE_RUNNING, _PENDING_REPORT_ENV
    environment = _PENDING_REPORT_ENV
    if environment is None:
        return
    _PENDING_REPORT_ENV = None
    _TIMELINE_RUNNING = False
    assertions = _PENDING_REPORT_ASSERTIONS

    # 从 Locust 统计数据构建 per-request 条目
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

    # 用 Locust 全局统计评估 SLA 断言
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
        logger.info(f"SLA 断言: {passed} 通过, {failed} 失败")
        for r in assertion_results:
            status = "通过" if r.passed else "失败"
            logger.info(
                f"  [{status}] {r.assertion.metric} "
                f"{r.assertion.operator.value} {r.assertion.threshold} "
                f"(实际值: {r.actual_value})"
            )

    # 生成 HTML 报告
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
    logger.info(f"HTML 报告: {report_path.absolute()}")

    # 同时挂载到 Allure
    from framework.reporting.allure import attach_text

    attach_text("Load Test Report", str(report_path.absolute()))


def _register_event_hooks(assertions: list[LoadAssertion]) -> None:
    """注册 Locust 事件钩子: 时间序列采集、SLA 断言、HTML 报告.

    钩子:
      - test_start: 启动时间序列采集协程
      - quitting: 保存环境引用, 通过 atexit 延迟生成报告

    幂等: 每个进程只注册一次 (标志位保护).
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
