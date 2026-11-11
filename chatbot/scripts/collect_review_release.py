"""Refresh public source evidence, never overwrite the active data release."""
import hashlib
import json
import time
from datetime import UTC, datetime

import httpx

from rag_app.config import ROOT
from scripts.collect_nin_foods import download

OUT = ROOT / 'data/collected/review_2026-10-30'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for dataset in ['dishes', 'foods']:
        target = OUT / ('nin_' + dataset)
        try:
            rows, manifest = download(target, 100, 0.6, dataset)
            save(target / 'records.json', rows)
            save(target / 'manifest.json', manifest)
            results.append({'id': 'nin_' + dataset, 'status': 'collected', 'records': len(rows)})
        except Exception as error:
            results.append({'id': 'nin_' + dataset, 'status': 'failed', 'error': str(error)[:300]})
        save(OUT / 'collection_manifest.json', results)
    previous = json.loads((ROOT/'data/collected/rag_supplements_2026-10-08/manifest.json').read_text(encoding='utf-8'))
    sources = [{'id': 'nin-dishes-page', 'url': 'https://viendinhduong.vn/vi/cong-cu-va-tien-ich/gia-tri-dinh-duong-mon-an'},
               {'id': 'niddk-activity', 'url': 'https://www.niddk.nih.gov/health-information/diabetes/overview/diet-eating-physical-activity'},
               {'id': 'cdc-activity', 'url': 'https://www.cdc.gov/diabetes/living-with/physical-activity.html'}]
    sources += [s for s in previous['sources'] if s.get('url')]
    seen = set()
    with httpx.Client(timeout=25, follow_redirects=True, headers={'User-Agent': 'NutriGuide-source-review/1.0'}) as client:
        for source in sources:
            if source['url'] in seen:
                continue
            seen.add(source['url'])
            try:
                response = client.get(source['url'])
                response.raise_for_status()
                kind = response.headers.get('content-type', '')
                suffix = '.pdf' if response.content.startswith(b'%PDF') else '.html'
                filename = 'raw/' + source['id'] + suffix
                path = OUT / filename
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(response.content)
                digest = hashlib.sha256(response.content).hexdigest()
                result = {'id': source['id'], 'url': source['url'], 'final_url': str(response.url),
                          'retrieved_at': datetime.now(UTC).isoformat(), 'content_type': kind,
                          'sha256': digest, 'raw_file': filename, 'bytes': len(response.content),
                          'status': 'collected_pending_review', 'unchanged': digest == source.get('sha256')}
            except Exception as error:
                result = {'id': source['id'], 'url': source['url'], 'status': 'failed', 'error': str(error)[:300]}
            results.append(result)
            save(OUT / 'collection_manifest.json', results)
            print(source['id'], result['status'], flush=True)
            time.sleep(0.6)


if __name__ == '__main__':
    main()
