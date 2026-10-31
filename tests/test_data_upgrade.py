import json

import pytest

from rag_app.config import Settings
from rag_app.domain import AnswerBlock, GeneratedAnswer
from rag_app.ingestion import corpus_fingerprint
from rag_app.provider import (
    GroundingReview,
    OpenAIProvider,
    ProviderFailure,
    apply_grounding_review,
)
from rag_app.retrieval import Retriever


def test_manifest_or_chunking_changes_require_reindex(tmp_path):
    original = Settings(_env_file=None)
    manifest = json.loads(original.source_manifest.read_text(encoding='utf-8'))
    path = tmp_path / 'sources.json'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    cfg = original.model_copy(update={'source_manifest': path})
    fingerprint = corpus_fingerprint(cfg)
    assert corpus_fingerprint(cfg.model_copy(update={'chunk_overlap': 30})) != fingerprint
    manifest['sources'][0]['segments'][0]['section'] += ' revised'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    assert corpus_fingerprint(cfg) != fingerprint
    manifest['sources'][0]['filename'] = 'missing-approved-document.pdf'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='Thiếu file nguồn'):
        corpus_fingerprint(cfg)


def test_embedding_provider_never_silently_falls_back_when_key_missing():
    from types import SimpleNamespace
    cfg = Settings(_env_file=None, embedding_mode='gemini', gemini_api_key='')
    provider = OpenAIProvider(cfg, client=SimpleNamespace())
    with pytest.raises(ProviderFailure, match='GEMINI_API_KEY'):
        provider.embed(['hello'])
    provider.close()


def test_gemini_can_use_explicit_openai_embedding_without_model_rewrite(monkeypatch):
    import rag_app.gemini_provider as module
    from rag_app.gemini_provider import GeminiProvider
    calls = []
    class Embedder:
        def __init__(self, cfg):
            assert cfg.embedding_mode == 'openai'
            assert cfg.embedding_model == 'text-embedding-3-small'
        def embed(self, texts):
            calls.append(texts)
            return [[1, 0]]
        def close(self):
            calls.append('closed')
    monkeypatch.setattr(module, 'OpenAIProvider', Embedder)
    cfg = Settings(_env_file=None, gemini_api_key='test-only', embedding_mode='openai')
    provider = GeminiProvider(cfg)
    assert provider.embed_documents(['text']) == [[1, 0]]
    provider.close()
    assert calls == [['text'], 'closed']


def test_repeated_query_reuses_vector_but_calls_generation_again(system, corpus):
    system.store.replace_index(corpus, {'mode': 'hybrid', 'embedding_identity': system.cfg.embedding_identity},
                               [[1, 0.5, 0.1] for _ in corpus])
    for _ in range(2):
        result = system.client.post('/api/chat', json={'message': 'Ăn trái cây thế nào?'}).json()
        assert result['status'] == 'answered'
    assert len(system.provider.embed_calls) == 1
    assert len(system.provider.generate_calls) == 2
    assert result['timings_ms']['embedding_cache_hit'] == 1
    service = system.app.state.service
    service._query_vectors.clear()
    system.client.post('/api/chat', json={'message': 'Ăn trái cây thế nào?'})
    assert len(system.provider.embed_calls) == 2


def test_english_evidence_accepts_reviewed_translation_but_not_unreviewed_claims():
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(
        text='Chọn rau như bắp cải và bông cải xanh.', citation_ids=['C1'])], uncertainty='')
    excerpts = [{'id': 'C1', 'language': 'en', 'text': 'Choose vegetables such as cabbage and broccoli.'}]
    review = GroundingReview.model_validate({'accepted_blocks': [
        {'block_index': 0, 'evidence': [{'citation_id': 'C1', 'line_ids': [0]}]}]})
    assert apply_grounding_review(answer, review, excerpts).supported
    assert not apply_grounding_review(answer, GroundingReview(accepted_blocks=[]), excerpts).supported


def test_general_sugar_free_advice_cannot_assert_calories_in_every_zero_drink():
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(
        text='Không uống thoải mái vì nước ngọt zero sugar vẫn chứa calo.', citation_ids=['C1'])], uncertainty='')
    excerpts = [{'id': 'C1', 'language': 'en', 'text': 'Foods that are sugar-free are not calorie-free. Moderation is key.'}]
    review = GroundingReview.model_validate({'accepted_blocks': [
        {'block_index': 0, 'evidence': [{'citation_id': 'C1', 'line_ids': [0]}]}]})
    assert not apply_grounding_review(answer, review, excerpts, 'Nước ngọt zero sugar uống thoải mái được không?').supported
    answer.blocks[0].text = 'Các sản phẩm có chất thay thế đường cần dùng vừa phải.'
    assert apply_grounding_review(answer, review, excerpts, 'Nước ngọt zero sugar uống thoải mái được không?').supported
    answer.blocks[0].text = 'Không nên uống thoải mái vì không đường không đồng nghĩa không calo và có thể gây tăng cân.'
    assert not apply_grounding_review(answer, review, excerpts, 'Nước ngọt zero sugar uống thoải mái được không?').supported
    answer.blocks[0].text = 'Sản phẩm không đường không có nghĩa không có calo và vẫn có thể gây tăng cân, do đó cần sử dụng vừa phải.'
    assert not apply_grounding_review(answer, review, excerpts, 'Nước ngọt zero sugar uống thoải mái được không?').supported


