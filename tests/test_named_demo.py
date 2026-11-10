"""Named menu uses catalog amounts and keeps fictional profile boundaries."""
from fastapi.testclient import TestClient

from rag_app.config import Settings
from rag_app.food_data import FoodItem, FoodPlan, get_catalog
from rag_app.main import create_app
from rag_app.meal_gateway import MockMealGateway, check_plan
from rag_app.meal_models import DemoProfileUpdate, sum_nutrients


def test_named_demo_uses_verified_catalog_quantities():
    snapshot = MockMealGateway('named').snapshot('alice')
    assert len(snapshot.plan.items) == 8
    assert any(item.name == 'Phở gà' for item in snapshot.plan.items)
    assert snapshot.plan.catalog_version == 'named-demo-v1'
    assert not snapshot.plan.validation_passed and snapshot.plan.solver_status == 'NOT_RUN'
    assert snapshot.plan.totals == sum_nutrients(snapshot.plan.items)
    for item in snapshot.plan.items:
        result = get_catalog().execute(FoodPlan(operation='lookup', items=[
            FoodItem(name=item.recipe_id, amount=item.amount, unit='g')]))['items'][0]
        energy = next(n['amount_value'] for n in result['nutrients'] if n['key'] == 'energy')
        assert item.nutrients.energy_kcal == energy
        assert result['id'] in ';'.join(item.source_refs)
        assert not item.ingredients_complete
    assert check_plan(snapshot.plan, snapshot.profile, mock=True)


def test_named_demo_profile_is_per_owner_and_does_not_represcribe_menu():
    gateway = MockMealGateway('named')
    original = gateway.snapshot('alice')
    updated = gateway.update_profile('alice', DemoProfileUpdate(
        base_version=1, profile=original.profile.model_copy(update={'weight': 82, 'allergies': ['gà'],
                                                                 'restrictions_resolved': False})))
    assert updated.profile.weight == 82 and updated.profile.profile_version == 2
    assert updated.plan.profile_version == 2 and updated.plan.version == 2
    assert updated.plan.items == original.plan.items and updated.plan.totals == original.plan.totals
    assert not updated.profile.restrictions_resolved and not updated.plan.validation_passed
    assert gateway.snapshot('bob').profile.weight == 60


def test_named_demo_chat_reads_visible_lunch_and_profile_without_model(tmp_path):
    cfg = Settings(_env_file=None, storage_dir=tmp_path, meal_service_mode='mock',
                   meal_demo_dataset='named', gemini_api_key='', openai_api_key='')
    with TestClient(create_app(cfg)) as client:
        snapshot = client.get('/api/meal-context').json()
        result = client.post('/api/chat', json={'message': 'Bữa trưa của tôi có những món gì?'}).json()
        assert result['status'] == 'answered' and result['answer_origin'] == 'static'
        assert 'Cơm trắng' in result['answer'] and 'Ức gà' in result['answer']
        assert 'đề xuất đổi' not in result['answer']
        simple = client.post('/api/chat', json={'message': 'Nói dễ hiểu hơn về thực đơn của tôi'}).json()
        # Conversational rephrasing may select a summary; neither may claim a personalized target.
        assert 'cá nhân' in simple['answer'] and 'vừa khoảng' not in simple['answer']
        total = client.post('/api/chat', json={'message': 'Bữa trưa của tôi có bao nhiêu calo?'}).json()
        assert total['status'] == 'answered' and 'kcal' in total['answer']
        assert 'recom.docx' not in client.post('/api/chat', json={
            'message': 'Nguồn số liệu món này lấy từ đâu?',
            'meal_context': {'plan_id': snapshot['plan']['id'], 'item_id': 'lunch-rice'}}).json()['answer']
        snapshot['profile']['weight'] = 75
        saved = client.put('/api/demo/profile', json={'baseVersion': 1, 'profile': snapshot['profile']})
        assert saved.status_code == 200
        assert '75 kg' in client.post('/api/chat', json={'message': 'Tôi nặng bao nhiêu?'}).json()['answer']
        after = client.post('/api/chat', json={'message': 'Bữa trưa của tôi có những món gì?'}).json()
        assert after['status'] == 'answered' and 'Cơm trắng' in after['answer']
