from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from rag_app.config import Settings
from rag_app.domain import AnswerBlock, GeneratedAnswer
from rag_app.main import create_app
from rag_app.provider import ProviderFailure


def ask(client, message="Người tiểu đường nên ăn trái cây thế nào?", **kwargs):
    return client.post("/api/chat", json={"message": message, "cloud_consent": True, **kwargs})


def test_health_status_and_static_ui(system):
    assert system.client.get("/health").json()["status"] == "ok"
    assert system.client.get("/api/status").json()["chunk_count"] > 0
    html = system.client.get("/")
    assert html.status_code == 200 and "NutriGuide" in html.text
    assert "script-src 'self'" in html.headers["content-security-policy"]
    assert system.client.get("/static/app.js").status_code == 200
    docs = system.client.get("/docs")
    assert docs.status_code == 200 and "api-docs.js" in docs.text
    assert system.client.get("/openapi.json").json()["paths"]["/api/chat"]


@pytest.mark.parametrize(
    "body",
    [
        {"message": " "},
        {"message": "x" * 2001},
        {"message": "abc\u0000"},
        {"message": "ok", "session_id": "not-uuid"},
        {"message": "ok", "extra": 1},
    ],
)
def test_invalid_requests(system, body):
    assert system.client.post("/api/chat", json=body).status_code == 422


def test_answer_with_checked_citations(system):
    result = ask(system.client).json()
    assert result["status"] == "answered"
    assert result["citations"][0]["id"] == "C1"
    assert "[C1]" in result["answer"]
    assert result["usage"]["input_tokens"] == 12
    assert result["answer_origin"] == "custom_provider" and result["model"] is None
    assert not result["provider_response_ids"]
    assert not result["history_saved"] and system.client.get("/api/sessions").json() == []


def test_safety_is_immediate_without_provider_calls_or_fabricated_citations(system):
    for message in ("Tôi bị suy thận", "Tôi nên tăng liều insulin?", "Người nhà bất tỉnh"):
        result = ask(system.client, message).json()
        assert result["status"] == "safety" and not result["citations"]
        assert result["answer_origin"] == "static" and not result["provider_response_ids"]
    assert not system.provider.generate_calls
    assert not system.provider.policy_calls and not system.provider.embed_calls


def test_unintegrated_services_explicit(system):
    assert ask(system.client, "Tạo thực đơn cho tôi").json()["status"] == "integration_required"
    assert not system.provider.generate_calls


def test_greeting(system):
    assert ask(system.client, "Xin chào").json()["status"] == "greeting"


def test_legacy_cloud_consent_does_not_disable_api(system):
    result = ask(system.client, cloud_consent=False)
    assert result.status_code == 200 and system.provider.generate_calls


def test_provider_failure_is_not_mocked_success(system):
    system.provider.error = ProviderFailure("OpenAI tạm thời không khả dụng")
    result = ask(system.client)
    assert result.status_code == 503 and "tạm thời" in result.json()["detail"]


def test_invalid_citation_becomes_abstention(system):
    system.provider.answer = GeneratedAnswer(
        supported=True,
        blocks=[AnswerBlock(text="Bịa thông tin", citation_ids=["C999"])],
        uncertainty="",
    )
    result = ask(system.client).json()
    assert result["status"] == "insufficient_evidence" and not result["citations"]
    assert "Bịa" not in result["answer"]


def test_unsupported_answer_abstains(system):
    system.provider.answer = GeneratedAnswer(supported=False, blocks=[], uncertainty="")
    assert ask(system.client).json()["status"] == "insufficient_evidence"


def test_history_consent_ownership_delete_and_feedback(system):
    first = ask(system.client, save_history=True).json()
    sid = first["session_id"]
    assert len(system.client.get("/api/sessions").json()) == 1
    assert system.client.get(f"/api/sessions/{sid}").status_code == 200
    second = ask(system.client, "Còn nước ép thì sao?", save_history=True, session_id=sid).json()
    assert second["session_id"] == sid
    assert system.provider.generate_calls[-1][2]
    assert (
        system.client.post(
            "/api/feedback", json={"message_id": first["message_id"], "rating": "helpful"}
        ).status_code
        == 204
    )
    with TestClient(system.app) as other:
        assert other.get(f"/api/sessions/{sid}").status_code == 404
        assert other.delete(f"/api/sessions/{sid}").status_code == 404
        assert ask(other, session_id=sid).status_code == 404
        assert (
            other.post(
                "/api/feedback", json={"message_id": first["message_id"], "rating": "helpful"}
            ).status_code
            == 404
        )
    assert system.client.delete(f"/api/sessions/{sid}").status_code == 204
    assert system.client.get(f"/api/sessions/{sid}").status_code == 404


def test_unknown_session_hidden(system):
    assert ask(system.client, session_id=str(uuid4())).status_code == 404


def test_source_pdf_allowlist(system):
    assert system.client.get("/api/documents/byt5481-nutrition/pdf").status_code == 200
    assert system.client.get("/api/documents/byt1353/pdf").status_code == 404
    assert system.client.get("/api/documents/not-real/pdf").status_code == 404
    docs = system.client.get("/api/documents").json()
    assert len(docs) == 36
    assert system.client.get('/api/documents/ada-labels/pdf').status_code == 200


def test_cross_origin_rejected(system):
    result = system.client.post(
        "/api/chat", json={"message": "xin chào"}, headers={"Origin": "https://evil.example"}
    )
    assert result.status_code == 403


def test_rate_limit(system):
    for _ in range(system.cfg.rate_limit_per_minute):
        assert ask(system.client, "xin chào").status_code == 200
    result = ask(system.client, "xin chào")
    assert result.status_code == 429 and result.headers["Retry-After"] == "60"


def test_no_key_openai_mode_returns_503(tmp_path, corpus):
    cfg = Settings(storage_dir=tmp_path, openai_api_key="", _env_file=None)
    app = create_app(cfg)
    app.state.store.replace_index(corpus, {"mode": "lexical"})
    with TestClient(app) as client:
        assert ask(client).status_code == 503


def test_no_index_returns_503(tmp_path):
    cfg = Settings(storage_dir=tmp_path, openai_api_key="", _env_file=None)
    with TestClient(create_app(cfg)) as client:
        assert ask(client).status_code == 503


def test_extractive_mode_removed():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(answer_mode="extractive", _env_file=None)


@pytest.mark.parametrize("message", ["Xin chào", "Tạo thực đơn cho tôi"])
def test_non_safety_chat_needs_real_key(tmp_path, message):
    cfg = Settings(storage_dir=tmp_path, openai_api_key="", gemini_api_key="", _env_file=None)
    with TestClient(create_app(cfg)) as client:
        assert ask(client, message).status_code == 503


def test_hybrid_query_embedding_and_model_mismatch(system, corpus):
    system.store.replace_index(
        corpus,
        {"mode": "hybrid", "embedding_identity": system.cfg.embedding_identity},
        [[1, 0.5, 0.1] for _ in corpus],
    )
    assert ask(system.client).status_code == 200
    assert system.provider.embed_calls
    assert ask(system.client, cloud_consent=False).status_code == 200
    system.store.replace_index(
        corpus,
        {"mode": "hybrid", "embedding_model": "wrong-model"},
        [[1, 0.5, 0.1] for _ in corpus],
    )
    assert ask(system.client).status_code == 503


def test_concurrent_read_requests(system):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: system.client.get("/api/status"), range(24)))
    assert all(r.status_code == 200 and r.json()["index_ready"] for r in responses)
