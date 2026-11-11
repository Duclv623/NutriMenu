"""Small real Gemini probes. Never print credentials or upstream error messages."""
import json
from datetime import UTC, datetime

import httpx

from rag_app.config import ROOT, Settings


def main():
    cfg = Settings()
    records = []
    headers = {'x-goog-api-key':cfg.gemini_api_key.get_secret_value()}
    base = 'https://generativelanguage.googleapis.com/v1beta/models/'
    probes = [
        ('generation', cfg.gemini_model, 'generateContent', {
            'contents':[{'parts':[{'text':'Trả lời duy nhất: KEY_OK'}]}],
            'generationConfig':{'maxOutputTokens':32,'temperature':0}}),
        ('embedding', cfg.gemini_embedding_model, 'embedContent', {
            'content':{'parts':[{'text':'Một câu hỏi dinh dưỡng dùng để kiểm tra API.'}]},
            'outputDimensionality':cfg.gemini_embedding_dimensions}),
    ]
    with httpx.Client(timeout=cfg.gemini_timeout, follow_redirects=False) as client:
        for operation, model, method, body in probes:
            record = {'operation':operation,'model':model}
            try:
                response = client.post(base + model + ':' + method,headers=headers,json=body)
                record['http_status'] = response.status_code
                result = response.json()
                record['ok'] = response.status_code == 200
                if record['ok']:
                    if operation == 'generation':
                        record['response_id'] = result.get('responseId')
                        record['usage'] = result.get('usageMetadata',{})
                        record['returned_expected_text'] = any('KEY_OK' in p.get('text','') for c in result.get('candidates',[]) for p in c.get('content',{}).get('parts',[]))
                    else:
                        record['dimensions'] = len(result.get('embedding',{}).get('values',[]))
                else:
                    error = result.get('error',{})
                    record['error_status'] = error.get('status')
                    record['error_reasons'] = [d.get('reason') for d in error.get('details',[]) if d.get('reason')]
            except Exception as error:
                record.update(ok=False,error_class=type(error).__name__)
            records.append(record)
    report = {'checked_at':datetime.now(UTC).isoformat(),'host':'generativelanguage.googleapis.com','probes':records}
    folder = ROOT/'docs/gemini'
    folder.mkdir(exist_ok=True)
    (folder/'key-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
