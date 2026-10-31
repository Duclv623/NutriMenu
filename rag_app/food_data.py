"""Local, source-preserving nutrition lookup. No LLM arithmetic or inferred portions."""
import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from decimal import Decimal
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rag_app.config import ROOT
from rag_app.data_quality import review_record
from rag_app.retrieval import fold
from rag_app.safety import is_intake_advice

DATA = ROOT/'data/structured'
SOURCES = {
    'nin_foods': {'title':'Viện Dinh dưỡng — dữ liệu thực phẩm', 'year':2026,
                  'url':'https://viendinhduong.vn/vi/cong-cu-va-tien-ich/gia-tri-dinh-duong-thuc-pham'},
    'nin_dishes': {'title':'Viện Dinh dưỡng — dữ liệu món ăn', 'year':2026,
                   'url':'https://viendinhduong.vn/vi/cong-cu-va-tien-ich/gia-tri-dinh-duong-mon-an'},
    'fct2007': {'title':'Bảng thành phần thực phẩm Việt Nam 2007', 'year':2007,
                'url':'/api/documents/vtn-fct-2007/pdf'},
}


class FoodItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1,max_length=150)
    amount: float | None = Field(default=None,gt=0,le=100000)
    unit: str = Field(default='g',max_length=25)


class FoodPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation: Literal['lookup','compare','sum','search']
    items: list[FoodItem] = Field(max_length=5)
    nutrients: list[str] = Field(default_factory=list,max_length=15)
    dataset: Literal['auto','nin_foods','nin_dishes','fct2007'] = 'auto'
    clarification: str = ''


def canonical(name,unit):
    s=fold(name)
    tests=[('energy',r'nang luong|energy|calo|kcal'),('protein',r'protein|chat dam|^dam$'),
        ('saturated_fatty_acids',r'(?:acid|axit|chat) beo bao hoa|tong so acid beo no|total saturated'),
        ('monounsaturated_fatty_acids',r'khong bao hoa don|khong no.*1 noi doi|total monounsaturated'),
        ('polyunsaturated_fatty_acids',r'khong bao hoa da|khong no nhieu noi doi|total polyunsaturated'),
        ('fat',r'^lipid|^chat beo|total lipid|^beo$|^fat$'),('carbohydrate',r'glucid|carbohydrate|chat bot duong|^carbs?$'),
        ('cellulose',r'celluloza'),('fiber',r'chat xo|fibre|fiber|^xo$'),
        ('sodium',r'natri|sodium|^na$'),('calcium',r'^calci\b|calcium|canxi'),('iron',r'^sat|iron'),
        ('water',r'^nuoc|water'),('added_sugars',r'duong them|duong bo sung|added sugars?'),('sugar',r'duong tong|sugars?.*total|total sugar|^duong$'),
        ('vitamin_c',r'vit.? ?c\b|vitamin c'),('potassium',r'^kali|potassium'),
        ('phosphorus',r'phot\s*pho|phospho|phosphor'),('magnesium',r'magie|magnesium'),
        ('zinc',r'^kem\b|zinc'),('copper',r'^dong\b|copper'),('selenium',r'selen'),
        ('manganese',r'^mangan|manganese'),
        ('vitamin_a_rae',r'vit(?:amin)?\s*a[- ]*rae'),('retinol',r'retinol'),
        ('vitamin_b1',r'vit(?:amin)?\s*b1\b|thiamin'),('vitamin_b2',r'vit(?:amin)?\s*b2\b|riboflavin'),
        ('vitamin_b3',r'vit(?:amin)?\s*(?:b3|pp)\b|niacin'),
        ('vitamin_b5',r'vit(?:amin)?\s*b5\b|pantothenic'),('vitamin_b6',r'vit(?:amin)?\s*b6\b|pyridoxin'),
        ('biotin',r'vit(?:amin)?\s*(?:b7|h)\b|biotin'),
        ('folic_acid',r'folic|vit(?:amin)?\s*b9\b'),
        ('folate_dfe',r'folate.*dfe'),('folate_food',r'folate.*food'),('folate',r'folat'),
        ('vitamin_b12',r'vit(?:amin)?\s*b12\b|cyanocobalamin'),
        ('vitamin_d',r'vit(?:amin)?\s*d\b'),('vitamin_e',r'vit(?:amin)?\s*e\b'),
        ('vitamin_k',r'vit(?:amin)?\s*k\b')]
    for key,pattern in tests:
        if re.search(pattern,s):
            return key+('_kj' if key=='energy' and unit.lower()=='kj' else '')
    return re.sub(r'[^a-z0-9]+','_',s).strip('_')


