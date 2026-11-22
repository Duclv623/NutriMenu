# Chay Frontend (Cong 5173 - React + Vite Dashboard & Meal Planner)
param([int]$Port = 5173)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$npmCmd = "C:\Program Files\nodejs\npm.cmd"
if (-not (Test-Path $npmCmd)) { $npmCmd = "npm" }
if (-not (Test-Path -LiteralPath 'node_modules')) {
    & $npmCmd ci
}
Write-Host ">> Khoi dong Frontend tren http://localhost:$Port ..." -ForegroundColor Green
& $npmCmd run dev -- --port $Port
