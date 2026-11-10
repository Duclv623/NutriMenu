param([int]$Port = 8002)
$ErrorActionPreference = 'Stop'
$taskPreviousMode = $env:MEAL_SERVICE_MODE
Push-Location $PSScriptRoot
try {
    $env:MEAL_SERVICE_MODE = 'mock'
    Write-Host "NutriGuide meal demo: http://127.0.0.1:$Port/"
    Write-Host 'Fictional fixtures only. No CP-SAT is executed; existing .env is not changed.'
    & .\.venv\Scripts\python.exe -X utf8 -m uvicorn rag_app.main:create_app --factory --host 127.0.0.1 --port $Port
} finally {
    if ($null -eq $taskPreviousMode) { Remove-Item Env:MEAL_SERVICE_MODE -ErrorAction SilentlyContinue }
    else { $env:MEAL_SERVICE_MODE = $taskPreviousMode }
    Pop-Location
}
