import pytest

from rag_app.food_data import FoodItem, FoodPlan, canonical, get_catalog
from rag_app.safety import classify


@pytest.mark.parametrize('question,intent', [
    ('Tôi đang mang bầu, nên ăn cơm thế nào?', 'special_population'),
    ('Tôi bị bệnh thận mạn giai đoạn 3, nên ăn thế nào?', 'special_population'),
    ('Tôi mắc đái tháo đường típ một, nên ăn gì?', 'special_population'),
    ('Tôi muốn tiêm 10 đơn vị insulin trước bữa sáng được không?', 'medication'),
    ('Tôi nên uống metformin 500mg ngày mấy lần?', 'medication'),
    ('Tôi không hề khó thở hay đau ngực, chỉ hỏi về bữa sáng.', 'knowledge'),
    ('Tôi đang lơ mơ, lú lẫn sau tiêm insulin, phải làm sao?', 'emergency'),
])
def test_new_safety_phrasings(question, intent):
    assert classify(question) == intent


def test_quarantined_dishes_cannot_leak_numbers_into_evidence():
    from rag_app.food_data import food_hits
    plan = FoodPlan(operation='sum', items=[FoodItem(name='nin_dishes:VPF-000358', amount=100),
                                           FoodItem(name='nin_foods:10001', amount=100)])
    result = get_catalog().execute(plan)
    dish = result['items'][0]
    assert dish['review_status'] == 'quarantined'
    assert not dish['calculation_available']
    assert not result['totals']
    assert '190.4' not in '\n'.join(h.chunk.text for h in food_hits(result))


def test_folate_keys_and_label_missing_field(system):
    assert canonical('Folate, DFE', 'mcg') != canonical('Folate tổng số', 'mcg')
    catalog = system.app.state.service.supplements
    plan = FoodPlan(operation='lookup', items=[FoodItem(name='supp-th-product-banh-gao-xot-pho-mai-th-true-food-300-g', amount=100)], nutrients=['đường thêm', 'canxi'])
    result = catalog.execute('label', plan, '')
    evidence = '\n'.join(h.chunk.text for h in catalog.hits(result))
    assert 'Đường thêm' in evidence and 'Canxi' in evidence and 'không công bố' in evidence


def test_source_comparison_keeps_both_sources(system):
    assert not get_catalog().looks_like_lookup('So sánh khuyến cáo chất béo của Bộ Y tế và NIDDK.')
    hits = system.app.state.service.retriever().search('So sánh khuyến cáo chất béo của Bộ Y tế và NIDDK.', mode='lexical')
    assert {'byt5481-nutrition', 'niddk-healthy-living'} <= {h.chunk.source_id for h in hits}


def test_context_is_bounded_and_new_subject_replaces_topic(system):
    session = system.client.post('/api/chat', json={'message':'Tôi ăn phở buổi sáng được không?'}).json()['session_id']
    for _ in range(15):
        system.client.post('/api/chat', json={'message':'Vậy nên ăn như thế nào?', 'session_id':session})
    service = system.app.state.service
    histories = list(service._transient.values())
    assert max(len(t['question']) for _, _, turns in histories for t in turns) < 100
    assert max(len(call[0]) for call in system.provider.generate_calls) < 1100


def test_food_warning_is_preserved(system):
    from rag_app.domain import AnswerBlock, GeneratedAnswer
    system.provider.answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(text='Kết quả kiểm tra.', citation_ids=['C1'])], uncertainty='Giới hạn cần giữ.')
    result = system.client.post('/api/chat', json={'message':'100g sữa bò tươi có bao nhiêu carb?'}).json()
    assert 'Giới hạn cần giữ.' in result['warnings']


def test_refreshed_energy_has_source_evidence():
    record = get_catalog().get('nin_foods:1045')
    energy = next(n for n in record['nutrients'] if n['key'] == 'energy')
    assert energy['previous_value'] == 1
    assert energy['value'] == 351.8
    assert energy['review_evidence']['evidence_sha256']


def test_portion_definition_keeps_intake_principles(system):
    hits = system.app.state.service.retriever().search('Tôi ăn phở buổi sáng được không?', mode='lexical')
    assert any(h.chunk.source_id == 'niddk-healthy-living' and 'Lên kế hoạch lượng' in h.chunk.section for h in hits)
