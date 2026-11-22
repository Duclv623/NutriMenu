"""Regression pairs from the November audit. No network or shared user state."""
import json
from unittest.mock import Mock

import pytest

from rag_app.config import ROOT, Settings
from rag_app.domain import ChatRequest
from rag_app.food_data import FoodItem, FoodPlan, get_catalog
from rag_app.history_store import HistoryStoreError
from rag_app.meal_chat import meal_action
from rag_app.meal_gateway import MockMealGateway
from rag_app.safety import classify
from rag_app.service import ChatService


@pytest.fixture
def service(shared_corpus):
    return ChatService(Settings(_env_file=None), shared_corpus, meal_gateway=MockMealGateway("named"))


@pytest.mark.parametrize("message", [
    "Mẹ tôi gọi mãi không dậy, giờ phải làm gì?",
    "Gọi bố mãi mà bố vẫn không tỉnh.",
    "Mẹ em lay mãi không đáp ứng.",
    "Tôi đang khó thở",
])
def test_urgent_never_waits_for_profile_or_model(service, monkeypatch, message):
    snapshot = Mock(side_effect=AssertionError("urgent boundary contacted meal backend"))
    monkeypatch.setattr(service.meals, "snapshot", snapshot)
    reply = service.chat(ChatRequest(message=message), "audit")
    assert reply.intent == "emergency" and reply.status == "safety"
    assert "115" in reply.answer
    snapshot.assert_not_called()


@pytest.mark.parametrize("message", [
    "Tôi không tính calo, chỉ muốn biết nên ăn rau gì?",
    "Toi khong tinh luong duong moi ngay",
    "Mình không tính tiền món này",
    "Tôi không khó thở, chỉ hỏi về rau",
])
def test_nonurgent_control(message):
    assert classify(message) != "emergency"


def test_urgent_response_survives_history_outage(service, monkeypatch):
    monkeypatch.setattr(service.store, "save_message", Mock(side_effect=HistoryStoreError("offline")))
    reply = service.chat(ChatRequest(message="Bố tôi bất tỉnh", save_history=True), "audit")
    assert reply.status == "safety" and "115" in reply.answer and not reply.history_saved
    assert any("lịch sử" in warning for warning in reply.warnings)


@pytest.mark.parametrize("message", [
    "Theo Bộ Y tế, bữa phụ có cần tính vào khẩu phần cả ngày không?",
    "Bữa phụ có tính vào khẩu phần cả ngày không theo QĐ 5481?",
    "Theo NIDDK, bữa sáng có tác dụng gì?",
])
def test_source_questions_bypass_saved_menu(message):
    assert meal_action(message) is None
    assert meal_action("Bữa trưa của tôi có món gì?") == "show"


@pytest.mark.parametrize("question", ["Tôi cần mua bao nhiêu kg gạo cho cả nhà?",
                                      "Nhà mình nên mua bao nhiêu kg gạo?",
                                      "Tôi nên giảm bao nhiêu kg?"])
def test_kg_question_is_not_a_profile_fact(service, question):
    assert "60 kg" in service.chat(ChatRequest(message="Tôi nặng bao nhiêu?"), "audit").answer
    reply = service.chat(ChatRequest(message=question), "audit")
    if "gạo" in question:
        assert reply.status == "needs_clarification" and "bao nhiêu người" in reply.clarification_question
    else:
        assert reply.status == "insufficient_evidence" and "mục tiêu" in reply.answer
    assert "60 kg" not in reply.answer


@pytest.mark.parametrize("target", ["protein", "đạm", "natri", "carb"])
def test_label_must_answer_the_requested_field(service, target):
    prefix = "Hộp A 200 g có 5 g đường/100 g. Ăn hết hộp A thì có bao nhiêu "
    reply = service.chat(ChatRequest(message=prefix + target + "?"), "audit")
    assert reply.status == "needs_clarification" and reply.clarification_question
    assert target in reply.answer and "10 g" not in reply.answer
    sugar = service.chat(ChatRequest(message=prefix + "đường?"), "audit")
    assert sugar.status == "answered" and "10 g đường" in sugar.answer


def test_switch_from_relative_to_self(service):
    def ask(q, previous=None):
        return service.chat(ChatRequest(message=q, session_id=previous and previous.session_id), "audit")
    first = ask("Em gái tôi đang mang thai, em nên ăn gì?")
    followup = ask("Vậy nên ăn bao nhiêu?", first)
    assert first.scope_restriction == followup.scope_restriction == "special_population"
    answer = ask("Chuyển sang hỏi về tôi, tôi 45 tuổi. Carb là gì?", followup)
    assert answer.status == "answered" and answer.citations and answer.scope_restriction is None
    assert ask("Carb là gì?", answer).status == "answered"


def test_hue_noodles_offer_specific_variant():
    result = get_catalog().execute(FoodPlan(operation="lookup", items=[FoodItem(name="bún bò Huế", amount=100)], nutrients=["calo"]))
    assert not result["items"] and not result["totals"]
    assert any("giò heo" in x["name"] for x in result["unresolved"][0]["candidates"])

