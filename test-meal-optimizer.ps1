# ==============================================================================
# Script kiem tra thuat toan sinh thuc don toi uu Google OR-Tools CP-SAT
# ==============================================================================
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$mvnCmd = Join-Path $PSScriptRoot 'mealoptimizerservice\mvnw.cmd'

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host " [NutriMenu] KIEM TRA THUAT TOAN SINH THUC DON GOOGLE OR-TOOLS CP-SAT" -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "Dang bien dich va thuc thi Solver Unit Test trong mealoptimizerservice..." -ForegroundColor Yellow

Set-Location -LiteralPath (Join-Path $PSScriptRoot "mealoptimizerservice")
& $mvnCmd test -Dtest=CpSatMealOptimizationEngineTest

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host ">> THANH CONG: Cac test CP-SAT duoc chon da qua." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host ">> LOI: Kiem tra that bai. Vui long xem log chi tiet o tren." -ForegroundColor Red
}
exit $LASTEXITCODE
