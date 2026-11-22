Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "Khoi dong NutriGuide API Gateway (Port 8080)..." -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Set-Location -LiteralPath (Join-Path $PSScriptRoot 'gateway')

if (Get-Command node -ErrorAction SilentlyContinue) {
    node server.js
} else {
    $python = "C:\testda\chatbot\.venv\Scripts\python.exe"
    & $python -X utf8 -m uvicorn gateway_app.main:create_app --factory --host 127.0.0.1 --port 8080
}
