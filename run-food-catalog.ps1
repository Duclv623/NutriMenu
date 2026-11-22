# Chay Food Catalog Service (Cong 8081 - Quan ly Danh muc & Dinh duong)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path $PSScriptRoot "foodcatalogservice")
$env:JAVA_HOME = "C:\Program Files\Java\jdk-21.0.11"
$mvnCmd = "C:\apache-maven-3.9.16-bin\apache-maven-3.9.16\bin\mvn.cmd"
if (-not (Test-Path $mvnCmd)) { $mvnCmd = "mvn" }

Write-Host ">> Khoi dong Food Catalog Service tren cong 8081..." -ForegroundColor Green
& $mvnCmd spring-boot:run