def number(raw):
    if raw is None or str(raw).strip() in {'','-','–'}:
        return None
    try:
        value=float(str(raw).replace(',','.'))
        return value if math.isfinite(value) and value>=0 else None
    except (ValueError,TypeError):
        return None


def normalized(value):
    value=fold(value)
    for original,replacement in [('bap','ngo'),('dau hu','dau phu'),('heo','lon')]:
        value=re.sub(r'\b'+original+r'\b',replacement,value)
    if value.strip() == 'sua tuoi':
        value = 'sua bo tuoi'
    return ' '.join(re.findall(r'[a-z0-9]+',value))


def spelling(value):
    """Preserve Vietnamese distinctions (cơm/cốm, bò/bơ) in user names."""
    value = unicodedata.normalize('NFC', value).lower()
    for original, replacement in [('bắp', 'ngô'), ('đậu hũ', 'đậu phụ'), ('heo', 'lợn')]:
        value = re.sub(r'\b' + original + r'\b', replacement, value)
    return ' '.join(re.findall(r'[^\W_]+', value))


def compatible_spelling(query, name):
    name_words = spelling(name).split()
    # Unaccented tokens remain searchable. An explicitly accented token may
    # not silently match another Vietnamese word with the same ASCII fold.
    return all(not (word != fold(word) and any(fold(n) == fold(word) for n in name_words)
                    and word not in name_words) for word in spelling(query).split())


def raw_grain_prefix(query):
    """Only raw grain qualifiers may be omitted when offering grain choices.

    Never remove cooked-rice state or infer gram values for a dish.
    """
    q = normalized(query)
    if q.startswith('gao ') and re.search(r'\s(?:chua nau|song)$', q):
        return re.sub(r'\s(?:chua nau|song)$', '', q)
    return None


def read_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as stream:
        return list(csv.DictReader(stream))


def verify_fct(folder):
    report=json.loads((folder/'quality_report.json').read_text(encoding='utf-8'))
    if report['food_records']!=526 or report['pages']!=567 or report['issues']:
        raise ValueError('FCT chưa vượt kiểm tra trích xuất.')
    for name in ['foods.json','pages.json']:
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=report.get('exports',{}).get(name):
            raise ValueError(f'FCT export đã đổi checksum: {name}')
    if hashlib.sha256((ROOT/'data/VTN_FCT_2007.pdf').read_bytes()).hexdigest()!=report['source_sha256']:
        raise ValueError('PDF FCT đã thay đổi; cần trích xuất và index lại.')
    return report


