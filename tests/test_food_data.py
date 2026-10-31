import json

import pytest

from rag_app.config import ROOT
from rag_app.food_data import FoodItem, FoodPlan, canonical, get_catalog, normalized


def run(name,amount=None,unit='g',dataset='auto',nutrients=None):
    return get_catalog().execute(FoodPlan(operation='lookup',items=[FoodItem(name=name,amount=amount,unit=unit)],
        dataset=dataset,nutrients=nutrients or []))


def test_all_sources_and_pdf_pages_accounted_for():
    catalog=get_catalog()
    assert catalog.status()['datasets']=={'nin_foods':853,'nin_dishes':1250,'fct2007':526,'usda':3}
    assert catalog.status()['unknown_portion_records']==1250
    assert all(r['reference_amount_g']==100 for r in catalog.records.values() if r['dataset']!='nin_dishes')
    report=json.loads((ROOT/'data/structured/fct2007/quality_report.json').read_text(encoding='utf-8'))
    assert report['pages']==567 and report['nutrient_rows']==45762 and report['issues']==[]
    assert report['ordinals']==list(range(1,527))
    records=[r for r in catalog.records.values() if r['dataset']=='fct2007']
    assert all(len(r['nutrients'])==87 and r['name'] and r['page'] for r in records)
    assert sum(len(r['nutrients']) for r in catalog.records.values() if r['dataset']=='nin_foods')==34544+853
    assert sum(len(r['nutrients']) for r in catalog.records.values() if r['dataset']=='nin_dishes')==17185


def test_pdf_values_are_separate_from_reference_codes():
    r=get_catalog().get('fct2007:1007')
    calcium=next(n for n in r['nutrients'] if n['key']=='calcium')
    assert (calcium['value'],calcium['reference_code'])==(4, '5')
    sodium=next(n for n in r['nutrients'] if n['key']=='sodium')
    assert (sodium['value'],sodium['reference_code'])==(3, '5')
    assert canonical('Vitamin D (Calciferol)','μg')!='calcium'
    assert r['name']=='NGÔ BẮP TƯƠI'


def test_scaling_grams_and_kilograms_uses_exact_stored_values():
    for amount,unit in [(200,'g'),(.2,'kg')]:
        i=run('sữa bò tươi',amount,unit)['items'][0]
        assert i['id']=='nin_foods:10001'
        assert next(n['amount_value'] for n in i['nutrients'] if n['key']=='protein')==7.8
        assert next(n['amount_value'] for n in i['nutrients'] if n['key']=='energy')==148
        assert any(a['id']=='fct2007:10001' for a in i['alternatives'])


@pytest.mark.parametrize('unit',['ml','bát','quả','hộp'])
def test_no_invented_volume_or_portion_conversion(unit):
    i=run('sữa bò tươi',200,unit)['items'][0]
    assert not i['calculation_available'] and all(n['amount_value'] is None for n in i['nutrients'])


@pytest.mark.parametrize('amount,unit',[(200,'g'),(.2,'kg')])
def test_dishes_require_source_basis_verification_and_preserve_provenance(amount,unit):
    i=run('nin_dishes:HAP-223025',amount,unit)['items'][0]
    assert i['name']=='Tiết luộc' and i['reference_amount_g'] is None
    assert not i['calculation_available'] and i['amount_g']==200
    assert all(n['amount_value'] is None for n in i['nutrients'])
    assert next(n['source_value'] for n in i['nutrients'] if n['key']=='protein')==11.4
    assert i['source_metadata']['source_record_id']=='6937d98ef6722f52330e1d15'
    assert i['source_metadata']['dish_components_count']=='0'
    assert all(n['source_row']['source_record_id']=='6937d98ef6722f52330e1d15' for n in i['nutrients'])


def test_ambiguous_names_request_selection_and_unknown_stays_unknown():
    choices=run('thịt bò',100)['unresolved'][0]['candidates']
    assert any('tươi' in c['name'].lower() or 'sống' in c['name'].lower() for c in choices)
    assert run('thực phẩm xyzkhôngcó123',100)['unresolved']


def test_rice_spelling_never_resolves_to_green_rice_flakes():
    catalog = get_catalog()
    assert all('cốm' not in r['name'].lower() for r in catalog.search('cơm'))
    assert run('cốm', 100)['items'][0]['id'] == 'fct2007:1021'
    rice = run('cơm', 100)
    assert rice['items'][0]['id'] == 'usda:168878' and rice['assumptions']
    ascii_rice = run('com', 100)
    assert not ascii_rice['items'] and ascii_rice['unresolved']
    cooked = run('Cơm tẻ miệng bát', 100)['items'][0]
    assert cooked['reference_amount_g'] is None and not cooked['calculation_available']
    bowl=run('Cơm tẻ miệng bát',1,'bát')['items'][0]
    assert not bowl['calculation_available'] and all(n['amount_value'] is None for n in bowl['nutrients'])
    plan = FoodPlan(operation='lookup', items=[FoodItem(name='com', amount=100)])
    ascii_rice['request'] = plan.model_dump()
    history = [{'question': '100g com bao nhiêu calo?', 'response': {'food_result': ascii_rice}}]
    assert catalog.resolve_selection('cơm', history) is None
    assert catalog.resolve_selection('com', history) is None
    assert catalog.resolve_selection('cốm', history).items[0].name == 'fct2007:1021'


