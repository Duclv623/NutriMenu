import pytest
from fastapi.testclient import TestClient
from rag_app.config import Settings
from rag_app.main import create_app
from rag_app.meal_gateway import MockMealGateway, MealServiceError
from rag_app.meal_models import DemoProfileUpdate, SwapRequest, ApplySwap


def update(gateway, owner='a', **changes):
    old = gateway.snapshot(owner)
    profile = old.profile.model_copy(update={**changes, "restrictions_resolved": False, "excluded_ingredient_ids": []})
    return gateway.update_profile(owner, DemoProfileUpdate(base_version=old.profile.profile_version, profile=profile))


def test_demo_update_isolated_stale_and_invalidates_proposal():
    gateway = MockMealGateway()
    old = gateway.snapshot('a')
    proposal = gateway.preview('a', SwapRequest(plan_id=old.plan.id, base_version=1, item_id='breakfast-1', instruction='Đổi món sáng'))
    current = update(gateway, weight=75)
    assert current.profile.profile_version == 2 and current.profile.weight == 75
    assert current.plan.profile_version == 1
    assert gateway.snapshot('b').profile.weight == 60
    with pytest.raises(MealServiceError):
        gateway.apply('a', ApplySwap(plan_id=old.plan.id, base_version=1, proposal_id=proposal.id))
    with pytest.raises(MealServiceError, match='thay đổi'):
        gateway.preview('a', SwapRequest(plan_id=old.plan.id, base_version=1, item_id='breakfast-1', instruction='Đổi món sáng'))
    refreshed = gateway.refresh_demo_plan('a')
    assert refreshed.plan.profile_version == 2 and refreshed.plan.version == 2
    assert refreshed.plan.target == old.plan.target
    assert refreshed.plan.totals == old.plan.totals


@pytest.mark.parametrize('changes,code', [({'allergies':['đậu phộng']},'PROFILE_INCOMPLETE'), ({'allergies':None},'PROFILE_INCOMPLETE'), ({'age':16},'OUT_OF_SCOPE'), ({'scope_status':'unknown'},'OUT_OF_SCOPE')])
def test_demo_cannot_resolve_real_allergies_or_scope(changes, code):
    gateway = MockMealGateway()
    update(gateway, **changes)
    with pytest.raises(MealServiceError) as error:
        gateway.refresh_demo_plan('a')
    assert error.value.code == code


@pytest.mark.parametrize('saved', [True, False])
def test_latest_profile_facts_saved_and_transient(tmp_path, saved):
    cfg = Settings(_env_file=None,storage_dir=tmp_path,gemini_api_key='',openai_api_key='',meal_service_mode='mock')
    with TestClient(create_app(cfg)) as client:
        old = client.get('/api/meal-context').json()
        first = client.post('/api/chat',json={'message':'tôi nặng bao nhiêu','save_history':saved}).json()
        assert '60 kg' in first['answer']
        old['profile']['weight'] = 74
        result = client.put('/api/demo/profile',json={'baseVersion':1,'profile':old['profile']})
        assert result.status_code == 200
        second = client.post('/api/chat',json={'message':'tôi nặng bao nhiêu','session_id':first['session_id'],'save_history':saved})
        assert second.status_code == 200
        assert '74 kg' in second.json()['answer'] and 'phiên bản 2' in second.json()['answer']
        stale = client.put('/api/demo/profile',json={'baseVersion':1,'profile':old['profile']})
        assert stale.status_code == 409


@pytest.mark.parametrize('mode', ['disabled','http'])
def test_demo_routes_disabled_outside_mock(tmp_path, mode):
    args = {'meal_api_base_url':'http://127.0.0.1:8999'} if mode == 'http' else {}
    cfg = Settings(_env_file=None,storage_dir=tmp_path,gemini_api_key='',openai_api_key='',meal_service_mode=mode, **args)
    with TestClient(create_app(cfg)) as client:
        assert client.post('/api/demo/plan-refresh').status_code == 404
        profile = MockMealGateway().snapshot('a').profile.model_dump(by_alias=True)
        assert client.put('/api/demo/profile',json={'baseVersion':1,'profile':profile}).status_code == 404


def test_latest_profile_context_is_not_embedding_or_shared_state(system):
    from rag_app.domain import ChatRequest
    service = system.app.state.service
    gateway = service.meals = MockMealGateway()
    service.chat(ChatRequest(message='Tôi nên chọn trái cây thế nào?',save_history=False), 'a')
    assert system.provider.plan_calls[-1][0].backend_profile['weight'] == 60
    update(gateway, weight=81, preferences=['ăn chay'])
    service.profile_changed('a')
    service.chat(ChatRequest(message='Tôi nên chọn trái cây thế nào?',save_history=False), 'a')
    question = system.provider.plan_calls[-1][0]
    assert question.backend_profile['weight'] == 81 and question.backend_profile['profileVersion'] == 2 and 'ăn chay' in question.backend_profile['preferences']
    assert str(question) == 'Tôi nên chọn trái cây thế nào?'
    service.chat(ChatRequest(message='Tôi nên chọn trái cây thế nào?',save_history=False), 'b')
    assert system.provider.plan_calls[-1][0].backend_profile['weight'] == 60
    service.chat(ChatRequest(message='Carbohydrate là gì?',save_history=False), 'a')
    assert 'BACKEND_PROFILE_DATA' not in system.provider.plan_calls[-1][0]
    assert not system.provider.embed_calls


def test_emergency_and_medication_win_over_profile_fact(tmp_path):
    cfg = Settings(_env_file=None,storage_dir=tmp_path,gemini_api_key='',openai_api_key='',meal_service_mode='mock')
    with TestClient(create_app(cfg)) as client:
        for message in ['Tôi nặng bao nhiêu, tôi đang lú lẫn vã mồ hôi run tay', 'Tôi nặng bao nhiêu, tăng liều insulin thế nào?']:
            response = client.post('/api/chat',json={'message':message}).json()
            assert response['status'] == 'safety'
            assert 'ghi cân nặng' not in response['answer']


