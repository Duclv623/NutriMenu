# Pending profile-vs-food-amount regression tests; draft not applied.
import pytest
from rag_app.food_data import get_catalog
from rag_app.safety import classify

PROFILE = 'Tôi là nam, 30 tuổi, cao 170 cm, nặng 70 kg và vận động nhiều; câu trả lời có khác người ngồi văn phòng không?'

def test_profile_weight_is_not_food_quantity():
    assert classify(PROFILE) == 'knowledge'
    assert not get_catalog().looks_like_lookup(PROFILE)
    assert not get_catalog().looks_like_lookup('Cân nặng của tôi là 70 kg, nhu cầu năng lượng có khác không?')

@pytest.mark.parametrize('question', ['100g cơm chín có bao nhiêu carb?', '1kg gạo lứt có bao nhiêu calo?', 'Tôi nặng 70 kg, 100g cơm chín có bao nhiêu carb?', 'usda:168878'])
def test_actual_food_quantities_and_ids_are_preserved(question):
    assert get_catalog().looks_like_lookup(question)


def test_profile_comparison_reaches_knowledge_planner(system):
    result = system.client.post('/api/chat', json={'message':PROFILE}).json()
    assert result['intent']=='knowledge'
    assert result['food_result'] is None
    assert system.provider.plan_calls
