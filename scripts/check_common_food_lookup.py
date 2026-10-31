"""Exercise the two reported food questions against the real configured model."""
import json
import sqlite3

from fastapi.testclient import TestClient

from rag_app.config import ROOT, Settings
from rag_app.main import create_app


def main():
    cfg = Settings()
    folder = ROOT / 'tmp/common-food-live'
    folder.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(cfg.storage_dir / 'rag.sqlite3') as source, sqlite3.connect(folder / 'rag.sqlite3') as target:
        source.backup(target)
    cfg = cfg.model_copy(update={'storage_dir': folder})
    output = ROOT / 'docs/release-2026-10-31/common-food-live.json'
    results = []
    with TestClient(create_app(cfg)) as client:
        milk = client.post('/api/chat', json={'message': '200 ml sữa bò tươi có bao nhiêu calo?'}).json()
        assert milk['status'] == 'needs_clarification' and milk['reference_result']['unresolved']
        results.append(milk)
        print('milk', milk['answer'], flush=True)
        for message, session in [
            ('TH nguyên chất', milk['session_id']),
            ('Tổng 150 g cơm chín và 100 g ức gà chín có bao nhiêu calo và đạm?', None),
        ]:
            request = {'message': message}
            if session:
                request['session_id'] = session
            response = client.post('/api/chat', json=request)
            body = response.json()
            results.append(body)
            output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(response.status_code, body.get('answer', body.get('detail')), flush=True)
            assert response.status_code == 200 and body['status'] == 'answered'
        assert results[1]['reference_result']['items'][0]['calculated_nutrients']['energy_kcal'] == 126.4
        totals = {n['key']: n['value'] for n in results[2]['food_result']['display_totals']}
        assert totals == {'energy': 339, 'protein': 32.035}
        assert results[2]['answer'].startswith('Ước tính:') and 'Giả định tham khảo:' in results[2]['answer']


if __name__ == '__main__':
    main()
