# Automation Platform

企业级 Python 自动化测试平台。共享框架内核 + 各业务系统独立测试代码，覆盖接口自动化（首阶段）、数据库/缓存/消息校验、数据驱动、接口依赖、并发执行与 Allure 报告，后续扩展 Web/App 与 AI Agent。

## 技术栈

Python 3.12 · pytest · httpx · pydantic v2 · allure · loguru · sqlalchemy · redis · asyncio · pytest-xdist(已集成) · playwright(已集成) · appium(已集成) · AI LLM(已集成)

依赖管理使用 uv；`pyproject.toml` + `uv.lock` 为唯一来源，`requirements.txt` 为导出产物。

## 目录结构

```
automation-platform/
├── framework/                  # 共享框架核心（uv 工作区成员，可编辑安装）
│   ├── pyproject.toml
│   └── src/framework/
│       ├── core/               # 配置/日志/上下文/异常/注册中心（Phase 1）
│       ├── clients/            # 能力客户端
│       │   ├── http/           # 接口自动化（httpx，Phase 2）
│       │   ├── web/            # Web 自动化（playwright，已集成）
│       │   ├── app/            # App 自动化（appium，已集成）
│       │   ├── db/             # 数据库（sqlalchemy，Phase 4）
│       │   ├── cache/          # Redis（Phase 4）
│       │   └── mq/             # Kafka / RabbitMQ / RocketMQ（三端已集成）
│       ├── testing/            # 测试基础设施
│       │   ├── datadriven/     # 数据驱动（Phase 3）
│       │   ├── dependency/     # 接口依赖编排（Phase 3）
│       │   ├── extractors/     # 响应提取（Phase 2）
│       │   └── assertions/     # 断言库（Phase 2）
│       ├── reporting/          # Allure 报告扩展
│       ├── plugins/            # 插件与扩展点
│       │   └── ai/             # AI 失败分析（FailureAnalyzer + LLMAnalyzer，已集成）
│       └── utils/              # 通用工具
├── projects/                    # 业务系统测试工程（template 模板，oms/wms/tms + jms 系列）
├── server/                      # 测试管理平台后端（FastAPI + pytest 执行器）
├── frontend/                    # 测试管理平台前端（Vue 3 + Element Plus）
├── config/envs/                # 全局环境配置
├── docker/                     # Dockerfile 与本地依赖编排
│   ├── Dockerfile
│   └── docker-compose.yml
├── scripts/ci/                # CI 统一入口 ci.sh（GitLab+Jenkins 共用）
├── tests/                      # 框架自身单元/集成测试
├── conftest.py
├── pyproject.toml              # 项目元数据 + uv 工作区 + mypy
├── ruff.toml                   # ruff 配置
├── pytest.ini                  # pytest 配置
├── requirements.txt            # 由 uv.lock 导出（勿手改）
├── .pre-commit-config.yaml
├── Makefile
├── .gitlab-ci.yml
├── .env.example
├── AI_RULES.md                 # AI 开发红线（16 条）
└── README.md
```

## 业务系统命名约定

JMS 系统按国家/地区部署，文件夹命名规则：**jms + 2 位地区代码**。新增国家时
用户直接告知文件夹名（如 jmsus = 美国），按 template 结构复制即可。

| 文件夹   | 地区         | 代码来源        | 类型   |
| -------- | ------------ | --------------- | ------ |
| jmseg  | 埃及 Egypt   | EG (ISO 国家码) | API    |
| jmseu  | 德国 Germany | EU (欧洲)       | WebUI  |

其他业务系统（oms/wms/	ms）直接用系统缩写命名。详见各项目 README。

## 快速开始

```bash
uv sync                          # 装 Python 3.12 + 工作区成员 framework，生成/更新 uv.lock
uv run pytest                    # 运行测试（串行）
uv run pytest -n auto            # 并发执行（pytest-xdist，CI 默认）
make test-parallel              # 并发执行（等价）
uv run ruff check .              # 静态检查
uv run ruff format --check .     # 格式检查
uv run mypy                      # 类型检查
```

一键修复：`uv run ruff check --fix . && uv run ruff format .`

提交钩子：`uv run pre-commit install`

## requirements.txt

由 `uv.lock` 导出，便于非 uv 环境用 pip 安装；勿手动编辑。重新生成：

```bash
uv export --frozen -o requirements.txt            # 含开发依赖
uv export --frozen --no-dev -o requirements.txt    # 仅运行时依赖
```

## Docker

