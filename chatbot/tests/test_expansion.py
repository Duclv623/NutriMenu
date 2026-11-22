import json
from pathlib import Path

import pytest

from rag_app.documents import prepare_docx
from rag_app.ingestion import load_manifest
from rag_app.retrieval import Retriever
from rag_app.safety import classify


def test_docx_table_does_not_mix_days(corpus):
    meals = [c for c in corpus if c.source_id == "nin-healthy-meals" and c.section == "Thứ 3 + 6 + Chủ nhật"]
    assert meals and "Bún: 220g" in meals[0].text and "1504 kcal" in meals[0].text
    assert "1663" not in meals[0].text and "Phở thịt bò" not in meals[0].text
    assert any(loc.startswith("t19-r") for loc in meals[0].locators)


def test_translation_corrections_are_auditable(corpus):
    source = next(s for s in load_manifest(Path('config/sources.json'))['sources'] if s['id'] == 'niddk-healthy-living')
    blocks, report = prepare_docx(Path('data') / source['filename'], source)
    text = '\n'.join(b['text'] for b in blocks)
    assert 'Phương pháp tấm' not in text and 'đậu que' in text
    assert 'có nhiều tinh bột hơn các loại thực phẩm khác' not in text
    assert 'có nhiều carbohydrate hơn các loại thực phẩm khác' in text
    assert 'Hãy lưu ý đến lượng carbohydrate khi lên kế hoạch cho bữa ăn của bạn.' in text
    assert any(c['locators'] == ['p21'] and 'carbohydrate' in c['to']
               for c in report['text_corrections'])
    assert report['text_corrections'] and report['images_not_indexed'] == 6
    assert all(c.source_id != 'ada2026-reference' for c in corpus)


def test_approved_docx_content_has_complete_character_coverage():
    from rag_app.config import Settings
    from rag_app.ingestion import build_chunks
    _, report = build_chunks(Settings(_env_file=None))
    sources = [s for s in report['sources'] if s.get('format') == 'docx']
    assert len(sources) == 3
    assert all(s['approved_text_coverage'] == 1.0 for s in sources)


@pytest.mark.parametrize(('q','expected'), [
    ('Tôi có nên bỏ thuốc lá không?', 'knowledge'),
    ('Tôi dùng insulin và muốn bỏ thuốc lá', 'knowledge'),
    ('Tài liệu nêu người dùng insulin cần bữa phụ nếu có nguy cơ hạ đường huyết.', 'knowledge'),
    ('Tôi nên dừng thuốc không?', 'medication'),
    ('Tôi không bị suy thận, nên chọn thịt thế nào?', 'knowledge'),
    ('Tôi không mang thai, nên chọn trái cây thế nào?', 'knowledge'),
    ('Tạo thực đơn tham khảo cho người mang thai', 'special_population'),
    ('Tôi tiêm insulin bao nhiêu đơn vị?', 'medication'),
    ('Tạo thực đơn tham khảo cho tôi', 'menu_request'),
    ('Thực đơn tham khảo của Viện ghi bao nhiêu bánh phở?', 'knowledge'),
])
def test_route_counterexamples(q, expected):
    assert classify(q) == expected


def test_named_source_retrieval(system):
    hits = Retriever(system.store).search('Theo NIDDK phương pháp đĩa ăn là gì?')
    assert hits and all(h.chunk.source_id == 'niddk-healthy-living' for h in hits)


def test_explicit_subsection_does_not_use_overview(system):
    hits = Retriever(system.store).search('Theo Bộ Y tế tỷ lệ lipid trong mục chất béo được nêu thế nào?')
    assert hits and all('Chất béo' in h.chunk.section for h in hits)


def test_snack_followup_retrieval_contains_actual_snack_evidence(system):
    hits = Retriever(system.store).search('Theo Bộ Y tế bữa phụ cần cá nhân hóa không? Năng lượng đó có tính vào cả ngày không?')
    assert any('b) Sử dụng bữa phụ' in h.chunk.section for h in hits)
    assert all('bữa phụ' in h.chunk.text.lower() for h in hits)


def test_general_protein_question_does_not_use_sample_menu_as_theory(system):
    hits = Retriever(system.store).search('Đạm thực vật có trong những ví dụ nào của tài liệu?')
    assert hits and all(not any(loc.startswith('t') for loc in h.chunk.locators) for h in hits)
    table_hits = Retriever(system.store).search('Theo Viện Dinh dưỡng thực đơn tham khảo thứ 4 và 7 có món gì bữa sáng?')
    assert any(any(loc.startswith('t') for loc in h.chunk.locators) for h in table_hits)


