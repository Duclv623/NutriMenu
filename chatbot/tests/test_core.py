import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

from rag_app.config import Settings
from rag_app.domain import AnswerBlock, GeneratedAnswer
from rag_app.ingestion import build_chunks, chunk_unit, clean_text, load_manifest
from rag_app.provider import OpenAIProvider, ProviderFailure, embed_chunks, redact
from rag_app.retrieval import Retriever, fold, tokens
from rag_app.safety import classify
from rag_app.security import RateLimiter
from rag_app.service import make_citations, validate_answer
from rag_app.store import Store


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("Tôi cần ăn bao nhiêu chất xơ mỗi ngày?", "knowledge"),
        ("Cần ăn bao nhiêu protein mỗi ngày?", "knowledge"),
        ("Tôi tiêm insulin, có cần bữa phụ không?", "knowledge"),
        ("Bữa trưa của tôi tổng bao nhiêu kcal?", "food_lookup"),
        ("100 g đậu phụ bao nhiêu protein?", "food_lookup"),
        ("Hãy đổi món trong thực đơn", "menu_request"),
        ("Bé 10 tuổi ăn thế nào?", "special_population"),
        ("Tôi 17 tuổi mắc tiểu đường", "special_population"),
        ("Đái tháo đường type 1 có ăn được không?", "special_population"),
        ("Tôi đang mang thai", "special_population"),
        ("Tôi khó thở và đau ngực", "emergency"),
        ("Bố tôi bất tỉnh", "emergency"),
        ("Tôi có nên ngừng metformin?", "medication"),
        ("Nên dùng thuốc nào?", "medication"),
        ("Tôi nên tiêm insulin trước hay sau ăn?", "medication"),
        ("Xin chào!", "greeting"),
    ],
)
def test_classification(question, intent):
    assert classify(question) == intent


def test_unicode_chunks():
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    text = "Chất xơ và trái cây tốt cho chế độ ăn cân đối.\n" * 100
    chunks = chunk_unit(text, 120, 25)
    assert len(chunks) > 2
    assert all("\ufffd" not in c and len(enc.encode(c)) <= 120 for c in chunks)
    assert chunks[-1].endswith("đối.")


def test_clean_does_not_change_numeric_rules():
    text = clean_text("28\n5.2. Dinh dư ng\nGlucid: 50 – 60% tổng năng lượng\n")
    assert "50 – 60%" in text and "Dinh" in text and not text.startswith("28")


@pytest.mark.parametrize("filename", ["../secret.pdf", "C:\\secret.pdf", "sub/a.pdf"])
def test_manifest_paths_blocked(tmp_path, filename):
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps({"schema_version": 1, "sources": [{"id": "test", "filename": filename}]})
    )
    with pytest.raises(ValueError):
        load_manifest(path)


def test_manifest_requires_reviewed_role(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "test",
                        "filename": "test.pdf",
                        "enabled": True,
                        "role": "structured_food_data",
                    }
                ],
            }
        )
    )
    with pytest.raises(ValueError):
        load_manifest(path)


@pytest.mark.parametrize(
    "change", ["hash", "pages", "start", "end", "order", "page_range", "empty"]
)
def test_ingestion_fail_closed(tmp_path, change):
    manifest = load_manifest(Path("config/sources.json"))
    source = manifest["sources"][0]
    segment = source["segments"][0]
    if change == "hash":
        source["sha256"] = "incorrect"
    elif change == "pages":
        source["expected_pages"] = 6
    elif change == "start":
        segment["start_regex"] = "UNMATCHABLE_MARKER"
    elif change == "end":
        segment["end_regex"] = "UNMATCHABLE_MARKER"
    elif change == "order":
        segment["start_regex"], segment["end_regex"] = segment["end_regex"], segment["start_regex"]
    elif change == "page_range":
        segment["pages"] = [1000]
    else:
        for item in manifest["sources"]:
            item["enabled"] = False
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    cfg = Settings(source_manifest=path, _env_file=None)
    with pytest.raises(ValueError):
        build_chunks(cfg)


def test_store_atomic_index_and_cache(tmp_path, corpus):
    store = Store(tmp_path / "test.sqlite3")
    vectors = [[1.0, 0.5] for _ in corpus]
    store.replace_index(corpus, {"mode": "hybrid"}, vectors)
    chunks, matrix, metadata = store.load_index()
    assert len(chunks) == len(corpus) and matrix.shape == (len(corpus), 2)
    revision = metadata["revision"]
    with pytest.raises(ValueError):
        store.replace_index(corpus, {}, [[1.0, float("nan")]])
    assert store.load_index()[2]["revision"] == revision
    store.cache_vector("key", [1, 2])
    assert store.cached_vector("key") == [1, 2]
    assert store.cached_vector("missing") is None
    with pytest.raises(ValueError):
        store.cache_vector("bad", [float("inf")])


def test_embedding_cache_reuse(system, corpus):
    first = embed_chunks(system.provider, system.store, corpus, "test-model")
    assert len(first) == len(corpus)
    calls = len(system.provider.embed_calls)
    second = embed_chunks(system.provider, system.store, corpus, "test-model")
    assert np.allclose(first, second) and len(system.provider.embed_calls) == calls
    embed_chunks(system.provider, system.store, corpus, "new-model")
    assert len(system.provider.embed_calls) > calls


