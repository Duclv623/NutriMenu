"""Check NIN export basis and nutrient fidelity against the saved crawler pages."""
import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from rag_app.config import ROOT
from rag_app.food_data import get_catalog


def read_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def audit_dataset(dataset, expected_records):
    folder=ROOT/f'data/structured/nin_{dataset}_2026-10-06'
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    originals=[]
    for request in manifest['requests']:
        raw=(folder/request['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==request['sha256'], request['file']
        originals.extend(json.loads(raw)['data'])
    assert len(originals)==expected_records
    assert json.loads((folder/f'{dataset}_full.json').read_text(encoding='utf-8'))==originals
    for filename, checksum in manifest['exports'].items():
        assert hashlib.sha256((folder/filename).read_bytes()).hexdigest()==checksum, filename
    core=json.loads((folder/f'{dataset}_core.json').read_text(encoding='utf-8'))
    assert len(core)==expected_records and all(r['reference_amount_g']==100 for r in core)
    for filename in [f'{dataset}_core.csv', f'{dataset}_all_nutrients.csv']:
        rows=read_rows(folder/filename)
        assert len(rows)==expected_records and all(r['reference_amount_g']=='100' for r in rows)
    expected=[]
    is_dish=dataset=='dishes'
    for record in originals:
        for nutrient in record['nutritional_components' if is_dish else 'nutrition']:
            items=[nutrient, *nutrient.get('equivalenceComponents', [])] if is_dish else [nutrient]
            for item in items:
                raw=item.get('amount', item.get('value')) if is_dish else item.get('value')
                value=None if raw is None or raw=='' else float(raw)
                unit=item.get('unit_name', item.get('unit', '')) if is_dish else item.get('unit', '')
                expected.append((record['code'], record['_id'], item.get('key',''), unit, value))
    long_rows=read_rows(folder/'nutrients_long.csv')
    code_key='dish_code' if is_dish else 'food_code'
    actual=[(r[code_key], r['source_record_id'], r['nutrient_key'], r['unit'],
             None if r['value']=='' else float(r['value'])) for r in long_rows]
    assert actual==expected, f'{dataset}: nutrient values or order differ from crawler cache'
    assert all(r['reference_amount_g']=='100' for r in long_rows)
    return {'records':expected_records, 'nutrient_rows':len(long_rows),
            'raw_cache_hashes_valid':True, 'all_export_hashes_valid':True,
            'full_export_matches_raw_cache':True, 'all_tables_reference_amount_g':100,
            'all_long_nutrient_values_match_source':True,
            'basis_verification':manifest['reference_basis_verification']}


def main():
    report={'checked_at':datetime.now(UTC).isoformat(),
            'nin_foods':audit_dataset('foods',853), 'nin_dishes':audit_dataset('dishes',1250),
            'catalog':get_catalog().status(),
            'clinical_validation':False}
    destination=Path(ROOT/'docs/food-integration/normalization-100g-audit.json')
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