```bash
docker build -f docker/Dockerfile -t automation-platform:dev .
docker run --rm automation-platform:dev uv run pytest

# 本地测试依赖（MySQL / Redis / Kafka）
docker compose -f docker/docker-compose.yml up -d
```

## CI/CD

流水线：代码提交 → 安装依赖 → 冒烟测试（smoke）→ 回归测试（regression）→ 生成 Allure → 发布报告。
所有命令集中在 `scripts/ci/ci.sh`，GitLab 与 Jenkins 共用同一入口（避免重复）。

测试分级用 pytest marker：`@pytest.mark.smoke`（关键路径，每次提交快速门禁）与
`@pytest.mark.regression`（全量，回归阶段）。marker 已在 `pytest.ini` 注册并启用 `--strict-markers`。

**GitLab CI**（`.gitlab-ci.yml`）：stages = lint → smoke → regression → report。
默认镜像 `python:3.12-slim`（ci.sh 自动装 uv + allure-pytest）；设 `CI_IMAGE` 用预构建镜像加速。
`pages` 任务在 main/tag 上生成 Allure HTML 并发布到 GitLab Pages。

**Jenkins**（`Jenkinsfile`）：声明式流水线，docker agent，命令同样走 `scripts/ci/ci.sh`；
报告用 Jenkins Allure Plugin（`allure` step）发布，无需在 agent 装 allure CLI。

**CI 镜像**（`docker/Dockerfile.ci`）：预装 Python 3.12 + uv + JRE + allure CLI 2.30.0。

```bash
docker build -f docker/Dockerfile.ci -t automation-platform:ci .
# GitLab: variables: { CI_IMAGE: "registry/automation-platform:ci" }
# Jenkins: CI_IMAGE='registry/automation-platform:ci'
```

本地复现 CI 命令（Linux）：

```bash
sh scripts/ci/ci.sh install      # uv sync --frozen + allure-pytest
sh scripts/ci/ci.sh smoke        # pytest -m smoke
sh scripts/ci/ci.sh regression   # pytest -m regression
sh scripts/ci/ci.sh install-allure && sh scripts/ci/ci.sh report   # 生成 Allure HTML
```
## Makefile（Linux/CI）

```bash
make sync lint format type test test-cov
```

Windows 无 make 时直接使用 `uv run ...` 命令。

## 文档索引

完整文档导航见 [`docs/文档索引.md`](docs/文档索引.md).

| 文档 | 用途 | 受众 |
| --- | --- | --- |
| `AI_RULES.md` | 16 条开发红线(不可违反) | AI 助手 + 开发者 |
| `AGENTS.md` | 任务执行规范(会话启动/探索/留痕) | AI 助手 |
| `docs/文档索引.md` | 全部文档统一导航 | 全员 |
| `docs/快速上手.md` | 从 0 到第一个用例(30 分钟) | 新人 |
| `docs/用户手册.md` | 完整操作手册(配置/运行/扩展/维护) | 使用者 |
| `docs/架构设计.md` | 概要设计 + 详细设计(架构/分层/模块/扩展点) | 测试开发 |
| `docs/概要设计文档.md` | 测试管理平台后端概要设计(已填充实例) | 测试开发 + 架构师 |
| `docs/详细设计文档.md` | 测试管理平台后端详细设计(已填充实例) | 测试开发 |
| `docs/概要设计模板.md` | 概要设计模板(通用,含占位符,复制使用) | 测试开发 |
| `docs/详细设计模板.md` | 详细设计模板(通用,含占位符,复制使用) | 测试开发 |
| `docs/部署与运维.md` | Docker / 一键启动 / 备份恢复 / 镜像管理 | 运维 + 测试开发 |
| `docs/CI-CD流水线.md` | ci.sh / GitLab CI / Jenkins 三者关系与本地复现 | 测试开发 + CI 维护 |
| `docs/GitLab本地部署.md` | 部门协同用的本地 GitLab 服务(地址/账号/同事使用) | 运维 + 同事 |
| `docs/测试管理平台技术方案.md` | 测试管理平台架构、流程、运行方式与演进规划 | 测试开发 + 使用者 |
| `docs/协作留痕.docx` | 架构开发留痕(对话累积) | AI 助手 + 开发者 |
| `docs/业务留痕-<国家>.docx` | 各国业务测试留痕 | AI 助手 + 开发者 |
| `方案.docx` | 平台搭建教程(外部视角,参考用) | 参考 |

