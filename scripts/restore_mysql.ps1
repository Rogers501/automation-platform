param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root "docker\docker-compose.yml"
$mysqlId = docker compose -f $composeFile ps -q mysql
if (-not $mysqlId) {
    Write-Error "MySQL container is not running. Start it with: docker compose -f docker/docker-compose.yml up -d mysql"
}
if (-not (Test-Path $BackupFile)) {
    Write-Error "Backup file not found: $BackupFile"
}

$password = if ($env:MYSQL_PASSWORD) { $env:MYSQL_PASSWORD } else { "testerpw" }
$user = if ($env:MYSQL_USER) { $env:MYSQL_USER } else { "tester" }
$database = if ($env:MYSQL_DATABASE) { $env:MYSQL_DATABASE } else { "automation" }

Get-Content $BackupFile | docker exec --interactive --env MYSQL_PWD=$password $mysqlId mysql -u$user $database
if ($LASTEXITCODE -ne 0) {
    Write-Error "mysql restore failed with exit code $LASTEXITCODE"
}
Write-Host "MySQL backup restored: $BackupFile"
