# loadtest -- 接口压测项目 (Locust + YAML 场景驱动)

基于 Locust 的接口压测项目. 压测场景用 YAML 数据驱动 (复用 framework
`testing.load` 模块), 支持按国家隔离场景, 多格式数据源 (CSV/TXT/JSON/JSONL),
业务级 JSON 断言, 阶梯式加压找瓶颈, 自动生成 HTML 报告.

## 快速开始

### 一个 PyCharm 配置, 用参数切换场景

在 PyCharm 中新建一个 Run Configuration:
- Script path: `projects/loadtest/run.py`
- Working directory: `C:\work\PythonProject\automation-platform\projects\loadtest`
- Parameters: `waybill_get -t 10s`

切换场景只改 Parameters:

```bash
# 快速调试 (默认 1 个用户)
python run.py waybill_get -t 10s

# 200 并发, 每秒拉起 20 个用户, 跑 10 秒
python run.py waybill_get -t 10s -u 200 -r 20

# 完整压测形状 (200 并发, ramp-up 2min -> hold 56min -> ramp-down 2min)
python run.py waybill_get --shape -t 3600s

# 阶梯加压找瓶颈 (50->100->...->500 用户, 每档 2 分钟)
python run.py waybill_get --shape -p load_profile_jmsbr_stepped -t 840s

# 列出所有可用场景
python run.py --list
```

### JMeter 参数对照

| JMeter | Locust / run.py | 说明 |
| --- | --- | --- |
| 线程数 (Thread Count) | `-u` / `--users` | 并发用户数, 直接对应 |
| Ramp-Up 时间 (秒) | `-r` / `--spawn-rate` | JMeter 给总时间, Locust 给每秒速率. 换算: `spawn-rate = 线程数 / Ramp-Up时间` |

### 两种运行模式

1. **固定并发模式** (默认, 不加 `--shape`): 用 `-u` 控制并发数, `-r` 控制拉起速率, `-t` 控制时间. 适合快速调试和短时间验证.
2. **压测形状模式** (`--shape`): 走 `config/load_profile_<env>.yaml` 定义的 ramp-up/hold/ramp-down 阶段. 适合完整压测和大促容量验证.

## 可用场景

| 场景名 | 环境 | 接口 | 数据源 | 说明 |
| --- | --- | --- | --- | --- |
| `waybill_get` | jmsbr | spm/common/get | waybill_nos1.txt | 获取运单数据单条 |
| `waybill_query` | jmsbr | spm/common/listByWaybillNos | waybill_nos1.txt + waybill_nos2.txt | 获取运单数据批量 |
| `waybill_query_order` | jmsbr | order/listByWaybillNos | waybill_nos1.txt + waybill_nos2.txt | 获取运单数据批量2 |
| `cost_calculate` (jmsbr) | jmsbr | comCostAndWeight | cost_data.csv | 单条算费 |
| `cost_calculate` (cost) | cost | comCostAndWeight | cost_data.csv | 单条算费 (cost 环境) |
| `login` (test) | test | 登录页 | users.csv | 登录 (test 环境) |
| `login` (uat) | uat | 登录页 | users.csv | 登录 (uat 环境) |

> 场景名在多个环境中重复时 (如 `cost_calculate`), 用完整路径消歧: `jmsbr/cost_calculate`

## 目录结构

```
loadtest/
├── run.py                  # 压测启动脚本 (一个 PyCharm 配置, 参数切换场景)
├── locustfile.py           # Locust 入口 (加载 YAML 场景, 构建 HttpUser + Shape)
├── runner.py               # Locust 集成层 (场景执行, 数据驱动, 断言, 报告)
├── conftest.py             # framework 配置定位 (APP_CONFIG_DIR)
├── pytest.ini              # pytest 配置
├── pyproject.toml          # uv workspace 成员 (locust 依赖)
├── config/
│   ├── envs/               # 环境配置 (base_url, HTTP 设置)
│   │   ├── jmsbr.yaml      # 巴西环境 (算费 host + 运单查询 host)
│   │   ├── cost.yaml       # 算费环境
│   │   ├── test.yaml       # 测试环境
│   │   ├── uat.yaml        # UAT 环境
│   │   └── dev.yaml / prod.yaml
│   ├── load_profile_jmsbr.yaml          # jmsbr 压测形状 (200 并发, 1 小时)
│   ├── load_profile_jmsbr_stepped.yaml  # jmsbr 阶梯加压 (50->500, 找瓶颈)
│   ├── load_profile_cost.yaml           # cost 压测形状
│   └── load_profile.yaml                # 默认压测形状
├── data/                   # 数据源文件 (按国家存放)
│   └── jmsbr/
│       ├── waybill_nos1.txt    # 运单号数据源 1 (17MB, 百万级)
│       ├── waybill_nos2.txt    # 运单号数据源 2 (17MB, 百万级)
│       ├── waybill_nos.txt     # 运单号示例 (小文件)
│       └── cost_data.csv       # 算费数据源 (多字段 CSV)
├── scenarios/              # 压测场景 (按国家隔离)
│   ├── jmsbr/              # 巴西场景
│   │   ├── waybill_get.yaml
│   │   ├── waybill_query.yaml
│   │   ├── waybill_query_order.yaml
│   │   └── cost_calculate.yaml
│   ├── cost/
│   │   └── cost_calculate.yaml
│   ├── test/
│   │   └── login.yaml
│   └── uat/
│       └── login.yaml
├── reports/                # 压测报告输出目录
│   └── load_report.html    # HTML 报告 (自动生成)
└── testcase/               # 单元测试
    ├── test_scenario.py    # 场景加载 + 指标计算测试
    └── test_load_engine.py # 压测引擎测试 (LoadProfile/断言/DataProvider)
```

