"""Collect a small, source-checked set of cooked-food reference records."""
import hashlib
import json

import httpx

from rag_app.config import ROOT

FOODS = [
    (169704, "Rice, brown, long-grain, cooked (Includes foods for USDA's Food Distribution Program)",
     'Cơm gạo lứt hạt dài nấu chín', ['cơm gạo lứt chín', 'cơm gạo lứt', 'cơm gạo lứt nấu chín'], {}),
    (168914, 'Rice noodles, cooked', 'Bún gạo đã nấu chín',
     ['bún gạo chín', 'bún gạo', 'bún chín', 'bún'],
     {'bún': 'Tạm tính bún theo bún gạo đã nấu chín, không gồm nước dùng và món ăn kèm.'}),
    (168878, 'Rice, white, long-grain, regular, enriched, cooked',
     'Cơm trắng gạo hạt dài nấu chín',
     ['cơm trắng', 'cơm trắng chín', 'cơm gạo tẻ chín', 'cơm gạo tẻ nấu chín', 'cơm chín', 'cơm'],
     {'cơm chín': 'Tạm tính cơm chín theo cơm trắng gạo hạt dài nấu chín.',
      'cơm': 'Tạm tính cơm theo cơm trắng gạo hạt dài nấu chín.'}),
    (2705954, 'Chicken breast, NS as to cooking method, skin not eaten',
     'Ức gà chín bỏ da, chưa xác định cách chế biến',
     ['ức gà chín', 'lườn gà chín', 'ức gà chín bỏ da', 'lườn gà chín bỏ da'],
     {'ức gà chín': 'Tạm tính ức gà chín theo phần thịt bỏ da, cách chế biến chưa xác định trong bản ghi USDA.',
      'lườn gà chín': 'Tạm tính lườn gà chín theo phần thịt bỏ da, cách chế biến chưa xác định trong bản ghi USDA.'}),
    (171477, 'Chicken, broilers or fryers, breast, meat only, cooked, roasted',
     'Ức gà chín nướng, chỉ phần thịt bỏ da',
     ['ức gà nướng bỏ da', 'ức gà chín nướng bỏ da', 'lườn gà nướng bỏ da'], {}),
]


def main():
    folder = ROOT / 'data/structured/common_food_references'
    (folder / 'raw').mkdir(parents=True, exist_ok=True)
    records = []
    with httpx.Client(timeout=45) as client:
        for fdc_id, expected, name, aliases, assumptions in FOODS:
            response = client.get(f'https://api.nal.usda.gov/fdc/v1/food/{fdc_id}',
                                  params={'api_key': 'DEMO_KEY'})
            response.raise_for_status()
            raw = response.json()
            if raw.get('fdcId') != fdc_id or raw.get('description') != expected:
                raise ValueError('USDA identity changed: ' + str(fdc_id))
            if raw.get('dataType') not in {'SR Legacy', 'Survey (FNDDS)'}:
                raise ValueError('Unreviewed USDA data type')
            raw_file = f'raw/{fdc_id}.json'
            (folder / raw_file).write_bytes(response.content)
            records.append({'fdc_id': fdc_id, 'description': expected, 'name': name,
                            'aliases': aliases, 'assumptions': assumptions,
                            'raw_file': raw_file, 'sha256': hashlib.sha256(response.content).hexdigest(),
                            'source_url': f'https://fdc.nal.usda.gov/food-details/{fdc_id}/nutrients',
                            'basis': '100 g phần ăn được đã nấu chín',
                            'basis_amount_g': 100, 'collected_at': '2026-10-31',
                            'limitations': 'Số liệu tham khảo của đúng bản ghi USDA; không phải kết quả phân tích phần ăn thực tế. Không bao gồm dầu hoặc gia vị bổ sung ngoài bản ghi.'})
            print(fdc_id, raw['description'], flush=True)
    (folder / 'manifest.json').write_text(json.dumps({'schema_version': 1, 'records': records},
                                                     ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
