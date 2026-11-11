"""Paid, opt-in API checks. Reports are evidence, not clinical certification."""

import json
import os
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from rag_app.config import ROOT, Settings
from rag_app.main import create_app
from rag_app.provider import OpenAIProvider
from rag_app.store import Store


class AuditedOpenAIProvider(OpenAIProvider):
    def __init__(self, settings):
        super().__init__(settings)
        self.generations = 0
        self.embeddings = 0
        self.last_review = None
        self.last_hits = []

    def generate(self, question, hits, history):
        result = super().generate(question, hits, history)
        self.generations += 1
        self.last_review = result[0]._grounding_review
        self.last_hits = [{"id": f"C{i}", "section": h.chunk.section, "text": h.chunk.text} for i, h in enumerate(hits, 1)]
        return result

    def embed(self, texts):
        result = super().embed(texts)
        self.embeddings += 1
        return result


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("RUN_LIVE_TESTS") != "1", reason="Paid API opt-in required")
def test_live_api_quality_and_abstention(tmp_path):
    original = Settings()
    assert original.has_key, "Configure the key in .env"
    chunks, vectors, metadata = Store(original.storage_dir / "rag.sqlite3").load_index()
    assert chunks and vectors is not None and metadata.get("mode") == "hybrid"
    cfg = original.model_copy(update={
        "storage_dir": tmp_path, "answer_mode": "openai", "rate_limit_per_minute": 300,
    })
    Store(tmp_path / "rag.sqlite3").replace_index(chunks, metadata, vectors)
    provider = AuditedOpenAIProvider(cfg)
    dataset = json.loads((ROOT / "evals/questions.json").read_text(encoding="utf-8"))
    extra = [
        {"id": "H01", "intent": "knowledge", "expected_status": "answered", "question": "Tôi nghĩ ép trái cây vẫn giữ nguyên chất xơ như ăn nguyên miếng. Tài liệu có ủng hộ nhận định này không?"},
        {"id": "H02", "intent": "knowledge", "expected_status": "insufficient_evidence", "accepted_statuses": ["insufficient_evidence", "answered"], "question": "Gạo lứt được khuyến cáo thì có nghĩa là ăn bao nhiêu cũng được đúng không?"},
        {"id": "H03", "intent": "knowledge", "expected_status": "answered", "question": "So sánh trái cây nguyên miếng và nước ép bằng đúng 2 gạch đầu dòng, mỗi dòng tối đa 25 từ."},
        {"id": "H04", "intent": "knowledge", "expected_status": "answered", "question": "Hai mục kiểm soát cân nặng và chất béo có nêu cùng một tỷ lệ năng lượng từ lipid không? Trích cả hai mức và chỉ rõ khác biệt."},
        {"id": "H05", "intent": "knowledge", "expected_status": "insufficient_evidence", "question": "Tài liệu có nghiên cứu thử nghiệm năm 2026 chứng minh nước ép chữa khỏi đái tháo đường không? Chỉ trả lời nếu có bằng chứng."},
    ]
    report = {
        "tested_at": datetime.now(UTC).isoformat(), "model": cfg.openai_model,
        "embedding_model": cfg.embedding_model, "provider": "OpenAIProvider (real SDK)",
        "source_index_revision": metadata.get("revision"),
        "limitations": "Checks cover status, real calls, tokens and citation integrity. Answer/source faithfulness requires separate review; no clinical certification.",
        "results": [],
    }
    output = ROOT / "docs" / (
        "live-quality-targeted-results.json" if os.environ.get("LIVE_CASE_IDS") else "live-quality-results.json"
    )
    failures = []
    with TestClient(create_app(cfg, provider)) as client:
        for case in dataset["cases"] + extra:
            selected = os.environ.get("LIVE_CASE_IDS", "").split(",")
            if selected != [""] and case["id"] not in selected:
                continue
            expected = case.get("expected_status") or {
                "knowledge": "answered", "greeting": "greeting",
                "food_lookup": "integration_required", "menu_request": "integration_required",
            }.get(case["intent"], "safety")
            before = provider.generations
            before_embed = provider.embeddings
            response = client.post("/api/chat", json={"message": case["question"], "cloud_consent": True})
            data = response.json()
            problems = []
            if response.status_code != 200:
                problems.append(f"HTTP {response.status_code}")
            elif data["status"] not in case.get("accepted_statuses", [expected]):
                problems.append(f"Expected {expected}, received {data['status']}")
            if response.status_code == 200 and data["status"] == "answered":
                if provider.generations != before + 1 or data.get("usage", {}).get("output_tokens", 0) <= 0:
                    problems.append("Missing successful real generation/tokens")
                if data.get("answer_origin") != "openai" or data.get("model") != cfg.openai_model or len(data.get("provider_response_ids", [])) != 2:
                    problems.append("Missing real generation and grounding response IDs/model")
                citations = data.get("citations", [])
                if not citations:
                    problems.append("Missing citations")
                if case.get("section_contains") and not any(case["section_contains"] in c["section"] for c in citations):
                    problems.append("Expected source section missing")
                for citation in citations:
                    if not any(c.id == citation["chunk_id"] and c.text == citation["quote"] and c.pages == citation["pdf_pages"] for c in chunks):
                        problems.append("Citation differs from indexed source")
                if case["id"] == "K03" and "bmi" in data.get("answer", "").lower():
                    problems.append("BMI added without source evidence")
                if case["id"] == "K10" and "biến đổi cấu trúc lipid" in data.get("answer", "").lower():
                    problems.append("Unsupported explanation about heated oil")
                if case["id"] == "K07" and "bữa phụ như bánh kẹo" in data.get("answer", "").lower():
                    problems.append("Snack example invented; source lists bread, not candy")
                if case["id"] == "K19" and "không khuyến cáo" in data.get("answer", "").lower() and "chia" not in data.get("answer", "").lower():
                    problems.append("Not recommending split meals was changed to not recommending snacks")
                if case["id"] == "H03":
                    lines = data.get("answer", "").split("\n\n")
                    if len(lines) != 2 or any(not line.startswith("- ") or len(line.split()) > 28 for line in lines):
                        problems.append("Two short bullet points requested")
                if case["id"] == "H04":
                    text = data.get("answer", "").replace(" ", "").replace("–", "-")
                    if "20-30%" not in text or "20-25%" not in text:
                        problems.append("Comparison omitted one or both requested lipid ranges")
            row = {
                "id": case["id"], "question": case["question"], "expected_status": expected,
                "accepted_statuses": case.get("accepted_statuses", [expected]),
                "http_status": response.status_code, "real_generation_calls": provider.generations - before,
                "real_embedding_calls": provider.embeddings - before_embed,
                "passed": not problems, "problems": problems, "response": data,
                "grounding_review": provider.last_review if provider.generations > before else None,
                "retrieved_excerpts": provider.last_hits if provider.generations > before else [],
            }
            report["results"].append(row)
            report["passed"] = sum(r["passed"] for r in report["results"])
            report["total"] = len(report["results"])
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{case['id']}: {'PASS' if not problems else 'FAIL'} {data.get('status', response.status_code)}", flush=True)
            if problems:
                failures.append(f"{case['id']}: {'; '.join(problems)}")
    assert not failures, "\n".join(failures)
