"""Bounded context and verified revision checks; no model/network access."""
import json
from types import SimpleNamespace

import numpy as np

from rag_app.config import Settings
from rag_app.domain import AnswerBlock, Chunk, GeneratedAnswer, Hit
from rag_app.provider import GroundingReview, OpenAIProvider
from rag_app.retrieval import Retriever
from rag_app.service import make_citations


def chunk(id, section, *, source='byt5481-nutrition', related=(), size=100, locators=()):
    return Chunk(id=id, source_id=source, title='Nguồn thử', text='Bằng chứng ' + section,
                 section=section, pages=[1], printed_pages=[1], filename='test.pdf',
                 year=2020, version='test', sha256='test', token_count=size,
                 related_sections=list(related), locators=list(locators))


def retriever(chunks, primary_count=1):
    vectors = np.asarray([[1., 0.] if i < primary_count else [0., 1.]
                          for i in range(len(chunks))])
    return Retriever(SimpleNamespace(load_index=lambda: (chunks, vectors, {'mode': 'hybrid'})))


def search(engine, query='calo', top_k=1):
    return engine.search(query, top_k=top_k, query_vector=[1., 0.], min_dense=.9, mode='dense')


def test_chroma_dense_search_respects_existing_source_filter(tmp_path):
    from rag_app.chroma_index import write_chroma_index
    from rag_app.store import Store

    chunks = [chunk('a', 'Năng lượng'), chunk('b', 'Khẩu phần', source='other'),
              chunk('c', 'Chất xơ')]
    store = Store(tmp_path / 'rag.sqlite3')
    vectors = [[.8, .6], [1., 0.], [.2, .98]]
    store.replace_index(chunks, {'mode': 'hybrid', 'embedding_identity': 'test-vector'}, vectors)
    indexed_chunks, indexed_vectors, metadata = store.load_index()
    write_chroma_index(tmp_path / 'chroma', indexed_chunks, indexed_vectors, metadata)
    question = 'Theo Bộ Y tế, năng lượng được trình bày ở đâu?'
    before = Retriever(store).search(question, top_k=2, query_vector=[1., 0.], mode='hybrid')
    engine = Retriever(store, chroma_path=tmp_path / 'chroma')
    after = engine.search(question, top_k=2, query_vector=[1., 0.], mode='hybrid')
    assert engine.vectors is None
    assert [hit.chunk.id for hit in after] == [hit.chunk.id for hit in before]
    assert 'a' in [hit.chunk.id for hit in after] and 'b' not in [hit.chunk.id for hit in after]
    assert np.isclose(next(hit.dense_score for hit in after if hit.chunk.id == 'a'), .8)


def test_companions_append_without_displacing_primary_citations():
    chunks = [chunk('a', 'A', related=['C']), chunk('b', 'B'), chunk('c', 'C')]
    engine = retriever(chunks, primary_count=2)
    hits = search(engine, top_k=2)
    assert [h.chunk.id for h in hits] == ['a', 'b', 'c']
    citations = make_citations(hits)
    assert [(c.id, c.chunk_id, c.pdf_pages) for c in citations] == [
        ('C1', 'a', [1]), ('C2', 'b', [1]), ('C3', 'c', [1])]
    assert hits[-1].chunk is chunks[-1]


def test_companions_respect_named_source_and_table_filters():
    chunks = [chunk('a', 'A', related=['other::B', 'Table', 'Valid']),
              chunk('b', 'B', source='other'), chunk('c', 'Table', locators=['t1']),
              chunk('d', 'Valid')]
    assert [h.chunk.id for h in search(retriever(chunks), 'Theo Bộ Y tế calo')] == ['a', 'd']


def test_companions_obey_budget_dedup_and_one_hop():
    chunks = [chunk('a', 'A', related=['Large', 'C', 'D', 'E']),
              chunk('b', 'Large', size=841),
              chunk('c', 'C', size=400, related=['A', 'Indirect']),
              chunk('c', 'C', size=1), chunk('d', 'D', size=440),
              chunk('e', 'E', size=1), chunk('f', 'Indirect', size=1)]
    engine = retriever(chunks)
    for _ in range(2):
        hits = search(engine)
        assert [h.chunk.id for h in hits] == ['a', 'c', 'd']
        assert sum(h.chunk.token_count for h in hits[1:]) == 840
    # A linked companion's own link must not pull another section into context.
    one_hop = retriever([chunks[0].model_copy(update={'related_sections': ['C']}),
                        chunks[2], chunks[-1]])
    assert [h.chunk.id for h in search(one_hop)] == ['a', 'c']


def answer(*texts):
    return GeneratedAnswer(supported=True, blocks=[AnswerBlock(text=t, citation_ids=['C1'])
                                                  for t in texts], uncertainty='')


def review(*indices):
    return GroundingReview.model_validate({'accepted_blocks': [
        {'block_index': i, 'evidence': [{'citation_id': 'C1', 'line_ids': [0]}]}
        for i in indices]})


def provider_with(outputs):
    sequence = iter(outputs)
    calls = []

    def parse(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(id=f'fake-{len(calls)}', status='completed',
                               output_parsed=next(sequence),
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5))

    provider = OpenAIProvider(Settings(_env_file=None),
                              client=SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    return provider, calls


def test_generation_and_review_share_evidence_line_ids():
    source = chunk('a', 'Chất tạo ngọt').model_copy(update={
        'text': '- Dùng vừa phải.\nGiữ nguyên điều kiện.\n- Đọc nhãn.'})
    provider, calls = provider_with([answer('Dùng vừa phải.'), review(0)])
    result, _ = provider.generate('Tài liệu nói gì về chất tạo ngọt?', [Hit(chunk=source, score=1)], [])
    generator = json.loads(calls[0]['input'][1]['content'])['SOURCE_EXCERPTS'][0]
    reviewer = json.loads(calls[1]['input'][1]['content'])['SOURCE_EXCERPTS'][0]
    assert result.supported and len(calls) == 2
    assert generator['text'] == source.text and 'text' not in reviewer
    assert generator['allowed_line_ids'] == reviewer['allowed_line_ids'] == [0, 1]
    assert generator['evidence_lines'] == reviewer['evidence_lines'] == [
        {'id': 0, 'text': '- Dùng vừa phải. Giữ nguyên điều kiện.'},
        {'id': 1, 'text': '- Đọc nhãn.'}]


def test_revision_feedback_preserves_only_verified_content_and_rechecks():
    source = chunk('a', 'Chất tạo ngọt').model_copy(update={'text': 'Dùng chất tạo ngọt vừa phải.'})
    direct = 'Dùng chất tạo ngọt vừa phải.'
    provider, calls = provider_with([
        answer(direct, 'Giúp giảm đường huyết.'), review(0, 1), answer(direct), review(0)])
    result, usage = provider.generate('Tài liệu nói gì về chất tạo ngọt?',
                                      [Hit(chunk=source, score=1)], [])
    feedback = json.loads(calls[2]['input'][1]['content'])['revision_feedback']
    assert feedback['verified_blocks'] == [{'text': direct, 'citation_ids': ['C1']}]
    assert feedback['verified_evidence'] == [
        {'block_index': 0, 'citation_id': 'C1', 'lines': [source.text]}]
    assert feedback['unresolved_goals'] == []
    assert len(feedback['previous_draft']['blocks']) == 2
    assert result.supported and [b.text for b in result.blocks] == [direct]
    assert len(calls) == 4 and calls[3]['text_format'] is GroundingReview
    assert usage == {'input_tokens': 40, 'output_tokens': 20}
