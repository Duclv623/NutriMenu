"""Reproducible, coordinate-based FCT extraction; run with pdfplumber installed.

Never use flattened PDF text for nutrient numbers: reference columns can touch values.
"""
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pdfplumber
from pdfplumber.utils import extract_text

ROOT = Path(__file__).resolve().parents[1]
OLD = 'µ¸¶·¹¨»¾¼½Æ©ÇÊÈÉË®ÌÐÎÏÑªÒÕÓÔÖ×ÝØÜÞßãáâä«åèæçé¬êíëìîïóñòô­õøö÷ùúýûüþ'
NEW = 'àáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ'
MAP = dict(zip(OLD,NEW,strict=True)) | dict(zip('¡¢§£¤¥¦','ĂÂĐÊÔƠƯ',strict=True)) | {'μ':'à','−':'ư'}


def decode_chars(chars):
    result = []
    for c in chars:
        c = dict(c)
        if 'Vn' in c['fontname']:
            c['text'] = ''.join(MAP.get(s,s) for s in c['text'])
            if 'ArialH' in c['fontname']:
                c['text'] = c['text'].upper()
        result.append(c)
    return result


def text(chars):
    return extract_text(chars,x_tolerance=1,y_tolerance=2) if chars else ''


def rectangle(chars,x0,y0,x1,y1):
    return [c for c in chars if x0 <= (c['x0']+c['x1'])/2 < x1 and y0 <= (c['top']+c['bottom'])/2 < y1]


def save_exports(out,records,pages,report):
    if (len(pages)!=567 or len(records)!=526 or len({r['code'] for r in records})!=526
            or sorted(r['ordinal'] for r in records)!=list(range(1,527))
            or any(len(r['nutrients'])!=87 or not r['name'] for r in records) or report['issues']):
        raise ValueError('FCT inventory/quality check failed; do not publish these exports.')
    for name,data in [('foods.json',records),('pages.json',pages)]:
        (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    core=['id','code','name','name_en','ordinal','page','reference_amount_g','basis','discard_percent']
    with (out/'foods_core.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=core,extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
    fields=['id','code','name','page','nutrient','unit','value','raw_value','reference_code']
    with (out/'nutrients_long.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader()
        for r in records:
            for n in r['nutrients']:
                writer.writerow({**{k:r[k] for k in ['id','code','name','page']},'nutrient':n['name'],
                    **{k:n[k] for k in ['unit','value','raw_value','reference_code']}})
    report['exports']={name:hashlib.sha256((out/name).read_bytes()).hexdigest()
        for name in ['foods.json','pages.json','foods_core.csv','nutrients_long.csv']}
    (out/'quality_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    source = ROOT/'data/VTN_FCT_2007.pdf'
    out = ROOT/'data/structured/fct2007'
    out.mkdir(exist_ok=True)
    pages, records, issues = [], [], []
    with pdfplumber.open(source) as doc:
        for n,page in enumerate(doc.pages,1):
            clean = page.dedupe_chars(tolerance=1)
            chars = decode_chars(clean.chars)
            full = text(chars)
            code = re.search(r'Mã số:\s*(\d+)',full)
            stt = re.search(r'STT:\s*(\d+)',full)
            inventory = {'page':n,'text':full,'kind':'reference_text'}
            if code and stt and n > 11:
                words = clean.extract_words()
                tables = clean.find_tables()
                table = max(tables,key=lambda t:(t.bbox[2]-t.bbox[0])*(t.bbox[3]-t.bbox[1]))
                xs = sorted(set(round(c[0],1) for c in table.cells))
                xs.append(round(table.bbox[2],1))
                if len(xs) != 9:
                    raise ValueError(f'Page {n}: unexpected columns {xs}')
                label = next((w for w in words if '(Vietnamese)' in w['text']),{'top':51.5,'bottom':59.6})
                eng = next((w for w in words if '(English)' in w['text']),{'top':65.5,'bottom':73.7})
                name = text(rectangle(chars,220,label['top']-4,465,label['bottom']+2)).strip()
                name_en = text(rectangle(chars,220,eng['top']-3,465,eng['bottom']+2)).strip()
                row = {'id':'fct2007:'+code[1], 'code':code[1], 'name':name,'name_en':name_en,
                    'ordinal':int(stt[1]),'dataset':'fct2007','page':n,
                    'reference_amount_g':100,'basis':'100 g phần ăn được',
                    'discard_percent':None,'nutrients':[]}
                waste = re.search(r'Thải bỏ \(%\):\s*([\d.]+)',full)
                if waste:
                    row['discard_percent'] = float(waste[1])
                for side in (0,4):
                    col = xs[side:side+5]
                    units = [w for w in words if col[1] <= (w['x0']+w['x1'])/2 < col[2]
                             and w['top'] > table.bbox[1]+22 and re.fullmatch(r'g|mg|μg|µg|KCal|KJ|kcal|kJ',w['text'])]
                    for unit in units:
                        mid = (unit['top']+unit['bottom'])/2
                        cells = [text(rectangle(chars,col[i],mid-4.8,col[i+1],mid+4.8)).strip() for i in range(4)]
                        label,unit_text,value,reference = cells
                        if not label and unit_text.lower()=='kj':
                            label='Năng lượng (Energy)'
                        raw = value
                        if value in {'-','–',''}:
                            number = None
                        elif re.fullmatch(r'\d+(?:[.,]\d+)?',value):
                            number = float(value.replace(',','.'))
                        else:
                            number = None
                            issues.append({'page':n,'code':code[1],'nutrient':label,'raw_value':raw,'type':'unparsed_value'})
                        if not label or not unit_text:
                            issues.append({'page':n,'code':code[1],'type':'missing_label_unit','cells':cells})
                        row['nutrients'].append({'name':label,'unit':unit_text,'value':number,
                            'raw_value':raw,'reference_code':reference,'bbox':[col[0],round(mid-4.8,2),col[-1],round(mid+4.8,2)]})
                inventory.update(kind='food_record',record_id=row['id'])
                records.append(row)
                (out/'checkpoint_foods.json').write_text(json.dumps(records,ensure_ascii=False),encoding='utf-8')
            pages.append(inventory)
            page.close()
            if n%50==0:
                print(f'Processed {n}/{len(doc.pages)} pages',flush=True)
    counts = Counter(len(r['nutrients']) for r in records)
    report = {'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'pages':len(pages),'food_records':len(records),'unique_codes':len({r['code'] for r in records}),
        'ordinals':sorted({r['ordinal'] for r in records}), 'nutrient_rows':sum(counts[k]*k for k in counts),
        'nutrient_count_distribution':dict(counts),'issues':issues,
        'method':'font-aware TCVN3 conversion, deduplicated characters, geometric value/reference columns, unit-anchored rows',
        'clinical_validation':False}
    save_exports(out,records,pages,report)
    print(json.dumps({k:v for k,v in report.items() if k!='ordinals'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
