param([int]$Port = 8000, [ValidateSet('named','mathematical')][string]$Dataset = 'named')
$ErrorActionPreference = 'Stop'
$taskPreviousMode = $env:MEAL_SERVICE_MODE
$taskPreviousDataset = $env:MEAL_DEMO_DATASET
Push-Location $PSScriptRoot
try {
    $env:MEAL_SERVICE_MODE = 'mock'
    $env:MEAL_DEMO_DATASET = $Dataset
    Write-Host "NutriGuide meal demo: http://127.0.0.1:$Port/"
    Write-Host 'Fictional fixtures only. No CP-SAT is executed; existing .env is not changed.'
    & .\.venv\Scripts\python.exe -X utf8 -m uvicorn rag_app.main:create_app --factory --host 127.0.0.1 --port $Port
} finally {
    if ($null -eq $taskPreviousMode) { Remove-Item Env:MEAL_SERVICE_MODE -ErrorAction SilentlyContinue }
    else { $env:MEAL_SERVICE_MODE = $taskPreviousMode }
    if ($null -eq $taskPreviousDataset) { Remove-Item Env:MEAL_DEMO_DATASET -ErrorAction SilentlyContinue }
    else { $env:MEAL_DEMO_DATASET = $taskPreviousDataset }
    Pop-Location
}
