import json
from types import SimpleNamespace

import pytest

from rag_app.domain import AnswerBlock, GeneratedAnswer
from rag_app.provider import DirectDraft, DirectReview, OpenAIProvider
from rag_app.routing import ResponsePlan, constrain_plan


def plan(strategy='direct_llm', goal='practical_steps', **updates):
    return ResponsePlan(strategy=strategy, goal=goal, focus='Giúp người dùng thực hiện việc đang hỏi.', **updates)


@pytest.mark.parametrize('question', [
    'Theo Bộ Y tế, tôi cần bao nhiêu chất xơ?',
    'Tài liệu nói gì về bữa phụ?',
    'Một ngày nên ăn bao nhiêu gram cơm?',
    'GI của phở là bao nhiêu?',
    'So sánh tác động đường huyết của nước ép và trái cây.',
    'Tỷ lệ carbohydrate 50% có phù hợp không?',
    'Ăn xôi có tốt không?',
])
def test_model_cannot_select_unsourced_direct_for_clinical_or_exact_question(question):
    assert constrain_plan(plan(), question).strategy != 'direct_llm'


def test_diacritic_gi_and_ordinary_theo_do_not_force_source_lookup():
    assert constrain_plan(plan(), 'Chuẩn bị đồ ăn mang đi cần chú ý gì?').strategy == 'direct_llm'
    assert constrain_plan(plan('practical_rag', 'schedule'), 'Ăn theo ca đêm nên sắp xếp thế nào?').strategy == 'practical_rag'


def test_direct_answer_skips_index_retrieval_and_embedding(system):
    system.provider.response_plan = plan()
    system.store.replace_index([], {'mode': 'lexical'})
    result = system.client.post('/api/chat', json={'message': 'Tôi hay quên chuẩn bị đồ ăn mang đi.'}).json()
    assert result['status'] == 'answered' and result['response_strategy'] == 'direct_llm'
    assert not result['citations'] and '[C' not in result['answer']
    assert system.provider.direct_calls and not system.provider.generate_calls
    assert not system.provider.embed_calls and result['usage']['output_tokens'] == 10


def test_direct_rephrasing_uses_transient_answer_without_saving_history(system):
    system.provider.response_plan = plan('direct_llm', 'explanation')
    first = system.client.post('/api/chat', json={'message': 'Giải thích carb dễ hiểu.'}).json()
    second = system.client.post('/api/chat', json={
        'message': 'Giải thích lại đơn giản hơn', 'session_id': first['session_id']}).json()
    question, _, history = system.provider.direct_calls[-1]
    assert question.startswith('Giải thích carb dễ hiểu.\nCâu hỏi tiếp: ')
    assert history[-1]['response']['answer'] == first['answer']
    assert not second['history_saved'] and system.client.get('/api/sessions').json() == []


def test_practical_source_prompts_receive_the_expected_user_outcome(system):
    from rag_app.provider import GroundingReview
    from rag_app.retrieval import Retriever
    hits = Retriever(system.store).search('Ăn phở ngoài quán nên chọn thế nào?')
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(
        text='Chọn nước dùng trong, bớt sợi và thêm rau.', citation_ids=['C1'])], uncertainty='')
    review = GroundingReview.model_validate({'accepted_blocks': [
        {'block_index': 0, 'evidence': [{'citation_id': 'C1', 'line_ids': [0]}]}]})
    provider, endpoint = provider_with(system, [answer, review])
    selected = plan('practical_rag', 'practical_steps')
    provider.generate_practical('Ăn phở ngoài quán nên chọn thế nào?', hits, [], selected)
    payloads = [json.loads(c['input'][1]['content']) for c in endpoint.calls]
    assert len(payloads) == 2 and all(p['RESPONSE_GOAL'] == selected.model_dump() for p in payloads)


def test_practical_schedule_asks_missing_context_and_uses_sources(system):
    question = 'Tôi làm ca đêm, bữa chính và bữa phụ nên sắp xếp thế nào?'
    system.provider.response_plan = plan('practical_rag', 'schedule',
        clarification_question='Bạn làm ca từ mấy giờ đến mấy giờ và thường ngủ lúc nào?')
    first = system.client.post('/api/chat', json={'message': question, 'save_history': True}).json()
    assert first['response_strategy'] == 'practical_rag' and first['status'] == 'needs_clarification'
    assert not first['citations'] and not system.provider.generate_calls
    assert first['clarification_question'] and not system.provider.direct_calls
    system.provider.response_plan = plan('practical_rag', 'schedule')
    # Also work after the transient context is lost and disk history is read.
    system.app.state.service._transient.clear()
    second = system.client.post('/api/chat', json={
        'message': 'Ca của tôi từ 22h đến 6h, ngủ từ 8h đến 14h.',
        'session_id': first['session_id']}).json()
    resolved = system.provider.plan_calls[-1][0]
    assert resolved.startswith(question + '\nCâu hỏi tiếp: ')
    assert '22h' in resolved and not second['clarification_question']
    assert system.provider.practical_calls[-1][3].goal == 'schedule'


