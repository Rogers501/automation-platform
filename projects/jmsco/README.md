# jmsco -- 哥伦比亚 JMS 系统 WebUI 自动化测试

jmsco = JMS + CO (哥伦比亚). 基于 framework 的 WebUI 自动化测试项目,
测试 哥伦比亚 JMS 系统的登录等功能.

## 目录结构

`
jmsco/
├── conftest.py              # pytest 钩子: Allure 报告生成 + 自动打开
├── pytest.ini               # pytest 配置 (--alluredir=allure-results)
├── pyproject.toml           # uv workspace 成员定义
├── config/envs/             # 环境配置 (dev/test/uat/prod)
│   ├── dev.yaml             # 开发环境
│   ├── test.yaml            # 测试环境 (UAT 真实地址)
│   ├── uat.yaml             # UAT 环境
│   └── prod.yaml            # 生产环境
├── pages/                   # Page Object 层
│   ├── base_page.py         # BasePage: 封装 WebClient 通用操作
│   ├── login_page.py        # LoginPage: 登录页选择器与操作
│   └── captcha_page.py      # SlidePuzzleCaptcha: 滑块验证码(人工完成)
├── testcase/
│   └── test_login_web.py    # WebUI 登录测试 (真实浏览器)
├── fixture/
│   └── web_client.py        # WebClient fixture (真实浏览器)
├── data/                    # 测试数据 (按环境隔离)
│   ├── test/
│   │   └── login_cases.yaml # test 环境登录用例 (数据驱动)
│   └── uat/
│       └── login_cases.yaml # UAT 环境登录用例 (数据驱动)
└── allure-results/          # Allure 原始结果 (gitignore)
`

## 核心设计

- **Page Object 模式 (rule 4/8)**: BasePage 封装 WebClient 通用操作 (goto/click/
  fill/text/wait/screenshot/is_visible/evaluate/locator/mouse), LoginPage 继承它
  并定义登录页专属选择器与流程. 选择器集中管理, UI 变更只改一处.
- **滑块验证码**: 登录提交后触发滑块验证码 (拖动下方滑块完成拼图).
  自动破解缺口位置太慢且易被封 IP, 采用人工处理 (human-in-the-loop): 操作员在
  可见浏览器手动完成滑动, 脚本等待 dashboard 文本 功能入口 确认登录成功.
  仅真实浏览器模式生效.
- **环境隔离 + 数据驱动 (rule 10)**: 测试数据按环境分离 --
  `data/test/login_cases.yaml` (test) 和 `data/uat/login_cases.yaml` (uat).
  APP_ENV 决定加载哪个数据文件, 凭据不硬编码在代码或配置中.
  每条 case 对应一个参数化测试用例, 支持多账号/多场景扩展.
- **Allure 报告**: 测试结束后自动生成 HTML 报告并通过 llure open 打开
  (不转圈; CI 跳过). 详见下方"Allure 报告"章节.

## 环境配置

### 1. 安装依赖

`powershell
# 平台根目录执行
uv sync
playwright install chromium
`

### 2. 配置凭据 (.env)

在平台根目录 .env 添加:

`nv
JMSCO_TEST_USERNAME=你的员工编号
JMSCO_TEST_PASSWORD=你的密码
`

### 3. 运行测试

`powershell
cd projects/jmsco

# 真实浏览器测试 (需 .env 凭据 + 可见浏览器, 自动打开)
APP_ENV=test pytest
`

真实浏览器测试流程: 打开登录页 -> 切换中文 ->
输入凭据 -> 人工滑块验证码 -> 验证登录成功.

## 登录页选择器

| 选择器            | 值                                   | 说明             |
| ----------------- | ------------------------------------ | ---------------- |
| USERNAME_INPUT  | input[placeholder=请输入员工编号] | 用户名输入框     |
| PASSWORD_INPUT  | input[placeholder=请输密码]       | 密码输入框       |
| LOGIN_BUTTON    | utton:has-text(登录)             | 登录按钮         |
| REMEMBER_PWD    | .rp-check                         | 记住密码复选框   |
| WELCOME_TEXT    | .welcome                          | 欢迎信息         |

## 滑块验证码处理

登录提交后出现滑块验证码 (拖动下方滑块完成拼图). SlidePuzzleCaptcha
封装在 pages/captcha_page.py, 继承 BasePage, 采用人工处理模式:

**人工滑动**: 操作员在可见浏览器手动完成滑动. solve() 先检测是否已跳过
验证码 (URL 离开 /login), 若仍在登录页则等待 dashboard 成功文本出现.

**成功检测**: 等待页面出现 	ext=功能入口 文本 (120s 超时), 检测到即代表
登录成功. 未检测到则保存诊断截图 captcha_debug.png.

| 标志 / 文件           | 说明                          |
| --------------------- | ----------------------------- |
| 	ext=功能入口       | 登录成功标志 (dashboard 文本) |
| captcha_debug.png   | 失败诊断截图                  |

> **注意**: 仅真实浏览器模式 (JMSCO_REAL_BROWSER=1) 生效, 需可见浏览器
> (headless=false) 供操作员手动滑动.

## Allure 报告

测试会话结束时自动生成 Allure HTML 报告并打开浏览器. pytest.ini 配置了
--alluredir=allure-results, conftest.py 的 pytest_sessionfinish 钩子负责:

- 写 environment.properties + categories.json
- 调用 llure generate 生成 HTML 到 llure-report/
- logger 输出报告**绝对路径**(IDE 控制台可点击) + llure open 命令
- 启动 llure open(固定端口 5274, 启动前 
etstat 清理旧服务器避免进程堆积)
  本地 HTTP 服务器并打开浏览器(不转圈; CI 环境跳过)

手动查看:

`powershell
# 推荐: 本地服务器(不转圈)
allure open allure-report
# 指定端口
allure open --port 5274 allure-report
`

依赖本地 llure CLI (
pm i -g allure-commandline) + Java.
未安装 CLI 时跳过 HTML 生成并 logger 提示.

> **转圈说明**: Allure 报告是 SPA, 通过 fetch 加载 data/*.json. 直接用 ile://
> 打开 index.html 时 Chrome 禁止跨源 fetch 会一直转圈. 钩子用 llure open 启动
> 本地 HTTP 服务器打开(不转圈); 也可手动运行控制台输出的 allure open 命令.
>
> **PyCharm**: runner 默认加 --no-summary 抑制 pytest_terminal_summary, 故
> 生成与打开放在 pytest_sessionfinish(不受影响). 控制台可见报告绝对路径日志.

## IDE 配置 (PyCharm)

本项目已纳入 uv workspace (utomation-platform/pyproject.toml 的
[tool.uv.workspace] members 含 projects/jmsco), ramework 通过
[tool.uv.sources] framework = { workspace = true } 解析为本地包.
PyCharm 需指向**平台根**的 workspace venv (非 projects/jmsco/.venv):

1. **解释器**: Settings -> Project -> Python Interpreter -> Existing:
   C:\\work\\PythonProject\\automation-platform\\.venv\\Scripts\\python.exe
2. **工作目录**: Run Configuration -> Working directory 设为 projects/jmsco
3. **环境变量**: Run Configuration -> Environment variables 添加:
   - JMSCO_REAL_BROWSER=1 (真实浏览器模式)
   - APP_ENV=test 或 APP_ENV=uat (选择环境 + 对应测试数据)
   - 或在 .env 中配置 APP_ENV (conftest 自动加载)