## 数据驱动 (Data Provider)

场景 YAML 中的 `{{...}}` 模板在运行时由 `DataProvider` 解析, 支持以下类型:

### 多格式数据源

| 格式 | 扩展名 | 结构 | 模板语法 |
| --- | --- | --- | --- |
| CSV | .csv | 表头 + 行 | `{{data.<file>.<column>}}` |
| TXT | .txt | 每行一个值 | `{{data.<file>.value}}` |
| JSON | .json | 对象数组 | `{{data.<file>.<key>}}` |
| JSONL | .jsonl | 每行一个 JSON 对象 | `{{data.<file>.<key>}}` |

数据源文件放在 `data/<env>/` 目录, 按行顺序读取, 读完自动循环.

### 内置模板

| 模板 | 说明 | 示例 |
| --- | --- | --- |
| `{{uuid}}` | 随机 UUID4 | `"X-Trace-Id": "{{uuid}}"` |
| `{{timestamp}}` | Unix 时间戳 | `"ts": "{{timestamp}}"` |
| `{{random.int(min,max)}}` | 随机整数 | `"qty": "{{random.int(1,100)}}"` |
| `{{random.float(min,max)}}` | 随机浮点数 | `"rate": "{{random.float(0,1)}}"` |
| `{{random.choice(a,b,c)}}` | 随机选择 | `"color": "{{random.choice(red,green,blue)}}"` |

### 类型转换

在模板前加 `{{int:...}}` 或 `{{float:...}}` 前缀, 将读取的字符串转为整数或浮点数:

```yaml
productTypeId: "{{int:data.jmsbr/cost_data.productTypeId}}"    # 字符串 -> 整数
number: "{{float:data.jmsbr/cost_data.number}}"               # 字符串 -> 浮点数
```

### 行一致性

同一个 `resolve()` 调用中, 多次引用同一个数据源文件会读取同一行数据,
不会每次引用都推进游标. 例如:

```yaml
waybillNos:
  - "{{data.jmsbr/waybill_nos1.value}}"   # 第 1 行
  - "{{data.jmsbr/waybill_nos2.value}}"   # 第 1 行 (不同文件, 独立游标)
```

下一次请求时, 两个文件各自推进到第 2 行, 互不干扰.

## 业务级 JSON 断言 (assert_json)

场景 YAML 的 step 中声明 `assert_json`, runner 会在 HTTP 状态码检查通过后,
解析响应 JSON 体并校验声明的字段. 任一字段不匹配即标记为失败:

```yaml
steps:
  - name: "POST spm/common/get"
    method: POST
    url: http://10.94.7.103:30122/waybillouterapi/spm/common/get
    json:
      waybillNo: "{{data.jmsbr/waybill_nos1.value}}"
      columns: [...]
    expected_status: 200
    assert_json:
      succ: true       # 校验响应体中 succ 字段是否为 true
```

断言流程: HTTP 状态码检查 -> HTTP 4xx/5xx 检查 -> assert_json 业务字段检查.
只有全部通过才标记 `resp.success()`, 否则 `resp.failure()`.

## 压测形状 (Load Profile)

### 完整压测形状 (config/load_profile_jmsbr.yaml)

200 并发用户, ramp-up 2 分钟 -> hold 56 分钟 -> ramp-down 2 分钟, 共 1 小时:

```yaml
profile:
  stop_after_last: true
  stages:
    - name: ramp_up
      target_users: 200      # 目标并发用户
      spawn_rate: 10          # 每秒新增用户数
      duration: 120           # 持续秒数
    - name: hold
      target_users: 200
      spawn_rate: 0           # 0 = 保持
      duration: 3360
    - name: ramp_down
      target_users: 0
      spawn_rate: 20
      duration: 120

assertions:
  - metric: p99_ms
    operator: lt
    threshold: 2000           # P99 < 2s
  - metric: error_rate
    operator: lt
    threshold: 0.05           # 错误率 < 5%
  - metric: rps
    operator: gt
    threshold: 50             # 吞吐量 > 50 RPS
```

