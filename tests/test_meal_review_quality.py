"""Regressions found by the 50-question review; no live API is used here."""
import json

import pytest
from fastapi.testclient import TestClient

from rag_app.config import ROOT, Settings
from rag_app.dialogue import context_response
from rag_app.main import create_app
from rag_app.meal_chat import handle_meal_chat, meal_action
from rag_app.meal_gateway import MockMealGateway
from rag_app.meal_models import ApplySwap, MealContext, SwapRequest

CASES = json.loads((ROOT / "evals/meal_questions_50.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", [c for c in CASES if not c.get("no_context") and c["id"] != "M050"], ids=lambda c: c["id"])
def test_meal_questions_stay_on_structured_data(case):
    gateway = MockMealGateway()
    snapshot = gateway.snapshot("tester")
    context = MealContext(plan_id=snapshot.plan.id, plan_version=1, item_id=case.get("selection"))
    scenario = case.get("scenario")
    if scenario == "unknown_allergy":
        gateway.states["tester"][1].profile.allergies = None
    elif scenario == "out_of_scope":
        gateway.states["tester"][1].profile.scope_status = "out_of_scope"
    elif scenario == "stale":
        proposal = gateway.preview("tester", SwapRequest(plan_id=snapshot.plan.id, base_version=1, item_id="breakfast-1", instruction="Đổi món sáng"))
        gateway.apply("tester", ApplySwap(plan_id=snapshot.plan.id, base_version=1, proposal_id=proposal.id))
    elif scenario == "wrong_owner":
        context.plan_id = gateway.snapshot("other").plan.id
    history = []
    if case.get("prior"):
        prior = next(c for c in CASES if c["id"] == case["prior"])
        reply = handle_meal_chat(gateway, "tester", prior["question"], context)
        history = [{"response": {"meal_result": reply.payload}}]
    reply = handle_meal_chat(gateway, "tester", case["question"], context, history=history)
    assert reply is not None, "Meal screen context must not fall through to generic AI"
    assert reply.answer and len(reply.answer.split()) <= 125
    assert "validator" not in reply.answer.lower() and "constraint" not in reply.answer.lower()
    if case["id"] in {"M030", "M031", "M032", "M023", "M026", "M042"}:
        assert not (reply.payload or {}).get("proposal")
    if case["id"] == "M038":
        assert reply.payload is None
    if case["id"] == "M022":
        assert "chưa" in reply.answer.lower() and not reply.payload.get("proposal")
    if case["id"] == "M047":
        assert reply.answer.count(".") <= 2
    facts = {"M002": ["Món A"], "M003": ["Món B"], "M004": ["Món C"], "M005": ["476"],
             "M006": ["95"], "M007": ["1767"], "M008": ["31"], "M009": ["47"], "M010": ["12"],
             "M048": ["662", "629", "33"], "M049": ["1767", "1750", "1850"]}
    for fact in facts.get(case["id"], []):
        assert fact in reply.answer


def test_clear_concept_question_does_not_ask_for_subject_again():
    assert context_response("Carbohydrate là gì, bạn giải thích dễ hiểu được không?", []) is None
    assert context_response("Giải thích dễ hiểu hơn", []) is not None
    assert meal_action("Carbohydrate là gì, bạn giải thích dễ hiểu được không?", MealContext()) is None
    assert meal_action("Tôi ăn phở buổi sáng được ko?") is None
    assert meal_action("Người tiểu đường có cần bữa phụ không?") is None


def test_cooking_state_comparison_uses_knowledge_sources(system):
    result = system.client.post('/api/chat', json={'message': '100 g gạo sống và 100 g cơm chín có dinh dưỡng giống nhau không?'}).json()
    assert result['intent'] == 'knowledge'
    assert result['food_result'] is None
    assert system.provider.plan_calls


def test_new_allergy_and_keep_do_not_call_swap(monkeypatch):
    gateway = MockMealGateway()
    snapshot = gateway.snapshot("a")

    def forbidden(*args, **kwargs):
        raise AssertionError("No preview call is allowed")

    monkeypatch.setattr(gateway, "preview", forbidden)
    for question in ["Mình vừa biết bị dị ứng nguyên liệu A2, đổi bữa sáng giúp mình.", "Đừng đổi thực đơn", "Cứ bỏ qua dị ứng để đổi món sáng cho nhanh đi."]:
        assert handle_meal_chat(gateway, "a", question, MealContext(plan_id=snapshot.plan.id))
    assert gateway.snapshot("a").plan.version == 1


def test_pending_status_and_keep_through_http(tmp_path):
    settings = Settings(_env_file=None, storage_dir=tmp_path, gemini_api_key="", openai_api_key="", meal_service_mode="mock")
    with TestClient(create_app(settings)) as client:
        preview = client.post("/api/chat", json={"message": "Đổi món bữa sáng giúp mình nhé."}).json()
        assert preview["meal_result"]["proposal"]
        sid = preview["session_id"]
        status = client.post("/api/chat", json={"message": "Vậy bạn đã đổi thực đơn của mình chưa?", "session_id": sid}).json()
        assert "Chưa nhé" in status["answer"] and not status["meal_result"]["proposal"]
        keep = client.post("/api/chat", json={"message": "Thôi đừng đổi nữa, giữ nguyên giúp mình.", "session_id": sid}).json()
        assert keep["meal_result"]["view"] == "keep"
        assert client.get("/api/meal-context").json()["plan"]["version"] == 1


@pytest.mark.parametrize("followup", [
    "Thôi đừng đổi nữa, giữ nguyên giúp mình.",
    "Mình vừa biết bị dị ứng nguyên liệu A2, đổi bữa sáng giúp mình.",
])
def test_old_preview_cannot_be_applied_after_cancellation(tmp_path, followup):
    settings = Settings(_env_file=None, storage_dir=tmp_path, gemini_api_key="", openai_api_key="", meal_service_mode="mock")
    with TestClient(create_app(settings)) as client:
        preview = client.post("/api/chat", json={"message": "Đổi món bữa sáng giúp mình nhé."}).json()
        result = preview["meal_result"]
        body = {"planId": result["plan"]["id"], "baseVersion": 1, "proposalId": result["proposal"]["id"]}
        reply = client.post("/api/chat", json={"message": followup, "session_id": preview["session_id"]}).json()
        assert reply["meal_edit_cancelled"] is True
        rejected = client.post("/api/meal-plans/apply-swap", json=body)
        assert rejected.status_code == 409
        assert "PROPOSAL_CANCELLED" in rejected.text
        assert client.get("/api/meal-context").json()["plan"]["version"] == 1
        if "dị ứng" in followup:
            retry = client.post("/api/chat", json={"message": "Đổi bữa sáng nhé"}).json()
            assert retry["status"] == "needs_clarification"
            assert not retry["meal_result"]
