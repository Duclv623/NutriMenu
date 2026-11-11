"""Opt-in real, paid OpenAI test. Skipping is NOT a passing live result."""

import os

import pytest

from rag_app.config import Settings
from rag_app.domain import ChatRequest
from rag_app.ingestion import build_chunks
from rag_app.provider import OpenAIProvider, embed_chunks
from rag_app.service import ChatService
from rag_app.store import Store


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_TESTS") != "1",
    reason="Explicit RUN_LIVE_TESTS=1 required: real paid API",
)
def test_real_openai_hybrid_and_grounded_answer(tmp_path):
    cfg = Settings(storage_dir=tmp_path, answer_mode="openai")
    assert cfg.has_key, "Set a NEW key in .env; never paste it in chat"
    chunks, _ = build_chunks(cfg)
    store = Store(tmp_path / "rag.sqlite3")
    provider = OpenAIProvider(cfg)
    try:
        vectors = embed_chunks(provider, store, chunks, cfg.embedding_model)
        store.replace_index(
            chunks, {"mode": "hybrid", "embedding_model": cfg.embedding_model}, vectors
        )
        service = ChatService(cfg, store, provider)
        response = service.chat(
            ChatRequest(
                message="Theo QĐ 5481 của Bộ Y tế, nên ăn trái cây nguyên miếng hay uống nước ép?",
                cloud_consent=True,
            ),
            "live-test",
        )
        assert response.status == "answered" and response.citations
        assert any(33 in c.pdf_pages for c in response.citations)
        assert "[C" in response.answer and response.usage["output_tokens"] > 0
        outside = service.chat(
            ChatRequest(message="Viết chương trình Java sắp xếp mảng cho tôi", cloud_consent=True),
            "live-test",
        )
        assert outside.status == "insufficient_evidence"
    finally:
        provider.close()
