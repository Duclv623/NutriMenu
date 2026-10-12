param(
    [switch]$Reindex,
    [int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$ragPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $ragPython)) {
    throw 'Chua co .venv. Chay python -m venv .venv va .\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt'
}
$ragIndexJson = & $ragPython -X utf8 -c "import json; from rag_app.config import Settings; from rag_app.ingestion import corpus_fingerprint; from rag_app.store import Store; cfg=Settings(); chunks,_,meta=Store(cfg.storage_dir/'rag.sqlite3').load_index(); print(json.dumps({'ready':bool(chunks),'compatible':meta.get('mode')=='hybrid' and meta.get('embedding_identity')==cfg.embedding_identity and meta.get('corpus_fingerprint')==corpus_fingerprint(cfg)}))"
if ($LASTEXITCODE -ne 0) { throw 'Khong doc duoc cau hinh/index; xem loi phia tren.' }
$ragIndexState = $ragIndexJson | ConvertFrom-Json
if ($Reindex -or -not $ragIndexState.ready -or -not $ragIndexState.compatible) {
    & $ragPython -X utf8 -m rag_app.cli ingest --mode hybrid
    if ($LASTEXITCODE -ne 0) { throw 'Ingestion that bai; index cu khong bi thay bang index loi.' }
}
Write-Host "Mo http://127.0.0.1:$Port/ - Ctrl+C de dung."
& $ragPython -X utf8 -m uvicorn rag_app.main:create_app --factory --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
