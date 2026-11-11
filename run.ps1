param([int]$Port = 5173)
$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot 'frontend')
try {
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Can cai Node.js 22.12+ (hoac 24 LTS) de chay frontend.' }
    if (-not (Test-Path -LiteralPath 'node_modules')) {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Cai thu vien that bai. Kiem tra ket noi va chay npm ci trong frontend.' }
    }
    & npm.cmd run dev -- --port $Port
} finally { Pop-Location }