@pytest.mark.parametrize('question', [
    'Một ngày tôi nên ăn bao nhiêu gram cơm?',
    'Tôi nên ăn bao nhiêu calo mỗi ngày?',
    'Tôi ăn 200g cơm có được không?',
    'Mỗi ngày ăn bao nhiêu cơm?',
])
def test_recommended_intake_is_not_composition_lookup(question):
    from rag_app.safety import classify
    assert classify(question) == 'knowledge'
    assert not get_catalog().looks_like_lookup(question)


def test_uncooked_grain_qualifier_offers_real_types_without_choosing_one():
    for name in ['gạo tẻ chưa nấu', 'gạo tẻ sống']:
        result = run(name, 100)
        assert not result['items'] and result['unresolved'][0]['candidates']
        assert all(c['dataset'] != 'nin_dishes' and normalized(c['name']).startswith('gao te')
                   for c in result['unresolved'][0]['candidates'])
    cooked = run('cơm trắng đã nấu chín', 100)
    assert not cooked['items']


def test_selected_id_overrides_model_name_but_unknown_id_is_not_invented():
    catalog=get_catalog()
    plan=FoodPlan(operation='lookup',items=[FoodItem(name='Tiết luộc',amount=100)],nutrients=['protein'])
    catalog.bind_explicit_ids(plan,'100g Tiết luộc mã nin_dishes:HAP-223025 có bao nhiêu đạm?')
    assert plan.items[0].name=='nin_dishes:HAP-223025'
    assert catalog.execute(plan)['items'][0]['id']=='nin_dishes:HAP-223025'
    unknown=FoodPlan(operation='lookup',items=[FoodItem(name='nin_dishes:UNKNOWN')])
    catalog.bind_explicit_ids(unknown,'Tra cứu nin_dishes:UNKNOWN')
    assert catalog.execute(unknown)['unresolved'][0]['candidates']==[]
    assert catalog.looks_like_lookup('Tra cứu nin_dishes:HAP-223025')


def test_source_anomalies_preserved_without_using_them_in_calculation():
    catalog=get_catalog()
    invalid=catalog.get('nin_foods:7090002')
    row=next(n for n in invalid['nutrients'] if str(n['raw_value'])=='-0.03')
    assert row['value'] is None and row['quality_note']
    duplicate=catalog.get('nin_dishes:VPF-000428')
    rows=[n for n in duplicate['nutrients'] if n['source_key']=='chat-bot-duong']
    assert len(rows)==2 and all(n['value'] is None and 'raw_value' in n and n['quality_note'] for n in rows)
    assert catalog.status()['quality_issues']>=3
    assert catalog.status()['review_statuses']['quarantined']>0


@pytest.mark.parametrize('nutrient,key,expected',[('vitamin D','vitamin_d',1),('vitamin E','vitamin_e',.06),
    ('vitamin B6','vitamin_b6',.04),('phốt pho','phosphorus',88.14),('magnesium','magnesium',14.84)])
def test_nutrient_aliases_do_not_report_existing_values_as_missing(nutrient,key,expected):
    item=run('nin_foods:10001',100,nutrients=[nutrient])['items'][0]
    assert any(n['key']==key and n['value']==expected for n in item['display_nutrients'])


def test_sum_requires_all_amounts_and_preserves_missing_values():
    c=get_catalog()
    items=[FoodItem(name='nin_foods:10001',amount=100),FoodItem(name='nin_foods:10002',amount=200)]
    r=c.execute(FoodPlan(operation='sum',items=items))
    assert next(n['value'] for n in r['totals'] if n['key']=='protein')==10.9
    assert next(n['value'] for n in r['totals'] if n['key']=='fiber') is None
    items[1].amount=None
    assert not c.execute(FoodPlan(operation='sum',items=items))['totals']


def test_pdf_source_explicit_and_no_cellulose_substitution():
    r=run('ngô bắp tươi',100,dataset='fct2007',nutrients=['chất xơ'])
    i=r['items'][0]
    assert i['dataset']=='fct2007' and i['page']==20
    assert i['display_nutrients'][0]['value'] is None
    assert next(n['value'] for n in i['nutrients'] if n['key']=='cellulose')==1.2


def test_nutrition_api_citations_and_ui_are_connected(system):
    system.provider.food_plan=FoodPlan(operation='lookup',items=[FoodItem(name='sữa bò tươi',amount=200)],nutrients=['protein'])
    r=system.client.post('/api/chat',json={'message':'200g sữa bò tươi có bao nhiêu đạm?'}).json()
    assert r['status']=='answered' and r['food_result']['items'][0]['display_nutrients'][0]['amount_value']==7.8
    assert r['citations'][0]['document_url']=='/api/foods/nin_foods:10001/preview'
    assert system.client.get(r['citations'][0]['document_url']).status_code==200
    assert system.client.get('/api/foods?q=sua%20bo%20tuoi').json()['results'][0]['id']=='nin_foods:10001'
    assert system.client.get('/api/foods/fct2007:1007').json()['page']==20
    assert system.client.get('/api/foods/not-real').status_code==404
    assert system.client.get('/api/documents/vtn-fct-2007/pdf').status_code==200
    last=system.client.get('/api/foods?offset=2620&limit=20').json()
    assert last['total']==2632 and len(last['results'])==12
    assert [r['dataset'] for r in last['results']].count('fct2007') == 9
    assert [r['dataset'] for r in last['results']].count('usda') == 3
    assert system.client.get('/api/foods?dataset=nin_dishes&offset=1250').json()['results']==[]
