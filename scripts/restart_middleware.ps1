# scripts/restart_middleware.ps1
# IP 变更后一键重启所有中间件。唯一要改的地方: docker/.env 的 HOST_IP
# 运行方式: 在项目根目录的 PowerShell 里执行
#   powershell -ExecutionPolicy Bypass -File .\scripts\restart_middleware.ps1
# 可选参数:
#   -SkipGitLab   跳过 GitLab 重建（改 external_url 需要 reconfigure，约 3-5 分钟）
#   -WithInfra    加启 redis/kafka（框架缓存/MQ 测试用；镜像缺失时自动从 docker.1ms.run 拉取）

param(
    [switch]$SkipGitLab = $false,
    [switch]$WithInfra = $false
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

Write-Host "`n========== IP 变更一键重启开始 ==========" -ForegroundColor Cyan

# -------------------------------------------------
# 1. 从 docker/.env 读 HOST_IP（唯一配置点）
# -------------------------------------------------
$EnvFile = Join-Path $ProjectRoot 'docker\.env'
$HostIp = (Get-Content $EnvFile | Where-Object { $_ -match '^HOST_IP=' }) -replace '^HOST_IP=', ''
if (-not $HostIp) {
    throw "docker/.env 里没有 HOST_IP= 这一行，请先补上"
}
Write-Host ">>> 配置 IP: $HostIp (来源 docker/.env)" -ForegroundColor Green

# -------------------------------------------------
# 2. 校验本机当前 IP 是否与配置一致（DHCP 变了会提示）
# -------------------------------------------------
$CurrentIp = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -like '10.66.*' } |
    Select-Object -ExpandProperty IPAddress -First 1
if (-not $CurrentIp) {
    Write-Host "!!! 未找到 10.66.* 的本机 IP（不在公司网络?），跳过校验" -ForegroundColor Yellow
} elseif ($CurrentIp -ne $HostIp) {
    Write-Host "!!! 警告: 本机当前 IP 是 $CurrentIp，docker/.env 里是 $HostIp" -ForegroundColor Red
    Write-Host "!!! 本机 IP 又变了: 先把 docker/.env 的 HOST_IP 改成 $CurrentIp，再重跑本脚本" -ForegroundColor Red
    Write-Host "!!! 继续用 $HostIp 启动（同事将无法通过此 IP 访问）..." -ForegroundColor Red
} else {
    Write-Host ">>> 本机 IP 校验通过: $CurrentIp" -ForegroundColor Green
}

# -------------------------------------------------
# 3. 同步 gitlab remote + 迁移存储凭据到新 IP
#    (GCM 按"主机:端口"存储凭据, 且新版默认拒绝明文 HTTP)
# -------------------------------------------------
$GitlabUrl = "http://${HostIp}:8929/root/automation-platform.git"
git remote set-url gitlab $GitlabUrl
git config --global credential.gcmAllowUnsafeRemotes true | Out-Null
git config --global "credential.http://${HostIp}:8929.provider" generic | Out-Null
Write-Host ">>> git remote gitlab 已指向 $GitlabUrl" -ForegroundColor Green

$env:GCM_INTERACTIVE = 'Never'
# 两个 PS5.1 坑, 都绕开:
# a) EAP=Stop 时原生命令写 stderr 会被当成异常掐断管道 (GCM 对 http 必打警告) → 此块降级 Continue
# b) 本脚本头部对 $OutputEncoding/[Console] 编码赋值后, PS 管道写原生命令 stdin 会损坏字节
#    → git credential 的输入一律走临时文件 + cmd /c 重定向, 不用 PS 管道
$PrevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'

function Write-GitCredentialStdin {
    param([string]$Payload)
    $Tmp = [IO.Path]::GetTempFileName()
    [IO.File]::WriteAllText($Tmp, $Payload, (New-Object System.Text.UTF8Encoding $false))
    return $Tmp
}

$OldUrls = git config --global --get-regexp '^credential\.http://.*\.provider$' 2>$null |
    ForEach-Object { $_.Split(' ')[0] -replace '^credential\.', '' -replace '\.provider$', '' } |
    Where-Object { $_ -notmatch [regex]::Escape($HostIp) }
