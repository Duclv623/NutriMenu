"""Named demonstration portions derived from existing, verified food records."""
import json

from rag_app.config import ROOT
from rag_app.food_data import FoodItem, FoodPlan, get_catalog
from rag_app.meal_models import PlanItem, sum_nutrients


def named_demo_fixture():
    fixture = json.loads((ROOT / 'data/fixtures/meal_named_demo.json').read_text(encoding='utf-8'))
    catalog = get_catalog()
    items = []
    fields = {'energy_kcal': ('energy', 'kcal'), 'carbohydrate_g': ('carbohydrate', 'g'),
              'protein_g': ('protein', 'g'), 'fat_g': ('fat', 'g'),
              'fiber_g': ('fiber', 'g'), 'sodium_mg': ('sodium', 'mg')}
    for row in fixture['items']:
        result = catalog.execute(FoodPlan(operation='lookup', items=[
            FoodItem(name=row['foodId'], amount=row['amount'], unit='g')]))
        if result['unresolved'] or len(result['items']) != 1:
            raise ValueError('Named demo requires an exact, available food record')
        record = result['items'][0]
        if (record['id'] != row['foodId'] or record.get('review_status') != 'verified'
                or not record['calculation_available']):
            raise ValueError('Named demo food basis is not verified')
        nutrients = {}
        for field, (key, unit) in fields.items():
            values = [n['amount_value'] for n in record['nutrients']
                      if n['key'] == key and n['unit'].lower() == unit]
            nutrients[field] = values[0] if len(values) == 1 else None
        refs = [record['source']['title'] + ': ' + record['id'], record['source']['url'],
                record['basis_note']]
        if record.get('limitations'):
            refs.append(record['limitations'])
        items.append(PlanItem(
            id=row['id'], recipe_id=record['id'], recipe_version='catalog-snapshot-v1',
            name=record['name'], meal_type=row['mealType'], portion_id='DEMO_GRAMS',
            amount=row['amount'], unit='g', state=row.get('state', 'cooked'),
            nutrition_basis='as_consumed', nutrients=nutrients,
            # Food tables do not establish a complete ingredient/allergen list.
            ingredients=[{'id': record['id'], 'name': record['name']}],
            ingredients_complete=False, source_refs=refs))
    energy = sum_nutrients(items).energy_kcal
    if energy is None:
        raise ValueError('Named demo requires complete energy data')
    return {**fixture, 'items': [item.model_dump(mode='json') for item in items],
            'alternatives': [],
            'target': {'version': 'demo-total-only', 'sourceRefs': ['Tổng mẫu, không phải nhu cầu cá nhân'],
                       'bounds': {'energy_kcal': {'minimum': energy, 'maximum': energy}}}}
