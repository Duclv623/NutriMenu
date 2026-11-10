# Pending E2E tests for tmp/q010-unresolved-goal-draft.patch.
# Kept outside tests/ and not collected until the approved patch is applied.
from types import SimpleNamespace
import pytest
from rag_app.domain import AnswerBlock, GeneratedAnswer
from rag_app.provider import GroundingReview, OpenAIProvider
from rag_app.routing import ResponsePlan

@pytest.mark.parametrize('question', ['an pho sang dc ko, toi bi tieu duong?', 'Tôi ăn phở bữa sáng được không?'])
def test_exhausted_decision_revision_reports_limit_before_verified_tips(system, monkeypatch, question):
    service = system.app.state.service
    retriever = service.retriever()
    hit = retriever.search('ăn phở')[0]
    hit = hit.model_copy(update={'chunk':hit.chunk.model_copy(update={'text':'When having noodle dishes, choose clear soup.', 'language':'en'})})
    monkeypatch.setattr(retriever, 'search', lambda *args: [hit])
    monkeypatch.setattr(service, 'retriever', lambda: retriever)
    draft = GeneratedAnswer(supported=True, blocks=[
        AnswerBlock(text='Bạn có thể ăn phở và kiểm soát đường huyết tốt hơn.', citation_ids=['C1']),
        AnswerBlock(text='Khi ăn món sợi, chọn nước dùng trong.', citation_ids=['C1'])], uncertainty='')
    review = GroundingReview.model_validate({'accepted_blocks':[{'block_index':1,'evidence':[{'citation_id':'C1','line_ids':[0]}]}],
        'needs_revision':True,'revision_reason':'Nguồn chưa chứng minh món ăn phù hợp riêng hoặc lợi ích đường huyết.'})
    responses = iter([draft,review,draft,review])
    calls=[]
    def parse(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(id=f'pending-regression-{len(calls)}', status='completed', output_parsed=next(responses), usage=None)
    provider = OpenAIProvider(system.cfg, client=SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    monkeypatch.setattr(provider, 'plan_response', lambda *args: (
        ResponsePlan(strategy='evidence_rag',goal='decision',focus='Giải quyết câu hỏi ăn được không.'),
        GeneratedAnswer(supported=False,blocks=[],uncertainty=''), {}))
    audit=[]
    original=provider.generate
    def capture(*args,**kwargs):
        answer,usage=original(*args,**kwargs)
        audit.append(answer._grounding_review)
        return answer,usage
    monkeypatch.setattr(provider,'generate',capture)
    monkeypatch.setattr(service,'provider',provider)
    result=system.client.post('/api/chat',json={'message':question}).json()
    paragraphs=result['answer'].split('\n\n')
    assert paragraphs[0] == 'Mình chưa đủ căn cứ từ các đoạn trích đã kiểm tra để kết luận món này phù hợp riêng cho bạn.'
    assert '[C' not in paragraphs[0]
    assert 'nước dùng trong' in paragraphs[1] and '[C1]' in paragraphs[1]
    assert 'tốt hơn' not in result['answer']
    assert result['citations'][0]['id']=='C1'
    assert audit[-1]['supported_evidence'] is True
    assert audit[-1]['goal_complete'] is False
    assert audit[-1]['unresolved_goals']==['intake_suitability_decision']
    assert len(calls)==4  # Existing bounded generation+review attempts only.