### 阶梯加压找瓶颈 (config/load_profile_jmsbr_stepped.yaml)

逐步增加并发用户, 每档保持 2 分钟, 观察响应时间和错误率在哪个并发量级开始恶化:

| 阶段 | 并发用户 | 持续时间 | 预估 QPS (按 332ms 响应) |
| --- | --- | --- | --- |
| step_50 | 50 | 2 min | ~150 |
| step_100 | 100 | 2 min | ~300 |
| step_150 | 150 | 2 min | ~450 |
| step_200 | 200 | 2 min | ~600 |
| step_300 | 300 | 2 min | ~900 |
| step_400 | 400 | 2 min | ~1200 |
| step_500 | 500 | 2 min | ~1500 |

```bash
python run.py waybill_get --shape -p load_profile_jmsbr_stepped -t 840s
```

> 阶梯测试的目的是找到接口的极限承压能力: 当 P99 延迟突然飙升或错误率
> 超过 5% 时的并发用户数, 就是该接口的瓶颈.

### QPS 计算

```
QPS = 并发用户数 / 平均响应时间(秒)
```

示例: 200 并发用户, 平均响应时间 332ms:
```
QPS = 200 / 0.332 = 602 QPS
```

> 注意: `wait_time` 已设为 0 (API 压测不需要用户思考时间), 所以 QPS 仅取决于
> 并发用户数和接口响应时间. 场景中的 `think_time` 也为 0.

## SLA 断言

压测形状文件的 `assertions` 段定义后置 SLA 断言, 在压测结束时对全局指标评估:

| 指标 | 说明 |
| --- | --- |
| `min_ms` / `avg_ms` / `max_ms` | 最小/平均/最大延迟 (毫秒) |
| `p50_ms` / `p90_ms` / `p95_ms` / `p99_ms` | 延迟分位数 (毫秒) |
| `rps` | 吞吐量 (requests per second) |
| `total_requests` / `total_errors` | 总请求数 / 总错误数 |
| `error_rate` | 错误率 (0-1) |
| `duration_seconds` | 压测持续时间 (秒) |

运算符: `eq` (等于), `ne` (不等于), `lt` (小于), `le` (小于等于), `gt` (大于), `ge` (大于等于)

断言结果在控制台输出 PASS/FAIL 汇总, 同时挂载到 Allure 报告.

## HTML 报告

压测结束后自动生成 `reports/load_report.html`, 包含:
- 统计表 (请求数、失败数、平均/最小/最大/中位数延迟、RPS、错误率)
- 延迟分位数表 (P50/P66/P75/P80/P90/P95/P98/P99/P99.9/P99.99)
- SVG 时间序列图表 (活跃用户数、RPS、平均延迟、错误率)
- 响应时间直方图
- APDEX 评分
- SLA 断言结果

## 调试日志

压测运行时自动输出以下调试日志 (仅首次, 不影响性能):
- **首次请求报文**: 打印第一个请求的完整 URL、请求头、请求体
- **首次响应报文**: 打印第一个响应的状态码和响应体
- **失败详情**: 打印前 3 次失败的 URL、状态码、响应体 (方便定位问题)

## 环境隔离

- `config/envs/jmsbr.yaml` + `scenarios/jmsbr/*.yaml` -- 巴西环境
- `config/envs/cost.yaml` + `scenarios/cost/*.yaml` -- 算费环境
- `config/envs/test.yaml` + `scenarios/test/*.yaml` -- 测试环境
- `config/envs/uat.yaml` + `scenarios/uat/*.yaml` -- UAT 环境
- `APP_ENV` 决定加载哪套配置和场景, 各环境完全隔离
- `data/<env>/` 目录按国家存放数据源文件

## 测试

```powershell
cd projects/loadtest
pytest  # 场景加载 + 指标计算 + 压测引擎单元测试 (不需要 locust)
```

| 测试文件 | 覆盖范围 | 用例数 |
| --- | --- | --- |
| `test_scenario.py` | 场景加载 + 延迟分位数 + 指标聚合 + assert_json | 9 |
| `test_load_engine.py` | LoadProfile.tick / 断言评估 / DataProvider 多格式 / 类型转换 | 67 |

> **注意**: Locust 使用 gevent (非 asyncio), 与功能测试的 httpx/asyncio 在同进程
> 不兼容. 因此压测项目使用独立 venv, 不与功能测试共享. framework 的场景模型
> (`LoadScenario`/`LoadStep`) 和指标 (`LatencyStats`/`LoadMetrics`) 是纯 Python,
> 两侧都能用.
