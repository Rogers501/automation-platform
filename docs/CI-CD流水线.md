# CI/CD 流水线

> 项目 CI/CD 流水线的设计与使用说明. 覆盖 `scripts/ci/ci.sh`、`.gitlab-ci.yml`、
> `Jenkinsfile` 三者的关系与本地复现步骤.

## 1. 总体设计

### 1.1 核心原则

**单入口**: 所有流水线命令集中在 `scripts/ci/ci.sh`, GitLab CI 和 Jenkins
**共用同一入口**, 避免命令重复.

```
.gitlab-ci.yml  ──┐
                   ├──▶ sh scripts/ci/ci.sh <command>
Jenkinsfile     ──┘
```

好处: 改命令只动 `ci.sh` 一处, 两个 CI 系统自动同步.

### 1.2 流水线阶段

```
提交代码
   ↓
[lint]   ruff check + ruff format --check + mypy
   ↓
[smoke]  pytest -m smoke -n auto         (冒烟, 快速门禁)
   ↓
[regression]  pytest -m regression -n auto  (全量回归)
   ↓
[report] allure generate → GitLab Pages / Jenkins Allure Plugin
```

| 阶段 | 命令 | 失败处理 |
| --- | --- | --- |
| lint | `ci.sh lint` | 阻断后续阶段 |
| smoke | `ci.sh smoke` | 阻断 regression |
| regression | `ci.sh regression` | 仍生成报告(artifacts always) |
| report | `ci.sh report` | 仅 main / tag 触发 |

## 2. ci.sh 命令清单

### 2.1 命令一览

| 命令 | 作用 | 关键依赖 |
| --- | --- | --- |
| `install` | `uv sync --frozen` + 安装 `allure-pytest` | uv |
| `install-allure` | 安装 allure CLI + JRE (Debian, 需 root) | apt-get |
| `lint` | ruff check + ruff format --check + mypy | uv |
| `smoke` | `pytest -m smoke -n auto` + allure 结果 + junit | uv, pytest-xdist |
| `regression` | `pytest -m regression -n auto` + allure 结果 + junit | uv, pytest-xdist |
| `report` | `allure generate` 生成 HTML | allure CLI |
| `clean` | 删除 allure 结果与报告目录 | - |

### 2.2 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ALLURE_RESULTS` | `allure-results` | pytest 写入 allure 结果目录 |
| `ALLURE_REPORT` | `allure-report` | HTML 报告输出目录 |
| `ALLURE_VERSION` | `2.30.0` | allure CLI 版本 (install-allure 用) |
| `UV_VERSION` | `0.11.14` | uv 版本 |
| `XDIST_WORKERS` | `auto` | pytest-xdist 并发数 |
| `JUNIT` | `reports/junit.xml` | JUnit XML 输出 |

## 3. GitLab CI

### 3.1 配置文件

`.gitlab-ci.yml`, 关键点:

- **默认镜像**: `python:3.12-slim`, ci.sh 自动装 uv + allure-pytest
- **加速**: 构建预装镜像 `docker/Dockerfile.ci`, 设 `CI_IMAGE=registry/automation-platform:ci`
- **缓存**: 按 `uv.lock` 内容做 cache key, 缓存 `.uv-cache/` 与 `.venv/`
- **artifacts**: smoke 与 regression 阶段产物 `allure-results/` + `reports/junit.xml`
- **Pages**: main/tag 上把 allure-results 合并生成 HTML 发布到 GitLab Pages

### 3.2 阶段配置

```yaml
stages:
  - lint
  - smoke
  - regression
  - report
```

| Job | Stage | 依赖 | 说明 |
| --- | --- | --- | --- |
| `lint` | lint | - | ruff + mypy, 失败阻断 |
| `smoke` | smoke | install | 冒烟测试, 产物 allure-results + junit |
| `regression` | regression | smoke | 回归测试, 产物 allure-results + junit |
| `pages` | report | smoke + regression | 生成 HTML 发布 Pages |

### 3.3 本地复现 (Linux/Mac)

```bash
# 装 Python 3.12 + uv
sh scripts/ci/ci.sh install           # uv sync --frozen + allure-pytest

# 跑 lint
sh scripts/ci/ci.sh lint

# 跑冒烟
sh scripts/ci/ci.sh smoke

# 跑回归
sh scripts/ci/ci.sh regression

# 装 allure CLI (生成 HTML 报告)
sh scripts/ci/ci.sh install-allure

# 生成 HTML
sh scripts/ci/ci.sh report
```

### 3.4 使用预构建 CI 镜像加速

默认 `python:3.12-slim` 每次都要装 uv + allure, 慢. 用 CI 镜像加速:

```bash
# 1. 构建 CI 镜像
docker build -f docker/Dockerfile.ci -t automation-platform:ci .

# 2. 推到 registry
docker tag automation-platform:ci registry.example.com/automation-platform:ci
docker push registry.example.com/automation-platform:ci

# 3. GitLab CI 配置 (Settings → CI/CD → Variables)
# CI_IMAGE=registry.example.com/automation-platform:ci
```

CI 镜像已预装: Python 3.12 + uv + JRE + allure CLI 2.30.0, `install-allure`
变 no-op.

## 4. Jenkins

### 4.1 配置文件

`Jenkinsfile`, 声明式流水线, 关键点:

- **Agent**: docker agent, 默认 `python:3.12-slim`, 通过 `CI_IMAGE` 环境变量覆盖
- **uv 缓存**: 挂载 `$HOME/.cache/uv:/root/.cache/uv` 提速
- **Allure**: 用 Jenkins Allure Plugin (`allure` step), **agent 上无需装 allure CLI**
- **JUnit**: `post.always` 收集 `reports/junit.xml`

