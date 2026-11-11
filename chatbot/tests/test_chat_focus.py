import httpx
import pytest

from rag_app.config import Settings
from rag_app.domain import AnswerBlock, GeneratedAnswer
from rag_app.food_data import FoodItem, FoodPlan, get_catalog, normalized
from rag_app.gemini_provider import GeminiClient
from rag_app.provider import GroundingReview, apply_grounding_review
from rag_app.retrieval import Retriever


def test_breakfast_cannot_retrieve_snack_restriction(system):
    retriever = Retriever(system.store)
    breakfast = retriever.search('Sáng tôi hay ăn bánh mì, có cần bỏ không?')
    assert breakfast and all('b) Sử dụng bữa phụ' not in h.chunk.section for h in breakfast)
    snack = retriever.search('Bữa phụ ăn bánh mì được không?')
    assert any('b) Sử dụng bữa phụ' in h.chunk.section for h in snack)


def test_reviewer_acceptance_cannot_override_meal_scope():
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(
        text='Không dùng bánh mì trong bữa phụ.', citation_ids=['C1'])], uncertainty='')
    review = GroundingReview.model_validate({'accepted_blocks': [{'block_index': 0,
        'evidence': [{'citation_id': 'C1', 'line_ids': [0]}]}]})
    sources = [{'id': 'C1', 'text': 'Không dùng bánh mì trong bữa phụ.'}]
    assert not apply_grounding_review(answer, review, sources, 'Sáng ăn bánh mì có cần bỏ không?').supported
    assert apply_grounding_review(answer, review, sources, 'Bữa phụ ăn bánh mì được không?').supported


def test_brown_rice_question_does_not_inherit_bread(system):
    first = system.client.post('/api/chat', json={'message': 'Sáng ăn bánh mì có cần bỏ không?', 'save_history': True}).json()
    second = system.client.post('/api/chat', json={'message': 'Ăn gạo lứt thì ăn nhiều cũng được nhỉ?', 'session_id': first['session_id']}).json()
    assert second['intent'] == 'knowledge'
    question, _, history = system.provider.generate_calls[-1]
    assert question == 'Ăn gạo lứt thì ăn nhiều cũng được nhỉ?' and history == []


@pytest.mark.parametrize('followup', ['nên ăn như thế nào', 'ăn thế nào?', 'nên ăn bao nhiêu là vừa?'])
def test_subject_free_intake_followup_retains_pho_topic(system, followup):
    first = system.client.post('/api/chat', json={'message': 'tôi ăn phở buổi sáng được ko'}).json()
    system.client.post('/api/chat', json={'message': followup, 'session_id': first['session_id']})
    question, _, history = system.provider.generate_calls[-1]
    assert question.startswith('tôi ăn phở buổi sáng được không\nCâu hỏi tiếp: ')
    assert question.endswith(followup) and history


def test_pho_suitability_does_not_retrieve_sample_menu_as_advice(system):
    hits = Retriever(system.store).search('tôi ăn phở buổi sáng được ko')
    assert hits and all(not any(loc.startswith('t') for loc in hit.chunk.locators) for hit in hits)


def test_explicit_breakfast_table_still_retrieves_sample_menu(system):
    hits = Retriever(system.store).search('Bảng thực đơn mẫu bữa sáng phở thịt bò của Viện Dinh dưỡng')
    assert any(any(loc.startswith('t') for loc in hit.chunk.locators) for hit in hits)


def test_daily_rice_intake_uses_guideline_evidence_without_food_table(system):
    response = system.client.post('/api/chat', json={'message': 'Một ngày tôi nên ăn bao nhiêu gram cơm?'}).json()
    assert response['intent'] == 'knowledge' and response['food_result'] is None
    assert system.provider.generate_calls and not system.provider.policy_calls


def test_intake_followup_does_not_inherit_previous_food_lookup(system):
    first = system.client.post('/api/chat', json={'message': '100g sữa bò tươi bao nhiêu calo?'}).json()
    second = system.client.post('/api/chat', json={
        'message': 'Vậy tôi nên uống bao nhiêu ml mỗi ngày?', 'session_id': first['session_id']}).json()
    assert second['intent'] == 'knowledge' and second['food_result'] is None


