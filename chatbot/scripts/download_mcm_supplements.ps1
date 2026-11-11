$ErrorActionPreference = 'Stop'
$destination = Join-Path $PSScriptRoot '..\data\collected\rag_supplements_2026-10-08'
$links = Get-Content -LiteralPath (Join-Path $destination 'extracted\mcmilk-pdf-links.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$records = @()
foreach ($index in @(1, 10, 11, 12, 13, 14, 37, 39, 40)) {
    $identifier = 'mcm-product-' + $index.ToString('00')
    $relative = 'raw/' + $identifier + '.pdf'
    $target = Join-Path $destination $relative
    if (-not (Test-Path -LiteralPath $target)) {
        # Windows validates the certificate using its trust store; TLS checking remains enabled.
        Invoke-WebRequest -Uri $links[$index].url -OutFile $target -UseBasicParsing -TimeoutSec 60
    }
    $records += [PSCustomObject]@{id=$identifier; title=$links[$index].text; url=$links[$index].url; raw_file=$relative}
    Write-Output $identifier
}
$records | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $destination 'structured\mcm-download-records.json') -Encoding UTF8