def test_hybrid_dimension_and_rrf(tmp_path, corpus):
    store = Store(tmp_path / "hybrid.sqlite3")
    store.replace_index(corpus, {"mode": "hybrid"}, [[1.0, 0.0] for _ in corpus])
    retriever = Retriever(store)
    hits = retriever.search("trái cây nước ép", query_vector=[1.0, 0], top_k=5)
    assert len(hits) == 5 and all(h.dense_score == 1 for h in hits)
    assert retriever.search("", query_vector=[1, 0]) == []
    with pytest.raises(ValueError):
        retriever.search("trái cây", query_vector=[1, 2, 3])
    with pytest.raises(ValueError):
        retriever.search("trái cây", query_vector=[np.nan, 0])
    assert len(retriever.search("trái cây", mode="dense", query_vector=[1, 0])) > 0
    assert all(h.lexical_score > 0 for h in retriever.search("trái cây", mode="lexical"))


def test_normalization():
    assert fold("Đái tháo ĐƯỜNG") == "dai thao duong"
    assert "trai_cay" in tokens("Trái cây")


@pytest.mark.parametrize(
    "variant",
    [
        "wrong_id",
        "no_id",
        "empty_text",
        "unsupported",
        "no_blocks",
        "fake_url",
        "fake_marker",
        "medication",
    ],
)
def test_answer_validation(system, variant):
    hits = Retriever(system.store).search("trái cây")
    citations = make_citations(hits)
    block = AnswerBlock(text="Theo tài liệu đã duyệt.", citation_ids=["C1"])
    answer = GeneratedAnswer(supported=True, blocks=[block], uncertainty="")
    if variant == "wrong_id":
        block.citation_ids = ["C999"]
    elif variant == "no_id":
        block.citation_ids = []
    elif variant == "empty_text":
        block.text = " "
    elif variant == "unsupported":
        answer.supported = False
    elif variant == "no_blocks":
        answer.blocks = []
    elif variant == "fake_url":
        block.text = "https://invented.example/source"
    elif variant == "fake_marker":
        block.text = "Ăn nhiều [C123]"
    else:
        block.text = "Tăng liều insulin lên 20 đơn vị"
    assert validate_answer(answer, citations) is None


def test_answer_valid_uses_only_referenced_sources(system):
    citations = make_citations(Retriever(system.store).search("trái cây"))
    answer = GeneratedAnswer(
        supported=True,
        blocks=[AnswerBlock(text="Theo tài liệu.", citation_ids=["C1", "C1"])],
        uncertainty="",
    )
    text, used = validate_answer(answer, citations)
    assert text.endswith("[C1]") and len(used) == 1


def test_rate_limiter_reset():
    from fastapi import HTTPException

    limiter = RateLimiter(2)
    limiter.check("user", now=0)
    limiter.check("user", now=1)
    with pytest.raises(HTTPException):
        limiter.check("user", now=2)
    limiter.check("user", now=62)


def test_redact_credentials_and_contact_data():
    text = redact("Email me@example.com 0912345678 sk-proj-abcdefghijklmnopqrstuvwxyz")
    assert "me@example.com" not in text and "0912345678" not in text and "sk-proj" not in text


def test_config_invalid_values(tmp_path):
    with pytest.raises(ValueError):
        Settings(chunk_tokens=120, chunk_overlap=120, _env_file=None)
    with pytest.raises(ValueError):
        Settings(app_env="production", _env_file=None)
    with pytest.raises(ValueError):
        Settings(food_api_base_url="file:///etc/passwd", _env_file=None)
    assert not Settings(openai_api_key="", _env_file=None).has_key
    assert (
        Settings(storage_dir=tmp_path, jwt_public_key_path="", _env_file=None).jwt_public_key_path
        is None
    )


def test_history_ownership_and_purge(system):
    store = system.store
    sid, mid = str(uuid4()), str(uuid4())
    store.save_message("a", sid, mid, "test", {"answer": "test"})
    assert store.sessions("b") == []
    with pytest.raises(PermissionError):
        store.history("b", sid)
    with pytest.raises(PermissionError):
        store.save_message("b", sid, str(uuid4()), "test", {})
    assert not store.feedback("b", mid, "helpful")
    assert store.feedback("a", mid, "helpful")
    assert not store.delete_session("b", sid)
    with store.connect() as db:
        db.execute("UPDATE messages SET created='2000-01-01'")
    store.purge_history(7)
    assert store.sessions("a") == []


def test_hybrid_keeps_strongest_lexical_evidence(system, corpus, monkeypatch):
    ordered = sorted(corpus, key=lambda chunk: chunk.id)
    vectors = [[-1.0, 0.0]] + [[1.0, 0.0] for _ in ordered[1:]]
    system.store.replace_index(ordered, {"mode": "hybrid"}, vectors)
    retriever = Retriever(system.store)
    monkeypatch.setattr(retriever.bm25, "get_scores", lambda _: np.arange(len(corpus), 0, -1))
    hits = retriever.search("nguyên tắc dinh dưỡng", top_k=3, query_vector=[1.0, 0.0])
    assert len(hits) == 3 and any(h.chunk.id == ordered[0].id for h in hits)
    assert all(h.chunk.id != ordered[0].id for h in retriever.search(
        "bữa phụ năng lượng", top_k=3, query_vector=[1.0, 0.0], mode="dense"
    ))


def test_provider_requires_key():
    with pytest.raises(ProviderFailure):
        OpenAIProvider(Settings(openai_api_key="", _env_file=None))