def test_contrastive_no_added_sugar_followup_retains_juice_context(system):
    first = system.client.post('/api/chat', json={
        'message': 'Nước ép hoa quả không bỏ đường thì uống thoải mái được không?'}).json()
    second = system.client.post('/api/chat', json={
        'message': 'Nhưng tôi không cho thêm đường mà?', 'session_id': first['session_id']}).json()
    question, _, history = system.provider.generate_calls[-1]
    assert second['intent'] == 'knowledge' and history
    assert question.startswith('Nước ép hoa quả') and question.endswith('Nhưng tôi không cho thêm đường mà?')


def test_fresh_vague_referent_asks_for_subject_before_retrieving(system):
    response = system.client.post('/api/chat', json={'message': 'Cái đó có được không?'}).json()
    assert response['status'] == 'needs_clarification'
    assert response['clarification_question'] and not system.provider.generate_calls


def test_capability_response_reflects_available_food_catalog(system):
    response = system.client.post('/api/chat', json={'message': 'Bạn có thể làm gì?'}).json()
    assert response['status'] == 'answered'
    assert 'tra thành phần thực phẩm' in response['answer']
    assert 'lưu thực đơn' in response['answer'] and 'chưa được kết nối' in response['answer']


def test_explicit_finance_question_redirects_to_nutrition_without_retrieval(system):
    response = system.client.post('/api/chat', json={'message': 'Hôm nay nên mua cổ phiếu nào?'}).json()
    assert response['status'] == 'insufficient_evidence' and not response['citations']
    assert 'không tư vấn đầu tư' in response['answer'] and 'dinh dưỡng' in response['answer']
    assert system.provider.policy_calls and not system.provider.generate_calls


def test_finance_background_does_not_block_actual_nutrition_question():
    from rag_app.safety import outside_nutrition_scope
    assert not outside_nutrition_scope('Tôi làm môi giới cổ phiếu, bữa sáng nên ăn gì?')


@pytest.mark.parametrize('message', [
    'Tôi đang run tay, vã mồ hôi, đo đường huyết 2.8 mmol/L thì nên làm gì?',
    'Tôi vừa đo glucose 2,8 mmol/l.',
    'Đường huyết của tôi 50 mg/dL và vã mồ hôi.',
    'Tôi đang run tay, đường máu 65 mg/dL.',
    'Tôi hiện ổn nhưng vừa đo đường huyết 2.8 mmol/L.',
])
def test_current_personal_low_glucose_uses_existing_urgent_boundary(message, system):
    response = system.client.post('/api/chat', json={'message': message}).json()
    assert response['intent'] == 'emergency' and response['status'] == 'safety'
    assert '115' in response['answer'] and not system.provider.generate_calls


@pytest.mark.parametrize('message', [
    'Theo tài liệu, đường huyết 2.8 mmol/L có ý nghĩa gì?',
    'Giả sử tôi run tay và đường huyết 50 mg/dL thì sao?',
    'Hôm qua tôi đo đường huyết 2.8 mmol/L, hiện đã ổn.',
    'Hôm qua tôi run tay, đường máu 2,8 mmol/L.',
    'Tôi đang run tay, đường huyết 5.2 mmol/L.',
    'Tôi ăn 2.8 gram đường và đo đường huyết.',
    'Định nghĩa ngưỡng đường huyết dưới 70 mg/dL là gì?',
])
def test_low_glucose_router_requires_current_report_and_matching_units(message):
    from rag_app.safety import classify
    assert classify(message) != 'emergency'


def test_plate_translation_scope(corpus):
    plate = [c for c in corpus if c.source_id == 'niddk-healthy-living' and 'Phương pháp đĩa ăn' in c.section]
    assert any('một phần tư đĩa ăn' in c.text for c in plate)
    assert all('một phần tư khẩu phần' not in c.text for c in plate)


