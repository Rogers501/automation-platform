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
# 4️⃣ 启动后端 FastAPI (uvicorn) - 后台进程,脚本退出时清理
# -------------------------------------------------
Write-Host ">>> 启动后端 FastAPI (端口 8900) ..." -ForegroundColor Yellow

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Error "未找到虚拟环境 Python: $PythonExe"
    exit 1
}

# 用 Start-Process 启动独立进程(不绑定 PowerShell Job 生命周期),
# 脚本前台等待 Ctrl+C 后通过 trap 清理子进程
$BackendProcess = Start-Process -FilePath $PythonExe `
    -ArgumentList "-m", "uvicorn", "server.main:app", "--host", "127.0.0.1", "--port", "8900" `
    -WorkingDirectory $ProjectRoot `
    -NoNewWindow `
    -PassThru

# 等待后端 /api/health 返回 database: connected（最多 30 秒）
Write-Host ">>> 等待后端 API 就绪 ..." -ForegroundColor Yellow
$ApiReady = $false
for ($i = 0; $i -lt 30; $i++) {
    if ($BackendProcess.HasExited) {
        Write-Error "后端进程异常退出 (ExitCode=$($BackendProcess.ExitCode))"
        exit 1
    }
    try {
        $Health = Invoke-RestMethod -Uri 'http://127.0.0.1:8900/api/health' -TimeoutSec 2 -ErrorAction Stop
        if ($Health.database -eq 'connected') { $ApiReady = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}
if (-not $ApiReady) {
    Write-Error "后端 API 启动超时，请直接运行 scripts/start_backend.ps1 查看报错"
    if (-not $BackendProcess.HasExited) { Stop-Process -Id $BackendProcess.Id -Force }
    exit 1
}
Write-Host ">>> 后端 API 已就绪 (database=connected)" -ForegroundColor Green

# -------------------------------------------------
# 5️⃣ 启动前端 Vite (npm run dev) - 后台进程
# -------------------------------------------------
Write-Host ">>> 启动前端 Vite (端口 5173) ..." -ForegroundColor Yellow
$FrontendDir = Join-Path $ProjectRoot "frontend"
if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Host ">>> 首次运行，安装前端依赖 ..." -ForegroundColor Yellow
    Push-Location $FrontendDir
    try { npm install } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "前端依赖安装失败"
        if (-not $BackendProcess.HasExited) { Stop-Process -Id $BackendProcess.Id -Force }
        exit $LASTEXITCODE
    }
}

$FrontendProcess = Start-Process -FilePath "npm.cmd" `
    -ArgumentList "run", "dev", "--", "--port", "5173" `
    -WorkingDirectory $FrontendDir `
    -NoNewWindow `
    -PassThru

# 轮询前端端口是否监听（最多 40 秒）
Write-Host ">>> 等待前端 Vite 编译完成 ..." -ForegroundColor Yellow
$FrontendReady = $false
for ($i = 0; $i -lt 40; $i++) {
    if ($FrontendProcess.HasExited) {
        Write-Error "前端 Vite 进程异常退出 (ExitCode=$($FrontendProcess.ExitCode))"
        if (-not $BackendProcess.HasExited) { Stop-Process -Id $BackendProcess.Id -Force }
        exit 1
    }
    $Conn = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
    if ($Conn) { $FrontendReady = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $FrontendReady) {
    Write-Warning "前端 Vite 在 40 秒内未监听 5173 端口，请稍后手动访问 http://localhost:5173"
} else {
    Write-Host ">>> 前端 Vite 已就绪 (5173 监听中)" -ForegroundColor Green
}

# -------------------------------------------------
# 6️⃣ 完成提示 + 前台等待 Ctrl+C
# -------------------------------------------------
Write-Host "`n========== 启动完成 ==========" -ForegroundColor Green
Write-Host "前端页面: http://localhost:5173" -ForegroundColor Cyan
Write-Host "后端文档: http://localhost:8900/docs" -ForegroundColor Cyan
Write-Host "MySQL 容器: $ContainerName (docker logs $ContainerName 查看日志)"
Write-Host "`n按 Ctrl+C 退出脚本将同时停止后端与前端进程 (MySQL 容器保留运行)`n" -ForegroundColor Cyan

# 注册清理钩子:脚本退出时(含 Ctrl+C)杀掉两个子进程
$null = Register-EngineEvent PowerShell.Exiting -Action {
    if ($script:BackendProcess -and -not $script:BackendProcess.HasExited) {
        Stop-Process -Id $script:BackendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($script:FrontendProcess -and -not $script:FrontendProcess.HasExited) {
        Stop-Process -Id $script:FrontendProcess.Id -Force -ErrorAction SilentlyContinue
    }
}

# 前台等待任一子进程退出;Ctrl+C 会触发上面的清理钩子
try {
    while (-not $BackendProcess.HasExited -and -not $FrontendProcess.HasExited) {
        Start-Sleep -Seconds 1
    }
} finally {
    if ($script:BackendProcess -and -not $script:BackendProcess.HasExited) {
        Stop-Process -Id $script:BackendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($script:FrontendProcess -and -not $script:FrontendProcess.HasExited) {
        Stop-Process -Id $script:FrontendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "`n>>> 子进程已清理，脚本退出。MySQL 容器仍保留运行。" -ForegroundColor Yellow
}
