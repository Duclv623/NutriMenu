import pytest

from rag_app.conversation import topic_for_turn
from rag_app.domain import AnswerBlock, GeneratedAnswer
from rag_app.provider import GroundingReview, apply_grounding_review
from rag_app.retrieval import fold
from rag_app.safety import is_elliptical_intake_followup, is_intake_advice


@pytest.mark.parametrize('followup', ['tôi ăn bao nhiêu thì ổn', 'bao nhiêu là vừa?', 'vậy ăn mấy tô thì được?'])
@pytest.mark.parametrize('saved', [False, True])
def test_quantity_followup_keeps_named_dish(system, followup, saved):
    first = system.client.post('/api/chat', json={'message':'sáng tôi ăn phở được không', 'save_history':saved}).json()
    response = system.client.post('/api/chat', json={'message':followup, 'session_id':first['session_id'], 'save_history':saved}).json()
    query, hits, _ = system.provider.generate_calls[-1]
    assert response['intent'] == 'knowledge' and response['food_result'] is None
    assert response['clarification_question'] and response['clarification_question'].endswith('?')
    assert query == 'sáng tôi ăn phở được không\nCâu hỏi tiếp: ' + followup
    assert all('phuong phap dia' not in fold(h.chunk.section) and 'the plate method' not in fold(h.chunk.section) for h in hits)
    assert is_elliptical_intake_followup(followup) and is_intake_advice(followup)


def test_saved_topic_survives_transient_context_loss(system):
    first = system.client.post('/api/chat', json={'message':'sáng tôi ăn phở được không','save_history':True}).json()
    system.client.post('/api/chat', json={'message':'tôi ăn bao nhiêu thì ổn', 'session_id':first['session_id'], 'save_history':True})
    system.app.state.service._transient.clear()
    system.client.post('/api/chat', json={'message':'vậy ăn mấy tô thì được?', 'session_id':first['session_id']})
    assert system.provider.generate_calls[-1][0].startswith('sáng tôi ăn phở được không\nCâu hỏi tiếp: ')


def test_fresh_quantity_question_asks_for_subject(system):
    result = system.client.post('/api/chat', json={'message':'tôi ăn bao nhiêu thì ổn'}).json()
    assert result['status'] == 'insufficient_evidence'
    assert not system.provider.generate_calls and system.provider.policy_calls


def test_new_food_subject_is_independent():
    history = [{'question':'sáng tôi ăn phở được không', 'topic':'sáng tôi ăn phở được không'}]
    assert topic_for_turn('Tôi nên ăn gạo lứt bao nhiêu?', history) == 'Tôi nên ăn gạo lứt bao nhiêu?'
    assert not is_elliptical_intake_followup('100g sữa bò có bao nhiêu calo?')


def reviewed(text, question):
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(text=text,citation_ids=['C1'])],uncertainty='')
    review = GroundingReview.model_validate({'accepted_blocks':[{'block_index':0,'evidence':[{'citation_id':'C1','line_ids':[0]}]}]})
    return apply_grounding_review(answer, review, [{'id':'C1','text':text}], question)


def test_plate_area_cannot_answer_named_dish_quantity():
    text = 'Rau chiếm một nửa đĩa ăn, nhóm carbohydrate chiếm một phần tư đĩa ăn.'
    result = reviewed(text, 'sáng tôi ăn phở được không\nCâu hỏi tiếp: tôi ăn bao nhiêu thì ổn')
    assert not result.supported and result._grounding_review['server_rejections']
    assert reviewed(text, 'Phương pháp đĩa ăn chia diện tích như thế nào?').supported


def test_wrong_drinking_clause_is_rejected_for_food_question():
    text = 'Bạn có thể cần ăn với khẩu phần nhỏ hơn hoặc uống ít thường xuyên hơn.'
    result = reviewed(text, 'sáng tôi ăn phở được không')
    assert not result.supported and result._grounding_review['server_rejections']
    assert reviewed(text, 'Tôi nên ăn uống như thế nào?').supported


def test_portion_details_answer_the_clarification_without_losing_subject(system):
    first = system.client.post('/api/chat', json={'message':'sáng tôi ăn phở được không'}).json()
    system.client.post('/api/chat', json={'message':'tôi ăn bao nhiêu thì ổn', 'session_id':first['session_id']})
    response = system.client.post('/api/chat', json={'message':'tô nhỏ, ăn hết', 'session_id':first['session_id']}).json()
    assert system.provider.generate_calls[-1][0].startswith('sáng tôi ăn phở được không\nCâu hỏi tiếp: ')
    assert response['clarification_question'] is None
    response = system.client.post('/api/chat', json={'message':'vậy ăn bao nhiêu là vừa?', 'session_id':first['session_id']}).json()
    assert response['clarification_question'] is None


def test_splitting_a_large_portion_does_not_invent_half_a_bowl():
    text = 'Bạn có thể chia đôi tô phở nếu tô quá lớn.'
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(text=text,citation_ids=['C1'])],uncertainty='')
    review = GroundingReview.model_validate({'accepted_blocks':[{'block_index':0,'evidence':[{'citation_id':'C1','line_ids':[0]}]}]})
    result = apply_grounding_review(answer, review, [{'id':'C1','text':'Có thể chia món ăn hoặc để riêng phần mang về.'}], 'sáng tôi ăn phở được không')
    assert not result.supported
