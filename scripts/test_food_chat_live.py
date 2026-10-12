"""Small real-key integration suite. Public synthetic questions, isolated history."""
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

CASES=[
    ('milk','200g sữa bò tươi có bao nhiêu đạm và calo?','nin_foods:10001'),
    ('pdf','100g ngô bắp tươi trong sách thành phần thực phẩm 2007 có bao nhiêu canxi?','fct2007:1007'),
    ('sum','Tính tổng đạm của 100g sữa bò tươi và 200g sữa dê tươi giúp tôi.','sum'),
    ('volume','200ml sữa bò tươi có bao nhiêu đạm?','volume'),
    ('dish','100g món Tiết luộc mã nin_dishes:HAP-223025 có bao nhiêu đạm?','nin_dishes:HAP-223025'),
    ('dish_200g','200g món Tiết luộc mã nin_dishes:HAP-223025 có bao nhiêu đạm?','nin_dishes:HAP-223025'),
    ('ambiguous','100g thịt bò có bao nhiêu calo?','ambiguous'),
    ('missing','100g ngô bắp tươi trong bảng 2007 có bao nhiêu chất xơ tổng số?','missing'),
    ('notes','Ký hiệu số 5 ở cột TLTK trong sách 2007 nghĩa là gì?','knowledge'),
    ('compare','200g sữa bò tươi với 100g sữa chua thì bên nào nhiều đạm và calo hơn?','compare'),
    ('fct_milk','100g sữa bò tươi trong bảng thực phẩm 2007 có bao nhiêu natri?','fct2007:10001'),
    ('selected','Tra cứu nin_dishes:HAP-223025; chất cần xem: đạm','nin_dishes:HAP-223025'),
    ('followup','Còn 200g thì sao?','nin_foods:10001'),
    ('vitamin','100g sữa bò tươi có bao nhiêu vitamin D và phốt pho?','nin_foods:10001'),
]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--ids',default='')
    parser.add_argument('--output',default='live-results.json')
    args=parser.parse_args()
    cfg=Settings()
    snapshot=Store(cfg.storage_dir/'rag.sqlite3').load_index()
    out=ROOT/'docs/food-integration'
    out.mkdir(exist_ok=True)
    report={'started_at':datetime.now(UTC).isoformat(),'model':cfg.active_model,'cases':[]}
    food_debug=[]
    original=OpenAIProvider.generate_food
    def capture(provider,question,hits,history):
        answer,usage=original(provider,question,hits,history)
        food_debug.append({'draft':answer.model_dump(),'review':answer._grounding_review,
            'sources':[h.chunk.text for h in hits],'response_ids':answer._provider_response_ids})
        return answer,usage
    OpenAIProvider.generate_food=capture
    with TemporaryDirectory(dir=ROOT/'tmp',prefix='food-live-') as folder:
        isolated=cfg.model_copy(update={'storage_dir':Path(folder),'rate_limit_per_minute':300})
        Store(Path(folder)/'rag.sqlite3').replace_index(*snapshot[:1],metadata=snapshot[2],vectors=snapshot[1])
        with TestClient(create_app(isolated)) as client:
            for cid,question,expected in CASES:
                if args.ids and cid not in args.ids.split(','):
                    continue
                request={'message':question}
                prior=None
                if cid=='followup':
                    first=client.post('/api/chat',json={'message':'100g sữa bò tươi có bao nhiêu đạm?','save_history':True})
                    prior={'http_status':first.status_code,'response':first.json()}
                    if first.status_code==200:
                        request.update(session_id=first.json()['session_id'],save_history=True)
                response=client.post('/api/chat',json=request)
                actual=response.json()
                errors=[]
                if response.status_code!=200:
                    errors.append('http_'+str(response.status_code))
                else:
                    if actual['answer_origin']!=cfg.answer_mode or not actual['provider_response_ids'] or not actual['usage'].get('output_tokens'):
                        errors.append('missing_real_api_provenance')
                    result=actual.get('food_result') or {}
                    items=result.get('items',[])
                    if ':' in expected and expected not in [i['id'] for i in items]:
                        errors.append('wrong_record')
                    if expected.startswith('nin_dishes:'):
                        if not items or any(not i['calculation_available'] or i['reference_amount_g']!=100 for i in items):
                            errors.append('wrong_dish_basis')
                        protein=22.8 if cid=='dish_200g' else 11.4
                        if not items or not any(n['key']=='protein' and n['amount_value']==protein for n in items[0]['display_nutrients']):
                            errors.append('wrong_dish_scaling')
                    if expected=='sum' and not any(n['key']=='protein' and n['value']==10.9 for n in result.get('totals',[])):
                        errors.append('wrong_sum')
                    if expected=='volume' and (not items or any(i['calculation_available'] for i in items)):
                        errors.append('invented_volume_conversion')
                    if expected=='ambiguous' and not result.get('unresolved'):
                        errors.append('missing_clarification')
                    if expected=='knowledge' and not any(c['source_id']=='vtn-fct-2007' for c in actual['citations']):
                        errors.append('missing_pdf_notes_citation')
                    if expected=='missing' and (not items or any(n['value'] is not None for n in items[0]['display_nutrients'])):
                        errors.append('invented_fiber')
                    if expected=='compare' and (result.get('operation')!='compare' or len(items)!=2):
                        errors.append('comparison_not_resolved')
                    if cid=='followup' and (prior['http_status']!=200 or not items or items[0]['amount_g']!=200
                            or not any(n['key']=='protein' and n['amount_value']==7.8 for n in items[0]['display_nutrients'])):
                        errors.append('followup_context_lost')
                report['cases'].append({'id':cid,'question':question,'http_status':response.status_code,
                    'errors':errors,'passed':not errors,'response':actual,'prior_turn':prior,'food_debug':list(food_debug)})
                food_debug.clear()
                report['passed']=sum(r['passed'] for r in report['cases'])
                (out/args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps({'id':cid,'passed':not errors,'errors':errors,'answer':actual.get('answer',actual.get('detail'))},ensure_ascii=False),flush=True)
                if response.status_code==503 and '429' in str(actual):
                    break


if __name__=='__main__':
    main()
