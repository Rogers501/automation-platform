# OMS 业务系统测试工程

复制本目录到 `projects/<system-name>/` 即可新建一个业务系统的自动化测试工程。模板依赖
共享框架 `framework`（接口/DB/Redis/MQ 客户端、断言、日志、trace 关联、失败留痕、
pytest fixtures），业务系统只维护自己的用例、接口封装、数据与配置。

## 目录结构

```
oms/
├── api/          # 业务接口封装（Page-Object 风格，基于 framework AsyncHttpClient）
│   ├── login.py  # 登录示例：login() -> Token
│   └── users.py  # 接口调用示例：list_users() / create_user()
├── testcase/     # 测试用例
│   ├── test_login.py              # 登录示例 + token 处理
│   ├── test_users_api.py          # 接口调用示例（带 trace 上下文）
│   ├── test_users_dataDriven.py   # yaml 数据驱动示例
│   └── test_db_validation.py      # 数据库校验示例
├── data/         # 数据驱动用例（yaml）
│   └── users_cases.yaml
├── sql/          # SQL 脚本（建表 / 校验查询）
│   ├── init_users.sql
│   └── check_users.sql
├── config/       # 多环境配置
│   └── envs/{dev,test,uat,prod}.yaml
├── fixture/      # 项目级 pytest fixtures
│   ├── clients.py   # http_client / api_client / db_client / mock_transport
│   └── auth.py      # token_manager / auth（BearerAuth + TokenManager 自动刷新）
├── conftest.py   # 启用 framework 插件 + 注入项目 fixtures + 配置定位
├── pyproject.toml
└── pytest.ini
```

## 五个示例

1. **登录示例** — `api/login.py` 的 `LoginApi.login()` 调用 `/login` 拿到 `Token`。
2. **token 处理** — `fixture/auth.py` 用 `TokenManager(refresh_fn=...)` + `BearerAuth`，
   首次请求自动登录、缓存 token、过期自动刷新；`api_client` 自带鉴权。
3. **接口调用示例** — `api/users.py` 的 `UsersApi` 经鉴权客户端调用业务接口。
4. **yaml 数据驱动示例** — `framework.testing.datadriven.load_cases` 读取
   `data/users_cases.yaml`，配合 `pytest.mark.parametrize`。
5. **数据库校验示例** — `DatabaseClient` + `framework.testing.assertions`
   （`assert_row_count` / `assert_column_value` / `assert_row_contains`），SQL 脚本放 `sql/`。

## Allure 报告

模板已集成 Allure（框架 `framework.reporting.allure` + hooks 自动附件）。未安装
`allure-pytest` 时全部 no-op，用例照常通过；安装后即可生成富报告。

- **自动附件**：`test_context` 在 teardown 自动把本次测试录制的 HTTP 交换（请求/响应，已脱敏）作为附件，无需手写。
- **显式步骤**：`framework.reporting.allure.step("...")` 包裹业务步骤。
- **显式附件**：`attach_db_result(rows, name=..., query=...)` 把数据库查询结果作为附件。
- **示例用例**：`testcase/test_allure_report.py`。

生成报告：

```powershell
uv pip install allure-pytest
cd projects/template
..\..\.venv\Scripts\python.exe -m pytest --alluredir=allure-results
allure serve allure-results
```
## 开箱即跑（mock）

模板默认用 `httpx.MockTransport` 模拟接口、用内存 SQLite 模拟数据库，复制后即可绿色通过：

```powershell
cd projects/template
..\..\.venv\Scripts\python.exe -m pytest
```

## 对接真实环境

1. 在 `config/envs/<env>.yaml` 填写真实 `http.base_url` / `database` 等（密钥走
   `APP_DATABASE__PASSWORD` 等环境变量或 `.env`，禁止硬编码，规则 10）。
2. 删除 `fixture/clients.py` 中的 `transport=mock_transport`，改用真实 `base_url`；
   `db_client` 改用真实数据库配置。
3. 切换环境：`APP_ENV=test`（或 uat/prod）。

## 新增系统

复制本目录到 `projects/<name>/`，按需修改 `api/`、`testcase/`、`data/`、`config/`。
如需作为可安装工作区成员，按 `pyproject.toml` 注释取消 `[build-system]` 与
`[tool.uv.sources]` 注释，并把路径加入根 `pyproject.toml` 的
`[tool.uv.workspace] members`。