$Migrated = $false
foreach ($OldUrl in $OldUrls) {
    if ($Migrated) { break }
    $OldHost = $OldUrl -replace '^http://', ''
    $Tmp = Write-GitCredentialStdin "protocol=http`nhost=$OldHost`n"
    $Filled = cmd /c "git credential fill < `"$Tmp`"" 2>$null
    Remove-Item $Tmp -Force -ErrorAction SilentlyContinue
    $CredUser = ($Filled | Where-Object { $_ -like 'username=*' }) -replace '^username=', ''
    $CredPass = ($Filled | Where-Object { $_ -like 'password=*' }) -replace '^password=', ''
    if ($CredUser -and $CredPass) {
        $Tmp = Write-GitCredentialStdin "protocol=http`nhost=$($HostIp):8929`nusername=$CredUser`npassword=$CredPass`n"
        $null = cmd /c "git credential approve < `"$Tmp`"" 2>$null
        Remove-Item $Tmp -Force -ErrorAction SilentlyContinue
        Write-Host ">>> GitLab 凭据已迁移: $OldHost -> $($HostIp):8929 (用户 $CredUser)" -ForegroundColor Green
        $Migrated = $true
    }
}
$ErrorActionPreference = $PrevEap
if (-not $Migrated) {
    Write-Host "!!! 未找到旧 IP 的存储凭据, 首次 push/pull 会弹窗输入一次账号密码" -ForegroundColor Yellow
}

# -------------------------------------------------
# 4. 主栈: mysql / backend / frontend (平台运行必需)
#    -WithInfra 时加启 redis / kafka (框架缓存/MQ 测试用)
#    (compose 项目目录是 docker/，自动加载 docker/.env)
# -------------------------------------------------
if ($WithInfra) {
    # redis/kafka 镜像可能被 Docker 清理过，docker.io 国内拉不动，用镜像源兜底
    # docker inspect/pull/tag 都往 stderr 写内容, 同样要降级 EAP (原因见第 3 步注释)
    $PrevEapInfra = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    foreach ($img in @('redis:7.4', 'bitnami/kafka:3.9')) {
        docker image inspect $img *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Host ">>> 本地缺镜像 $img，从 docker.1ms.run 拉取 ..." -ForegroundColor Yellow
            docker pull "docker.1ms.run/$img"
            docker tag "docker.1ms.run/$img" $img
            if ($LASTEXITCODE -ne 0) { throw "镜像 $img 拉取失败" }
        }
    }
    $ErrorActionPreference = $PrevEapInfra
}

$Services = 'mysql backend frontend'
if ($WithInfra) { $Services = "$Services redis kafka" }

Write-Host "`n>>> 启动主栈 ($Services) ..." -ForegroundColor Yellow
docker compose -f docker/docker-compose.yml up -d $Services.Split(' ')
if ($LASTEXITCODE -ne 0) { throw "主栈启动失败，exit=$LASTEXITCODE" }

# -------------------------------------------------
# 5. GitLab（docker/gitlab/ 下没有 .env，需 --env-file 显式指定）
# -------------------------------------------------
if (-not $SkipGitLab) {
    Write-Host "`n>>> 启动 GitLab (external_url 变更需 reconfigure，约 3-5 分钟) ..." -ForegroundColor Yellow
    docker compose -f docker/gitlab/docker-compose.yml --env-file docker/.env up -d
    if ($LASTEXITCODE -ne 0) { throw "GitLab 启动失败，exit=$LASTEXITCODE" }
} else {
    Write-Host "`n>>> 跳过 GitLab (-SkipGitLab)" -ForegroundColor Yellow
}

# -------------------------------------------------
# 6. 输出访问入口
# -------------------------------------------------
Write-Host "`n========== 重启完成，访问入口 ==========" -ForegroundColor Cyan
Write-Host "  前端工作台    http://${HostIp}:8080"
Write-Host "  后端 API 文档 http://${HostIp}:8080/docs"
Write-Host "  健康检查      http://${HostIp}:8080/api/health"
if (-not $SkipGitLab) {
    Write-Host "  GitLab Web    http://${HostIp}:8929 (刚重建的话需等几分钟就绪)"
}
Write-Host "  GitLab SSH    ssh://git@${HostIp}:2224"
Write-Host ""
Write-Host "提示: 后端 healthy 需约 30s; 防火墙 8080/8929/2224 已放行过则无需重复。" -ForegroundColor DarkGray
