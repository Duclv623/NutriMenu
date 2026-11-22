# Chay Food Catalog Service truc tiep trong thu muc service
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$mvnCmd = Join-Path $PSScriptRoot 'mvnw.cmd'

Write-Host ">> Khoi dong Food Catalog Service tren cong 8081..." -ForegroundColor Green
& $mvnCmd spring-boot:run
