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
$ragIndexJson = & $ragPython -X utf8 -c "import json; from rag_app.config import Settings; from rag_app.ingestion import corpus_fingerprint; from rag_app.store import Store; cfg=Settings(); local_pg=cfg.postgres_dsn.get_secret_value().rsplit('@',1)[-1].startswith('127.0.0.1:55432/'); chunks,_,meta=Store.from_settings(cfg).load_index(include_vectors=False); print(json.dumps({'ready':bool(chunks),'compatible':meta.get('mode')=='hybrid' and meta.get('embedding_identity')==cfg.embedding_identity and meta.get('corpus_fingerprint')==corpus_fingerprint(cfg),'localPostgres':local_pg}))"
if ($LASTEXITCODE -ne 0) { throw 'Khong doc duoc cau hinh/index; xem loi phia tren.' }
$ragIndexState = $ragIndexJson | ConvertFrom-Json
$ragPgData = Join-Path $PSScriptRoot 'storage\postgres-local'
if ($ragIndexState.localPostgres -and (Test-Path -LiteralPath (Join-Path $ragPgData 'PG_VERSION'))) {
    & pg_isready -h 127.0.0.1 -p 55432 -t 2 -q
    if ($LASTEXITCODE -eq 2) {
        & pg_ctl -D $ragPgData -l (Join-Path $PSScriptRoot 'storage\postgres-local.log') -o '-h 127.0.0.1 -p 55432' -w start
        if ($LASTEXITCODE -ne 0) { throw 'Khong khoi dong duoc PostgreSQL cuc bo cua NutriGuide.' }
    }
}
if ($Reindex -or -not $ragIndexState.ready -or -not $ragIndexState.compatible) {
    & $ragPython -X utf8 -m rag_app.cli ingest --mode hybrid
    if ($LASTEXITCODE -ne 0) { throw 'Ingestion that bai; index cu khong bi thay bang index loi.' }
}
Write-Host "Mo http://127.0.0.1:$Port/ - Ctrl+C de dung."
& $ragPython -X utf8 -m uvicorn rag_app.main:create_app --factory --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