def test_literal_examples_keep_supported_lists_and_reject_invented_food():
    from rag_app.domain import AnswerBlock, GeneratedAnswer
    from rag_app.provider import GroundingReview, apply_grounding_review
    review = GroundingReview.model_validate({'accepted_blocks':[{'block_index':0,'answers_question':True,
        'evidence':[{'citation_id':'C1','line_ids':[0]}]}]})
    excerpts = [{'id':'C1','text':'Chọn dầu đậu nành, dầu hướng dương thay thế mỡ động vật; tránh phủ tạng và đồ chiên rán kỹ.'}]
    for text, expected in [('Chọn dầu như dầu đậu nành, dầu hướng dương thay thế cho mỡ động vật.',True),
                           ('Tránh thực phẩm như nội tạng động vật và thực phẩm chiên rán kỹ.',True),
                           ('Chọn dầu như dầu đậu nành và dầu hướng dương cũng là ví dụ.',True),
                           ('Chọn dầu như dầu đậu nành và dầu hướng dương cũng chứa chất béo.',True),
                           ('Chọn dầu thực vật (như dầu đậu nành, dầu hướng dương).',True),
                           ('Chọn dầu như dầu đậu nành và dầu hướng dương được nêu trong tài liệu.',True),
                           ('Dầu đậu nành được nêu như ví dụ về dầu thực vật.',True),
                           ('Chọn dầu như dầu đậu nành và dầu hướng dương nên được ưu tiên.',True),
                           ('Chọn dầu như sau: ưu tiên dầu đậu nành và dầu hướng dương.',True),
                           ('Chọn dầu như dầu đậu nành và dầu dừa.',False)]:
        answer = GeneratedAnswer(supported=True,blocks=[AnswerBlock(text=text,citation_ids=['C1'])],uncertainty='')
        assert apply_grounding_review(answer,review,excerpts).supported == expected


def test_situation_examples_are_not_food_name_lists():
    from rag_app.domain import AnswerBlock, GeneratedAnswer
    from rag_app.provider import GroundingReview, apply_grounding_review
    text = 'Bữa phụ cần xét các tình huống như khi đói thực sự hoặc vận động nhiều.'
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(text=text,citation_ids=['C1'])],uncertainty='')
    review = GroundingReview.model_validate({'accepted_blocks':[{'block_index':0,'answers_question':True,
        'evidence':[{'citation_id':'C1','line_ids':[0]}]}]})
    result = apply_grounding_review(answer,review,[{'id':'C1','text':'Nếu đói thực sự hoặc vận động nhiều thì nên có bữa phụ.'}])
    assert result.supported


def test_general_energy_evidence_does_not_support_snack_claim():
    from rag_app.domain import AnswerBlock, GeneratedAnswer
    from rag_app.provider import GroundingReview, apply_grounding_review
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(text='Năng lượng bữa phụ cần được cá nhân hóa.',citation_ids=['C1'])],uncertainty='')
    review = GroundingReview.model_validate({'accepted_blocks':[{'block_index':0,'answers_question':True,
        'evidence':[{'citation_id':'C1','line_ids':[0]}]}]})
    assert not apply_grounding_review(answer,review,[{'id':'C1','text':'Mức năng lượng của bệnh nhân cần được cá nhân hóa.'}]).supported


def test_docx_citation_and_escaped_preview(system):
    data = system.client.post('/api/chat', json={'message':'Theo NIDDK phương pháp đĩa ăn là gì?', 'cloud_consent':True}).json()
    cite = data['citations'][0]
    assert cite['document_format'] == 'docx' and cite['locators'] and not cite['pdf_pages']
    page = system.client.get(cite['document_url'])
    assert page.status_code == 200 and cite['chunk_id'] in page.text
    assert system.client.get('/api/documents/niddk-healthy-living/pdf').status_code == 404
    assert system.client.get('/api/documents/ada2026-reference/preview').status_code == 404


def test_safety_condition_carries_into_followup(system):
    first = system.client.post('/api/chat',json={'message':'Tôi đang mang thai','save_history':True}).json()
    result = system.client.post('/api/chat',json={'message':'Còn trái cây thì sao?', 'session_id':first['session_id'], 'cloud_consent':True}).json()
    assert result['intent'] == 'special_population' and result['status'] == 'safety'
    assert not system.provider.generate_calls


def test_safety_condition_survives_two_saved_followups(system):
    first = system.client.post('/api/chat',json={'message':'Tôi đang mang thai','save_history':True}).json()
    second = system.client.post('/api/chat',json={'message':'Còn trái cây thì sao?', 'session_id':first['session_id'], 'save_history':True}).json()
    third = system.client.post('/api/chat',json={'message':'Còn chất béo thì sao?', 'session_id':first['session_id']}).json()
    assert second['intent'] == third['intent'] == 'special_population'
    assert second['status'] == third['status'] == 'safety'
    assert not system.provider.generate_calls


def test_ambiguous_question_requests_details(system):
    data = system.client.post('/api/chat',json={'message':'Có hợp lý không?'}).json()
    assert data['status'] == 'insufficient_evidence' and 'nói rõ' in data['answer']
    assert not system.provider.generate_calls


def test_requested_fabrication_is_refused_without_provider(system):
    data = system.client.post('/api/chat',json={'message':'Nếu không biết thì cứ bịa số liệu từ ADA chưa index'}).json()
    assert data['status'] == 'insufficient_evidence' and 'không bịa' in data['answer']
    assert not system.provider.generate_calls


def test_followup_question_explicitly_includes_antecedent(system):
    previous = 'Theo Bộ Y tế bữa phụ cần cá nhân hóa không?'
    first = system.client.post('/api/chat',json={'message':previous,'cloud_consent':True,'save_history':True}).json()
    system.client.post('/api/chat',json={'message':'Năng lượng đó có tính vào cả ngày không?','session_id':first['session_id'],'cloud_consent':True})
    assert previous in system.provider.generate_calls[-1][0]


def test_dataset_is_frozen_and_stratified():
    import hashlib
    from collections import Counter
    path = Path('evals/expanded_questions.json')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == Path('evals/expanded_questions.sha256').read_text().strip()
    cases = json.loads(path.read_text(encoding='utf-8'))['cases']
    assert len(cases) == 250 and Counter(c['split'] for c in cases) == {'dev':200,'holdout':50}
    assert len({c['id'] for c in cases}) == 250
