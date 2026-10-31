import json
from types import SimpleNamespace

import pytest

from rag_app.config import Settings
from rag_app.domain import AnswerBlock, GeneratedAnswer
from rag_app.provider import (
    EvidenceSpan,
    GroundingReview,
    OpenAIProvider,
    ProviderFailure,
    ReviewedBlock,
    apply_grounding_review,
)
from rag_app.retrieval import Retriever


class FakeEndpoint:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class SequenceEndpoint:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


def test_empty_meal_draft_retries_partial_principles_and_reviews_them(system):
    hits = Retriever(system.store).search('phương pháp đĩa ăn')[:1]
    empty = GeneratedAnswer(supported=False, blocks=[], uncertainty='Chưa có riêng món phở.')
    partial = GeneratedAnswer(supported=True, blocks=[AnswerBlock(
        text='Áp dụng phương pháp đĩa ăn.', citation_ids=['C1'])], uncertainty='Chưa có khẩu phần phở cá nhân.')
    review = GroundingReview(accepted_blocks=[ReviewedBlock(block_index=0,
        evidence=[EvidenceSpan(citation_id='C1', line_ids=[0])])])
    endpoint = SequenceEndpoint([SimpleNamespace(id=f'meal_{i}', status='completed',
        output_parsed=value, usage=SimpleNamespace(input_tokens=10, output_tokens=5))
        for i, value in enumerate([empty, partial, review])])
    provider = OpenAIProvider(system.cfg, client=SimpleNamespace(responses=SimpleNamespace(parse=endpoint)))
    answer, usage = provider.generate('Tôi ăn phở buổi sáng được không?', hits, [])
    assert answer.supported and len(endpoint.calls) == 3
    assert answer._provider_response_ids == ['meal_0', 'meal_1', 'meal_2']
    assert usage == {'input_tokens': 30, 'output_tokens': 15}
    assert 'revision_feedback' in json.loads(endpoint.calls[1]['input'][1]['content'])


def test_responses_schema_store_false_redaction(system):
    hits = Retriever(system.store).search("trái cây")
    endpoint = SequenceEndpoint([
        SimpleNamespace(
            id="resp_generation_test",
            status="completed",
            output_parsed=GeneratedAnswer(
                supported=True,
                blocks=[AnswerBlock(text="Test", citation_ids=["C1"])],
                uncertainty="",
            ),
            usage=SimpleNamespace(input_tokens=10, output_tokens=20),
        ),
        SimpleNamespace(
            id="resp_review_test", status="completed",
            output_parsed=GroundingReview(accepted_blocks=[ReviewedBlock(
                block_index=0, evidence=[EvidenceSpan(citation_id="C1", line_ids=[0])]
            )]),
            usage=SimpleNamespace(input_tokens=30, output_tokens=40),
        ),
    ])
    client = SimpleNamespace(responses=SimpleNamespace(parse=endpoint))
    provider = OpenAIProvider(system.cfg, client=client)
    answer, usage = provider.generate(
        "me@example.com hỏi trái cây", hits, []
    )
    assert answer.supported and usage == {"input_tokens": 40, "output_tokens": 60}
    assert all(call["store"] is False for call in endpoint.calls)
    assert endpoint.calls[0]["text_format"] is GeneratedAnswer
    assert "me@example.com" not in endpoint.calls[0]["input"][1]["content"]
    assert answer._provider_response_ids == ["resp_generation_test", "resp_review_test"]
    assert answer._provider_model == system.cfg.openai_model
    review_input = json.loads(endpoint.calls[1]["input"][1]["content"])
    # A second unnumbered copy caused real DOCX line-ID mistakes.
    assert all('text' not in source and source['evidence_lines'] for source in review_input['SOURCE_EXCERPTS'])


