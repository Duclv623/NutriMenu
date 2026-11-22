# Chay User Service (Cong 8083 - Quan ly Tai khoan & Ho so benh nhan)
param(
    [string]$DbUser = "postgres",
    [string]$DbPassword = "123"
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path $PSScriptRoot "Userservice")
$env:JAVA_HOME = "C:\Program Files\Java\jdk-21.0.11"
$env:DB_URL = "jdbc:postgresql://localhost:5432/menufood_users"
$env:DB_USERNAME = $DbUser
$env:DB_PASSWORD = $DbPassword
$env:PORT = "8083"

$mvnCmd = "C:\apache-maven-3.9.16-bin\apache-maven-3.9.16\bin\mvn.cmd"
if (-not (Test-Path $mvnCmd)) { $mvnCmd = "mvn" }

Write-Host ">> Khoi dong User Service tren cong 8083..." -ForegroundColor Green
& $mvnCmd spring-boot:run
