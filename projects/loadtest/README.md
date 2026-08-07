# loadtest -- 接口压测项目 (Locust + framework 场景驱动)

基于 Locust 的接口压测项目. 压测场景用 YAML 数据驱动 (复用 framework
`testing.load` 模块), 环境隔离 (test/uat 独立场景+配置), 指标采集 p50/p90/p99
延迟 + 错误率 + RPS, 结果可挂载到 Allure.

## 企业级压测能力

本项目实现了企业级性能测试平台的核心能力链:

| 能力 | 实现 | 配置位置 |
| --- | --- | --- |
| **Data Provider (数据准备)** | `DataProvider` 模板引擎: `{{uuid}}`, `{{random.int}}`, `{{csv.file.col}}`, `{{faker.*}}` | 场景 YAML 内联模板 |
| **API Client (接口封装)** | Locust `HttpUser` + framework `LoadScenario`/`LoadStep` | `scenarios/<env>/login.yaml` |
| **Locust (压测引擎)** | `LoadTestShape` (YAML-driven ramp stages) + `HttpUser` tasks | `config/load_profile.yaml` |
| **Allure 报告 (结果展示)** | per-user + 全局聚合指标 + SLA 断言附件 | 自动挂载 |
| **SLA 断言** | `evaluate_assertions()` 在 `test_stop` 时评估全局指标 | `config/load_profile.yaml` |

## 目录结构

```
loadtest/
├── locustfile.py          # Locust 入口 (加载 YAML 场景, 构建 HttpUser + Shape)
├── runner.py              # Locust 集成层 (场景 -> @task, 数据驱动, 指标, 断言)
├── conftest.py            # framework 配置定位 (APP_CONFIG_DIR)
├── pytest.ini             # pytest 配置
├── pyproject.toml         # uv workspace 成员 (locust 依赖)
├── config/
│   ├── envs/              # 环境配置 (dev/test/uat/prod)
│   │   ├── dev.yaml
│   │   ├── test.yaml      # 测试环境 (JMS Mexico UAT)
│   │   ├── uat.yaml       # UAT 环境 (JMS Colombia UAT)
│   │   └── prod.yaml
│   └── load_profile.yaml  # 压测形状 (ramp-up/hold/ramp-down) + SLA 断言
├── data/
│   └── users.csv          # CSV 数据源 (数据驱动 {{csv.users.*}})
├── scenarios/             # 压测场景 (按环境隔离, 数据驱动)
│   ├── test/
│   │   └── login.yaml
│   └── uat/
│       └── login.yaml
└── testcase/
    ├── test_scenario.py    # 场景加载 + 指标计算单元测试
    └── test_load_engine.py # 压测引擎单元测试 (LoadProfile/断言/DataProvider)
```

## 环境配置

### 独立 venv 安装

```powershell
cd projects/loadtest
python -m venv .venv
.venv\Scripts\activate
pip install locust

# framework 包通过 workspace 解析 (或 pip install -e ../../framework)
```

### 配置 .env

在平台根目录 `.env` 设置 `APP_ENV`:

```env
APP_ENV=test
```

### 运行压测

```powershell
cd projects/loadtest

# Web UI 模式 (浏览器打开 http://localhost:8089)
# Shape 驱动: load_profile.yaml 控制 ramp 阶段, 无需 --users/--spawn-rate
locust

# Headless 模式 (shape 驱动, 只需指定持续时间)
locust --headless -t 100s

# 指定环境 (切换场景+配置)
$env:APP_ENV="uat"; locust --headless -t 100s

# 无 shape 模式 (手动指定并发, 覆盖 load_profile.yaml)
locust --headless -u 50 -r 5 -t 30s
```

## 压测形状 (Load Profile)

`config/load_profile.yaml` 定义 ramp-up/hold/ramp-down 阶段, 由
`LoadProfile.tick()` 驱动 Locust `LoadTestShape`:

```yaml
profile:
  stop_after_last: true
  stages:
    - name: ramp_up
      target_users: 50      # 目标并发用户
      spawn_rate: 5          # 每秒新增用户数
      duration: 30           # 持续秒数
    - name: hold
      target_users: 50
      spawn_rate: 0          # 0 = 保持
      duration: 60
    - name: ramp_down
      target_users: 0
      spawn_rate: 10
      duration: 10
```

删除该文件 (或删除 `profile` 段) 后, Locust 回退到 `--users`/`--spawn-rate`
CLI 参数控制并发.