def test_food_clarification_is_reviewed_before_acceptance(system):
    from rag_app.food_data import FoodItem, FoodPlan, food_hits, get_catalog
    hits=food_hits(get_catalog().execute(FoodPlan(operation='lookup',items=[FoodItem(name='thịt bò',amount=100)])))
    draft=GeneratedAnswer(supported=False,blocks=[AnswerBlock(text='Cần chọn rõ loại thịt bò.',citation_ids=['C1'])],uncertainty='')
    endpoint=SequenceEndpoint([
        SimpleNamespace(id='test_food_draft',status='completed',output_parsed=draft,
            usage=SimpleNamespace(input_tokens=10,output_tokens=20)),
        SimpleNamespace(id='test_food_review',status='completed',output_parsed=GroundingReview(
            accepted_blocks=[ReviewedBlock(block_index=0,evidence=[EvidenceSpan(citation_id='C1',line_ids=[0])])]),
            usage=SimpleNamespace(input_tokens=30,output_tokens=40))])
    provider=OpenAIProvider(system.cfg,client=SimpleNamespace(responses=SimpleNamespace(parse=endpoint)))
    answer,usage=provider.generate_food('100g thịt bò có bao nhiêu calo?',hits,[])
    assert answer.supported and answer.blocks and len(endpoint.calls)==2
    assert answer._provider_response_ids==['test_food_draft','test_food_review']
    assert usage=={'input_tokens':40,'output_tokens':60}
    assert answer._grounding_review['accepted_block_count']==1


def test_partial_knowledge_is_reviewed_even_if_draft_says_unsupported(system):
    hits = Retriever(system.store).search('trái cây')[:1]
    hits[0] = hits[0].model_copy(update={'chunk': hits[0].chunk.model_copy(update={
        'text': 'Ăn trái cây nguyên miếng.'})})
    draft = GeneratedAnswer(supported=False, blocks=[AnswerBlock(
        text='Ăn trái cây nguyên miếng.', citation_ids=['C1'])], uncertainty='Chưa có thông tin riêng về mít.')
    review = GroundingReview(accepted_blocks=[ReviewedBlock(
        block_index=0, evidence=[EvidenceSpan(citation_id='C1', line_ids=[0])])])
    endpoint = SequenceEndpoint([SimpleNamespace(id=f'partial_{i}', status='completed', output_parsed=value,
        usage=SimpleNamespace(input_tokens=10, output_tokens=20)) for i, value in enumerate([draft, review])])
    provider = OpenAIProvider(system.cfg, client=SimpleNamespace(responses=SimpleNamespace(parse=endpoint)))
    answer, _ = provider.generate('Ăn trái cây như mít được không?', hits, [])
    assert answer.supported and answer.blocks and len(endpoint.calls) == 2
    assert answer.uncertainty == 'Chưa có thông tin riêng về mít.'


def test_failed_revision_retains_previously_verified_partial_answer(system):
    hits = Retriever(system.store).search('trái cây')[:1]
    hits[0] = hits[0].model_copy(update={'chunk': hits[0].chunk.model_copy(update={
        'text': 'Ăn trái cây nguyên miếng. Hạn chế nước ép.'})})
    draft = GeneratedAnswer(supported=True, blocks=[AnswerBlock(
        text='Ăn trái cây nguyên miếng.', citation_ids=['C1'])], uncertainty='')
    review = GroundingReview(accepted_blocks=[ReviewedBlock(block_index=0,
        evidence=[EvidenceSpan(citation_id='C1', line_ids=[0])])], needs_revision=True,
        revision_reason='Thiếu ý hạn chế nước ép ở C1/0.')
    failed = GeneratedAnswer(supported=False, blocks=[], uncertainty='')
    endpoint = SequenceEndpoint([SimpleNamespace(id=f'partial_{i}', status='completed', output_parsed=value,
        usage=SimpleNamespace(input_tokens=10, output_tokens=20)) for i, value in enumerate([draft, review, failed])])
    provider = OpenAIProvider(system.cfg, client=SimpleNamespace(responses=SimpleNamespace(parse=endpoint)))
    answer, usage = provider.generate('Nên chọn trái cây và nước ép thế nào?', hits, [])
    assert answer.supported and answer.blocks[0].text == 'Ăn trái cây nguyên miếng.'
    assert answer.uncertainty and len(endpoint.calls) == 3
    assert usage == {'input_tokens': 30, 'output_tokens': 60}


