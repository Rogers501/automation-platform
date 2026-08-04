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
│   └── captcha_page.py      # TencentSliderCaptcha: 腾讯滑块验证码求解器
├── testcase/
│   ├── test_login_web.py    # WebUI 登录测试 (CI假页面 + 真实浏览器)
│   └── test_captcha.py      # 验证码轨迹生成器单元测试
├── fixture/
│   └── web_client.py        # WebClient fixture (fake page / real browser)
├── data/
│   └── login_cases.yaml     # 登录测试数据 (yaml 数据驱动)
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
  Playwright 录制器只能记录点击, 无法拖拽滑块. `TencentSliderCaptcha` 通过
  三步解决: (1) 截图背景图 + JS canvas 像素分析定位缺口位置; (2) 拟人拖拽
  轨迹 (ease-out 加速 + 过冲 + 修正); (3) 验证结果检测 + 失败重试.
  详见下方"滑块验证码处理"章节.
- **测试隔离 (rule 14)**: 默认注入 `_FakeJmseuPage` 模拟 Playwright 页面,
  无需真实浏览器或网络即可运行. fake page 模拟登录 -> 仪表盘流转, 并校验
  LoginPage 使用了正确的选择器.
- **真实浏览器**: 设置 `JMSEU_REAL_BROWSER=1` 并在 `config/envs/<env>.yaml`
  配置 `web.base_url`, 即可对接真实 JMS 站点.
- **失败截图**: `screenshot_provider` fixture 覆盖框架默认 null provider,
  测试失败时自动通过 Playwright 截图.
- **Allure 步骤**: 用 `framework.reporting.allure.step` 包裹业务步骤,
  生成结构化报告.
- **数据驱动**: 登录测试数据在 `data/login_cases.yaml`, 通过
  `framework.testing.datadriven.load_cases` 加载.

## 开箱即跑 (fake page)

```powershell
cd projects/jmseu
..\..\.venv\Scripts\python.exe -m pytest
```

无需安装 Playwright 浏览器, fake page 模拟全部交互.

## 对接真实环境

1. 安装 Playwright 浏览器:
   ```powershell
   uv run playwright install chromium
   ```
2. 配置凭据: 复制 `.env.example` 为 `.env`, 填写 test 环境账号密码:
   ```
   JMSEU_TEST_USERNAME=01943937
   JMSEU_TEST_PASSWORD=<密码>
   APP_ENV=test
   ```
   `.env` 已被 .gitignore 忽略, 不会提交 (rule 10).
3. 运行真实浏览器测试:
   ```powershell
   $env:JMSEU_REAL_BROWSER = "1"
   $env:APP_ENV = "test"
   ..\..\.venv\Scripts\python.exe -m pytest
   ```
   真实浏览器测试流程: 打开登录页 -> Cookie consent -> 切换中文 ->
   输入凭据 -> 滑块验证码求解 -> 验证登录成功.

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
   JMSEU_REAL_BROWSER=1
   APP_ENV=test
   ```
   `channel=chrome` 和 `headless=false` 已内置在 `config/envs/test.yaml`,
   无需通过环境变量设置. 假页面用例 (`test_login_normal_scenario`) 无需任何环境变量.

> **注意**: 不要选 `projects/jmseu/.venv` (空壳, 无依赖) 或 `pytest.exe` (应选 `python.exe`).
> uv workspace venv 含 framework + playwright + pytest 全部依赖.

## LoginPage 选择器

选择器基于 Playwright 录制器对真实 test 环境的录制, 集中在 `LoginPage` 类:

| 常量              | 值                                    | 说明               |
| ----------------- | ------------------------------------- | ------------------ |
| `USERNAME_INPUT`  | `input[placeholder='请输入员工编号']` | 用户名输入框       |
| `PASSWORD_INPUT`  | `input[placeholder='请输密码']`       | 密码输入框         |
| `LOGIN_BUTTON`    | `button:has-text('登录')`             | 登录按钮           |
| `REMEMBER_PWD`    | `.rp-check`                           | 记住密码复选框     |
| `COOKIE_ACCEPT`   | `text=接受全部`                       | Cookie consent 按钮 |
| `WELCOME_TEXT`    | `.welcome`                            | 欢迎信息           |

## 滑块验证码处理

登录提交后出现腾讯滑块验证码 (tencent-captcha-dy). `TencentSliderCaptcha`
封装在 `pages/captcha_page.py`, 继承 `BasePage`:

**缺口检测**: 截图背景图 (`img[alt="背景"]`) 为 PNG, 转为 data URL 传入
浏览器内 JS, 通过 canvas `getImageData` 分析每列像素亮度, 找到显著暗于
平均值的列 (缺口阴影左边缘). 根据元素 bounding box 将图像像素坐标转换为
屏幕拖拽距离. 无需额外 Python 依赖 (Pillow/numpy), 全部在浏览器内完成.

**拟人拖拽**: `generate_trajectory(distance)` 生成 (dx, dy, delay_ms) 序列:
Phase 1 用 ease-out-cubic 加速到 目标+过冲, Phase 2 用 3-5 步修正回目标.
每步加入 +/-1px 垂直抖动和 8-50ms 随机延迟. 通过 `page.mouse` 的
move/down/up 执行拖拽 (录制器只能 click, 无法产生 drag).

**重试**: 拖拽后等待 1.5s 检测验证结果 (滑块区域是否消失). 失败则点击
"刷新验证" 获取新图, 最多重试 3 次.

| 选择器                                    | 说明            |
| ----------------------------------------- | --------------- |
| `img[alt="滑块"]`                         | 滑块手柄        |
| `img[alt="背景"]`                         | 背景图 (含缺口) |
| `.tencent-captcha-dy__verify-slider-area` | 滑块轨道区域    |
| `button:has-text("刷新验证")`             | 刷新验证码      |

> **注意**: 验证码自动化本质脆弱, 腾讯可能更新验证逻辑. CI 默认使用假页面
> 跳过验证码 (rule 14). 真实浏览器测试需要 `JMSEU_REAL_BROWSER=1`.