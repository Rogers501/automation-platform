param(
    [string]$OutputFile = "$PSScriptRoot\..\data\docker-images\mysql-8.4.tar"
)

$ErrorActionPreference = "Stop"
$image = "mysql:8.4"
$cacheImage = "mirror.gcr.io/library/mysql:8.4"

$existing = docker image ls $image --format "{{.ID}}"
if (-not $existing) {
    docker pull $cacheImage
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Unable to pull MySQL image from the public cache."
    }
    docker tag $cacheImage $image
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Unable to tag $cacheImage as $image."
    }
}

$outputDir = Split-Path -Parent $OutputFile
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
docker save --output $OutputFile $image
if ($LASTEXITCODE -ne 0) {
    Write-Error "Unable to save $image to $OutputFile."
}
Write-Host "MySQL image saved: $OutputFile"
