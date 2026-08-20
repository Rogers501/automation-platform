# scripts/start_all.ps1
# 一键启动：加载 MySQL 离线镜像 → 启动 MySQL 容器 → 启动后端 FastAPI → 启动前端 Vite
# 运行方式：在项目根目录的 PowerShell 里执行
#   powershell -ExecutionPolicy Bypass -File .\scripts\start_all.ps1

param(
    [switch]$Verbose = $false
)

# 控制台强制 UTF-8，避免中文输出乱码
try {
    chcp 65001 > $null
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    # 旧环境可能不支持 chcp，忽略即可
}

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "`n========== 一键启动开始 ==========" -ForegroundColor Cyan

# -------------------------------------------------
# 1️⃣ 确保 MySQL 离线镜像存在（若没有则从当前 docker 导出一次）
# -------------------------------------------------
$ImageTar = Join-Path $ProjectRoot 'data\docker-images\mysql-8.4.tar'
if (-not (Test-Path $ImageTar)) {
    Write-Host ">>> 未发现离线镜像，正在从本地 Docker 导出 ..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path (Split-Path $ImageTar) | Out-Null
    docker save -o $ImageTar mysql:8.4
    Write-Host ">>> 镜像已导出到 $ImageTar" -ForegroundColor Green
} else {
    Write-Host ">>> 离线镜像已存在，跳过导出" -ForegroundColor Green
}

# -------------------------------------------------
# 2️⃣ 确保数据目录存在（compose 里会挂载这里）
# -------------------------------------------------
$DataDir = Join-Path $ProjectRoot 'data\mysql'
if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    Write-Host ">>> 已创建持久化数据目录 $DataDir" -ForegroundColor Green
}

# -------------------------------------------------
# 3️⃣ 清理旧容器并启动 MySQL（映射 data/mysql 为持久化卷）
# -------------------------------------------------
$ContainerName = 'docker-mysql-1'
docker rm -f $ContainerName 2>$null | Out-Null

Write-Host ">>> 正在启动 MySQL 容器 ..." -ForegroundColor Yellow
docker run -d `
    --name $ContainerName `
    -p 3306:3306 `
    -e MYSQL_ROOT_PASSWORD=rootpw `
    -e MYSQL_DATABASE=automation `
    -e MYSQL_USER=tester `
    -e MYSQL_PASSWORD=testerpw `
    -v "${PWD}/data/mysql:/var/lib/mysql" `
    --health-cmd="mysqladmin ping -h localhost -uroot -prootpw" `
    --health-interval=10s `
    --health-timeout=5s `
    --health-retries=10 `
    mysql:8.4 | Out-Null

# 等待容器健康检查通过（最多 3 分钟）
Write-Host ">>> 等待 MySQL 健康检查 ..." -ForegroundColor Yellow
$Deadline = (Get-Date).AddMinutes(3)
while ($true) {
    $State = docker inspect --format='{{.State.Health.Status}}' $ContainerName 2>$null
    if ($State -eq 'healthy') { break }
    if ((Get-Date) -ge $Deadline) {
        Write-Error "MySQL 容器健康检查超时，请执行 docker logs $ContainerName 查看详情"
        exit 1
    }
    Start-Sleep -Seconds 5
}
Write-Host ">>> MySQL 容器已健康 ✅" -ForegroundColor Green

# -------------------------------------------------
# 4️⃣ 启动后端 FastAPI (uvicorn)
# -------------------------------------------------
Write-Host ">>> 启动后端 FastAPI (端口 8900) ..." -ForegroundColor Yellow
# 这里用 Start-Job 把 uvicorn 放后台，避免阻塞脚本
$BackendJob = Start-Job -ScriptBlock {
    param($Root)
    Set-Location $Root
    & "$Root\.venv\Scripts\python.exe" -m uvicorn server.main:app --host 127.0.0.1 --port 8900
} -ArgumentList $ProjectRoot

# 等待后端 /api/health 返回 database: connected（最多 30 秒）
Write-Host ">>> 等待后端 API 就绪 ..." -ForegroundColor Yellow
$ApiReady = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $Health = Invoke-RestMethod -Uri 'http://127.0.0.1:8900/api/health' -TimeoutSec 2 -ErrorAction Stop
        if ($Health.database -eq 'connected') { $ApiReady = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}
if (-not $ApiReady) {
    Write-Error "后端 API 启动超时，请检查后台任务日志 (Receive-Job -Id $($BackendJob.Id))"
    exit 1
}
Write-Host ">>> 后端 API 已就绪 (database=connected)" -ForegroundColor Green

# -------------------------------------------------
# 5️⃣ 启动前端 Vite (npm run dev)
# -------------------------------------------------
Write-Host ">>> 启动前端 Vite (端口 5173) ..." -ForegroundColor Yellow
$FrontendJob = Start-Job -ScriptBlock {
    param($Root)
    Set-Location (Join-Path $Root 'frontend')
    if (-not (Test-Path 'node_modules')) { npm install | Out-Null }
    npm run dev
} -ArgumentList $ProjectRoot

# 给前端几秒钟编译时间
Start-Sleep -Seconds 5

# -------------------------------------------------
# 6️⃣ 完成提示
# -------------------------------------------------
Write-Host "`n========== 启动完成 ==========" -ForegroundColor Green
Write-Host "前端页面: http://localhost:5173" -ForegroundColor Cyan
Write-Host "后端文档: http://localhost:8900/docs" -ForegroundColor Cyan
Write-Host "`n后台任务 ID:"
Write-Host "  MySQL 容器: $ContainerName (docker logs $ContainerName 查看日志)"
Write-Host "  后端 uvicorn: Job $($BackendJob.Id) (Receive-Job -Id $($BackendJob.Id) 查看日志)"
Write-Host "  前端 Vite:   Job $($FrontendJob.Id) (Receive-Job -Id $($FrontendJob.Id) 查看日志)"
Write-Host "`n直接在浏览器打开上面两个地址即可使用。按 Ctrl+C 退出脚本不会关闭后台服务。"