def test_carb_counting_question_needs_decision_not_just_food_definition():
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(
        text='Sữa chua có carbohydrate.', citation_ids=['C1'])], uncertainty='')
    excerpts = [{'id': 'C1', 'language': 'en', 'text': 'Yogurt contains carbohydrate. Count total carbohydrate if counting carbs.'}]
    review = GroundingReview.model_validate({'accepted_blocks': [
        {'block_index': 0, 'evidence': [{'citation_id': 'C1', 'line_ids': [0]}]}]})
    result = apply_grounding_review(answer, review, excerpts, 'Sữa chua không đường có cần tính carb không?')
    assert result._grounding_review['server_rejections']
    answer.blocks[0].text = 'Nếu đang đếm carb thì cần tính cả carbohydrate trong sữa chua.'
    result = apply_grounding_review(answer, review, excerpts, 'Sữa chua không đường có cần tính carb không?')
    assert result.supported and not result._grounding_review['server_rejections']


def test_unlimited_eating_question_cannot_be_satisfied_by_label_definition_alone():
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(
        text='Không thêm đường nghĩa là không bổ sung đường khi chế biến.', citation_ids=['C1'])], uncertainty='')
    excerpts = [{'id': 'C1', 'language': 'en', 'text': 'No extra sugar was added during processing.'}]
    review = GroundingReview.model_validate({'accepted_blocks': [
        {'block_index': 0, 'evidence': [{'citation_id': 'C1', 'line_ids': [0]}]}]})
    definition = apply_grounding_review(answer, review, excerpts, 'Không thêm đường nghĩa là gì?')
    assert definition.supported and not definition._grounding_review['server_rejections']
    decision = apply_grounding_review(answer, review, excerpts, 'Bánh ghi không thêm đường thì ăn thoải mái được không?')
    assert decision._grounding_review['server_rejections']
    answer.blocks[0].text = 'Không nên ăn không giới hạn sản phẩm gắn nhãn không thêm đường.'
    terse = apply_grounding_review(answer, review, excerpts, 'Bánh ghi không thêm đường thì ăn thoải mái được không?')
    assert terse._grounding_review['server_rejections']


def test_unlimited_zero_drink_question_needs_amount_decision_not_only_drink_type():
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(
        text='Nước giải khát có ga chỉ nên dùng loại không hoặc ít đường.', citation_ids=['C1'])], uncertainty='')
    excerpts = [{'id': 'C1', 'text': 'Nước giải khát có ga chỉ nên dùng loại không hoặc ít đường.'}]
    review = GroundingReview.model_validate({'accepted_blocks': [
        {'block_index': 0, 'evidence': [{'citation_id': 'C1', 'line_ids': [0]}]}]})
    choice = apply_grounding_review(answer, review, excerpts, 'Nên chọn loại nước giải khát nào?')
    assert choice.supported and not choice._grounding_review['server_rejections']
    amount = apply_grounding_review(answer, review, excerpts, 'Nước ngọt zero sugar thì ngày uống mấy lon cũng được hả?')
    assert amount._grounding_review['server_rejections']
    answer.blocks[0].text = 'Không nên uống không giới hạn vì chỉ nên chọn loại không hoặc ít đường.'
    scope = apply_grounding_review(answer, review, excerpts, 'Nước ngọt zero sugar thì ngày uống mấy lon cũng được hả?')
    assert not scope.supported and scope._grounding_review['server_rejections']


@pytest.mark.parametrize(('query', 'expected'), [
    ('Bánh không thêm đường nghĩa là gì?', 'ada-sweeteners'),
    ('Đọc nhãn thế nào để biết một hộp có mấy khẩu phần?', 'ada-labels'),
    ('Polyol có phải rượu không?', 'ada-sweeteners'),
    ('Nêm món ăn bớt muối thế nào?', 'ada-cooking'),
])
def test_new_topics_retrieve_actual_approved_sources(system, query, expected):
    hits = Retriever(system.store).search(query)
    assert expected in {h.chunk.source_id for h in hits}


def test_new_pdf_evidence_preserves_page_language_and_scope(corpus):
    new = [c for c in corpus if c.source_id in {'ada-labels', 'ada-sweeteners', 'ada-food-groups', 'ada-cooking'}]
    assert len(new) == 14
    assert all(c.language == 'en' and c.pages and c.document_format == 'pdf' for c in new)
    # Excluded graphics/generalizations must not become retrieval evidence.
    assert all('DOESN\'T RAISE BLOOD GLUCOSE' not in c.text for c in new)
    assert all('Frying creates trans fats' not in c.text for c in new)


def test_no_added_sugar_keeps_definition_and_total_carb_evidence_together(system):
    hits = Retriever(system.store).search('Bánh ghi không thêm đường thì tôi ăn thoải mái được đúng không?')
    texts = [h.chunk.text for h in hits if h.chunk.source_id == 'ada-sweeteners']
    assert any('No extra sugar' in text for text in texts)
    assert any(h.chunk.source_id == 'ada-labels' and 'Total Carbs' in h.chunk.text for h in hits)
    assert len(hits) <= 5


def test_label_carb_question_keeps_food_and_label_evidence_without_insulin_overview(system):
    retriever = Retriever(system.store)
    hits = retriever.search('Sữa chua không đường có cần tính carb không?')
    assert any(h.chunk.source_id == 'ada-food-groups' and 'Dairy' in h.chunk.text for h in hits)
    assert any(h.chunk.source_id == 'ada-labels' and 'Total Carbs' in h.chunk.text for h in hits)
    assert not any('Đếm lượng carbohydrate' in h.chunk.section and 'insulin' in h.chunk.text for h in hits)
    # General questions about starting carb counting still need this evidence.
    general = retriever.search('Đếm lượng carbohydrate khi dùng insulin là gì?')
    assert any('Đếm lượng carbohydrate' in h.chunk.section and 'insulin' in h.chunk.text for h in general)
