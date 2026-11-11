"""Package runnable source and required public data; excludes credentials/history."""
import hashlib
import json
from zipfile import ZIP_DEFLATED, ZipFile

from rag_app.config import ROOT
from rag_app.ingestion import original_source_path


def main():
    paths = set()
    for folder in ['rag_app', 'web', 'tests', 'scripts', 'evals', 'config', 'data/structured']:
        paths.update(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    for name in ['README.md','RELEASE_NOTES_2026-10-30.md','KE_HOACH_SUA_VA_THU_THAP_DATA_DATN.md',
                 'pyproject.toml','requirements.txt','requirements-dev.txt','requirements-data.txt',
                 'requirements.lock.txt','.env.example','.gitignore','.dockerignore','Dockerfile','compose.yaml','run.ps1']:
        if (ROOT/name).is_file():
            paths.add(ROOT/name)
    manifest = json.loads((ROOT/'config/sources.json').read_text(encoding='utf-8'))
    for source in manifest['sources']:
        file = ROOT/'data'/source['filename']
        if file.is_file():
            paths.add(file)
        if source.get('enabled') and source.get('original_raw_file'):
            paths.add(original_source_path(source))
    supplement_manifest = json.loads((ROOT/'data/structured/supplements/manifest.json').read_text(encoding='utf-8'))
    for source in supplement_manifest['sources'].values():
        paths.add(ROOT/'data/collected/rag_supplements_2026-10-08'/source['raw_file'])
    paths.update(p for p in (ROOT/'data/collected/review_2026-10-30').rglob('*') if p.is_file())
    paths.update(p for p in (ROOT/'data/staging/review_2026-10-30').rglob('*') if p.is_file())
    paths.update(p for p in (ROOT/'docs/release-2026-10-30').rglob('*') if p.is_file())
    checksums = {}
    output = ROOT/'releases/NutriGuide-2026-10-30.zip'
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED, compresslevel=4) as archive:
        for path in sorted(paths):
            relative = path.relative_to(ROOT).as_posix()
            if path.name == '.env' or 'storage' in path.relative_to(ROOT).parts:
                raise ValueError('Private runtime file must not be packaged')
            checksums[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
            archive.write(path, relative)
        archive.writestr('PACKAGE_SHA256.json', json.dumps(checksums, ensure_ascii=False, indent=2))
    with ZipFile(output) as archive:
        assert archive.testzip() is None
    print(json.dumps({'package':str(output),'files':len(paths),'bytes':output.stat().st_size,
                      'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