def test_profile_change_during_generation_discards_old_advice(system):
    from rag_app.domain import ChatRequest
    service = system.app.state.service
    gateway = service.meals = MockMealGateway()
    generate = system.provider.generate
    def updating_generate(*args):
        result = generate(*args)
        update(gateway, weight=99)
        service.profile_changed('a')
        return result
    system.provider.generate = updating_generate
    result = service.chat(ChatRequest(message='Tôi nên chọn trái cây thế nào?'), 'a')
    assert result.status == 'needs_clarification'
    assert 'Hồ sơ đã thay đổi' in result.answer
    assert result.answer_origin == 'static' and result.citations == []


def test_provider_separates_profile_from_question_in_planner_generator_and_review(system):
    import json
    from types import SimpleNamespace
    from rag_app.provider import BackendProfileQuestion, OpenAIProvider, GroundingReview, ReviewedBlock, EvidenceSpan
    from rag_app.domain import GeneratedAnswer, AnswerBlock
    from rag_app.routing import ResponsePlan
    from rag_app.retrieval import Retriever
    profile = MockMealGateway().snapshot('a').profile
    question = BackendProfileQuestion('Tôi nên chọn trái cây thế nào?', profile)
    class Endpoint:
        def __init__(self): self.calls = []
        def __call__(self, **kwargs):
            self.calls.append(kwargs)
            schema = kwargs['text_format']
            if schema is ResponsePlan:
                parsed = ResponsePlan(strategy='evidence_rag', goal='source_lookup', focus='Trái cây')
            elif schema is GroundingReview:
                parsed = GroundingReview(accepted_blocks=[ReviewedBlock(block_index=0,evidence=[EvidenceSpan(citation_id='C1',line_ids=[0])])])
            else:
                parsed = GeneratedAnswer(supported=True,blocks=[AnswerBlock(text='Nội dung kiểm thử.',citation_ids=['C1'])],uncertainty='')
            return SimpleNamespace(id='offline',status='completed',output_parsed=parsed,usage=SimpleNamespace(input_tokens=1,output_tokens=1))
    endpoint = Endpoint()
    provider = OpenAIProvider(system.cfg, client=SimpleNamespace(responses=SimpleNamespace(parse=endpoint)))
    provider.plan_response(question, [])
    provider.generate(question, Retriever(system.store).search('trái cây')[:1], [])
    assert len(endpoint.calls) == 3
    for call in endpoint.calls:
        payload = json.loads(call['input'][1]['content'])
        assert payload['USER_PROFILE']['profile']['weight'] == 60
        assert payload['USER_PROFILE']['profile']['profileVersion'] == 1
        assert payload.get('QUESTION',payload.get('question')) == str(question)
        assert 'BACKEND_PROFILE_DATA' not in payload.get('QUESTION',payload.get('question'))
        assert all('profileVersion' not in json.dumps(source) for source in payload.get('SOURCE_EXCERPTS',[]))


def test_profile_scope_applies_to_intake_question_without_pronoun(system):
    from rag_app.domain import ChatRequest
    service = system.app.state.service
    gateway = service.meals = MockMealGateway()
    update(gateway, owner='minor', age=16)
    query = 'Ăn phở buổi sáng được không?'
    result = service.chat(ChatRequest(message=query), 'minor')
    assert result.status == 'safety' and result.intent == 'special_population'
    assert not system.provider.generate_calls
    service.chat(ChatRequest(message=query), 'adult')
    assert system.provider.plan_calls[-1][0].backend_profile['age'] == 45


def test_demo_disabled_in_production_even_with_injected_mock(tmp_path):
    cfg = Settings(_env_file=None,storage_dir=tmp_path,gemini_api_key='',openai_api_key='',meal_service_mode='mock')
    app = create_app(cfg)
    cfg.app_env = 'production'
    with TestClient(app) as client:
        assert client.post('/api/demo/plan-refresh').status_code == 404
        profile = MockMealGateway().snapshot('a').profile.model_dump(by_alias=True)
        assert client.put('/api/demo/profile',json={'baseVersion':1,'profile':profile}).status_code == 404


@pytest.mark.parametrize('allergies,expected', [(None,'chưa khai thông tin dị ứng'), ([], 'đã khai không có dị ứng đã biết'), (['đậu phộng'], 'ghi nhận dị ứng: đậu phộng')])
def test_allergy_fact_is_short_and_distinguishes_missing_from_none(tmp_path, allergies, expected):
    cfg = Settings(_env_file=None,storage_dir=tmp_path,gemini_api_key='',openai_api_key='',meal_service_mode='mock')
    with TestClient(create_app(cfg)) as client:
        snapshot = client.get('/api/meal-context').json()
        snapshot['profile'].update(allergies=allergies,restrictionsResolved=False)
        assert client.put('/api/demo/profile',json={'baseVersion':1,'profile':snapshot['profile']}).status_code == 200
        reply = client.post('/api/chat',json={'message':'tôi dị ứng gì'}).json()
        assert reply['status'] == 'answered' and reply['answer_origin'] == 'static'
        assert expected in reply['answer'] and 'phiên bản 2' in reply['answer']
        assert 'chiều cao' not in reply['answer'] and 'cân nặng' not in reply['answer']
        assert reply['answer'].count('.') == 1
        summary = client.post('/api/chat',json={'message':'bạn đang dùng hồ sơ nào'}).json()
        assert 'chiều cao' in summary['answer'] and 'cân nặng' in summary['answer']
