# Chay User Service truc tiep trong thu muc service
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$mvnCmd = Join-Path $PSScriptRoot 'mvnw.cmd'

Write-Host ">> Khoi dong User Service tren cong 8083..." -ForegroundColor Green
& $mvnCmd spring-boot:run
