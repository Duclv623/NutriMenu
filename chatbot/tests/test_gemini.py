import json

import httpx
import pytest

from rag_app.config import Settings
from rag_app.domain import GeneratedAnswer
from rag_app.gemini_provider import GeminiClient, GeminiProvider
from rag_app.provider import ProviderFailure, redact


def cfg():
    return Settings(_env_file=None, answer_mode="gemini", gemini_api_key="unit-test-only-secret", gemini_request_interval=0)


def test_real_api_contract_headers_schema_and_provenance():
    def handler(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        assert not request.url.query and request.headers["x-goog-api-key"] == "unit-test-only-secret"
        body = json.loads(request.content)
        assert body["store"] is False
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["generationConfig"]["responseJsonSchema"]["properties"]["supported"]
        assert body["systemInstruction"]["parts"][0]["text"] == "system"
        return httpx.Response(200, json={"responseId":"unit-response-id", "candidates":[{
            "finishReason":"STOP", "content":{"parts":[{"text":json.dumps({
                "supported":False,"blocks":[],"uncertainty":""})}]}}],
            "usageMetadata":{"promptTokenCount":5,"candidatesTokenCount":4,"thoughtsTokenCount":2}})
    client = GeminiClient(cfg(), httpx.MockTransport(handler))
    result = client.parse(model=cfg().gemini_model, input=[{"role":"system","content":"system"},
        {"role":"user","content":"question"}], text_format=GeneratedAnswer,max_output_tokens=50)
    assert result.id == "unit-response-id" and result.usage.output_tokens == 6
    client.close()


@pytest.mark.parametrize("status", [401,403,404,429])
def test_api_errors_never_return_static_success_or_echo_secret(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status,json={"error":{"message":"unit-test-only-secret private upstream"}})
    client = GeminiClient(cfg(),httpx.MockTransport(handler))
    with pytest.raises(ProviderFailure) as error:
        client.post(cfg().gemini_model,"generateContent",{})
    assert "unit-test-only-secret" not in str(error.value) and len(calls) == 1
    client.close()


@pytest.mark.parametrize("data", [
    {"candidates":[]},
    {"candidates":[{"finishReason":"MAX_TOKENS"}]},
    {"candidates":[{"finishReason":"STOP","content":{"parts":[{"text":"not json"}]}}]},
    {"candidates":[{"finishReason":"STOP","content":{"parts":[{"text":'{"supported":false,"blocks":[],"uncertainty":""}'}]}}]},
])
def test_incomplete_invalid_or_missing_id_is_rejected(data):
    client = GeminiClient(cfg(),httpx.MockTransport(lambda request:httpx.Response(200,json=data)))
    with pytest.raises(ProviderFailure):
        client.parse(model=cfg().gemini_model,input=[],text_format=GeneratedAnswer,max_output_tokens=50)
    client.close()


def test_embedding_batch_preserves_each_document_and_query_format():
    seen = []
    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        assert request.url.path.endswith("gemini-embedding-2:batchEmbedContents")
        assert all("taskType" not in r and r["outputDimensionality"] == 768 for r in body["requests"])
        return httpx.Response(200,json={"embeddings":[{"values":[1.0]+[0.0]*767} for _ in body["requests"]]})
    provider = GeminiProvider(cfg(),httpx.MockTransport(handler))
    assert len(provider.embed_documents(["first", "second"])) == 2
    assert len(provider.embed(["query"])[0]) == 768
    assert seen[0]["requests"][1]["content"]["parts"][0]["text"].endswith("second")
    assert seen[1]["requests"][0]["content"]["parts"][0]["text"].startswith("task: search result | query:")
    assert cfg().embedding_identity != "gemini-embedding-2"
    provider.close()


def test_google_key_redaction():
    assert "AIza" not in redact("AIza" + "x"*32)
    assert "AQ." not in redact("AQ." + "x"*48)
    assert "unit-test-only-secret" not in repr(cfg())
