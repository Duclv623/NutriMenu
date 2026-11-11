"""One tiny real request; persist only quota identifiers, never upstream messages."""
import json
from datetime import UTC, datetime

import httpx

from rag_app.config import ROOT, Settings

cfg = Settings()
with httpx.Client(timeout=45,follow_redirects=False) as client:
    response = client.post('https://generativelanguage.googleapis.com/v1beta/models/'+cfg.gemini_model+':generateContent',
        headers={'x-goog-api-key':cfg.gemini_api_key.get_secret_value()},
        json={'contents':[{'parts':[{'text':'Reply: OK'}]}],'generationConfig':{'maxOutputTokens':20,'thinkingConfig':{'thinkingLevel':'minimal'}}})
    body = response.json()
    safe = {'checked_at':datetime.now(UTC).isoformat(),'http_status':response.status_code,
        'response_id':body.get('responseId'),'usage':body.get('usageMetadata'),
        'quota_violations':[v for d in body.get('error',{}).get('details',[]) for v in d.get('violations',[])],
        'retry_delay':[d['retryDelay'] for d in body.get('error',{}).get('details',[]) if 'retryDelay' in d]}
    (ROOT/'docs/gemini/limits-check.json').write_text(json.dumps(safe,indent=2),encoding='utf-8')
    print(json.dumps(safe,indent=2))
