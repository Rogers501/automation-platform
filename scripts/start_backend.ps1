param(
    [int]$Port = 8900
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "未找到虚拟环境 Python: $python"
    exit 1
}

Write-Host "后端 API: http://localhost:$Port"
Write-Host "接口文档: http://localhost:$Port/docs"
& $python -m uvicorn server.main:app --host 127.0.0.1 --port $Port --reload
