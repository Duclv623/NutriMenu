"""Bounded real-provider checks: <=12 cases, <=20 chat turns, no AI judge."""
import argparse
import json
import sqlite3

from fastapi.testclient import TestClient

from rag_app.config import ROOT, Settings
from rag_app.main import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ids', default='')
    parser.add_argument('--single-turn', action='store_true')
    args = parser.parse_args()
    cfg = Settings()
    output = ROOT/'docs/release-2026-10-30'
    output.mkdir(parents=True, exist_ok=True)
    isolated = ROOT/'tmp/release-2026-10-30/live'
    isolated.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(cfg.storage_dir/'rag.sqlite3') as src, sqlite3.connect(isolated/'rag.sqlite3') as dst:
        src.backup(dst)
    cfg = cfg.model_copy(update={'storage_dir':isolated,'rate_limit_per_minute':100})
    cases = json.loads((ROOT/'docs/audit-2026-10-30/representative-cases.json').read_text(encoding='utf-8'))['cases']
    if args.ids:
        cases = [c for c in cases if c['id'] in args.ids.split(',')]
    results = []
    turns = 0
    with TestClient(create_app(cfg)) as client:
        for case in cases[:12]:
            session = None
            for question in case['questions'][:1] if args.single_turn else case['questions']:
                if turns >= 20:
                    break
                body = {'message':question}
                if session:
                    body['session_id'] = session
                response = client.post('/api/chat',json=body)
                result = response.json()
                session = result.get('session_id')
                turns += 1
                results.append({'case':case['id'],'question':question,'http_status':response.status_code,
                                'expected':case['expected'],'response':result})
                filename = 'representative-recheck-' + '-'.join(c['id'] for c in cases) + '.json' if args.ids else 'representative-results.json'
                (output/filename).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
                print(case['id'],response.status_code,result.get('status'),flush=True)
                if response.status_code >= 500:
                    return


if __name__ == '__main__':
    main()
