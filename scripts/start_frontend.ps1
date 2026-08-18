param(
    [int]$Port = 5173
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "frontend")

if (-not (Test-Path "node_modules")) {
    Write-Host "首次运行，安装前端依赖..."
    npm install
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "前端页面: http://localhost:$Port"
npm run dev -- --port $Port
