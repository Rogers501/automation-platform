# jmseg 驿站报价维护 接口自动化测试项目

基于企业级 Python 自动化测试框架,从 `openapi.json` 生成的接口自动化项目。
覆盖「驿站报价维护」Tag 下 8 个端点:新增 / 修改 / 删除 / 审核 / 反审核 / 分页查询 / Raw 分页 / 详情。

## 目录结构

```
projects/jmseg/
├── openapi.json              # 接口规格来源(ApiFox 导出)
├── conftest.py               # 框架插件 + 配置定位 + fixtures 再导出
├── pyproject.toml            # 项目依赖(framework + faker)
├── pytest.ini                # 测试配置(smoke/regression marker)
├── models/                   # DTO + 枚举(Pydantic v2)
│   ├── enums.py              # FeeType / AuditStatus / RoundingMode ...
│   └── dto.py                # 18 个 schema(去重:LoginContext / Result[T])
├── api/                      # API 客户端
│   ├── base.py               # BaseClient(异步) / SyncClient(同步) / 鉴权识别
│   └── station_quote.py      # StationQuoteClient(单 Tag 单 Client,8 端点)
├── factories.py              # Faker 测试数据工厂(离线 fallback)
├── dependency.py             # 接口依赖 DAG + 拓扑排序 + 值提取
├── fixture/                  # pytest fixtures
│   ├── auth.py               # token(环境外置) / X-UPS-USER
│   └── clients.py            # 带状态 MockTransport / 异步 / 同步客户端
├── data/                     # 数据驱动用例(yaml)
├── config/envs/              # 多环境配置(dev/test/uat/prod)
└── testcase/                 # 测试用例
```

## 设计要点

- **单 Tag 单 Client**:`StationQuoteClient` 封装「驿站报价维护」全部 8 端点。
- **同步 + 异步**:异步主路径基于 framework `AsyncHttpClient`(完整重试/日志/录制);
  同步路径 `SyncClient` 基于 `httpx.Client`,复用同一 `_ENDPOINTS` 注册表,零逻辑重复。
- **DTO 去重**:登录上下文抽 `LoginContext`;VO 公共字段抽 `StationQuoteBaseVO`;
  5 个 `Result*` 信封合并为泛型 `Result[T]`。
- **字段名恢复**:ApiFox 导出污染了部分字段名(中文前缀),已按 description 第二行
  恢复为服务端 camelCase 别名,Python 字段使用 snake_case。
- **Token 自动注入**:`detect_auth_scheme` 从 openapi 自动识别 `authtoken` 自定义头
  (无 Bearer / Cookie),`BaseClient` 自动注入。
- **Faker 工厂**:优先 faker,未安装时回退纯 Python 生成器,保证离线全绿。
- **接口依赖 DAG**:`dependency.py` 声明 save→page→{detail,update,audit→unaudit,delete}。
- **不修改 framework**:BaseClient/SyncClient/DAG 均项目本地化,framework 核心零修改。

## 运行测试

```powershell
cd projects/jmseg
..\..\.venv\Scripts\python.exe -m pytest              # 全量
..\..\.venv\Scripts\python.exe -m pytest -m smoke      # 冒烟
..\..\.venv\Scripts\python.exe -m pytest -m regression # 回归
```

> 测试使用带状态的 `MockTransport`,无需真实服务即可全绿。
> `test_schema.py` 在未安装 `jsonschema` 时自动跳过。

## Allure 报告

```powershell
..\..\.venv\Scripts\python.exe -m pip install allure-pytest
..\..\.venv\Scripts\python.exe -m pytest --alluredir=allure-results
allure serve allure-results
```

未安装 allure-pytest 时,`step` / `attach_*` 全部 no-op,用例仍绿色;
`test_context` 在 teardown 自动把本次 HTTP 交换作为附件。

## 接入真实环境

1. 在 `config/envs/<env>.yaml` 配置 `http.base_url`。
2. 通过环境变量注入 token(禁止硬编码):
   ```powershell
   $env:APP_JMSEG_TOKEN = "<真实 token>"
   $env:APP_JMSEG_UPS_USER = "<用户标识>"
   $env:APP_ENV = "test"
   ```
3. 删除 `fixture/clients.py` 中的 `transport=mock_transport`,改用配置中的 `base_url`。

## 同步用法(脚本/REPL)

```python
import httpx
from api.base import SyncClient
from api.station_quote import StationQuoteClient
from factories import make_create_request

with httpx.Client(base_url="http://jmseg.test") as http:
    sc = SyncClient(StationQuoteClient, http, token="<token>", user="tester")
    resp = sc.save(make_create_request())   # 同步调用,复用同一端点注册表
    print(resp.json)
```

## 接口依赖链路

```
save ──► page ──► detail
              ├──► update
              ├──► audit ──► unaudit
              └──► delete
```

`page` 从 `$.data.records[0].id` 提取报价 id,供 detail/update/audit/delete 使用;
`unaudit` 依赖 `audit`(先审核再反审核)。