## 数据准备 (Data Provider)

场景 YAML 中的 `{{...}}` 模板在运行时由 `DataProvider` 解析, 支持以下类型:

| 模板 | 说明 | 示例 |
| --- | --- | --- |
| `{{uuid}}` | 随机 UUID4 | `"X-Trace-Id": "{{uuid}}"` |
| `{{timestamp}}` | Unix 时间戳 (整数) | `"ts": "{{timestamp}}"` |
| `{{random.int(min,max)}}` | 指定范围随机整数 | `"qty": "{{random.int(1,100)}}"` |
| `{{random.float(min,max)}}` | 指定范围随机浮点数 | `"rate": "{{random.float(0,1)}}"` |
| `{{random.choice(a,b,c)}}` | 从列表随机选择 | `"color": "{{random.choice(red,green,blue)}}"` |
| `{{csv.file.column}}` | CSV 顺序读取 (循环) | `"username": "{{csv.users.username}}"` |
| `{{faker.method}}` | Faker 随机数据 (需装 faker) | `"name": "{{faker.name}}"` |

模板可在 url / params / headers / json / data 任意字段中使用, 支持嵌套 dict
和 list. CSV 文件放在 `data/` 目录, 按行顺序读取, 读完循环.

### CSV 数据源示例

`data/users.csv`:

```csv
username,password
01943936,Jt7788521+
```

场景中引用:

```yaml
json:
  username: "{{csv.users.username}}"
  password: "{{csv.users.password}}"
```

## SLA 断言 (Assertions)

`config/load_profile.yaml` 的 `assertions` 段定义后置 SLA 断言, 在压测
结束 (`test_stop`) 时对全局聚合指标评估:

```yaml
assertions:
  - metric: p99_ms           # 指标名 (p99_ms / error_rate / rps / ...)
    operator: lt             # 比较运算 (eq/ne/lt/le/gt/ge)
    threshold: 500           # 阈值
    description: "P99 under 500ms"
  - metric: error_rate
    operator: lt
    threshold: 0.01
    description: "Error rate under 1%"
```

支持的指标:
- 延迟: `min_ms`, `avg_ms`, `p50_ms`, `p90_ms`, `p95_ms`, `p99_ms`, `max_ms`
- 吞吐: `rps`, `total_requests`, `total_errors`, `error_rate`, `duration_seconds`

断言结果自动挂载到 Allure 报告 (JSON 附件), 并在日志中输出 PASS/FAIL 汇总.

## 指标

压测运行时自动采集:

- **延迟分位数**: p50/p90/p95/p99 (毫秒)
- **错误率**: 失败请求 / 总请求
- **吞吐量**: RPS (requests per second)
- **Per-scenario 聚合**: 每个场景独立统计 + 全局聚合

指标通过 `LoadMetrics` 类聚合, 可挂载到 Allure 报告:

```python
from framework.testing.load import LoadMetrics

metrics = LoadMetrics(scenario_name="login_submit")
metrics.record(0.15, is_error=False)
metrics.record(0.23, is_error=True)
metrics.duration_seconds = 30.0
metrics.report()  # -> Allure JSON 附件
```

## 环境隔离

- `config/envs/test.yaml` + `scenarios/test/login.yaml` -- test 环境
- `config/envs/uat.yaml` + `scenarios/uat/login.yaml` -- UAT 环境
- `APP_ENV` 决定加载哪套配置和场景, 两套环境完全隔离
- `config/load_profile.yaml` 和 `data/` 为环境无关 (共享压测形状和数据源)

## 测试

```powershell
cd projects/loadtest
pytest  # 场景加载 + 指标计算 + 压测引擎单元测试 (不需要 locust)
```

| 测试文件 | 覆盖范围 | 用例数 |
| --- | --- | --- |
| `test_scenario.py` | 场景加载 + 延迟分位数 + 指标聚合 | 4 |
| `test_load_engine.py` | LoadProfile.tick / 断言评估 / DataProvider | 38 |

> **注意**: Locust 使用 gevent (非 asyncio), 与功能测试的 httpx/asyncio 在同进程
> 不兼容. 因此压测项目使用独立 venv, 不与功能测试共享. framework 的场景模型
> (`LoadScenario`/`LoadStep`) 和指标 (`LatencyStats`/`LoadMetrics`) 是纯 Python,
> 两侧都能用.
