import asyncio
import logging
import sqlite3

from fastapi.testclient import TestClient

from rag_app.domain import AnswerBlock, GeneratedAnswer
from rag_app.main import create_app, purge_history_periodically
from rag_app.provider import ProviderFailure
from rag_app.retrieval import Retriever
from rag_app.service import make_citations, validate_answer
from rag_app.store import Store


def test_requests_do_not_purge_history(system, monkeypatch):
    calls = []
    monkeypatch.setattr(system.store, 'purge_history', lambda days: calls.append(days))
    for _ in range(4):
        assert system.client.get('/api/foods?q=sữa').status_code == 200
    assert calls == []


def test_startup_purges_once_and_shutdown_does_not_repeat(system, monkeypatch):
    calls = []
    monkeypatch.setattr(Store, 'purge_history', lambda self, days: calls.append(days))
    with TestClient(create_app(system.cfg, system.provider)) as client:
        assert calls == [7]
        assert client.get('/api/foods?q=sữa').status_code == 200
        assert calls == [7]
    assert calls == [7]


def test_periodic_purge_recovers_and_stops(caplog):
    class Store:
        calls = 0

        def purge_history(self, days):
            assert days == 7
            self.calls += 1
            if self.calls == 1:
                raise sqlite3.OperationalError('secret database detail')

    async def exercise():
        store = Store()
        stop = asyncio.Event()
        task = asyncio.create_task(purge_history_periodically(store, 7, stop, 0.01))
        try:
            async with asyncio.timeout(3):
                while store.calls < 2:
                    await asyncio.sleep(0.01)
        finally:
            stop.set()
            await task
        calls = store.calls
        await asyncio.sleep(0.03)
        assert store.calls == calls

    with caplog.at_level(logging.WARNING, logger='rag_app.main'):
        asyncio.run(exercise())
    assert 'history_purge_failed' in caplog.text
    assert 'secret database detail' not in caplog.text


def test_request_logs_include_correlation_without_chat_content(system, caplog):
    with caplog.at_level(logging.INFO, logger='rag_app'):
        response = system.client.post('/api/chat', json={'message':'Xin chào private-patient-unique'})
    assert response.status_code == 200
    request_id = response.headers['X-Request-ID']
    assert request_id in caplog.text
    assert 'request_completed' in caplog.text and 'chat_completed' in caplog.text
    assert 'private-patient-unique' not in caplog.text
    assert 'rag_app' in caplog.text


def test_provider_failure_logs_no_private_exception_text(system, caplog):
    system.provider.error = ProviderFailure('secret-upstream-payload')
    response = system.client.post('/api/chat', json={'message':'Nên chọn trái cây thế nào?'})
    assert response.status_code == 503
    assert 'provider_failed' in caplog.text
    assert 'secret-upstream-payload' not in caplog.text


def test_final_guard_does_not_silently_drop_a_qualification(system):
    citations = make_citations(Retriever(system.store).search('trái cây'))
    generated = GeneratedAnswer(supported=True, blocks=[
        AnswerBlock(text='Thông tin này chỉ áp dụng với điều kiện ở đoạn tiếp theo.', citation_ids=['C1']),
        AnswerBlock(text='Điều kiện áp dụng chưa có nguồn hợp lệ.', citation_ids=['C999']),
    ], uncertainty='')
    assert validate_answer(generated, citations) is None