def test_explicit_source_request_overrides_direct_router(system):
    system.provider.response_plan = plan()
    result = system.client.post('/api/chat', json={'message': 'Theo NIDDK, ăn trái cây có lợi ích gì?'}).json()
    assert result['response_strategy'] == 'evidence_rag' and result['citations']
    assert not system.provider.direct_calls


def test_numeric_food_lookup_bypasses_conversation_router(system):
    result = system.client.post('/api/chat', json={'message': '100g sữa bò tươi có bao nhiêu calo?'}).json()
    assert result['response_strategy'] == 'structured_lookup'
    assert not system.provider.plan_calls and not system.provider.direct_calls


@pytest.mark.parametrize('question', [
    'Tôi nên tăng liều insulin lên bao nhiêu?',
    'Tôi đang mang thai, nên ăn thế nào?',
    'Tôi vừa đo đường huyết 2.8 mmol/L.',
])
def test_safety_precedes_all_answer_strategies(system, question):
    system.provider.response_plan = plan()
    result = system.client.post('/api/chat', json={'message': question}).json()
    assert result['status'] == 'safety' and result['response_strategy'] == 'safety'
    assert not system.provider.plan_calls and not system.provider.direct_calls


def test_rejected_direct_draft_is_not_served_and_requires_source_route(system):
    system.provider.response_plan = plan()
    system.provider.answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(
        text='Bạn nên ăn 150g cơm mỗi bữa.', citation_ids=[])], uncertainty='')
    result = system.client.post('/api/chat', json={'message': 'Tôi hay quên chuẩn bị đồ ăn mang đi.'}).json()
    assert result['response_strategy'] == 'evidence_rag'
    assert '150g' not in result['answer'] and system.provider.generate_calls


def test_no_evidence_never_enables_direct_guessing(system):
    system.provider.response_plan = plan('evidence_rag', 'source_lookup')
    system.provider.answer = GeneratedAnswer(supported=False, blocks=[], uncertainty='Thiếu bằng chứng.')
    result = system.client.post('/api/chat', json={'message': 'Tài liệu có nói về loại rau này không?'}).json()
    assert result['status'] == 'insufficient_evidence'
    assert not system.provider.direct_calls


class Endpoint:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(id=f'api-{len(self.calls)}', status='completed',
            output_parsed=next(self.outputs), usage=SimpleNamespace(input_tokens=10, output_tokens=5))


def provider_with(system, outputs):
    endpoint = Endpoint(outputs)
    provider = OpenAIProvider(system.cfg, client=SimpleNamespace(responses=SimpleNamespace(parse=endpoint)))
    return provider, endpoint


def test_real_direct_path_has_independent_review_and_no_fabricated_source(system):
    provider, endpoint = provider_with(system, [
        DirectDraft(text='Bạn có thể ghi danh sách đồ cần mang từ tối hôm trước.', uncertainty=''),
        DirectReview(safe=True, answers_question=True, requires_evidence=False, reason='Đúng phạm vi tổ chức thói quen.'),
    ])
    answer, usage = provider.generate_direct('Tôi hay quên chuẩn bị đồ ăn mang đi.', plan(), [])
    assert answer.supported and not answer.blocks[0].citation_ids
    assert len(endpoint.calls) == 2 and all(c['store'] is False for c in endpoint.calls)
    assert answer._provider_response_ids == ['api-1', 'api-2'] and answer._grounding_model is None
    assert usage == {'input_tokens': 20, 'output_tokens': 10}
    assert 'SOURCE_EXCERPTS' not in json.loads(endpoint.calls[0]['input'][1]['content'])


def test_review_rejects_vague_direct_answer(system):
    provider, _ = provider_with(system, [
        DirectDraft(text='Bạn cần duy trì thói quen ăn uống hợp lý.', uncertainty=''),
        DirectReview(safe=True, answers_question=False, requires_evidence=False, reason='Thiếu thao tác cụ thể.'),
    ])
    answer, _ = provider.generate_direct('Làm sao để đỡ quên chuẩn bị đồ ăn?', plan(), [])
    assert not answer.supported and not answer.blocks


@pytest.mark.parametrize('text', [
    'Ăn 200g cơm mỗi bữa.', 'Theo tài liệu, hãy ăn đúng giờ. [C1]',
    'Bạn nên tự tăng liều insulin.', 'Đồ ăn này giúp giảm đường huyết.',
    'Bạn nên lấy 50% năng lượng từ carbohydrate.',
])
def test_direct_draft_guard_catches_clinical_claims_before_review(system, text):
    provider, endpoint = provider_with(system, [DirectDraft(text=text, uncertainty='')])
    answer, _ = provider.generate_direct('Chuẩn bị đồ ăn mang đi thế nào?', plan(), [])
    assert not answer.supported and not answer.blocks and len(endpoint.calls) == 1


def test_planner_redacts_input_and_preserves_api_provenance(system):
    provider, endpoint = provider_with(system, [plan()])
    selected, metadata, usage = provider.plan_response('Tôi hay quên chuẩn bị đồ ăn. sk-' + 'x' * 40, [])
    payload = endpoint.calls[0]['input'][1]['content']
    assert 'sk-' not in payload and selected.strategy == 'direct_llm'
    assert metadata._provider_response_ids == ['api-1'] and usage['output_tokens'] == 5