def test_example_list_ends_before_next_recommendation():
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(
        text='Giảm ngũ cốc tinh chế như bánh mì trắng và ưu tiên ngũ cốc nguyên hạt.', citation_ids=['C1'])], uncertainty='')
    review = GroundingReview.model_validate({'accepted_blocks': [{'block_index': 0,
        'evidence': [{'citation_id': 'C1', 'line_ids': [0]}]}]})
    sources = [{'id': 'C1', 'text': 'Giảm ngũ cốc tinh chế (bánh mì trắng). Ưu tiên ngũ cốc nguyên hạt.'}]
    assert apply_grounding_review(answer, review, sources).supported
    answer.blocks[0].text = 'Giảm ngũ cốc tinh chế như bánh mì trắng và bánh mì dừa.'
    assert not apply_grounding_review(answer, review, sources).supported


def test_plate_food_example_cannot_become_group_quota():
    review = GroundingReview.model_validate({'accepted_blocks': [{'block_index': 0,
        'evidence': [{'citation_id': 'C1', 'line_ids': [0]}]}]})
    sources = [{'id': 'C1', 'text': 'Nhóm thực phẩm carbohydrate giàu chất xơ như gạo lứt, đậu hoặc trái cây nên chiếm một phần tư đĩa ăn.'}]
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(
        text='Gạo lứt nên chiếm một phần tư đĩa ăn.', citation_ids=['C1'])], uncertainty='')
    rejected = apply_grounding_review(answer, review, sources, 'Gạo lứt ăn nhiều được nhỉ?')
    assert not rejected.supported and rejected._grounding_review['server_rejections']
    answer.blocks[0].text = 'Cần kiểm soát lượng; nhóm carbohydrate chiếm 1/4 đĩa, gạo lứt là một ví dụ.'
    assert apply_grounding_review(answer, review, sources).supported
    answer.blocks[0].text = 'Cần kiểm soát lượng; nhóm carbohydrate giàu chất xơ như gạo lứt chỉ nên chiếm một phần tư đĩa.'
    assert apply_grounding_review(answer, review, sources).supported


def pending_history():
    catalog = get_catalog()
    plan = FoodPlan(operation='lookup', items=[FoodItem(name='sữa bò', amount=200, unit='ml')], nutrients=['calo'])
    result = catalog.execute(plan)
    result['request'] = plan.model_dump()
    return [{'question': '200ml sữa bò bao nhiêu calo', 'response': {'food_result': result}}]


@pytest.mark.parametrize('choice', ['sữa bò tươi', 'nin_foods:10001'])
def test_type_selection_preserves_quantity_nutrient_and_skips_planner(choice):
    catalog = get_catalog()
    plan = catalog.resolve_selection(choice, pending_history())
    assert plan.items[0].name == 'nin_foods:10001'
    assert plan.items[0].amount == 200 and plan.items[0].unit == 'ml' and plan.nutrients == ['calo']
    result = catalog.execute(plan)
    assert not result['items'][0]['calculation_available']
    assert len(result['items'][0]['display_nutrients']) == 1


@pytest.mark.parametrize('question', ['300ml sữa bò tươi bao nhiêu calo', 'sữa dê tươi', 'bánh mì có cần bỏ không?', 'tính 100g sữa bò tươi'])
def test_new_request_does_not_use_selection_shortcut(question):
    assert get_catalog().resolve_selection(question, pending_history()) is None


def test_milk_choices_exclude_bubble_tea_and_cross_source_duplicates():
    choices = pending_history()[0]['response']['food_result']['unresolved'][0]['candidates']
    assert choices and all('bò' in c['name'].lower() for c in choices)
    assert all(normalized(c['name']).startswith('sua bo') for c in choices)
    assert sum(c['name'].lower() == 'sữa bò tươi' for c in choices) == 1


@pytest.mark.parametrize(('question', 'amount', 'unit'), [
    ('200ml sữa bò bao nhiêu calo', 200, 'ml'),
    ('300ml sữa bò tươi bao nhiêu calo', 300, 'ml'),
    ('200g sữa bò tươi có bao nhiêu đạm và calo?', 200, 'g'),
])
def test_simple_lookup_uses_explicit_quantity(question, amount, unit):
    plan = get_catalog().simple_lookup(question)
    assert plan.items[0].amount == amount and plan.items[0].unit == unit
    assert plan.nutrients