## 阶段进度

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| 0 | 工程地基（uv / 工具链 / CI 骨架 / 冒烟测试） | 完成 |
| 0+ | 完整目录结构与基础设施文件 | 完成 |
| 1 | 框架核心（config / logger / context / exceptions / registry） | 完成 |
| 2 | API 能力 + 基础设施（http client / extractors / assertions） | 完成 |
| 3 | 数据驱动 + 接口依赖（datadriven / dependency DAG / variables） | 完成 |
| 4 | DB / Cache / MQ（Kafka + RabbitMQ + RocketMQ 三端） | 完成 |
| 5 | 并发执行（pytest-xdist）+ Allure 报告（attach/labels/environment/categories） | 完成 |
| 6 | Web/App 扩展（Playwright WebClient + Appium AppClient） | 完成 | (含腾讯滑块验证码自动求解器 TencentCaptchaSolver: OpenCV 缺口检测 + 人类轨迹模拟)
| 7 | CI/CD + Docker（GitLab CI / Jenkins / Dockerfile / docker-compose） | 完成 |
| 8 | AI 失败分析（FailureAnalyzer ABC + NullAnalyzer + LLMAnalyzer） | 完成 |
| 9 | 集成验证 + Allure 报告增强 + 文档同步 | 完成 |
| 10 | 数据生命周期 + AI用例生成 + 邮件通知/Allure历史 + 业务系统脚手架(oms/wms/tms) | 完成 |
| 11 | 接口压测引擎（Locust + YAML 场景 + 数据驱动 + SLA + HTML 报告） | 完成 |
| 12 | 数据源拉取脚本（生产运单库分页查询 -> CSV/TXT） | 完成 |
| 13 | 测试管理平台（FastAPI + Vue 3：查用例 / 跑用例 / 看报告） | 完成 |

原始 16 项目标全部功能实现。

## 设计决策（已确认）

### 测试管理平台

面向不写代码的测试人员，提供项目查询、用例查询、测试执行、报告查看四个入口。

```powershell
# 可选：启动本地 MySQL（首次会拉取镜像）
docker compose -f docker/docker-compose.yml up -d mysql

# 首次使用先安装依赖
.\.venv\Scripts\python.exe -m pip install -r server/requirements.txt
cd frontend; npm install

# 终端 1 启动后端
powershell -ExecutionPolicy Bypass -File scripts/start_backend.ps1

# 终端 2 启动前端
powershell -ExecutionPolicy Bypass -File scripts/start_frontend.ps1
```

或一键启动（MySQL 容器 + 后端 + 前端，单终端）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_all.ps1
```

脚本内部自动加载/导出 MySQL 离线镜像、启动容器并等待健康检查、启动后端并轮询 `/api/health`、启动前端 Vite。脚本头部强制 `chcp 65001` + UTF-8 输出，避免中文乱码。

访问 http://localhost:5173（开发模式），接口文档 http://localhost:8900/docs。

### 容器化部署（生产模式，给同事访问）

本地开发用上面的 `start_all.ps1`；给同事访问用容器化部署（nginx 托管 + 后端容器化）：

```bash
cd docker
docker compose build backend frontend
docker compose up -d mysql backend frontend
```

访问 http://10.66.67.26:8080（同事浏览器打开即用，无需装环境）。
首次部署需放行 Windows 防火墙 8080 端口，详见 `docs/部署与运维.md` §3.5。

### MySQL 数据持久化

MySQL 数据目录绑定在项目本地 `data/mysql/`，Docker Desktop 更新、卸载或容器重建都不会删除该目录。定期备份执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/backup_mysql.ps1
```

恢复备份：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/restore_mysql.ps1 -BackupFile data\backups\<backup.sql>
```

如需防止 Docker 镜像丢失，可导出离线镜像（文件在 `data/docker-images/`，不入 Git）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/save_mysql_image.ps1
docker load -i data\docker-images\mysql-8.4.tar
```

- 依赖管理：uv
- 优先级：API 优先（已完成闭环），Web/App 已实现（Playwright + Appium）
- MQ：三端已集成（Kafka / RabbitMQ / RocketMQ），统一 MessageClient 接口，可扩展
- AI：已实现 on_failure 失败分析（FailureAnalyzer ABC + LLMAnalyzer），后续可扩展自动生成用例
- 可选依赖均为 lazy import：playwright / appium / selenium / rocketmq / aio-pika，未安装时不影响运行

## AI 开发红线

见 `AI_RULES.md`（16 条），本助手每次任务开始前读取并遵守。
