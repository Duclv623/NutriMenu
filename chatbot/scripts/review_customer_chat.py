"""Small paid real-Gemini review, isolated user history, no extra judge calls.

Run from repo root: .venv/Scripts/python.exe scripts/review_customer_chat.py
Manual verdicts belong in the saved report after reading answers and source quotes.
"""
import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from rag_app.config import ROOT, Settings
from rag_app.main import create_app
from rag_app.provider import create_provider
from rag_app.store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ids', default='')
    parser.add_argument('--output', default='real-customer-results.json')
    parser.add_argument('--seed-report', action='append', default=[], help='Resume history from already generated real responses; repeat for multiple reports, no extra API calls')
    parser.add_argument('--dataset', type=Path)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    target_dir = args.output_dir or ROOT / 'docs/chat-review-2026-10-07'
    target_dir.mkdir(parents=True, exist_ok=True)
    bank = json.loads((args.dataset or target_dir / 'customer-scenarios.json').read_text(encoding='utf-8'))
    chosen = set(args.ids.split(',')) if args.ids else None
    cases = [c for c in bank['cases'] if c['id'] in chosen] if chosen else [c for c in bank['cases'] if c['live']]
    cfg = Settings()
    assert cfg.has_key, 'Configured real provider required'
    chunks, vectors, metadata = Store(cfg.storage_dir / 'rag.sqlite3').load_index()
    assert chunks, 'Existing approved index required'
    isolated_dir = target_dir / '.runtime' / str(uuid4())
    isolated_dir.mkdir(parents=True)
    isolated = cfg.model_copy(update={'storage_dir': isolated_dir, 'rate_limit_per_minute': 300})
    Store(isolated_dir / 'rag.sqlite3').replace_index(chunks, metadata, vectors)
    provider = create_provider(isolated)
    captures = []
    for name in ('generate', 'generate_food', 'generate_policy'):
        original = getattr(provider, name)
        def audited(*call_args, _original=original, _name=name, **kwargs):
            answer, usage = _original(*call_args, **kwargs)
            hits = call_args[1] if _name != 'generate_policy' else []
            captures.append({'stage': _name, 'draft': answer.model_dump(),
                             'grounding_review': answer._grounding_review,
                             'sources': [{'id': f'C{i}', 'chunk_id': h.chunk.id,
                                          'source_id': h.chunk.source_id, 'text': h.chunk.text}
                                         for i, h in enumerate(hits, 1)],
                             'provider_response_ids': answer._provider_response_ids})
            return answer, usage
        setattr(provider, name, audited)
    report = {'started_at': datetime.now(UTC).isoformat(), 'provider': cfg.answer_mode, 'model': cfg.active_model,
              'index_metadata': metadata, 'isolated_history': True, 'external_judge_calls': 0,
              'source_hashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in (ROOT/'rag_app').glob('*.py')}, 'cases': []}
    sessions = {}
    owner_uuid = str(uuid4())
    report['seed_reports'] = args.seed_report
    report['seeded_cases'] = []
    for seed_name in args.seed_report:
        seed = json.loads((target_dir / seed_name).read_text(encoding='utf-8'))
        for prior in seed['cases']:
            if prior['http_status'] != 200 or not prior['real_api_provenance']:
                continue
            body = prior['response']
            Store(isolated_dir / 'rag.sqlite3').save_message(
                'dev:' + owner_uuid, body['session_id'], body['message_id'], prior['question'], body)
            sessions[prior['session']] = body['session_id']
            report['seeded_cases'].append(prior['id'])
    with TestClient(create_app(isolated, provider)) as client:
        client.cookies.set('datn_owner', owner_uuid)
        for case in cases:
            request = {'message': case['question'], 'save_history': True}
            if case['session'] in sessions:
                request['session_id'] = sessions[case['session']]
            started = time.perf_counter()
            response = client.post('/api/chat', json=request)
            body = response.json()
            if response.status_code == 200:
                sessions[case['session']] = body['session_id']
            provenance = response.status_code == 200 and body.get('answer_origin') == cfg.answer_mode and bool(body.get('provider_response_ids')) and body.get('usage', {}).get('output_tokens', 0) > 0
            report['cases'].append({**case, 'http_status': response.status_code,
                'wall_latency_ms': round((time.perf_counter()-started)*1000),
                'real_api_provenance': bool(provenance), 'response': body,
                'generation_trace': list(captures), 'manual_verdict': 'pending', 'manual_notes': ''})
            captures.clear()
            (target_dir / args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'id':case['id'], 'status':body.get('status',response.status_code),
                              'latency_ms':body.get('latency_ms'), 'answer':body.get('answer',body.get('detail'))}, ensure_ascii=False), flush=True)
            if response.status_code == 503 and any(s in str(body) for s in ('429','quota','RESOURCE_EXHAUSTED')):
                break


if __name__ == '__main__':
    main()
