# jmseu - 德国 JMS 系统 WebUI 自动化测试

jmseu 是 JMS 系统的德国/欧洲站点 WebUI 自动化测试项目, 基于 framework 的
WebClient (Playwright) 实现, 采用 Page Object 模式组织页面对象.

## 命名约定

JMS 系统按国家/地区部署, 业务项目文件夹命名规则: **`jms` + 2 位地区代码**.

| 文件夹    | 地区         | 代码来源          | 说明               |
| --------- | ------------ | ----------------- | ------------------ |
| `jmseg`   | 埃及 Egypt   | EG (ISO 国家码)   | 接口自动化 (API)   |
| `jmseu`   | 德国 Germany | EU (欧洲)         | WebUI 自动化       |

新增国家时, 用户直接告知文件夹名 (如 `jmsus` = 美国), 按本目录结构复制即可,
无需额外提示地区含义. 文件夹名即项目标识, 出现在 pyproject.toml / config /
conftest 等所有位置.

## 目录结构

```
jmseu/
├── pages/                   # Page Object 层
│   ├── base_page.py         # BasePage: 封装 WebClient 通用操作
│   ├── login_page.py        # LoginPage: 登录页选择器与操作
│   └── captcha_page.py      # TencentSliderCaptcha: 人工滑块验证码(操作员手动完成)
├── testcase/
│   └── test_login_web.py    # WebUI 登录测试 (真实浏览器, 数据驱动)
├── fixture/
│   └── web_client.py        # WebClient fixture (真实浏览器)
├── data/                    # 测试数据 (按环境隔离)
│   ├── test/
│   │   └── login_cases.yaml # test 环境登录用例 (数据驱动)
│   └── uat/
│       └── login_cases.yaml # UAT 环境登录用例 (数据驱动)
├── config/envs/             # 多环境配置 (web.base_url 等)
├── conftest.py              # 框架插件 + 配置定位 + .env加载 + fixtures再导出
├── pyproject.toml
└── pytest.ini
```

## 架构设计

- **Page Object 模式**: `BasePage` 封装 WebClient 通用操作 (导航/点击/填写/
  等待/截图/is_visible/evaluate/locator/mouse), `LoginPage` 继承它并定义登录页
  专属选择器与流程. 选择器集中管理, UI 变更只改一处 (rule 4/8).
- **腾讯滑块验证码**: 登录提交后触发腾讯滑块验证码 (tencent-captcha-dy).
  自动破解缺口位置太慢且易被封 IP, 采用人工处理 (human-in-the-loop): 操作员在
  可见浏览器手动完成滑动, 脚本等待 dashboard 文本 `功能入口` 确认登录成功.
  仅真实浏览器模式生效.
  详见下方"滑块验证码处理"章节.
- **环境隔离 + 数据驱动 (rule 10)**: 测试数据按环境分离 --
  `data/test/login_cases.yaml` (test) 和 `data/uat/login_cases.yaml` (uat).
  APP_ENV 决定加载哪个数据文件, 凭据不硬编码在代码或配置中.
  每条 case 对应一个参数化测试用例, 支持多账号/多场景扩展.
- **失败截图**: `screenshot_provider` fixture 覆盖框架默认 null provider,
  测试失败时自动通过 Playwright 截图.
- **Allure 步骤**: 用 `framework.reporting.allure.step` 包裹业务步骤,
  生成结构化报告.
- **数据驱动**: 登录测试数据在 `data/<APP_ENV>/login_cases.yaml`, 通过
  `framework.testing.datadriven.load_cases` + `@pytest.mark.parametrize` 加载.

## 环境配置

1. 安装 Playwright 浏览器:
   ```powershell
   uv run playwright install chromium
   ```
2. 配置测试数据 (环境隔离):

   测试数据按环境分离, 位于 `data/<APP_ENV>/login_cases.yaml`:

   ```yaml
   # data/test/login_cases.yaml  (APP_ENV=test 时加载)
   cases:
     - id: normal_admin
       description: 管理员正常登录 (test环境)
       username: "你的员工编号"
       password: "你的密码"
       remember: true

   # data/uat/login_cases.yaml  (APP_ENV=uat 时加载)
   # 同结构, UAT 环境专用凭据
   ```

   test 和 uat 的数据互不影响, 切换环境只需改 APP_ENV.

3. 运行真实浏览器测试:
   ```powershell
   cd projects/jmseu

   # test 环境 (加载 data/test/login_cases.yaml + config/envs/test.yaml)
   APP_ENV=test pytest

   # UAT 环境 (加载 data/uat/login_cases.yaml + config/envs/uat.yaml)
   APP_ENV=uat pytest
   ```
   真实浏览器测试流程: 打开登录页 -> Cookie consent -> 切换中文 ->
   输入凭据 -> 滑块验证码求解 -> 验证登录成功.

## Allure 报告

