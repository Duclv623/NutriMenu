import shutil

import pytest

from rag_app.config import ROOT
from rag_app.food_data import FoodCatalog, FoodItem, FoodPlan, get_catalog

MEAL = 'Tổng 150 g cơm chín và 100 g ức gà chín có bao nhiêu calo và đạm?'
MILK = '200 ml sữa bò tươi có bao nhiêu calo?'


def test_cooked_meal_calculates_from_verified_cooked_records_with_visible_assumptions():
    catalog = get_catalog()
    plan = catalog.simple_lookup(MEAL)
    assert plan.operation == 'sum' and [i.amount for i in plan.items] == [150, 100]
    result = catalog.execute(plan)
    assert not result['unresolved']
    assert [i['id'] for i in result['items']] == ['usda:168878', 'usda:2705954']
    totals = {n['key']: n['value'] for n in result['display_totals']}
    assert totals == {'energy': 339, 'protein': 32.035}
    assert len(result['assumptions']) == 2
    assert all(i['review_status'] == 'verified' for i in result['items'])


def test_explicit_roasted_breast_uses_its_own_record_not_generic_cooked_value():
    catalog = get_catalog()
    result = catalog.execute(FoodPlan(operation='lookup', items=[FoodItem(name='ức gà nướng bỏ da', amount=100)]))
    item = result['items'][0]
    assert item['id'] == 'usda:171477' and not result['assumptions']
    assert next(n['amount_value'] for n in item['nutrients'] if n['key'] == 'energy') == 165


def test_raw_breast_alias_preserves_raw_state():
    rows = get_catalog().search('ức gà sống')
    assert rows[0]['id'] == 'nin_foods:7089' and rows[0]['match_score'] == 100


@pytest.mark.parametrize('name', ['ức gà chiên', 'ức gà luộc', 'ức gà chín còn da'])
def test_explicit_unavailable_preparations_are_not_replaced_by_default_estimate(name):
    result = get_catalog().execute(FoodPlan(operation='lookup', items=[FoodItem(name=name, amount=100)]))
    assert not result['items'] and result['unresolved']


def test_milk_asks_for_a_real_volume_label_without_live_or_cooked_question(system):
    body = system.client.post('/api/chat', json={'message': MILK}).json()
    assert body['status'] == 'needs_clarification'
    assert 'sống/chín' not in body['answer'] and 'bằng gram' not in body['answer']
    assert body['food_result']['display_suppressed']
    candidates = body['reference_result']['unresolved'][0]['candidates']
    assert len(candidates) == 6
    assert any('Nguyên Chất' in c['name'] and 'TH true MILK' in c['name'] for c in candidates)
    assert all('sô cô la' not in c['name'].lower() for c in candidates)
    assert not system.provider.generate_calls


@pytest.mark.parametrize('selection', ['TH nguyên chất', 'supp-th-product-sua-tuoi-tiet-trung-nguyen-chat-1-lit'])
def test_milk_selection_preserves_200ml_and_calculates_on_label_basis(system, selection):
    first = system.client.post('/api/chat', json={'message': MILK}).json()
    second = system.client.post('/api/chat', json={
        'message': selection, 'session_id': first['session_id']}).json()
    assert second['status'] == 'answered'
    result = second['reference_result']
    item = result['items'][0]
    assert item['requested_amount'] == 200 and item['requested_unit'] == 'ml'
    assert item['calculation_available'] and item['calculated_nutrients']['energy_kcal'] == 126.4
    assert item['display_nutrients'] == {'energy_kcal': 63.2}
    assert result['request']['nutrients'] == ['calo']


def test_meal_api_keeps_assumptions_visible_and_does_not_ask_for_known_weights(system):
    body = system.client.post('/api/chat', json={'message': MEAL}).json()
    assert body['status'] == 'answered' and body['response_strategy'] == 'structured_lookup'
    assert body['answer'].startswith('Ước tính:') and 'Giả định tham khảo:' in body['answer']
    assert not body['food_result']['unresolved'] and not system.provider.policy_calls


def test_no_empty_choice_instruction_for_a_missing_record(system):
    system.provider.food_plan = FoodPlan(operation='lookup', items=[FoodItem(name='ức gà luộc', amount=100)])
    body = system.client.post('/api/chat', json={'message': '100g ức gà luộc có bao nhiêu calo?'}).json()
    assert 'lựa chọn bên dưới' not in body['answer']
    assert 'chưa có bản ghi phù hợp' in body['answer']
    assert body['food_result']['unresolved'][0]['reason_code'] == 'missing_record'


def test_partial_sum_does_not_claim_a_complete_meal_total():
    result = get_catalog().execute(FoodPlan(operation='sum', items=[
        FoodItem(name='cơm trắng', amount=150), FoodItem(name='xyzkhôngcó123', amount=100)], nutrients=['calo', 'đạm']))
    assert result['items'] and result['unresolved'] and not result['totals']
    assert any('Chưa có tổng cho toàn bộ bữa' in n for n in result['notes'])


def test_usda_snapshot_tampering_is_rejected(tmp_path):
    target = tmp_path / 'common_food_references'
    shutil.copytree(ROOT / 'data/structured/common_food_references', target)
    (target / 'raw/168878.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='checksum'):
        FoodCatalog(tmp_path)


def test_cooked_brown_rice_uses_matching_verified_record():
    result = get_catalog().execute(FoodPlan(operation='lookup', items=[FoodItem(name='cơm gạo lứt chín', amount=100)]))
    assert result['items'][0]['id'] == 'usda:169704'
    assert not result['unresolved']
