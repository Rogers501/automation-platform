# GitLab 本地部署指南

> 本文档记录在部门内部本地搭建 GitLab CE 的完整流程, 用于团队协同开发.
> 独立于个人 gitee / github 仓库, 避免部门协作污染个人代码空间.

## 1. 概述

### 1.1 部署目标

| 项 | 说明 |
| --- | --- |
| 服务 | GitLab CE (社区版) |
| 部署方式 | Docker Desktop + docker-compose |
| 持久化 | 绑定挂载到 `C:/docker-data/git-server/` |
| 端口 | HTTP 8929 / SSH 2224 |
| 访问范围 | 部门内网, 通过宿主机 IP 访问 |
| 镜像备份 | 已导出 tar 文件, Docker 重装/换机器可恢复 |

### 1.2 与个人仓库的关系

```
本地开发机
├─ origin  → gitee.com / github.com (个人仓库, 不被部门协作污染)
└─ gitlab  → 10.66.67.26:8929      (本地 GitLab, 部门协同)
```

两条 remote 路径完全独立, 推送/拉取互不影响.

## 2. 服务信息

### 2.1 访问地址

| 类型 | 地址 |
| --- | --- |
| Web UI | http://10.66.67.26:8929 |
| HTTP 克隆 | `http://10.66.67.26:8929/root/automation-platform.git` |
| SSH 克隆 | `ssh://git@10.66.67.26:2224/root/automation-platform.git` |

> IP `10.66.67.26` 是宿主机内网 IP, 同事通过此 IP 访问.

### 2.2 账号

| 角色 | 用户名 | 密码 | 权限 |
| --- | --- | --- | --- |
| 管理员 | `root` | 见容器内 `/etc/gitlab/initial_root_password`, **首次登录后请改密** | 全部 |
| 团队共享账号 | `team` | `AutoDev2026!Xq` | Maintainer (可 push 到 main) |

> 注册已关闭: 新同事账号由 root 在 Web UI (Admin Area → Users) 创建分发.

### 2.3 关键文件路径

| 路径 | 说明 |
| --- | --- |
| `docker/gitlab/docker-compose.yml` | docker-compose 配置 |
| `C:/docker-data/git-server/config/` | GitLab 配置 (持久化) |
| `C:/docker-data/git-server/data/` | 仓库数据 (持久化) |
| `C:/docker-data/git-server/logs/` | 日志 (持久化) |
| `C:/docker-data/git-server/images/gitlab-ce-latest.tar` | 镜像 tar 备份 (1.4GB) |
| `C:/docker-data/git-server/images/README.md` | 镜像备份说明 |

## 3. 部署详情

### 3.1 docker-compose 配置

`docker/gitlab/docker-compose.yml`:

```yaml
services:
  gitlab:
    image: gitlab/gitlab-ce:latest
    container_name: gitlab
    restart: unless-stopped
    hostname: 10.66.67.26
    environment:
      GITLAB_OMNIBUS_CONFIG: |
        external_url 'http://10.66.67.26:8929'
        gitlab_rails['gitlab_shell_ssh_port'] = 2224
        gitlab_rails['gitlab_signup_enabled'] = false
        prometheus_monitoring_enable = false
        sidekiq['max_concurrency'] = 5
        puma['worker_processes'] = 2
        gitlab_rails['backup_keep_time'] = 604800
    ports:
      - "8929:8929"   # HTTP
      - "2224:22"     # SSH
    volumes:
      - C:/docker-data/git-server/config:/etc/gitlab
      - C:/docker-data/git-server/data:/var/opt/gitlab
      - C:/docker-data/git-server/logs:/var/log/gitlab
    shm_size: '256m'
```

### 3.2 关键配置说明

| 配置项 | 值 | 说明 |
| --- | --- | --- |
| `external_url` | `http://10.66.67.26:8929` | GitLab 显示在 Web UI 的克隆地址前缀, 同事看到的就是这个 |
| `gitlab_shell_ssh_port` | 2224 | SSH 克隆端口 (容器内 22, 宿主机 2224) |
| `gitlab_signup_enabled` | false | 关闭自助注册, 账号由管理员分发 |
| `prometheus_monitoring_enable` | false | 关闭监控, 减少内存占用 |
| `puma['worker_processes']` | 2 | Web 进程数, 部门规模够用 |
| `shm_size` | 256m | 共享内存, 避免 GitLab 处理大仓库 OOM |

### 3.3 资源占用

| 资源 | 占用 | 备注 |
| --- | --- | --- |
| 镜像大小 | 1.45GB | `gitlab/gitlab-ce:latest` |
| 容器内存 | ~3-4GB | 启动后稳定值 |
| 磁盘 | 持续增长 | 取决于仓库大小与 CI 产物 |

> 推荐宿主机至少 16GB 内存, Docker Desktop 至少分配 8GB.

## 4. 镜像与备份

### 4.1 镜像来源

由于 Docker Hub 国内访问不稳定, 镜像通过 `docker.1ms.run` 拉取后重新打 tag:

```bash
docker pull docker.1ms.run/gitlab/gitlab-ce:latest
docker tag docker.1ms.run/gitlab/gitlab-ce:latest gitlab/gitlab-ce:latest
```

### 4.2 镜像 tar 备份

已导出至 `C:/docker-data/git-server/images/gitlab-ce-latest.tar` (1.4GB).
防止 Docker Desktop 重装或 GC 删除镜像:

```bash
# 导出(已完成, 仅记录)
docker save gitlab/gitlab-ce:latest -o C:/docker-data/git-server/images/gitlab-ce-latest.tar

# 恢复
docker load -i C:/docker-data/git-server/images/gitlab-ce-latest.tar
```

### 4.3 数据持久化

GitLab 的配置/数据/日志均挂载到 `C:/docker-data/git-server/`, **Docker Desktop
升级/重装/容器重建都不会丢失数据**.

### 4.4 GitLab 备份

GitLab 内置备份命令 (备份数据库 + 仓库):

```bash
# 进入容器执行备份 (产物在 /var/opt/gitlab/backups, 已挂载到宿主机)
docker exec -t gitlab gitlab-backup create

# 恢复
docker exec -t gitlab gitlab-backup restore BACKUP=<timestamp>
```

配置文件 `/etc/gitlab/gitlab.rb` 与 `/etc/gitlab/gitlab-secrets.json` 需要单独
备份 (已挂在宿主机 `C:/docker-data/git-server/config/`).

## 5. 同事使用指南

### 5.1 首次使用

1. 向 root 申请 team 账号密码
2. 浏览器访问 http://10.66.67.26:8929 登录
3. 在 User Settings → Password 修改初始密码

### 5.2 克隆仓库

**HTTP (推荐, 无需 SSH key)**:

```bash
git clone http://10.66.67.26:8929/root/automation-platform.git
# 第一次会提示输入账号密码: team / AutoDev2026!Xq
# 可配置凭据缓存避免重复输入:
git config --global credential.helper manager    # Windows
git config --global credential.helper store      # Linux
```

**SSH (需要先添加公钥到 GitLab)**:

```bash
# 1. 本地生成 SSH key (已生成可跳过)
ssh-keygen -t ed25519 -C "your.name@team.com"

# 2. 复制公钥
cat ~/.ssh/id_ed25519.pub   # Windows: type %USERPROFILE%\.ssh\id_ed25519.pub

# 3. 在 GitLab Web UI: User Settings → SSH Keys → Add, 粘贴公钥

# 4. 克隆
git clone ssh://git@10.66.67.26:2224/root/automation-platform.git
```

### 5.3 日常推送

```bash
git add .
git commit -m "feat: ..."
git push origin main       # 推到部门本地 GitLab
```

> 注意: 本仓库的 remote 名是 `gitlab` 而非 `origin` (origin 指向个人 gitee/github).
> 见根目录 `git remote -v`.

### 5.4 防火墙 (管理员)

如果同事通过 IP 访问不到, 需在宿主机 Windows 防火墙放行端口:

```powershell
# 以管理员运行 PowerShell
New-NetFirewallRule -DisplayName "GitLab HTTP" -Direction Inbound -Protocol TCP -LocalPort 8929 -Action Allow
New-NetFirewallRule -DisplayName "GitLab SSH" -Direction Inbound -Protocol TCP -LocalPort 2224 -Action Allow
```

## 6. 运维命令

### 6.1 启停

```bash
cd C:/work/PythonProject/automation-platform/docker/gitlab

docker compose up -d          # 启动
docker compose down          # 停止并移除容器(数据保留)
docker compose restart       # 重启
docker compose logs -f       # 看日志
```

### 6.2 状态检查

```bash
docker ps --filter "name=gitlab"
# 期望: Up X minutes (healthy)
```

### 6.3 重置 root 密码

如果忘记 root 密码:

```bash
docker exec -it gitlab gitlab-rake "gitlab:password:reset[root]"
# 按提示输入新密码
```

### 6.4 创建新同事账号 (root 在 Web UI)

1. 登录 Web UI → Admin Area (顶部菜单扳手图标)
2. Overview → Users → New user
3. 填写 Name / Username / Email
4. 创建后点击用户 → Edit → 设密码
5. Projects → automation-platform → Members → 添加该用户 → 角色选 Maintainer

## 7. 故障排查

### 7.1 容器一直 `health: starting`

GitLab 启动需 3-5 分钟, 耐心等待. 如超过 10 分钟:

```bash
docker logs gitlab --tail 50
# 看是否有 PostgreSQL / Redis 启动失败
```

### 7.2 Web UI 502

```bash
docker exec gitlab gitlab-ctl status
# 期望所有服务 run 状态
docker exec gitlab gitlab-ctl restart
```

### 7.3 推送报 `403 Forbidden`

- 确认账号在项目成员里且角色 >= Developer
- 推 main 分支需要 >= Maintainer (GitLab 默认保护 main)
- 或 root 在 Project Settings → Repository → Protected Branches 调整

### 7.4 SSH 推送失败

- 确认 SSH key 已添加到 GitLab 用户
- 确认走 2224 端口: `ssh -T -p 2224 git@10.66.67.26` 应返回欢迎信息
- 检查宿主机防火墙 2224 端口是否放行

## 8. 后续演进

| 演进项 | 说明 | 优先级 |
| --- | --- | --- |
| HTTPS | 配置 SSL 证书 (内网可用自签名或内部 CA) | 中 |
| 备份脚本 | 定时执行 `gitlab-backup create` 并归档到 NAS | 高 |
| CI Runner | 接 GitLab CI Runner 跑项目流水线 (替代外部 GitLab CI) | 中 |
| LDAP 接入 | 接企业 LDAP/AD 做统一认证 | 低 |