测试会话结束时自动生成 Allure HTML 报告并打开浏览器. `pytest.ini` 配置了
`--alluredir=allure-results`, `conftest.py` 的 `pytest_sessionfinish` 钩子负责:

- 写 environment.properties + categories.json
- 调用 `allure generate` 生成 HTML 到 `allure-report/`
- logger 输出报告**绝对路径**(IDE 控制台可点击) + `allure open` 命令
- 启动 `allure open`(固定端口 5274, 启动前 `netstat` 清理旧服务器避免进程堆积) 本地 HTTP 服务器并打开浏览器(不转圈; CI 环境跳过)

产物:

- 结果目录: `allure-results/` (原始 JSON)
- HTML 报告: `allure-report/index.html`
- 环境元数据: `environment.properties` (env/base_url/browser/channel 等)
- 失败分类: `categories.json` (产品缺陷/测试缺陷/Flaky)

手动查看:

```powershell
# 推荐: 本地服务器(不转圈)
allure open "allure-report"
# 指定端口
allure open --port 5274 allure-report
```

依赖本地 `allure` CLI (`npm i -g allure-commandline`) + Java.
未安装 CLI 时跳过 HTML 生成并 logger 提示.

> **转圈说明**: Allure 报告是 SPA, 通过 fetch 加载 `data/*.json`. 直接用 `file://`
> 打开 index.html 时 Chrome 禁止跨源 fetch 会一直转圈. 钩子用 `allure open` 启动
> 本地 HTTP 服务器打开(不转圈); 也可手动运行控制台输出的 allure open 命令.
>
> **PyCharm**: runner 默认加 `--no-summary` 抑制 `pytest_terminal_summary`, 故
> 生成与打开放在 `pytest_sessionfinish`(不受影响). 控制台可见报告绝对路径日志.

## IDE 配置 (PyCharm)

本项目已纳入 uv workspace (`automation-platform/pyproject.toml` 的
`[tool.uv.workspace] members` 含 `projects/jmseu`), `framework` 通过
`[tool.uv.sources] framework = { workspace = true }` 解析为本地包.
PyCharm 需指向**平台根**的 workspace venv (非 `projects/jmseu/.venv`):

1. **解释器**: Settings -> Project -> Python Interpreter -> Existing:
   ```
   C:\work\PythonProject\automation-platform\.venv\Scripts\python.exe
   ```
2. **运行配置环境变量** (真实浏览器用例):
   ```
   # APP_ENV=test 或 uat (选择环境 + 对应测试数据)
   APP_ENV=test
   ```
   `channel=chrome` 和 `headless=false` 已内置在 `config/envs/test.yaml`,
   或在 .env 中配置 APP_ENV (conftest 自动加载).

> **注意**: 不要选 `projects/jmseu/.venv` (空壳, 无依赖) 或 `pytest.exe` (应选 `python.exe`).
> uv workspace venv 含 framework + playwright + pytest 全部依赖.

## LoginPage 选择器

选择器基于 Playwright 录制器对真实 test 环境的录制, 集中在 `LoginPage` 类:

| 常量              | 值                                    | 说明               |
| ----------------- | ------------------------------------- | ------------------ |
| `USERNAME_INPUT`  | `input[placeholder='请输入员工编号']` | 用户名输入框       |
| `PASSWORD_INPUT`  | `input[placeholder='请输密码']`       | 密码输入框         |
| `LOGIN_BUTTON`    | `button:has-text('登录')`             | 登录按钮           |
| `REMEMBER_PWD`    | `.lm-bottom-box > .remember-pwd > .rp-check` | 记住密码复选框 |
| `COOKIE_ACCEPT`   | `text=Alle akzeptieren`               | Cookie consent 按钮 |
| `WELCOME_TEXT`    | `.welcome`                            | 欢迎信息           |

## 滑块验证码处理

登录提交后可能出现腾讯滑块验证码 (tencent-captcha-dy). `TencentSliderCaptcha`
封装在 `pages/captcha_page.py`, 继承 `BasePage`, 采用人工处理模式 (human-in-the-loop):

**人工滑动**: 自动破解缺口位置太慢且易被封 IP, 改为操作员在可见浏览器手动完成
滑动. `solve()` 先检测是否已跳过验证码 (URL 离开 `/login`), 若仍在登录页则等待
dashboard 成功文本出现, 操作员在此期间完成滑动.

**成功检测**: 等待页面出现 `text=功能入口` 文本 (120s 超时), 检测到即代表登录成功.
未检测到则保存诊断截图 `captcha_debug.png`.

| 标志 / 文件           | 说明                          |
| --------------------- | ----------------------------- |
| `text=功能入口`       | 登录成功标志 (dashboard 文本) |
| `captcha_debug.png`   | 失败诊断截图                  |

> **注意**: 需可见浏览器 (`headless=false`) 供操作员手动滑动.