def test_server_rejection_repairs_missing_fruit_even_when_reviewer_says_complete(system):
    hits = Retriever(system.store).search('trái cây')[:1]
    hits[0] = hits[0].model_copy(update={'chunk': hits[0].chunk.model_copy(update={
        'text': '+ Hạn chế xoài, mít.\n+ Ăn chuối vừa phải.'})})
    draft = GeneratedAnswer(supported=True, blocks=[
        AnswerBlock(text='Hạn chế trái cây như xoài, mít và chuối.', citation_ids=['C1']),
        AnswerBlock(text='Ăn chuối vừa phải.', citation_ids=['C1'])], uncertainty='')
    fixed = GeneratedAnswer(supported=True, blocks=[
        AnswerBlock(text='Hạn chế xoài và mít.', citation_ids=['C1']),
        AnswerBlock(text='Ăn chuối vừa phải.', citation_ids=['C1'])], uncertainty='')
    review = GroundingReview(accepted_blocks=[ReviewedBlock(block_index=i,
        evidence=[EvidenceSpan(citation_id='C1', line_ids=[i])]) for i in range(2)])
    endpoint = SequenceEndpoint([SimpleNamespace(id=f'repair_{i}', status='completed', output_parsed=value,
        usage=SimpleNamespace(input_tokens=10, output_tokens=20))
        for i, value in enumerate([draft, review, fixed, review])])
    provider = OpenAIProvider(system.cfg, client=SimpleNamespace(responses=SimpleNamespace(parse=endpoint)))
    answer, _ = provider.generate('Xoài mít chuối có ăn được không?', hits, [])
    assert len(endpoint.calls) == 4 and len(answer.blocks) == 2
    feedback = json.loads(endpoint.calls[2]['input'][1]['content'])['revision_feedback']
    assert 'chuối' in feedback['reason']
    assert answer._grounding_review['attempts'][0]['server_rejections']


def test_grounding_review_drops_unsupported_blocks_and_checks_literal_evidence():
    answer = GeneratedAnswer(supported=True, uncertainty="", blocks=[
        AnswerBlock(text="Không dùng lại dầu chiên.", citation_ids=["C2"]),
        AnswerBlock(text="Nhiệt làm biến đổi cấu trúc lipid.", citation_ids=["C1"]),
        AnswerBlock(text="Một ý không có nguồn.", citation_ids=["C1"]),
    ])
    review = GroundingReview(accepted_blocks=[
        ReviewedBlock(block_index=0, evidence=[EvidenceSpan(citation_id="C1", line_ids=[0])]),
        ReviewedBlock(block_index=1, evidence=[EvidenceSpan(citation_id="C1", line_ids=[99])]),
        ReviewedBlock(block_index=2, evidence=[EvidenceSpan(citation_id="C999", line_ids=[0])]),
        ReviewedBlock(block_index=99, evidence=[EvidenceSpan(citation_id="C1", line_ids=[0])]),
    ])
    result = apply_grounding_review(answer, review, [{"id": "C1", "text": "Không dùng lại dầu chiên."}])
    assert result.supported and len(result.blocks) == 1
    assert result.blocks[0].citation_ids == ["C1"]
    rejected = apply_grounding_review(answer, GroundingReview(accepted_blocks=[]), [])
    assert not rejected.supported and not rejected.blocks
    wrapped = apply_grounding_review(answer, review, [{"id": "C1", "text": "Không dùng lại\ndầu chiên."}])
    assert len(wrapped.blocks) == 1
    off_topic = GroundingReview(accepted_blocks=[ReviewedBlock(
        block_index=0, answers_question=False,
        evidence=[EvidenceSpan(citation_id="C1", line_ids=[0])],
    )])
    assert not apply_grounding_review(answer, off_topic, [{"id": "C1", "text": "Không dùng lại dầu chiên."}]).supported


