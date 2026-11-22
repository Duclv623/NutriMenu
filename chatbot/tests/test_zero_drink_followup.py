import pytest
from rag_app.conversation import topic_for_turn, is_portion_description
from rag_app.safety import is_elliptical_intake_followup, is_intake_quantity_request
from rag_app.domain import AnswerBlock, GeneratedAnswer
from rag_app.provider import GroundingReview, apply_grounding_review

TOPIC = 'Nước ngọt zero sugar thì tôi uống bao nhiêu lon cũng được đúng không?'

@pytest.mark.parametrize('question', ['ngày uống mấy lon được', 'mỗi ngày uống mấy chai được?', 'uống bao nhiêu lon là vừa?', 'vậy uống mấy lon một ngày được?', 'ngày uống mấy lon'])
def test_zero_quantity_followup_keeps_subject(question):
    assert is_elliptical_intake_followup(question)
    assert is_intake_quantity_request(question)
    assert topic_for_turn(question, [{'question': TOPIC, 'topic': TOPIC}]) == TOPIC

@pytest.mark.parametrize('question', ['Tôi nên uống sữa mấy chai?', 'Tôi uống bia được không?', '100g cơm có bao nhiêu calo?'])
def test_named_new_subject_does_not_inherit_zero(question):
    assert not is_elliptical_intake_followup(question)
    assert topic_for_turn(question, [{'question': TOPIC, 'topic': TOPIC}]) == question

@pytest.mark.parametrize('portion', ['hai lon', '1 chai nhỏ'])
def test_drink_portion_keeps_subject(portion):
    assert is_portion_description(portion)
    assert topic_for_turn(portion, [{'question': TOPIC, 'topic': TOPIC}]) == TOPIC


def reviewed(text, question=TOPIC):
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(text=text, citation_ids=['C1'])], uncertainty='')
    review = GroundingReview.model_validate({'accepted_blocks':[{'block_index':0, 'evidence':[{'citation_id':'C1','line_ids':[0]}]}]})
    return apply_grounding_review(answer, review, [{'id':'C1','text': 'Sugar substitutes should be used in moderation. Alcohol should be limited.' , 'language':'en'}], question)


def test_moderation_only_requires_direct_answer_even_when_judge_accepts():
    answer = reviewed('Việc sử dụng các sản phẩm có chất tạo ngọt cần được thực hiện ở mức độ vừa phải.')
    assert answer._grounding_review['server_rejections']
    assert not answer.supported  # An evasive principle must not become verified fallback.
    direct = reviewed('Không nên uống bao nhiêu tùy thích; sản phẩm có chất thay thế đường cần dùng vừa phải.')
    assert direct.supported and not direct._grounding_review['server_rejections']


def test_zero_followup_rejects_real_but_irrelevant_alcohol_evidence():
    answer = reviewed('Cần hạn chế rượu bia.', TOPIC + '\nCâu hỏi tiếp: ngày uống mấy lon được')
    assert not answer.supported
    assert answer._grounding_review['server_rejections']
    assert reviewed('Cần hạn chế rượu bia.', 'Tôi nên uống rượu bia thế nào?').supported


@pytest.mark.parametrize('saved', [False, True])
def test_zero_followup_service_keeps_topic_without_reasking_drink(system, saved):
    first = system.client.post('/api/chat', json={'message': TOPIC, 'save_history': saved}).json()
    result = system.client.post('/api/chat', json={'message': 'ngày uống mấy lon được', 'session_id': first['session_id'], 'save_history': saved}).json()
    assert system.provider.generate_calls[-1][0] == TOPIC + '\nCâu hỏi tiếp: ngày uống mấy lon được'
    assert result['clarification_question'] is None


def test_zero_quantity_states_precise_evidence_limit():
    result = reviewed('Sản phẩm có chất thay thế đường cần dùng vừa phải.', TOPIC + '\nCâu hỏi tiếp: ngày uống mấy lon được')
    assert 'chưa đủ căn cứ' in result.uncertainty and 'zero' in result.uncertainty


def test_direct_zero_decision_needs_moderation_evidence():
    text = 'Không nên uống bao nhiêu tùy thích.'
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(text=text, citation_ids=['C1'])], uncertainty='')
    review = GroundingReview.model_validate({'accepted_blocks':[{'block_index':0, 'evidence':[{'citation_id':'C1','line_ids':[0]}]}]})
    result = apply_grounding_review(answer, review, [{'id':'C1','text':'Choose drinks without added sugar.', 'language':'en'}], TOPIC)
    assert not result.supported

@pytest.mark.parametrize('text', ['Không. Bạn vẫn nên dùng vừa phải.', 'Không, bạn vẫn cần dùng vừa phải.', 'Không nên uống bao nhiêu tùy thích.'])
def test_short_direct_refusal_accepts_moderation_evidence(text):
    result = reviewed(text)
    assert result.supported and not result._grounding_review['server_rejections']

@pytest.mark.parametrize('text', ['Không. Bạn vẫn nên dùng vừa phải.', 'Không, bạn vẫn cần dùng vừa phải.'])
def test_short_direct_refusal_still_needs_moderation_evidence(text):
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(text=text, citation_ids=['C1'])], uncertainty='')
    review = GroundingReview.model_validate({'accepted_blocks':[{'block_index':0, 'evidence':[{'citation_id':'C1','line_ids':[0]}]}]})
    result = apply_grounding_review(answer, review, [{'id':'C1','text':'Choose drinks without added sugar.', 'language':'en'}], TOPIC)
    assert not result.supported


def test_daily_followup_does_not_inherit_unlimited_decision_requirement():
    result = reviewed('Mình chưa đủ căn cứ chốt số lon nước ngọt zero nên uống mỗi ngày.', TOPIC + '\nCâu hỏi tiếp: ngày uống mấy lon được')
    assert result.supported and not result._grounding_review['server_rejections']
    assert 'chưa đủ căn cứ' in result.uncertainty
