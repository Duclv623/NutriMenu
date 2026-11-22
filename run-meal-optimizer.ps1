# Chay Meal Optimizer Service (Cong 8082 - Google OR-Tools CP-SAT)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path $PSScriptRoot "mealoptimizerservice")
$env:JAVA_HOME = "C:\Program Files\Java\jdk-21.0.11"
$mvnCmd = "C:\apache-maven-3.9.16-bin\apache-maven-3.9.16\bin\mvn.cmd"
if (-not (Test-Path $mvnCmd)) { $mvnCmd = "mvn" }

Write-Host ">> Khoi dong Meal Optimizer Service tren cong 8082..." -ForegroundColor Green
& $mvnCmd spring-boot:run