### 4.2 阶段配置

```groovy
stages {
    stage('Install')    { sh 'sh scripts/ci/ci.sh install' }
    stage('Lint')       { sh 'sh scripts/ci/ci.sh lint' }
    stage('Smoke')      { sh 'sh scripts/ci/ci.sh smoke' }
    stage('Regression') { sh 'sh scripts/ci/ci.sh regression' }
}
```

### 4.3 前置依赖

Jenkins controller 需要:

1. **Allure Plugin** (Jenkins 管理界面 → 插件管理 → 搜 "Allure")
2. **Docker agent** (能拉 `python:3.12-slim` 或自定义 CI_IMAGE)

### 4.4 使用预构建 CI 镜像

```groovy
// 在 Jenkins 项目配置里设环境变量
environment {
    CI_IMAGE = 'registry.example.com/automation-platform:ci'
}
```

或在 Jenkinsfile 改默认值:

```groovy
image "${env.CI_IMAGE ?: 'registry.example.com/automation-platform:ci'}"
```

## 5. 测试分级 (pytest marker)

### 5.1 marker 定义

`pytest.ini` 注册了两个 marker, 并启用 `--strict-markers` (未注册 marker 报错):

| marker | 用途 | CI 时机 |
| --- | --- | --- |
| `@pytest.mark.smoke` | 关键路径, 快速门禁 | 每次提交 |
| `@pytest.mark.regression` | 全量回归 | 回归阶段 |

### 5.2 用例示例

```python
@pytest.mark.smoke
async def test_login_returns_token(http_client):
    ...

@pytest.mark.regression
async def test_create_user_full_flow(api_client):
    ...
```

### 5.3 本地按 marker 跑

```bash
uv run pytest -m smoke          # 只跑冒烟
uv run pytest -m regression    # 只跑回归
uv run pytest -m "smoke or regression"   # 都跑
uv run pytest -m "not slow"    # 排除 slow
```

## 6. Allure 报告

### 6.1 结果产物

pytest 跑完会生成:

| 路径 | 说明 |
| --- | --- |
| `allure-results/*.json` | 每个用例一个 JSON (状态/耗时/步骤/标签) |
| `reports/junit.xml` | JUnit XML, CI 系统展示用 |

### 6.2 HTML 报告生成

```bash
# 装 allure CLI (CI 镜像已预装)
sh scripts/ci/ci.sh install-allure

# 生成 HTML (从 allure-results → allure-report)
sh scripts/ci/ci.sh report
```

### 6.3 CI 系统报告发布

| CI | 发布方式 |
| --- | --- |
| GitLab CI | `pages` job 把 `public/` 发布到 GitLab Pages |
| Jenkins | `post.always` 用 Allure Plugin `allure results: [...]` 步骤 |

GitLab Pages URL: `https://<group>.gitlab.io/<project>/`

Jenkins 报告链接: 在构建页面 "Allure Report" 图标点击.

## 7. 本地验证 CI 流程

### 7.1 用 Dockerfile.ci 跑一遍

```bash
# 1. 构建 CI 镜像
docker build -f docker/Dockerfile.ci -t automation-platform:ci .

# 2. 跑全部阶段(模拟 CI)
docker run --rm -v "$(pwd):/app" -w /app automation-platform:ci \
    sh -c "sh scripts/ci/ci.sh install && \
           sh scripts/ci/ci.sh lint && \
           sh scripts/ci/ci.sh smoke && \
           sh scripts/ci/ci.sh regression && \
           sh scripts/ci/ci.sh install-allure && \
           sh scripts/ci/ci.sh report"

# 3. 本地查看报告
# allure-report/index.html
```

### 7.2 跳过特定阶段

```bash
# 只验证 lint
sh scripts/ci/ci.sh install
sh scripts/ci/ci.sh lint
```

## 8. 本地 GitLab CI 配置

如需在本地 GitLab (`http://10.66.67.26:8929`) 跑流水线:

1. 推送代码到本地 GitLab (`git push gitlab main`)
2. 在 Web UI → 项目 → Settings → CI/CD:
   - Runners: 注册一个 runner (shell executor 或 docker executor)
   - Variables: 设 `CI_IMAGE` 等覆盖
3. 提交代码后自动触发 pipeline

> 本地 GitLab 部署见 `docs/GitLab本地部署.md`.

## 9. 故障排查

### 9.1 lint 失败

```bash
sh scripts/ci/ci.sh lint
# 看具体报错, 本地修复:
uv run ruff check --fix . && uv run ruff format .
uv run mypy
```

### 9.2 smoke 失败

```bash
# 本地复现
uv run pytest -m smoke -v --tb=long
```

### 9.3 allure report 生成失败

```bash
# 检查 allure CLI 是否装好
allure --version

# 装一遍
sh scripts/ci/ci.sh install-allure
```

### 9.4 CI 慢

- 用预构建 CI 镜像 (`CI_IMAGE=registry/automation-platform:ci`)
- 增大缓存命中 (uv.lock 不变时 `.venv/` 直接复用)
- 用 `XDIST_WORKERS=auto` 充分利用 CPU

### 9.5 JUnit 报告缺失

```bash
# ci.sh 默认写到 reports/junit.xml
# 如果 CI 系统找不到, 检查 artifacts paths 是否包含:
#   reports/junit.xml
```