@pytest.mark.parametrize('question', ['100g sữa và 200g trứng bao nhiêu calo', '100g ngô trong bảng 2007 bao nhiêu canxi', 'sữa bò tươi', '200g sữa bò tươi bao nhiêu đường huyết'])
def test_complex_requests_do_not_use_simple_parser(question):
    assert get_catalog().simple_lookup(question) is None


def test_only_cited_sources_contribute_warnings(system):
    system.provider.answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(
        text='Câu được kiểm thử.', citation_ids=['C1'])], uncertainty='')
    body = system.client.post('/api/chat', json={'message': 'Chất đạm có trong những thực phẩm nào?'}).json()
    _, hits, _ = system.provider.generate_calls[-1]
    assert body['warnings'][1:] == list(dict.fromkeys(hits[0].chunk.warnings))


def test_unsaved_dialogue_preserves_context_without_disk_history(system):
    system.provider.food_plan = FoodPlan(operation='lookup', items=[FoodItem(name='sữa bò', amount=200, unit='ml')], nutrients=['calo'])
    first = system.client.post('/api/chat', json={'message': '200ml sữa bò bao nhiêu calo'}).json()
    second = system.client.post('/api/chat', json={'message': 'sữa bò tươi', 'session_id': first['session_id']}).json()
    request = second['food_result']['request']
    assert request['items'][0]['amount'] == 200 and request['items'][0]['unit'] == 'ml'
    assert request['nutrients'] == ['calo'] and not second['history_saved']
    assert system.client.get('/api/sessions').json() == []
    with system.store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 0


def test_transient_history_is_owner_bound_and_expires(system):
    from rag_app.domain import ChatRequest
    service = system.app.state.service
    first = service.chat(ChatRequest(message='Chào bạn'), 'owner-a')
    with pytest.raises(PermissionError):
        service.chat(ChatRequest(message='Còn cái đó?', session_id=first.session_id), 'owner-b')
    key = str(first.session_id)
    owner, timestamp, turns = service._transient[key]
    service._transient[key] = (owner, timestamp-1801, turns)
    with pytest.raises(PermissionError):
        service.chat(ChatRequest(message='Còn cái đó?', session_id=first.session_id), 'owner-a')


def test_delete_saved_history_also_deletes_transient_context(system):
    first = system.client.post('/api/chat', json={'message': 'Xin chào', 'save_history': True}).json()
    sid = first['session_id']
    assert sid in system.app.state.service._transient
    assert system.client.delete('/api/sessions/'+sid).status_code == 204
    assert sid not in system.app.state.service._transient
    assert system.client.post('/api/chat', json={'message': 'Còn cái đó?', 'session_id': sid}).status_code == 404


def test_retriever_cache_refreshes_after_atomic_reindex(system, corpus):
    service = system.app.state.service
    first = service.retriever()
    assert service.retriever() is first
    system.store.replace_index(corpus, {'mode': 'lexical'})
    assert service.retriever() is not first


def test_burst_pacing_is_shared_and_refills(monkeypatch):
    now = [100.0]
    sleeps = []
    monkeypatch.setattr('rag_app.gemini_provider.time.monotonic', lambda: now[0])

    def sleep(delay):
        sleeps.append(delay)
        now[0] += delay

    monkeypatch.setattr('rag_app.gemini_provider.time.sleep', sleep)
    cfg = Settings(_env_file=None, gemini_api_key='unit-burst-key', gemini_request_interval=6.1, gemini_burst_requests=3)
    GeminiClient._buckets.clear()
    clients = [GeminiClient(cfg, httpx.MockTransport(lambda request: httpx.Response(200, json={}))) for _ in range(2)]
    try:
        for i in range(3):
            clients[i % 2].post(cfg.gemini_model, 'generateContent', {})
        assert not sleeps
        clients[1].post(cfg.gemini_model, 'generateContent', {})
        assert sum(sleeps) == pytest.approx(6.1)
        now[0] += 30
        previous = len(sleeps)
        for _ in range(3):
            clients[0].post(cfg.gemini_model, 'generateContent', {})
        assert len(sleeps) == previous
    finally:
        for client in clients:
            client.close()
        GeminiClient._buckets.clear()
