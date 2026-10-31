"""Regressions found through real web/API review on 2026-10-11."""
import pytest
from fastapi.testclient import TestClient

from rag_app.config import Settings
from rag_app.domain import AnswerBlock, GeneratedAnswer
from rag_app.food_data import FoodItem, FoodPlan, get_catalog
from rag_app.main import create_app
from rag_app.provider import GroundingReview, ProviderFailure, apply_grounding_review
from rag_app.safety import classify


def test_declared_diabetes_does_not_turn_food_question_into_diagnosis(system):
    question = 'Tôi bị tiểu đường type 2, có phải bỏ hẳn cơm trắng không?'
    response = system.client.post('/api/chat', json={'message': question}).json()
    assert response['status'] == 'answered' and system.provider.generate_calls
    assert not system.provider.policy_calls


@pytest.mark.parametrize(('question', 'intent'), [
    ('Đường cao quá, tôi uống thêm 1 viên metformin được không?', 'medication'),
    ('Tối ăn nhiều cơm thì chích thêm 2 đơn vị insulin được không?', 'medication'),
    ('Em đang có bầu 24 tuần, bác sĩ nói tiểu đường, ăn cơm thế nào?', 'special_population'),
    ('Tôi không có bầu, chỉ muốn tìm hiểu ăn uống.', 'knowledge'),
    ('Tôi không khó thở, không đau ngực, chỉ hỏi ăn chuối được không?', 'knowledge'),
    ('Tôi không khó thở nhưng đang đau ngực.', 'emergency'),
    ('Bố tôi không tỉnh và không nuốt được.', 'emergency'),
    ('Tôi vừa đo đường huyết 60 mg/dL, giờ nên làm gì?', 'emergency'),
    ('Vận động ngắt quãng khi ngồi văn phòng thế nào?', 'knowledge'),
])
def test_everyday_safety_language(question, intent):
    assert classify(question) == intent


def test_diagnosis_does_not_match_declared_disease_then_food_question():
    from rag_app.safety import is_diagnosis_request

    assert not is_diagnosis_request('Tôi đã bị tiểu đường type 2, có phải bỏ hẳn cơm trắng không?')
    assert is_diagnosis_request('Đường huyết đói 7,2 mmol/L thì tôi đã bị tiểu đường chưa?')


@pytest.mark.parametrize('question', [
    'Bố tôi bất tỉnh, có nên đổ nước đường vào miệng không?',
    'Tôi vừa đo đường huyết 60 mg/dL, giờ nên làm gì?',
    'Tôi uống thêm 1 viên metformin được không?',
    'Em đang có bầu, nên ăn gì?',
])
def test_medical_boundaries_work_with_no_key_index_or_provider(tmp_path, question):
    cfg = Settings(storage_dir=tmp_path, _env_file=None, gemini_api_key='', openai_api_key='')
    with TestClient(create_app(cfg)) as client:
        response = client.post('/api/chat', json={'message': question})
    assert response.status_code == 200
    answer = response.json()
    assert answer['status'] == 'safety' and answer['answer_origin'] == 'static'
    assert not answer['model'] and not answer['usage'] and not answer['provider_response_ids']
    if 'bất tỉnh' in question:
        assert '115' in answer['answer'] and 'Không cho' in answer['answer']


def test_boundary_does_not_wait_for_failing_provider(system):
    system.provider.error = ProviderFailure('Simulated provider outage')
    response = system.client.post('/api/chat', json={'message': 'Bố tôi bất tỉnh'}).json()
    assert response['status'] == 'safety' and '115' in response['answer']
    assert not system.provider.generate_calls and not system.provider.policy_calls


@pytest.mark.parametrize('saved', [False, True])
def test_special_population_survives_long_questions_and_history_trimming(system, saved):
    first = system.client.post('/api/chat', json={'message': 'Tôi đang có bầu.', 'save_history': saved}).json()
    sid = first['session_id']
    for _ in range(7):
        system.client.post('/api/chat', json={'message': 'Xin chào', 'session_id': sid, 'save_history': saved})
    if saved:
        # Force recovery from owner-bound persisted history, retaining the restriction.
        system.app.state.service._transient.clear()
    result = system.client.post('/api/chat', json={
        'message': 'Bữa sáng nên ăn bánh mì với sữa hay cháo thịt để đủ năng lượng đi làm?',
        'session_id': sid,
    }).json()
    assert result['intent'] == 'special_population' and result['status'] == 'safety'
    assert result['scope_restriction'] == 'special_population'
    assert not system.provider.generate_calls
    fresh = system.client.post('/api/chat', json={'message': 'Bữa sáng nên ăn thế nào?'}).json()
    assert fresh['intent'] == 'knowledge' and fresh['scope_restriction'] is None


def test_all_enabled_source_previews_open(system):
    sources = system.client.get('/api/documents').json()
    for source in sources:
        if source['enabled']:
            response = system.client.get(f'/api/documents/{source["id"]}/preview')
            assert response.status_code == 200, source['id']
            assert source['title'] in response.text


def test_core_nutrient_aliases_use_real_values_without_fatty_acid_rows():
    result = get_catalog().execute(FoodPlan(operation='lookup', items=[
        FoodItem(name='nin_foods:10001', amount=100, unit='g')],
        nutrients=['calo', 'carb', 'đạm', 'béo', 'xơ']))
    nutrients = {row['key']: row['amount_value'] for row in result['items'][0]['display_nutrients']}
    assert nutrients == {'energy': 74.0, 'carbohydrate': 4.8, 'protein': 3.9, 'fat': 4.4, 'fiber': None}


def test_ambiguous_food_keeps_choices_when_answer_provider_fails(system):
    system.provider.error = ProviderFailure('Simulated provider outage')
    response = system.client.post('/api/chat', json={'message': '100g thịt bò có bao nhiêu calo?'})
    assert response.status_code == 200
    result = response.json()
    assert result['answer_origin'] == 'static' and result['food_result']['unresolved'][0]['candidates']
    assert 'chọn' in result['answer'] and not system.provider.generate_calls


def test_missing_bowl_conversion_asks_for_grams(system):
    system.provider.food_plan = FoodPlan(operation='lookup', items=[
        FoodItem(name='Cơm tẻ miệng bát', amount=1, unit='bát')], nutrients=['carb'])
    response = system.client.post('/api/chat', json={'message': 'Một bát cơm có bao nhiêu carb?'}).json()
    assert ('gram' in response['answer'] or 'xác minh' in response['answer']) and 'basis' not in response['answer']
    assert not response['food_result']['items'][0]['calculation_available']


def test_omitting_abandonment_decision_triggers_revision():
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(
        text='Nên giảm cơm trắng.', citation_ids=['C1'])], uncertainty='')
    review = GroundingReview.model_validate({'accepted_blocks': [{'block_index': 0,
        'evidence': [{'citation_id': 'C1', 'line_ids': [0]}]}]})
    result = apply_grounding_review(answer, review,
        [{'id': 'C1', 'text': 'Nên giảm cơm trắng.'}],
        'Có phải bỏ hẳn cơm trắng không?')
    assert result._grounding_review['server_rejections']
