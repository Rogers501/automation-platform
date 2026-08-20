param(
    [string]$OutputDir = "$PSScriptRoot\..\data\backups"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root "docker\docker-compose.yml"
$mysqlId = docker compose -f $composeFile ps -q mysql
if (-not $mysqlId) {
    Write-Error "MySQL container is not running. Start it with: docker compose -f docker/docker-compose.yml up -d mysql"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outputFile = Join-Path $OutputDir "automation-$timestamp.sql"
$password = if ($env:MYSQL_PASSWORD) { $env:MYSQL_PASSWORD } else { "testerpw" }
$user = if ($env:MYSQL_USER) { $env:MYSQL_USER } else { "tester" }
$database = if ($env:MYSQL_DATABASE) { $env:MYSQL_DATABASE } else { "automation" }

docker exec --env MYSQL_PWD=$password $mysqlId mysqldump -u$user --single-transaction --routines --triggers $database | Out-File -FilePath $outputFile -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Error "mysqldump failed with exit code $LASTEXITCODE"
}
Write-Host "MySQL backup written: $outputFile"
