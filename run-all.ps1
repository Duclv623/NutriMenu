<#
.SYNOPSIS
    Script tich hop khoi chay toan bo he thong NutriMenu / NutriGuide tai C:\testda
#>
param(
    [switch]$LaunchAll,
    [switch]$TestSolver
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if ($TestSolver) {
    & (Join-Path $PSScriptRoot "test-meal-optimizer.ps1")
    exit $LASTEXITCODE
}

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "         HE THONG NUTRIMENU / NUTRIGUIDE TICH HOP (C:\testda)           " -ForegroundColor Yellow
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "Danh sach cac service:" -ForegroundColor White
Write-Host "  1. [Core] Meal Optimizer Service  - Cong 8082 (Google OR-Tools CP-SAT)" -ForegroundColor Cyan
Write-Host "  2. [Catalog] Food Catalog Service - Cong 8081 (Dinh duong & Mon an)" -ForegroundColor Cyan
Write-Host "  3. [User] User Service            - Cong 8083 (Tai khoan & Benh nhan)" -ForegroundColor Cyan
Write-Host "  4. [RAG AI] Chatbot Service       - Cong 8000 (Hoi dap chuyen sau RAG)" -ForegroundColor Cyan
Write-Host "  5. [Gateway] API Gateway          - Cong 8080 (Dieu phoi & Tich hop Microservices)" -ForegroundColor Green
Write-Host "  6. [UI] Frontend React + Vite     - Cong 5173 (Giao dien web truc quan)" -ForegroundColor Cyan
Write-Host "------------------------------------------------------------------------" -ForegroundColor Gray

if ($LaunchAll) {
    Write-Host ">> Dang mo cua so PowerShell rieng cho tung service..." -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy Bypass", "-File `"$PSScriptRoot\run-meal-optimizer.ps1`""
    Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy Bypass", "-File `"$PSScriptRoot\run-food-catalog.ps1`""
    Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy Bypass", "-File `"$PSScriptRoot\run-user-service.ps1`""
    Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy Bypass", "-File `"$PSScriptRoot\run-chatbot.ps1`""
    Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy Bypass", "-File `"$PSScriptRoot\run-gateway.ps1`""
    Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy Bypass", "-File `"$PSScriptRoot\run-frontend.ps1`""
    Write-Host ">> Tat ca 6 service da duoc khoi chay trong cac cua so rieng biet!" -ForegroundColor Green
    Write-Host ">> Mo trinh duyet tai: http://localhost:5173" -ForegroundColor Yellow
    exit 0
}

Write-Host "Chon thao tac:" -ForegroundColor White
Write-Host "  [T] Chay ngay Unit Test kiem chung thuat toan sinh thuc don CP-SAT" -ForegroundColor Yellow
Write-Host "  [A] Khoi chay TAT CA cac service (moi service 1 cua so rieng)" -ForegroundColor Green
Write-Host "  [1] Chay Meal Optimizer Service (8082)"
Write-Host "  [2] Chay Food Catalog Service (8081)"
Write-Host "  [3] Chay User Service (8083)"
Write-Host "  [4] Chay Chatbot Service (8000)"
Write-Host "  [5] Chay API Gateway (8080)"
Write-Host "  [6] Chay Frontend Web (5173)"
Write-Host "  [Q] Thoat"
$choice = Read-Host "Nhap lua chon cua ban"

switch ($choice.ToUpper()) {
    "T" { & "$PSScriptRoot\test-meal-optimizer.ps1" }
    "A" {
        Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy Bypass", "-File `"$PSScriptRoot\run-meal-optimizer.ps1`""
        Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy Bypass", "-File `"$PSScriptRoot\run-food-catalog.ps1`""
        Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy Bypass", "-File `"$PSScriptRoot\run-user-service.ps1`""
        Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy Bypass", "-File `"$PSScriptRoot\run-chatbot.ps1`""
        Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy Bypass", "-File `"$PSScriptRoot\run-gateway.ps1`""
        Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy Bypass", "-File `"$PSScriptRoot\run-frontend.ps1`""
        Write-Host ">> Da kich hoat toan bo he thong!" -ForegroundColor Green
    }
    "1" { & "$PSScriptRoot\run-meal-optimizer.ps1" }
    "2" { & "$PSScriptRoot\run-food-catalog.ps1" }
    "3" { & "$PSScriptRoot\run-user-service.ps1" }
    "4" { & "$PSScriptRoot\run-chatbot.ps1" }
    "5" { & "$PSScriptRoot\run-gateway.ps1" }
    "6" { & "$PSScriptRoot\run-frontend.ps1" }
    Default { Write-Host "Da huy." }
}
