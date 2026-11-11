param([switch]$Reindex, [int]$Port = 8000)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'chatbot\run.ps1') @PSBoundParameters
