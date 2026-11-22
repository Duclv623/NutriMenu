"""Regression tests for evidence provenance and present safety signals."""

import pytest

from rag_app.dialogue import context_response
from rag_app.food_data import FoodItem, FoodPlan, food_hits, get_catalog
from rag_app.retrieval import fold
from rag_app.supplements import SupplementCatalog


@pytest.mark.parametrize('catalog_kind', ['food', 'label'])
def test_model_clarification_never_becomes_tool_evidence(catalog_kind):
    # A model can write a confident claim instead of an actual question. It is
    # untrusted even if the requested item cannot be found in the catalog.
    invented = 'Sản phẩm này chắc chắn phù hợp với mọi người bệnh.'
    plan = FoodPlan(operation='lookup', items=[FoodItem(name='sản phẩm không tồn tại xyz')],
                    clarification=invented)
    if catalog_kind == 'food':
        result = get_catalog().execute(plan)
        hits = food_hits(result)
    else:
        catalog = SupplementCatalog()
        result = catalog.execute('label', plan, 'Tra sản phẩm không tồn tại xyz')
        hits = catalog.hits(result)
    assert result['unresolved']
    assert invented not in '\n'.join(hit.chunk.text for hit in hits)


def test_current_symptoms_with_unspecified_glucose_units_are_not_ignored():
    result = context_response('Tôi vừa đo đường huyết 3,2, hiện đang run. Số này nghĩa là gì?', [])
    assert result is not None
    text, clarification, status = result
    answer = fold(text + ' ' + (clarification or ''))
    assert status == 'safety'
    assert 'don vi' in answer
    assert 'so do duong huyet ban neu dang thap' not in answer
    assert 'ho tro' in answer or 'y te' in answer or 'cap cuu' in answer


@pytest.mark.parametrize(('message', 'required'), [
    ('Tôi vừa sửa cân nặng trong hồ sơ từ 68 kg sang 64 kg. Bạn dùng số nào?', ('ho so',)),
    ('Tôi chưa ghi dị ứng trong hồ sơ, vậy có thể xem là không bị dị ứng không?', ('di ung',)),
    ('Bạn có thể tạo và lưu thực đơn cá nhân cho tôi không?', ('thuc don',)),
    ('Cho tôi biết món này có những chất gì?', ('mon',)),
    ('Hãy cho xem nguồn của kết luận đó và vị trí đoạn trích.', ('noi dung',)),
])
def test_missing_context_and_capability_questions_get_specific_response(message, required):
    result = context_response(message, [])
    assert result is not None
    text, clarification, _ = result
    answer = fold(text + ' ' + (clarification or ''))
    assert all(term in answer for term in required)

@pytest.mark.parametrize(('absence', 'expected_count'), [
    ('NIDDK không đưa ra con số định lượng cụ thể về chất béo.', 1),
    ('Trong đoạn trích NIDDK không nêu con số định lượng cụ thể về chất béo.', 2),
    ('Mình hiện tại không có số liệu cụ thể về chất béo.', 2),
])
def test_grounding_limits_absence_claim_to_retrieved_excerpt(absence, expected_count):
    from rag_app.domain import AnswerBlock, GeneratedAnswer
    from rag_app.provider import (
        EvidenceSpan,
        GroundingReview,
        ReviewedBlock,
        apply_grounding_review,
    )

    answer = GeneratedAnswer(supported=True, uncertainty='', blocks=[
        AnswerBlock(text='Bộ Y tế nêu chất béo chiếm 20–25% tổng năng lượng.', citation_ids=['C1']),
        AnswerBlock(text=absence, citation_ids=['C2']),
    ])
    review = GroundingReview(accepted_blocks=[
        ReviewedBlock(block_index=0, evidence=[EvidenceSpan(citation_id='C1', line_ids=[0])]),
        ReviewedBlock(block_index=1, evidence=[EvidenceSpan(citation_id='C2', line_ids=[0])]),
    ])
    excerpts = [
        {'id': 'C1', 'text': 'Chất béo chiếm 20–25% tổng năng lượng.'},
        {'id': 'C2', 'text': 'Chọn thực phẩm phù hợp với kế hoạch ăn uống cá nhân.'},
    ]
    result = apply_grounding_review(answer, review, excerpts)
    assert len(result.blocks) == expected_count
    assert '20–25%' in result.blocks[0].text
    assert bool(result._grounding_review['server_rejections']) == (expected_count == 1)


def test_opposing_label_qualifiers_resolve_independently():
    catalog = SupplementCatalog()
    plan = FoodPlan(operation='compare', items=[
        FoodItem(name='Sữa chua không đường Mộc Châu', amount=100),
        FoodItem(name='Sữa chua ít đường Mộc Châu', amount=100),
    ], nutrients=['carbohydrate'])
    result = catalog.execute('label', plan, 'So sánh sữa chua không đường và ít đường Mộc Châu')
    assert not result['unresolved']
    assert [item['id'] for item in result['items']] == [
        'supp-mcm-product-40-label-p4', 'supp-mcm-product-37-label-p5',
    ]
    assert [item['calculated_nutrients']['carbohydrate_g'] for item in result['items']] == [4.5, 10.8]


def test_yogurt_example_cites_both_reviewed_labels_and_preserves_missing_sugar(system):
    body = system.client.post('/api/chat', json={
        'message': 'Sữa chua không đường và sữa chua ít đường khác nhau thế nào, loại nào tôi ăn thoải mái được?'
    }).json()
    assert body['status'] == 'answered' and body['answer_origin'] == 'static'
    assert len(body['citations']) == 2
    assert {c['source_id'] for c in body['citations']} == {'mcm-product-37', 'mcm-product-40'}
    items = {item['id']: item for item in body['reference_result']['items']}
    plain = items['supp-mcm-product-40-label-p4']['payload']['nutrients']
    reduced = items['supp-mcm-product-37-label-p5']['payload']['nutrients']
    assert plain['total_sugars_g'] is None and plain['carbohydrate_g'] == 4.5
    assert reduced['total_sugars_g'] == 9 and reduced['carbohydrate_g'] == 10.8
    assert '4,5' in body['answer'] and '10,8' in body['answer']
    assert 'không giới hạn' in body['answer'] and 'không áp cho mọi hãng' in body['answer']
