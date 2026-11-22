# Chay Meal Optimizer Service truc tiep trong thu muc service
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$mvnCmd = Join-Path $PSScriptRoot 'mvnw.cmd'

Write-Host ">> Khoi dong Meal Optimizer Service tren cong 8082..." -ForegroundColor Green
& $mvnCmd spring-boot:run
