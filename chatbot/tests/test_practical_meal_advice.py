import pytest

from rag_app.domain import AnswerBlock, GeneratedAnswer
from rag_app.provider import GroundingReview, apply_grounding_review
from rag_app.retrieval import Retriever, is_noodle_meal_advice


@pytest.mark.parametrize('question', [
    'Khi ăn phở ngoài quán thì tôi nên chú ý gì để kiểm soát lượng ăn?',
    'Sáng tôi ăn phở được không?',
    'Ăn bún ngoài quán nên gọi thế nào?',
    'Ăn hủ tiếu nên chọn như thế nào?',
    'Sáng ăn phở được không?\nCâu hỏi tiếp: Nên ăn như thế nào?',
])
@pytest.mark.parametrize('mode', ['lexical', 'hybrid'])
def test_noodle_advice_has_component_choices_and_lean_protein(system, question, mode):
    options = {'mode': mode}
    if mode == 'hybrid':
        chunks, _, _ = system.store.load_index()
        # Even when dense matches are uninformative, retain the practical
        # source and its explicitly linked lean-protein qualification.
        system.store.replace_index(chunks, {'mode': 'hybrid'}, [[1, 0, 0] for _ in chunks])
        options['query_vector'] = [1, 0, 0]
    hits = Retriever(system.store).search(question, **options)
    practical = [h.chunk for h in hits if h.chunk.source_id == 'singhealth-noodle-choices']
    assert practical and 'Ask for less noodles and more vegetables.' in practical[0].text
    assert 'oily soup' in practical[0].text
    assert any(h.chunk.source_id == 'endocrine-diet' and 'đạm “nạc”' in h.chunk.section for h in hits)
    assert all(not any(loc.startswith('t') for loc in h.chunk.locators) for h in hits)


@pytest.mark.parametrize('question', [
    'Sáng ăn bánh mì có cần bỏ không?',
    '100g phở có bao nhiêu calo?',
    'Ăn phở hay bún làm đường huyết tăng nhanh hơn?',
    'GI của phở khi ăn sáng là bao nhiêu?',
    'Bảng thực đơn bữa sáng phở thịt bò của Viện Dinh dưỡng',
])
def test_practical_noodle_rule_does_not_replace_other_questions(question):
    assert not is_noodle_meal_advice(question)


def test_named_source_is_not_overridden_by_noodle_companion(system):
    hits = Retriever(system.store).search('Theo Bộ Y tế, nên ăn phở như thế nào?', mode='lexical')
    assert hits and all(h.chunk.source_id == 'byt5481-nutrition' for h in hits)


def test_sliced_meat_does_not_prove_lean_meat_even_if_reviewer_accepts():
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(
        text='Chọn thịt nạc khi ăn phở.', citation_ids=['C1'])], uncertainty='')
    review = GroundingReview.model_validate({'accepted_blocks': [
        {'block_index': 0, 'evidence': [{'citation_id': 'C1', 'line_ids': [0]}]}]})
    sources = [{'id': 'C1', 'language': 'en', 'text': 'Choose sliced meat instead of minced meat.'}]
    rejected = apply_grounding_review(answer, review, sources, 'Ăn phở nên chọn thế nào?')
    assert not rejected.supported and rejected._grounding_review['server_rejections']
    sources[0]['text'] = 'Choose lean meat.'
    assert apply_grounding_review(answer, review, sources, 'Ăn phở nên chọn thế nào?').supported