def test_grounding_rejects_examples_missing_from_selected_lines():
    answer = GeneratedAnswer(supported=True, uncertainty="", blocks=[
        AnswerBlock(text="Không dùng thực phẩm tăng đường huyết nhanh trong bữa phụ như bánh kẹo.", citation_ids=["C1"]),
    ])
    review = GroundingReview(accepted_blocks=[ReviewedBlock(
        block_index=0, evidence=[EvidenceSpan(citation_id="C1", line_ids=[0])],
    )])
    excerpts = [{"id": "C1", "text": "Không dùng thực phẩm tăng đường huyết nhanh trong bữa phụ như bánh mỳ, khoai nướng."}]
    assert not apply_grounding_review(answer, review, excerpts).supported
    answer.blocks[0].text = "Không dùng thực phẩm tăng đường huyết nhanh trong bữa phụ như bánh mì."
    assert apply_grounding_review(answer, review, excerpts).supported
    answer.blocks[0].text = "Nên dùng ngũ cốc nguyên hạt như gạo lứt trong bữa ăn."
    excerpts[0]["text"] = "+ Nên dùng ngũ cốc nguyên hạt\nnhư gạo lứt/gạo lật trong bữa ăn."
    assert apply_grounding_review(answer, review, excerpts).supported


def test_grounding_api_failure_does_not_return_unverified_answer(system):
    endpoint = SequenceEndpoint([
        SimpleNamespace(status="completed", output_parsed=GeneratedAnswer(
            supported=True, blocks=[AnswerBlock(text="Có nguồn", citation_ids=["C1"])], uncertainty=""
        ), usage=SimpleNamespace(input_tokens=10, output_tokens=20)),
        RuntimeError("sensitive upstream text"),
    ])
    provider = OpenAIProvider(system.cfg, client=SimpleNamespace(responses=SimpleNamespace(parse=endpoint)))
    with pytest.raises(ProviderFailure) as exc:
        provider.generate("trái cây", Retriever(system.store).search("trái cây"), [])
    assert "sensitive" not in str(exc.value)


@pytest.mark.parametrize('still_missing', [False, True])
def test_one_revision_is_checked_bounded_and_all_usage_is_reported(system, still_missing):
    hits = Retriever(system.store).search('trái cây')[:1]
    hits[0] = hits[0].model_copy(update={'chunk':hits[0].chunk.model_copy(update={
        'text':'Ăn trái cây nguyên miếng. Hạn chế nước ép.'})})
    draft = GeneratedAnswer(supported=True,blocks=[AnswerBlock(text='Ăn trái cây nguyên miếng.',citation_ids=['C1'])],uncertainty='')
    fixed = GeneratedAnswer(supported=True,blocks=[AnswerBlock(text='Ăn trái cây nguyên miếng; hạn chế nước ép.',citation_ids=['C1'])],uncertainty='')
    evidence = [ReviewedBlock(block_index=0,evidence=[EvidenceSpan(citation_id='C1',line_ids=[0])])]
    outputs = [draft, GroundingReview(accepted_blocks=evidence,needs_revision=True,revision_reason='Thiếu ý hạn chế nước ép ở C1/0.'),
        fixed, GroundingReview(accepted_blocks=evidence,needs_revision=still_missing,revision_reason='Cần xem thêm ý.')]
    endpoint = SequenceEndpoint([SimpleNamespace(id=f'resp_test_{i}',status='completed',output_parsed=value,
        usage=SimpleNamespace(input_tokens=10,output_tokens=20)) for i,value in enumerate(outputs)])
    provider = OpenAIProvider(system.cfg,client=SimpleNamespace(responses=SimpleNamespace(parse=endpoint)))
    answer, usage = provider.generate('Nên chọn trái cây và nước ép thế nào?',hits,[])
    assert answer.supported and 'hạn chế nước ép' in answer.blocks[0].text.lower()
    assert len(endpoint.calls) == len(answer._provider_response_ids) == 4
    assert usage == {'input_tokens':40,'output_tokens':80}
    assert 'revision_feedback' in json.loads(endpoint.calls[2]['input'][1]['content'])
    assert len(answer._grounding_review['attempts']) == 2
    assert bool(answer.uncertainty) == still_missing