class FoodCatalog:
    def __init__(self, root=DATA):
        self.root=Path(root)
        self.records={}
        self.audit=[]
        overrides_path = self.root / 'review_verified_overrides.json'
        overrides = json.loads(overrides_path.read_text(encoding='utf-8')) if overrides_path.exists() else []
        for override in overrides:
            evidence = (ROOT / override['evidence_file']).resolve()
            if not evidence.is_relative_to((ROOT / 'data/collected').resolve()) or hashlib.sha256(evidence.read_bytes()).hexdigest() != override['evidence_sha256']:
                raise ValueError('Verified override evidence changed')
            source_rows = json.loads(evidence.read_text(encoding='utf-8'))
            source_row = next(r for r in source_rows if r['code'] == override['source_code'])
            if number(source_row[override['source_field']]) != override['new_value']:
                raise ValueError('Override does not match source value')
        for dataset,folder,filename,key in [
            ('nin_foods','nin_foods_2026-10-06','foods_core.csv','food_code'),
            ('nin_dishes','nin_dishes_2026-10-06','dishes_core.csv','dish_code')]:
            directory=self.root/folder
            if not directory.exists():
                continue
            manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
            for file in [filename,'nutrients_long.csv']:
                expected=manifest['exports'][file]
                if hashlib.sha256((directory/file).read_bytes()).hexdigest()!=expected:
                    raise ValueError(f'Dữ liệu nguồn đã đổi checksum: {dataset}/{file}')
            for row in read_csv(directory/filename):
                rid=dataset+':'+row[key]
                reference_amount_g=number(row['reference_amount_g'])
                if reference_amount_g != 100:
                    raise ValueError(f'Cơ sở dữ liệu NIN phải là 100 g: {rid}')
                self.records[rid]={'id':rid,'code':row[key],'name':row['name_vi'],'name_en':row['name_en'],
                    'dataset':dataset,'page':None,'category':row.get('category_vi',''),
                    'source_metadata':dict(row),
                    'reference_amount_g':reference_amount_g,
                    'basis':'100 g phần ăn được' if dataset=='nin_foods' else '100 g món ăn',
                    'nutrients':[]}
                if dataset=='nin_foods':
                    self.records[rid]['nutrients'].append({'key':'energy','name':'Năng lượng','unit':'kcal',
                        'value':number(row['energy_kcal']),'raw_value':row['energy_kcal'],'source_key':'energy'})
            for row in read_csv(directory/'nutrients_long.csv'):
                record=self.records[dataset+':'+row[key]]
                if number(row['reference_amount_g']) != record['reference_amount_g']:
                    raise ValueError(f'Cơ sở dòng chất dinh dưỡng không khớp: {record["id"]}')
                value=number(row['value'])
                nutrient={'key':canonical(row['nutrient_name_vi'],row['unit']),
                    'name':row['nutrient_name_vi'],'name_en':row['nutrient_name_en'],
                    'unit':row['unit'],'value':value,'raw_value':row.get('raw_value',row['value']),
                    'source_key':row['nutrient_key'],'parent_key':row.get('parent_nutrient_key',''),
                    'source_row':dict(row)}
                if row['value'] and value is None:
                    nutrient['quality_note']='Giá trị nguồn không hợp lệ, không dùng để tính.'
                    self.audit.append({'record':record['id'],'issue':'invalid_value','raw':row['value']})
                record['nutrients'].append(nutrient)
        pdf=self.root/'fct2007/foods.json'
        if pdf.exists():
            verify_fct(pdf.parent)
            for record in json.loads(pdf.read_text(encoding='utf-8')):
                for nutrient in record['nutrients']:
                    nutrient['key']=canonical(nutrient['name'],nutrient['unit'])
                self.records[record['id']]=record
        for record in self.records.values():
            record['source']=SOURCES[record['dataset']]
            seen=Counter((n.get('source_key',n['key']),n['unit'],n.get('parent_key','')) for n in record['nutrients'])
            for nutrient in record['nutrients']:
                key=(nutrient.get('source_key',nutrient['key']),nutrient['unit'],nutrient.get('parent_key',''))
                if seen[key]>1:
                    nutrient.update(value=None,quality_note='Nguồn có dòng trùng; xem dữ liệu gốc, không tự chọn giá trị.')
            for key,count in seen.items():
                if count>1:
                    self.audit.append({'record':record['id'],'issue':'duplicate_nutrient','key':key,'rows':count})
            record['_name']=normalized(record['name'])
            record['_english']=normalized(record.get('name_en',''))
            for override in overrides:
                if record['id'] == override['id']:
                    nutrient = next(n for n in record['nutrients'] if n['key'] == override['nutrient_key'])
                    if nutrient['value'] != override['old_value']:
                        raise ValueError('Override baseline changed; review required')
                    nutrient['previous_value'] = nutrient['value']
                    nutrient['value'] = override['new_value']
                    nutrient['quality_note'] = 'Giá trị cập nhật theo nguồn NIN thu 30/10/2026; giữ giá trị trước và bằng chứng riêng.'
                    nutrient['review_evidence'] = override
            for issue in review_record(record):
                self.audit.append({'record': record['id'], 'issue': issue})

    def status(self):
        return {'ready':bool(self.records),'records':len(self.records),
            'datasets':dict(Counter(r['dataset'] for r in self.records.values())),
            'unknown_portion_records':sum(r['reference_amount_g'] is None for r in self.records.values()),
            'quality_issues':len(self.audit),
            'review_statuses':dict(Counter(r['review_status'] for r in self.records.values()))}

    def get(self,rid):
        return {k:v for k,v in self.records[rid].items() if not k.startswith('_')}

    def search(self,query,dataset='auto',limit=8):
        raw_prefix = raw_grain_prefix(query)
        q=raw_prefix or normalized(query)
        query_tokens=set(q.split())
        explicit_state=bool(query_tokens & {'song','tuoi','chin','luoc','hap','chien','kho','hop','nuong','om','ran'})
        ranked=[]
        for r in self.records.values():
            if dataset!='auto' and r['dataset']!=dataset:
                continue
            name=r['_name']
            if raw_prefix and (r['dataset'] == 'nin_dishes' or not name.startswith(raw_prefix)
                               or set(name.split()) & {'chin', 'nau', 'rang', 'chien', 'hap', 'luoc'}):
                continue
            if query.lower() in {r['id'].lower(),r['code'].lower()}:
                score=200
            elif not compatible_spelling(query, r['name']):
                continue
            elif q in {name,r['_english']}:
                score=100
            elif q and re.search(r'\b'+re.escape(q)+r'\b',name):
                score=75-len(name.split())*.3
            else:
                tokens=set(q.split())
                common=tokens&set(name.split())
                score=55*len(common)/max(len(tokens),1)-abs(len(name.split())-len(tokens)) if common else 0
            if 65<=score<100 and name.startswith(q + ' ') and not explicit_state and set(name.split()) & {'tuoi','song'}:
                score+=4
            if raw_prefix:
                # Source grain types still need explicit selection; do not
                # silently reinterpret a preparation qualifier as an exact ID.
                score = min(score, 64)
            if score>=25:
                ranked.append((score,1 if r['dataset']=='nin_foods' else 0,r))
        ranked.sort(key=lambda row:(-row[0],-row[1],row[2]['id']))
        return [{**self.get(r['id']),'match_score':round(score,2)} for score,_,r in ranked[:limit]]

    def looks_like_lookup(self,query):
        if is_intake_advice(query):
            return False
        q=fold(query)
        return bool(re.search(r'\b(?:nin_foods|nin_dishes|fct2007):[a-z0-9-]+\b',q)
            or re.search(r'\d+(?:[.,]\d+)?\s*(?:g|gram|kg|ml|lit)\b',q)
            or re.search(r'bao nhieu|ham luong|thanh phan|chua (?:chat|gi)|tra cuu|so sanh|nhieu (?:dam|protein|calo|canxi)|it (?:calo|duong)|tong (?:calo|dam|dinh duong)',q)
            and any(re.search(r'\b'+term+r'\b', q) for term in ('thuc pham','mon an','sua','com','pho','trung','thit','rau','gao','chuoi')))

    def bind_explicit_ids(self,plan,question):
        """A user's selected source ID takes precedence over model name parsing."""
        ids=list(dict.fromkeys(re.findall(r'\b(?:nin_foods|nin_dishes|fct2007):[A-Za-z0-9-]+\b',question)))
        known=[rid for rid in ids if rid in self.records]
        if len(known)==1 and len(plan.items)==1:
            plan.items[0].name=known[0]
            plan.dataset='auto'
        elif len(known)>1 and len(known)==len(plan.items):
            remaining=list(known)
            for item in plan.items:
                matches=[rid for rid in remaining if item.name==rid or normalized(item.name)==self.records[rid]['_name']]
                if len(matches)==1:
                    item.name=matches[0]
                    remaining.remove(matches[0])
            plan.dataset='auto'
        return plan

    def resolve_selection(self, question, history):
        """Merge a bare selected name/ID into the pending request, without an
        extra model call or trusting quantities in previous answer prose."""
        if not history:
            return None
        result = history[-1].get('response', {}).get('food_result') or {}
        pending = result.get('unresolved', [])
        q = normalized(question.strip(' .!?'))
        matches = [(p, c) for p in pending for c in p.get('candidates', [])
                   if (q == normalized(c['name']) and compatible_spelling(question, c['name'])
                       and spelling(question.strip(' .!?')) != spelling(p['query']))
                   or question.strip() == c['id']]
        if not matches or len({p['query'] for p, _ in matches}) != 1:
            return None
        # Same name across sources: keep the original candidate priority.
        pending_item, selected = matches[0]
        try:
            plan = FoodPlan.model_validate(result['request'])
        except (KeyError, ValueError):
            return None
        items = [i for i in plan.items if i.name == pending_item['query']]
        if len(items) != 1:
            return None
        items[0].name = selected['id']
        plan.dataset = 'auto'
        plan.clarification = ''
        return plan

    def simple_lookup(self, question):
        """Parse only explicit single-food quantity + nutrient questions.
        Complex/free-form requests still go through the real model planner."""
        match = re.fullmatch(r'\s*(\d+(?:[.,]\d+)?)\s*(g|gram|gam|kg|ml)\s+(.+?)\s+(?:có\s+)?bao nhiêu\s+(.+?)[?!.]*\s*', question, re.I)
        if not match:
            return None
        amount, unit, name, nutrients = match.groups()
        if re.search(r'\b(?:va|voi|tong|so sanh|theo|2007|bang|sach)\b', fold(name)):
            return None
        fields = [s.strip(' ?!.') for s in re.split(r'\s+và\s+|,', nutrients, flags=re.I)]
        allowed = {'energy', 'protein', 'fat', 'carbohydrate', 'fiber', 'calcium', 'sodium', 'iron', 'vitamin_d', 'vitamin_c', 'phosphorus'}
        if not fields or any(canonical(s, '') not in allowed for s in fields):
            return None
        candidates = self.search(name)
        if not candidates or candidates[0]['match_score'] < 65:
            return None
        try:
            return FoodPlan(operation='lookup', items=[FoodItem(name=name, amount=float(amount.replace(',', '.')), unit=unit.lower())], nutrients=fields)
        except ValueError:
            return None

    def execute(self,plan):
        output={'operation':plan.operation,'items':[],'unresolved':[],'totals':[],'notes':[],
                'catalog_counts':self.status()['datasets']}
        if plan.clarification:
            output['notes'].append(plan.clarification)
        for requested in plan.items:
            candidates=self.search(requested.name,plan.dataset)
            if not candidates:
                output['unresolved'].append({'query':requested.name,'reason':'Không tìm thấy thực phẩm phù hợp.','candidates':[]})
                continue
            best=candidates[0]
            exact=[c for c in candidates if c['match_score']>=100]
            same_source_exact=[c for c in exact if c['dataset']==best['dataset']]
            prefix = normalized(requested.name)
            # An ASCII exact match is not unambiguous if a different accented
            # word also matches: "com" could mean cơm or cốm.
            spellings = {tuple(spelling(c['name']).split()[:len(prefix.split())]) for c in candidates
                         if normalized(c['name']) == prefix or normalized(c['name']).startswith(prefix + ' ')}
            accent_ambiguous = spelling(requested.name) == fold(spelling(requested.name)) and len(spellings) > 1
            # Identical names in older sources are alternatives, never silently mixed.
            if accent_ambiguous or len(same_source_exact)>1 or (not exact and (best['match_score']<65 or len([c for c in candidates if c['match_score']>=best['match_score']-3])>1)):
                choices = candidates
                if not exact:
                    # Partial ingredient selection must contain all requested
                    # words: 'sữa bò' must not offer 'sữa tươi trân châu'.
                    prefix = raw_grain_prefix(requested.name) or normalized(requested.name)
                    choices = [c for c in candidates if normalized(c['name']).startswith(prefix + ' ')
                               or normalized(c['name']) == prefix]
                seen = set()
                unique = []
                for c in choices:
                    name = normalized(c['name'])
                    # Keep same-source duplicate records distinguishable, but
                    # don't clutter choices with a second source of the same food.
                    if name in seen and c['dataset'] != best['dataset']:
                        continue
                    seen.add(name)
                    unique.append(c)
                output['unresolved'].append({'query':requested.name,'reason':'Cần chọn đúng loại/trạng thái thực phẩm.',
                    'candidates':[{'id':c['id'],'name':c['name'],'dataset':c['dataset']} for c in unique[:6]]})
                continue
            item={k:v for k,v in best.items() if k not in {'match_score','nutrients'}}
            item['alternatives']=[{'id':c['id'],'name':c['name'],'dataset':c['dataset']} for c in exact if c['id']!=best['id']]
            item['requested_amount']=requested.amount
            item['requested_unit']=requested.unit
            item['requested_name']=requested.name
            unit=fold(requested.unit.strip())
            grams=requested.amount*(1000 if unit in {'kg','kilogram'} else 1) if requested.amount is not None and unit in {'g','gram','gam','kg','kilogram'} else None
            item['amount_g']=grams
            item['calculation_available']=best['reference_amount_g'] is not None and (requested.amount is None or grams is not None)
            item['basis_note']=best['basis']
            if requested.amount is not None and grams is None:
                item['basis_note']+='; chưa có khối lượng tương ứng với đơn vị '+requested.unit+', không quy đổi sang gram.'
            factor=Decimal(str(grams or best['reference_amount_g']))/Decimal(str(best['reference_amount_g'])) if item['calculation_available'] else None
            selected=[]
            for nutrient in best['nutrients']:
                n=dict(nutrient)
                n['amount_value']=float((Decimal(str(n['value']))*factor).quantize(Decimal('.000001'))) if n['value'] is not None and factor is not None else None
                selected.append(n)
            item['nutrients']=selected
            if plan.nutrients:
                wanted=[canonical(n,'') for n in plan.nutrients]
                # Known synonyms select one canonical nutrient, not every name
                # containing a broad word such as "béo" (fatty acids).
                available_keys = {n['key'] for n in selected}
                shown=[n for n in selected if n['key'] in wanted or any(
                    key not in available_keys and normalized(q) in normalized(n['name'])
                    for q, key in zip(plan.nutrients, wanted, strict=True))]
                for query,key in zip(plan.nutrients,wanted,strict=True):
                    if not any(n['key']==key or normalized(query) in normalized(n['name']) for n in shown):
                        shown.append({'key':key,'name':query,'unit':'','value':None,'amount_value':None,
                                      'quality_note':'Không có trường tương ứng trong bản ghi nguồn.'})
                item['display_nutrients']=shown
            else:
                core={'energy','protein','fat','carbohydrate','fiber','sodium','calcium','iron','cellulose','vitamin_c'}
                item['display_nutrients']=[n for n in selected if n['key'] in core]
            item['record_url']='/api/foods/'+item['id']+'/preview'
            output['items'].append(item)
        if plan.operation=='sum' and output['items'] and not output['unresolved']:
            if all(i['calculation_available'] and i['requested_amount'] is not None for i in output['items']):
                keys=set.union(*[{(n['key'],n['unit'].lower()) for n in i['nutrients']} for i in output['items']])
                keys |= {('energy','kcal'),('protein','g'),('fat','g'),('carbohydrate','g'),('fiber','g'),('sodium','mg')}
                for key,unit in sorted(keys):
                    groups=[[n for n in i['nutrients'] if (n['key'],n['unit'].lower())==(key,unit)] for i in output['items']]
                    valid=all(len(group)==1 and group[0]['amount_value'] is not None for group in groups)
                    name=next((group[0]['name'] for group in groups if group),{'fiber':'Chất xơ'}.get(key,key))
                    output['totals'].append({'key':key,'name':name,'unit':unit,
                        'value':float(sum(Decimal(str(group[0]['amount_value'])) for group in groups)) if valid else None})
                output['notes'].append('Tổng chỉ áp dụng các thực phẩm/khối lượng đã tra, không bao gồm gia vị hoặc dầu chưa khai báo.')
            else:
                output['notes'].append('Chưa tính tổng: cần khối lượng bằng gram và cơ sở khẩu phần đã xác minh cho mọi thành phần.')
        if not plan.items:
            output['notes'].append('Cần tên thực phẩm/món ăn để tra cứu.')
        wanted={canonical(n,'') for n in plan.nutrients} if plan.nutrients else {'energy','protein','fat','carbohydrate','fiber','sodium','calcium','iron'}
        output['display_totals']=[n for n in output['totals'] if n['key'] in wanted]
        return output


