"""Acceptance tests written before implementation. Real corpus, no paid API calls."""

from pathlib import Path

from rag_app.config import Settings
from rag_app.ingestion import build_chunks, load_manifest
from rag_app.retrieval import Retriever
from rag_app.safety import classify
from rag_app.store import Store


def test_corpus_is_nutrition_only(tmp_path):
    cfg = Settings(storage_dir=tmp_path, _env_file=None)
    chunks, report = build_chunks(cfg)
    assert chunks
    enabled = {s['id'] for s in load_manifest(cfg.source_manifest)['sources'] if s['enabled']}
    assert {c.source_id for c in chunks} == enabled
    assert {"byt5481-nutrition", "nin-healthy-meals", "endocrine-diet", "niddk-healthy-living", "vtn-fct-2007", "ada-labels", "ada-sweeteners", "ada-food-groups", "ada-cooking"}.issubset(enabled)
    assert len(enabled) == 32
    pdf = [c for c in chunks if c.source_id == "byt5481-nutrition"]
    assert {p for c in pdf for p in c.pages} == {30, 31, 32, 33, 34}
    assert "Quản lý các bệnh đồng mắc" not in "\n".join(c.text for c in pdf)
    assert "Không tập thể dục" not in "\n".join(c.text for c in pdf)
    assert all(c.token_count <= cfg.chunk_tokens for c in chunks)
    assert report["enabled_sources"] == 32
    assert len({p for c in chunks if c.source_id == 'vtn-fct-2007' for p in c.pages}) == 41
    assert all(not c.pages and c.locators for c in chunks if c.document_format == "docx")


def test_fruit_retrieval(tmp_path):
    cfg = Settings(storage_dir=tmp_path, _env_file=None)
    chunks, _ = build_chunks(cfg)
    store = Store(cfg.storage_dir / "rag.sqlite3")
    store.replace_index(chunks, {"mode": "lexical"})
    retriever = Retriever(store)
    hits = retriever.search("Trái cây nên ăn nguyên miếng hay uống nước ép?", top_k=3)
    assert hits and any("nước ép" in hit.chunk.text for hit in hits)


def test_manifest_uses_local_files():
    manifest = load_manifest(Path("config/sources.json"))
    assert len(manifest["sources"]) == 36
    assert sum(bool(s["enabled"]) for s in manifest["sources"]) == 32


def test_routes_do_not_invent_menu_data():
    assert classify("100g sữa bò có bao nhiêu kcal?") == "food_lookup"
    assert classify("Lập thực đơn cho tôi trong 7 ngày") == "menu_request"
    assert classify("Người tiểu đường nên ăn trái cây thế nào?") == "knowledge"
    assert classify("Tôi nên tăng liều insulin lên bao nhiêu?") == "medication"
    assert classify("Tôi bị suy thận, nên ăn bao nhiêu đạm?") == "special_population"
