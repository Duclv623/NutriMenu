"""Build review artifacts and one source-checked knowledge addition, without LLM calls."""
import hashlib
import json
import re
from collections import Counter
from html import unescape

from rag_app.config import ROOT
from rag_app.food_data import FoodCatalog

OUT = ROOT / 'data/staging/review_2026-10-30'
RAW = ROOT / 'data/collected/review_2026-10-30'


def save(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    catalog = FoodCatalog()
    save('quality_report.json', {'catalog': catalog.status(), 'issues': catalog.audit,
                               'clinical_review': False})
    pending = [{'id': r['id'], 'name': r['name'], 'status': r['review_status'],
                'flags': r['quality_flags'], 'missing': 'Source evidence of reference mass/portion and nutrient units',
                'source': r['source']} for r in catalog.records.values() if r['review_status'] != 'verified']
    save('pending_verification.json', pending)
    save('normalized_records.json', [catalog.get(rid) for rid in catalog.records])
    rows = []
    for p in sorted((RAW / 'nin_dishes/raw').glob('*.json')):
        rows.extend(json.loads(p.read_text(encoding='utf-8'))['data'])
    old = json.loads((ROOT/'data/structured/nin_dishes_2026-10-06/dishes_full.json').read_text(encoding='utf-8'))
    duplicate_ids = [k for k, n in Counter(r['_id'] for r in rows).items() if n > 1]
    save('nin_comparison.json', {'previous_records':len(old), 'new_rows':len(rows),
         'new_unique_ids':len({r['_id'] for r in rows}), 'duplicate_ids':duplicate_ids,
         'removed_codes':sorted({r['code'] for r in old}-{r['code'] for r in rows}),
         'decision':'Do not replace active data: duplicate source IDs and missing per-record basis evidence.'})
    fresh_foods = RAW/'nin_foods/records.json'
    if fresh_foods.exists():
        foods = json.loads(fresh_foods.read_text(encoding='utf-8'))
        old_foods = {r['code']:r for r in json.loads((ROOT/'data/structured/nin_foods_2026-10-06/foods_full.json').read_text(encoding='utf-8'))}
        changed = [r for r in foods if r['code'] in old_foods and r != old_foods[r['code']]]
        save('food_candidates.json', changed)
        save('food_refresh_summary.json', {'downloaded':len(foods),'changed_records':len(changed),
                                         'decision':'Candidates retained separately; no cross-source filling of missing nutrients.'})
    raw_path = RAW/'raw/ada-sitting.html'
    text = unescape(re.sub('<[^>]+>', ' ', raw_path.read_text(encoding='utf-8')))
    text = re.sub(r'\s+', ' ', text)
    expected = 'recommends that everyone break up bouts of sitting with brief activity every 30 minutes'
    if expected not in text:
        raise ValueError('ADA source text changed; content review required')
    digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    prepared = {'schema_version':1,'source_id':'ada-sitting-breaks',
                'original_url':'https://diabetes.org/health-wellness/fitness/break-sitting-streak',
                'original_sha256':digest,'segments':[{
                    'section':'Ngắt thời gian ngồi lâu bằng vận động ngắn',
                    'locators':['article-introduction-paragraph-2'],
                    'text':'Bài giáo dục Breaking Sitting Streaks của ADA khuyến nghị ngắt các đợt ngồi bằng hoạt động ngắn mỗi 30 phút; những đợt vận động ngắn có thể đặc biệt hữu ích với người đái tháo đường type 2. Đây là nguyên tắc giáo dục chung, không phải chương trình tập được cá nhân hóa.'}]}
    filename = 'supplement-ada-sitting-breaks.json'
    target = ROOT/'data'/filename
    target.write_text(json.dumps(prepared, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest_path = ROOT/'config/sources.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    source = {'id':'ada-sitting-breaks','filename':filename,'format':'curated',
              'title':'ADA — Breaking Sitting Streaks','url':prepared['original_url'],
              'year':2026,'version':'Thu 30/10/2026; trang không xác định năm xuất bản; không gán là Standards 2026.',
              'enabled':True,'role':'knowledge','language':'vi',
              'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
              'original_collection':'review_2026-10-30','original_raw_file':'raw/ada-sitting.html',
              'original_sha256':digest,'segments':[{'section':prepared['segments'][0]['section']}],
              'warnings':['Nguyên tắc vận động chung; chương trình cá nhân cần được chuyên gia đánh giá.',
                          'Năm 2026 là ngày thu, không phải xác nhận năm xuất bản hay phiên bản Standards.']}
    manifest['sources'] = [s for s in manifest['sources'] if s['id'] != source['id']] + [source]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    save('knowledge_review.json', {'source_id':source['id'],'method':'Literal source check and Vietnamese paraphrase comparison',
                                'clinical_review':False,'original_sha256':digest,'locator':'article introduction, paragraph 2'})
    (OUT/'normalization_log.jsonl').write_text('\n'.join(json.dumps({
        'id':r['id'],'field':'reference_amount_g','before':r['source_reference_amount_g'], 'after':r['reference_amount_g'],
        'reason':r['quality_flags'] or ['per_record_basis_unverified'], 'raw_preserved':True},ensure_ascii=False)
        for r in catalog.records.values() if r['review_status'] != 'verified')+'\n',encoding='utf-8')
    print(json.dumps({'catalog':catalog.status(),'pending_records':len(pending),'new_knowledge_source':source['id']},ensure_ascii=False))


if __name__ == '__main__':
    main()