@lru_cache(maxsize=1)
def get_catalog():
    return FoodCatalog()


def food_hits(result):
    from rag_app.domain import Chunk, Hit
    hits=[]
    for item in result['items']:
        amount=f"{item['requested_amount']} {item['requested_unit']}" if item['requested_amount'] is not None else 'không nêu, xem cơ sở nguồn'
        lines=[f"Thực phẩm: {item['name']} ({item.get('name_en','')}).",
            f"Nguồn: {item['source']['title']}; mã {item['code']}; cơ sở: {item['basis_note']}.",
            f"Khối lượng người hỏi: {amount}. Có thể quy đổi: {item['calculation_available']}."]
        for n in item['display_nutrients']:
            lines.append(f"- {n['name']}: giá trị gốc {n['value'] if n['value'] is not None else 'chưa có dữ liệu'} {n['unit']}; "
                f"giá trị theo lượng hỏi {n['amount_value'] if n['amount_value'] is not None else 'chưa tính được'} {n['unit']}. "
                +n.get('quality_note',''))
        if item['alternatives']:
            lines.append('Có bản ghi cùng tên ở nguồn khác: '+', '.join(i['id'] for i in item['alternatives'])+'. Không trộn số liệu giữa các nguồn.')
        body='\n'.join(lines)
        hits.append(Hit(score=1,chunk=Chunk(id=item['id'],source_id='vtn-fct-2007' if item['dataset']=='fct2007' else item['dataset'],
            title=item['source']['title'],text=body,section=item['name'],pages=[item['page']] if item['page'] else [],
            printed_pages=[item['ordinal']] if item.get('ordinal') else [],filename='VTN_FCT_2007.pdf' if item['page'] else 'nutrients_long.csv',
            source_url=item['source']['url'],year=item['source']['year'],version=str(item['source']['year']),
            sha256=hashlib.sha256(body.encode()).hexdigest(),token_count=0,
            document_format='pdf' if item['page'] else 'structured',locators=[item['id']],
            warnings=['Số liệu theo nguồn và loại thực phẩm đã chọn; không dùng để tự xây khẩu phần điều trị.'])))
    extra=[]
    for unresolved in result['unresolved']:
        extra.append(f"Yêu cầu {unresolved['query']}: {unresolved['reason']} Lựa chọn: "+json.dumps(unresolved['candidates'],ensure_ascii=False))
    extra.extend(result['notes'])
    if result['totals']:
        extra.append('Tổng tính bằng code theo các lượng đã khai báo: '+json.dumps(result['display_totals'],ensure_ascii=False))
    if extra:
        body='\n'.join(extra)
        hits.append(Hit(score=1,chunk=Chunk(id='lookup-context',source_id='nutrition-tool',title='Kết quả kiểm tra yêu cầu tra cứu',
            text=body,section='Điều kiện tra cứu và phép tính',pages=[],printed_pages=[],filename='',source_url='/api/foods',
            year=2026,version='1',sha256=hashlib.sha256(body.encode()).hexdigest(),token_count=0,
            document_format='structured',locators=[])))
    return hits


