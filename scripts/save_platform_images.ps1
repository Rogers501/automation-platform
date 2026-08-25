param(
    # 镜像列表, 默认备份测试管理平台相关镜像
    [string[]]$Images = @(
        "automation-platform-backend:latest",
        "automation-platform-frontend:latest",
        "python:3.12-slim",
        "node:20-alpine",
        "nginx:alpine"
    ),
    # 输出目录
    [string]$OutputDir = "$PSScriptRoot\..\data\docker-images"
)

$ErrorActionPreference = "Stop"

# 确保输出目录存在
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

# 强制 UTF-8 输出, 避免中文乱码
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$total = $Images.Count
$success = 0
$failed = @()

Write-Host "========== 测试管理平台镜像备份 =========="
Write-Host "目标目录: $OutputDir"
Write-Host "待备份镜像数: $total"
Write-Host ""

for ($i = 0; $i -lt $total; $i++) {
    $image = $Images[$i]
    # 镜像名里的冒号和斜杠替换成下划线, 作为文件名
    # 用 .Replace 不用 -replace, 避免正则解析问题
    $filename = $image.Replace(":", "_").Replace("/", "_")
    $outputFile = Join-Path $OutputDir "$filename.tar"

    Write-Host "[$($i + 1)/$total] $image"

    # 检查镜像是否存在 (不用 2>$null, PowerShell 5.1 行为奇怪)
    $existing = docker image ls $image --format "{{.ID}}" | Out-String
    if ([string]::IsNullOrWhiteSpace($existing)) {
        Write-Host "  [SKIP] 镜像不存在, 跳过" -ForegroundColor Yellow
        $failed += "$image (not found)"
        continue
    }

    # 已存在同名文件, 提示覆盖
    if (Test-Path $outputFile) {
        $oldSize = (Get-Item $outputFile).Length / 1MB
        Write-Host "  覆盖已存在文件 (旧: $("{0:N1}" -f $oldSize) MB)"
    }

    # docker save 导出
    docker save --output $outputFile $image
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [FAIL] docker save 失败" -ForegroundColor Red
        $failed += "$image (save failed)"
        continue
    }

    $size = (Get-Item $outputFile).Length / 1MB
    Write-Host "  [OK] $("{0:N1}" -f $size) MB -> $outputFile" -ForegroundColor Green
    $success++
}

Write-Host ""
Write-Host "========== 备份完成 =========="
Write-Host "成功: $success / $total"
if ($failed.Count -gt 0) {
    Write-Host "失败:" -ForegroundColor Red
    foreach ($f in $failed) { Write-Host "  - $f" -ForegroundColor Red }
    exit 1
}

Write-Host ""
Write-Host "恢复命令:"
Write-Host "  docker load -i `"$OutputDir\automation-platform-backend_latest.tar`""
Write-Host "  docker load -i `"$OutputDir\automation-platform-frontend_latest.tar`""
Write-Host "  docker load -i `"$OutputDir\python_3.12-slim.tar`""
Write-Host "  docker load -i `"$OutputDir\node_20-alpine.tar`""
Write-Host "  docker load -i `"$OutputDir\nginx_alpine.tar`""
