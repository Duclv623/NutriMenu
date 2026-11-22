# Chạy Chatbot Service (Cổng 8000 - AI Hỏi đáp RAG)
param([switch]$Reindex, [int]$Port = 8000)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'chatbot\run.ps1') @PSBoundParameters