def render_food(food):
    rows=''.join('<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in (
        n['name'],n['value'] if n['value'] is not None else 'Chưa có dữ liệu',n['unit'],n.get('raw_value',''),
        n.get('reference_code',n.get('source_key','')),n.get('quality_note','')) )+'</tr>' for n in food['nutrients'])
    link=food['source']['url']+(f"#page={food['page']}" if food.get('page') else '')
    return '<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Thành phần thực phẩm</title><link rel="stylesheet" href="/static/styles.css"><body><main><a href="/">← Chatbot</a><h1>'+escape(food['name'])+'</h1><p>'+escape(food['name_en'])+'</p><p>'+escape(food['basis'])+'</p><p>'+escape(food['source']['title'])+' · '+escape(food['id'])+'</p><a href="'+escape(link,quote=True)+'" target="_blank" rel="noopener">Mở nguồn gốc</a><div class="nutrition-scroll"><table class="nutrition"><thead><tr><th>Thành phần</th><th>Giá trị</th><th>Đơn vị</th><th>Ô gốc</th><th>Mã nguồn</th><th>Ghi chú</th></tr></thead><tbody>'+rows+'</tbody></table></div><p>Giữ nguyên khác biệt giữa các nguồn. Giá trị thiếu không phải số 0.</p></main></body></html>'
