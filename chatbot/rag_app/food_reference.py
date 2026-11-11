"""Small verified USDA snapshots, separate from the original NIN exports."""
import hashlib
import json
import re

NUTRIENTS = {
    1008: ('energy', 'Năng lượng', 'kcal'),
    1003: ('protein', 'Chất đạm', 'g'),
    1004: ('fat', 'Chất béo', 'g'),
    1005: ('carbohydrate', 'Carbohydrate', 'g'),
    1079: ('fiber', 'Chất xơ', 'g'),
    1093: ('sodium', 'Natri', 'mg'),
}


def load_food_references(root):
    folder = root / 'common_food_references'
    path = folder / 'manifest.json'
    if not path.exists():
        return []
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest['schema_version'] != 1:
        raise ValueError('Unsupported common-food manifest')
    records = []
    for entry in manifest['records']:
        raw_path = (folder / entry['raw_file']).resolve()
        if not raw_path.is_relative_to(folder.resolve()):
            raise ValueError('USDA snapshot outside reference directory')
        raw_bytes = raw_path.read_bytes()
        if hashlib.sha256(raw_bytes).hexdigest() != entry['sha256']:
            raise ValueError('USDA source checksum changed')
        raw = json.loads(raw_bytes)
        if (raw['fdcId'] != entry['fdc_id'] or raw['description'] != entry['description']
                or raw['dataType'] not in {'SR Legacy', 'Survey (FNDDS)'}
                or entry['basis_amount_g'] != 100):
            raise ValueError('USDA record identity/basis mismatch')
        nutrients = []
        for row in raw['foodNutrients']:
            source = row['nutrient']
            if source['id'] not in NUTRIENTS:
                continue
            key, name, unit = NUTRIENTS[source['id']]
            if source['unitName'].lower() != unit:
                raise ValueError('USDA nutrient unit changed')
            nutrients.append({'key': key, 'name': name, 'unit': unit,
                              'value': row.get('amount'), 'raw_value': str(row.get('amount', '')),
                              'source_key': str(source['id']), 'source_row': row})
        for key in ('energy', 'protein'):
            matches = [n for n in nutrients if n['key'] == key and n['value'] is not None]
            if len(matches) != 1:
                raise ValueError('USDA essential nutrient missing or duplicated: ' + key)
        records.append({'id': f"usda:{raw['fdcId']}", 'code': str(raw['fdcId']),
                        'name': entry['name'], 'name_en': raw['description'], 'dataset': 'usda',
                        'page': None, 'reference_amount_g': 100, 'basis': entry['basis'],
                        'aliases': entry['aliases'], 'alias_assumptions': entry['assumptions'],
                        'limitations': entry['limitations'], 'source_metadata': entry,
                        'nutrients': nutrients,
                        'source': {'title': 'USDA FoodData Central — ' + raw['dataType'],
                                   'url': entry['source_url'], 'year': int(re.search(r'\b(?:19|20)\d{2}\b', raw['publicationDate'])[0])}})
    return records