@pytest.mark.parametrize("case", json.loads((ROOT / "evals/defense_foods.json").read_text("utf8")),
                         ids=lambda case: case["food"])
def test_exact_serving_via_chat_api(system, case):
    body = system.client.post("/api/chat", json={"message": f"100 g {case['food']} có bao nhiêu calo?"}).json()
    result = body["food_result"]
    if case["outcome"] == "verified":
        assert body["status"] == "answered" and body["citations"][0]["chunk_id"] == case["id"]
        assert str(case["kcal"]) in body["answer"]
        assert result["items"][0]["display_nutrients"][0]["amount_value"] == case["kcal"]
    else:
        assert not result["items"] and not result["totals"] and body["status"] != "answered"
        unresolved = result["unresolved"][0]
        assert unresolved["reason_code"] == case["outcome"]
        if "candidate" in case:
            assert case["candidate"] in {c["name"] for c in unresolved["candidates"]}


@pytest.mark.parametrize(("subject", "kcal"), [("ổ bánh mì thịt", 461), ("đĩa cơm tấm chả", 592),
                                               ("tô phở bò chín", 456)])
def test_reported_serving_has_source_and_distinct_basis(service, subject, kcal):
    r = service.chat(ChatRequest(message=f"Một {subject} có bao nhiêu calo?"), "audit")
    assert r.status == "answered" and str(kcal) in r.answer
    assert r.citations[0].printed_pages == [85] and r.citations[0].document_url.endswith("So-23.pdf")
    from rag_app.nutrition_reference import published_portion_energy
    assert published_portion_energy(f"Hai {subject} có bao nhiêu calo?") is None
    assert published_portion_energy(f"100 g {subject} có bao nhiêu calo?") is None


def test_self_restriction_survives_subject_phrase(service):
    r = service.chat(ChatRequest(message="Tôi đang mang thai."), "audit")
    r = service.chat(ChatRequest(message="Chuyển sang hỏi về tôi. Carb là gì?", session_id=r.session_id), "audit")
    assert r.status == "safety" and not r.restriction_for_relative


def test_retriever_does_not_confuse_muc_level_with_section(shared_corpus):
    from rag_app.retrieval import Retriever
    hits = Retriever(shared_corpus).search("Mức năng lượng khẩu phần cần cá nhân hóa theo những yếu tố nào?")
    assert any(h.chunk.source_id == "byt5481-nutrition" and "5.2.2." in h.chunk.section for h in hits[:5])

def test_user_supplies_missing_label_field(service):
    first = service.chat(ChatRequest(message="Hộp A 200 g có 5 g đường/100 g. Ăn nửa hộp A có bao nhiêu protein?"), "audit")
    second = service.chat(ChatRequest(message="Nhãn ghi 4 g protein/100 g", session_id=first.session_id), "audit")
    assert first.status == "needs_clarification" and second.status == "answered"
    assert "4 g protein" in second.answer and "đường" not in second.answer


def test_label_does_not_answer_an_unknown_field_with_sugar():
    from rag_app.nutrition_reference import label_calculation
    assert label_calculation("Hộp A 200 g có 5 g đường/100 g. Ăn hết hộp A có bao nhiêu kẽm?", []) is None

def test_sourced_snack_question_uses_real_document_and_knowledge_route(system):
    system.app.state.service.meals = MockMealGateway("named")
    response = system.client.post("/api/chat", json={"message":
        "Theo Bộ Y tế, bữa phụ có cần tính vào khẩu phần cả ngày không?"}).json()
    assert response["intent"] == "knowledge" and response["meal_result"] is None
    assert response["response_strategy"] == "evidence_rag"
    assert any("b) Sử dụng bữa phụ" in h.chunk.section for h in system.provider.generate_calls[-1][1])


def test_urgent_followup_keeps_the_trigger(service):
    first = service.chat(ChatRequest(message="Bố tôi bất tỉnh."), "audit")
    second = service.chat(ChatRequest(message="Vậy giờ sao?", session_id=first.session_id), "audit")
    assert second.intent == "emergency" and "115" in second.answer
    assert "Số đo đường huyết bạn nêu" not in second.answer

def test_static_scope_notice_during_provider_outage(system):
    from rag_app.provider import ProviderFailure

    system.provider.error = ProviderFailure("offline")
    response = system.client.post("/api/chat", json={"message": "Tôi muốn viết code Python."}).json()
    assert response["status"] == "insufficient_evidence" and response["answer_origin"] == "static"
    assert "viết mã" in response["answer"] and not response["citations"]


def test_energy_lookup_keeps_source_caveat(system):
    reply = system.client.post("/api/chat", json={"message": "100 g sữa bò tươi có bao nhiêu calo?"}).json()
    assert reply["status"] == "answered" and reply["answer_origin"] == "static"
    assert any("loại thực phẩm đã chọn" in warning for warning in reply["warnings"])
