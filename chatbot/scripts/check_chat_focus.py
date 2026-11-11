"""Targeted real-key dialogue regression; history isolated from user sessions."""
import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from rag_app.config import ROOT, Settings
from rag_app.main import create_app
from rag_app.provider import OpenAIProvider
from rag_app.store import Store

QUESTIONS = [
    'Sáng tôi hay ăn bánh mì, có cần bỏ không?',
    'Ăn gạo lứt thì ăn nhiều một chút cũng được nhỉ?',
    '200ml sữa bò bao nhiêu calo',
    'sữa bò tươi',
    '300ml sữa bò tươi bao nhiêu calo',
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--indices', default='0,1,2,3,4')
    parser.add_argument('--no-save', action='store_true')
    args = parser.parse_args()
    cfg = Settings()
    chunks, vectors, metadata = Store(cfg.storage_dir/'rag.sqlite3').load_index()
    report = {'started_at': datetime.now(UTC).isoformat(), 'model': cfg.active_model, 'cases': []}
    target = ROOT/'docs/chat-quality'/args.output
    target.parent.mkdir(exist_ok=True)
    reviews = []
    original = OpenAIProvider.generate

    def capture(provider, *args, **kwargs):
        answer, usage = original(provider, *args, **kwargs)
        reviews.append(answer._grounding_review)
        return answer, usage

    OpenAIProvider.generate = capture
    with TemporaryDirectory(dir=ROOT/'tmp', prefix='focus-live-') as folder:
        isolated = cfg.model_copy(update={'storage_dir': Path(folder), 'rate_limit_per_minute': 300})
        Store(Path(folder)/'rag.sqlite3').replace_index(chunks, metadata, vectors)
        with TestClient(create_app(isolated)) as client:
            session = None
            for index in map(int, args.indices.split(',')):
                payload = {'message': QUESTIONS[index], 'save_history': not args.no_save}
                if session:
                    payload['session_id'] = session
                response = client.post('/api/chat', json=payload)
                body = response.json()
                if response.status_code == 200:
                    session = body['session_id']
                errors = []
                if response.status_code != 200:
                    errors.append('http_'+str(response.status_code))
                else:
                    if body['answer_origin'] != 'gemini' or not body['provider_response_ids']:
                        errors.append('missing_real_api')
                    if index == 0 and ('bữa phụ' in body['answer'].lower() or body['status'] != 'answered'):
                        errors.append('breakfast_not_answered')
                    if index == 1 and ('phần tư khẩu phần' in body['answer'].lower() or body['status'] != 'answered'):
                        errors.append('plate_scope_wrong')
                    if index == 1 and not any(s in body['answer'].lower() for s in ('nhóm', 'carb', 'carbohydrate')):
                        errors.append('plate_group_scope_missing')
                    if index in (3, 4):
                        result = body.get('food_result') or {}
                        request = result.get('request') or {}
                        items = request.get('items', [])
                        if not items or items[0]['amount'] != (200 if index == 3 else 300) or items[0]['unit'] != 'ml':
                            errors.append('quantity_context_lost')
                        if not request.get('nutrients'):
                            errors.append('nutrient_context_lost')
                        if any(i['calculation_available'] for i in result.get('items', [])):
                            errors.append('invented_volume_conversion')
                report['cases'].append({'index': index, 'question': QUESTIONS[index], 'http_status': response.status_code,
                                        'errors': errors, 'response': body, 'reviews': list(reviews)})
                reviews.clear()
                target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                print(json.dumps({'index': index, 'errors': errors, 'latency_ms': body.get('latency_ms'),
                                  'answer': body.get('answer', body.get('detail'))}, ensure_ascii=False), flush=True)
                if response.status_code != 200:
                    break


if __name__ == '__main__':
    main()
