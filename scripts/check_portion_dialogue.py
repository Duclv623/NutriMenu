"""Two representative real-provider turns, using an isolated copy of the index."""
import json
import sqlite3

from fastapi.testclient import TestClient

from rag_app.config import ROOT, Settings
from rag_app.main import create_app


def main():
    cfg = Settings()
    isolated = ROOT/'tmp/portion-dialogue-check'
    isolated.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(cfg.storage_dir/'rag.sqlite3') as src, sqlite3.connect(isolated/'rag.sqlite3') as dst:
        src.backup(dst)
    cfg = cfg.model_copy(update={'storage_dir':isolated})
    output = ROOT/'docs/release-2026-10-30/portion-dialogue.json'
    results = []
    with TestClient(create_app(cfg)) as client:
        session = None
        for question in ['sáng tôi ăn phở được không', 'tôi ăn bao nhiêu thì ổn']:
            request = {'message':question}
            if session:
                request['session_id'] = session
            response = client.post('/api/chat', json=request)
            body = response.json()
            session = body.get('session_id')
            results.append({'question':question,'http_status':response.status_code,'response':body})
            output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
            print(response.status_code,body.get('answer',body.get('detail')),flush=True)
            if response.status_code != 200:
                break


if __name__ == '__main__':
    main()