@pytest.mark.parametrize(
    "upstream",
    [
        RuntimeError("secret upstream text"),
        SimpleNamespace(status="incomplete", output_parsed=None),
    ],
)
def test_provider_safe_failures(system, upstream):
    provider = OpenAIProvider(
        system.cfg, client=SimpleNamespace(responses=SimpleNamespace(parse=FakeEndpoint(upstream)))
    )
    with pytest.raises(ProviderFailure) as exc:
        provider.generate("trái cây", [], [])
    assert "secret" not in str(exc.value)


def test_embedding_order_and_error_handling(system):
    endpoint = FakeEndpoint(
        SimpleNamespace(
            data=[SimpleNamespace(index=1, embedding=[2]), SimpleNamespace(index=0, embedding=[1])]
        )
    )
    provider = OpenAIProvider(
        system.cfg, client=SimpleNamespace(embeddings=SimpleNamespace(create=endpoint))
    )
    assert provider.embed(["a", "b"]) == [[1], [2]]
    endpoint.response = SimpleNamespace(data=[])
    with pytest.raises(ProviderFailure):
        provider.embed(["a"])
    endpoint.response = RuntimeError("sensitive")
    with pytest.raises(ProviderFailure) as exc:
        provider.embed(["a"])
    assert "sensitive" not in str(exc.value)


def test_quota_failure_is_actionable_without_leaking_upstream_data(system, monkeypatch):
    from rag_app.provider import safe_provider_failure
    error = RuntimeError('private account data and sk-secret-value')
    error.status_code = 429
    error.body = {'error':{'type':'insufficient_quota'}}
    message = str(safe_provider_failure(error,'generic failure'))
    assert 'quota' in message and 'Billing/Usage' in message
    assert 'private account' not in message and 'sk-secret' not in message
    error.status_code = 500
    assert str(safe_provider_failure(error,'generic failure')) == 'generic failure'
    # A failed chat must stop this paid case before a judge call is attempted.
    from pathlib import Path

    import scripts.run_expanded_eval as runner
    quota = 'OpenAI báo thiếu quota. Hãy kiểm tra Billing/Usage.'
    class ErrorClient:
        def __init__(self, app):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, *args, **kwargs):
            return SimpleNamespace(status_code=503,json=lambda:{'detail':quota})
    provider = SimpleNamespace(events=[],client=None,close=lambda:None)
    monkeypatch.setattr(runner,'AuditedProvider',lambda cfg:provider)
    monkeypatch.setattr(runner,'TestClient',ErrorClient)
    monkeypatch.setattr(runner,'ROOT',Path(system.cfg.storage_dir))
    (runner.ROOT/'tmp').mkdir()
    case = {'id':'quota-probe','question':'câu thử không chứa dữ liệu cá nhân','expected_status':'answered','intent':'knowledge'}
    row = runner.evaluate_case(case,system.cfg,system.store.load_index(),'judge-never-called')
    assert row['quota_blocked'] and not row['passed'] and row['http_status'] == 503
    assert row['execution_error'] == 'RuntimeError'
    assert 'grade' not in row and 'judge_usage' not in row


def test_key_not_in_config_repr():
    cfg = Settings(openai_api_key="secret-test-value", _env_file=None)
    assert "secret-test-value" not in repr(cfg)
