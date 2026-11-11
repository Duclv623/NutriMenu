import time
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from rag_app.config import Settings
from rag_app.main import create_app
from rag_app.meal_chat import handle_meal_chat, meal_action
from rag_app.meal_gateway import (
    HttpMealGateway,
    MealServiceError,
    MockMealGateway,
    check_plan,
    validate_proposal,
)
from rag_app.meal_models import (
    ApplySwap,
    MealContext,
    MealPlan,
    NutritionProfile,
    SwapRequest,
)


@pytest.fixture
def meals():
    return MockMealGateway()


@pytest.fixture
def meal_client(tmp_path):
    cfg = Settings(_env_file=None, storage_dir=tmp_path, gemini_api_key="", openai_api_key="", meal_service_mode="mock")
    with TestClient(create_app(cfg)) as client:
        yield client


def swap_request(snapshot, instruction="Đổi món sáng", item_id="breakfast-1"):
    return SwapRequest(plan_id=snapshot.plan.id, base_version=snapshot.plan.version,
                       item_id=item_id, instruction=instruction)


def test_doc_example_and_missing_values_are_not_zero(meals):
    snapshot = meals.snapshot("a")
    assert snapshot.plan.totals.energy_kcal == 1767
    assert snapshot.plan.totals.carbohydrate_g == 253
    assert snapshot.plan.totals.fiber_g is None and snapshot.plan.totals.sodium_mg is None
    assert snapshot.plan.solver_status == "NOT_RUN"
    assert not check_plan(snapshot.plan, snapshot.profile, mock=True)
    reply = handle_meal_chat(meals, "a", "Bữa trưa của tôi có bao nhiêu carbohydrate?")
    assert "95 g" in reply.answer and reply.payload["dataMode"] == "mock"
    assert reply.payload["context"]["item_id"] == "lunch-1"
    missing = handle_meal_chat(meals, "a", "Toàn ngày bao nhiêu chất xơ?", MealContext(plan_id=snapshot.plan.id))
    assert "chưa có dữ liệu" in missing.answer
    assert missing.payload['plan']['totals']['fiberG'] is None


def test_preview_does_not_mutate_and_apply_revalidates_version(meals):
    before = meals.snapshot("a")
    proposal = meals.preview("a", swap_request(before))
    assert meals.snapshot("a").plan.version == 1
    assert proposal.plan.totals.energy_kcal == 1781
    assert proposal.plan.items[1:] == before.plan.items[1:]
    apply = ApplySwap(plan_id=before.plan.id, proposal_id=proposal.id, base_version=1)
    after = meals.apply("a", apply)
    assert after.plan.version == 2 and after.plan.totals.carbohydrate_g == 252
    with pytest.raises(MealServiceError) as error:
        meals.apply("a", apply)
    assert error.value.code == "NOT_FOUND"
    with pytest.raises(MealServiceError) as stale:
        meals.preview("a", swap_request(before))
    assert stale.value.code == "STALE_PLAN"


def test_doc_example_d_is_rejected_despite_better_energy(meals):
    before = meals.snapshot("a")
    with pytest.raises(MealServiceError) as error:
        meals.preview("a", swap_request(before, "Đổi sang demo:D"))
    assert error.value.code == "NO_FEASIBLE_PLAN"
    assert meals.snapshot("a").plan == before.plan


def test_owner_isolation_and_proposal_ownership(meals):
    before = meals.snapshot("a")
    proposal = meals.preview("a", swap_request(before))
    assert meals.snapshot("b").plan.id != before.plan.id
    with pytest.raises(MealServiceError) as missing:
        meals.snapshot("b", plan_id=before.plan.id)
    assert missing.value.code == "NOT_FOUND"
    with pytest.raises(MealServiceError):
        meals.apply("b", ApplySwap(plan_id=before.plan.id, proposal_id=proposal.id, base_version=1))


@pytest.mark.parametrize("changes,code", [
    ({"allergies": None}, "PROFILE_INCOMPLETE"),
    ({"restricted_ingredients": None}, "PROFILE_INCOMPLETE"),
    ({"restrictions_resolved": False}, "PROFILE_INCOMPLETE"),
    ({"scope_status": "unknown"}, "PROFILE_INCOMPLETE"),
    ({"scope_status": "out_of_scope"}, "OUT_OF_SCOPE"),
    ({"profile_version": 2}, "STALE_PLAN"),
])
def test_profile_guards_before_swap(meals, changes, code):
    before = meals.snapshot("a")
    meals.states["a"][1].profile = before.profile.model_copy(update=changes)
    with pytest.raises(MealServiceError) as error:
        meals.preview("a", swap_request(before))
    assert error.value.code == code


def test_new_exclusion_rechecked_before_apply(meals):
    before = meals.snapshot("a")
    proposal = meals.preview("a", swap_request(before))
    meals.states["a"][1].profile.excluded_ingredient_ids = ["demo:ingredient-a2"]
    with pytest.raises(MealServiceError) as error:
        meals.apply("a", ApplySwap(plan_id=before.plan.id, proposal_id=proposal.id, base_version=1))
    assert error.value.code == "DATA_INCOMPLETE"
    assert meals.snapshot("a").plan.version == 1


def test_expiry_and_new_profile_invalidate_proposals(meals):
    before = meals.snapshot("a")
    proposal = meals.preview("a", swap_request(before))
    meals.proposals[str(proposal.id)][1].expires_at = time.time() - 1
    with pytest.raises(MealServiceError) as error:
        meals.apply("a", ApplySwap(plan_id=before.plan.id, proposal_id=proposal.id, base_version=1))
    assert error.value.code == "PROPOSAL_EXPIRED"


def test_followup_changes_meal_and_whole_day_scope(meals):
    before = meals.snapshot("a")
    context = MealContext(plan_id=before.plan.id, plan_version=1, item_id="breakfast-1")
    lunch = handle_meal_chat(meals, "a", "Bữa trưa bao nhiêu kcal?", context)
    assert "662 kcal" in lunch.answer
    whole = handle_meal_chat(meals, "a", "Cả ngày bao nhiêu kcal?", context)
    assert "1767 kcal" in whole.answer
    ambiguous = handle_meal_chat(meals, "a", "Đổi món trong thực đơn của tôi")
    assert ambiguous.status == "needs_clarification" and len(ambiguous.payload["choices"]) == 3
    assert meal_action("Chất xơ có vai trò gì?", context) is None
    assert meal_action("Theo tài liệu, ăn cơm thế nào?", context) is None
    assert meal_action("Protein có tác dụng gì?", context) is None
    assert meal_action("Vì sao bữa trưa nhiều đạm?", context) == "explain"


def test_sugar_is_not_inferred_from_carbohydrate(meals):
    reply = handle_meal_chat(meals, "a", "Bữa trưa có bao nhiêu đường?")
    assert reply.status == "insufficient_evidence"
    assert "không suy lượng đường từ carbohydrate" in reply.answer


def test_snapshot_schema_rejects_bad_totals_nonfinite_and_resolved_empty_exclusions(meals):
    before = meals.snapshot("a")
    values = before.plan.model_dump()
    values["totals"]["energyKcal"] = 0
    with pytest.raises(ValidationError):
        MealPlan.model_validate(values)
    profile = before.profile.model_dump()
    profile["weight"] = float("nan")
    with pytest.raises(ValidationError):
        NutritionProfile.model_validate(profile)
    profile.update(weight=60, allergies=["unknown ingredient"])
    with pytest.raises(ValidationError):
        NutritionProfile.model_validate(profile)


def test_proposal_cannot_silently_change_locked_meals(meals):
    before = meals.snapshot("a")
    request = swap_request(before)
    proposal = meals.preview("a", request)
    changed = proposal.plan.items[1].model_copy(update={"name": "Changed another meal"})
    proposal.plan.items[1] = changed
    with pytest.raises(MealServiceError) as error:
        validate_proposal(before, request, proposal)
    assert error.value.code == "DATA_INCOMPLETE"


def test_api_flow_without_llm_and_opt_in_history(meal_client):
    client = meal_client
    context = client.get("/api/meal-context").json()
    assert context["dataMode"] == "mock"
    first = client.post("/api/chat", json={"message": "Xem thực đơn hôm nay của tôi"}).json()
    assert first["status"] == "answered" and first["answer_origin"] == "static"
    assert not first["citations"] and not first["usage"]
    follow = client.post("/api/chat", json={"message": "Bữa sáng bao nhiêu kcal?", "session_id": first["session_id"]}).json()
    assert "476 kcal" in follow["answer"]
    changed = client.post("/api/chat", json={"message": "Đổi món này", "session_id": first["session_id"]}).json()
    proposal = changed["meal_result"]["proposal"]
    assert client.get("/api/meal-context").json()["plan"]["version"] == 1
    applied = client.post("/api/meal-plans/apply-swap", json={"planId": proposal["planId"], "proposalId": proposal["id"], "baseVersion": 1})
    assert applied.status_code == 200 and applied.json()["plan"]["version"] == 2
    assert client.get("/api/sessions").json() == []
    saved = client.post("/api/chat", json={"message": "Xem thực đơn hôm nay của tôi", "save_history": True}).json()
    assert saved["history_saved"]
    assert client.get(f"/api/sessions/{saved['session_id']}").json()


def test_safety_precedes_explicit_meal_action(meal_client):
    result = meal_client.post("/api/chat", json={"message": "Tôi đang mang thai", "meal_action": "show"}).json()
    assert result["status"] == "safety" and result["meal_result"] is None


def test_api_context_cannot_supply_or_override_profile(meal_client):
    result = meal_client.post("/api/chat", json={"message": "Xem thực đơn", "profile": {"allergies": []}})
    assert result.status_code == 422
    result = meal_client.get("/api/meal-context?plan_id=../other")
    assert result.status_code == 422
    result = meal_client.post("/api/meal-plans/apply-swap", json={"planId": str(uuid4()), "proposalId": str(uuid4()), "baseVersion": 1}, headers={"Origin": "https://other.example"})
    assert result.status_code == 403


def test_unknown_allergies_and_preferences_remain_distinct():
    p = NutritionProfile(profile_version=1, preferences=["egg"])
    assert p.allergies is None and not p.excluded_ingredient_ids
    assert p.preferences == ["egg"] and p.goal is None and p.target_weight is None


def http_snapshot(meals):
    value = meals.snapshot("a").model_dump(mode="json")
    value["dataMode"] = "http"
    value["plan"]["solverStatus"] = "FEASIBLE"
    for item in value["plan"]["items"]:
        item.update(state="cooked", nutritionBasis="as_consumed")
    return value


def http_gateway(handler):
    settings = Settings(_env_file=None, meal_service_mode="http", meal_api_base_url="https://backend.example/api/")
    return HttpMealGateway(settings, transport=httpx.MockTransport(handler))


def test_http_forwards_bearer_only_to_fixed_backend_and_no_fallback(meals):
    calls = []
    value = http_snapshot(meals)

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=value)

    gateway = http_gateway(handler)
    try:
        with pytest.raises(MealServiceError) as auth:
            gateway.snapshot("a")
        assert auth.value.code == "AUTH_REQUIRED" and not calls
        snapshot = gateway.snapshot("a", "Bearer user-token")
        assert snapshot.data_mode == "http" and calls[0].url.path == "/api/me/meal-context"
        assert calls[0].headers["authorization"] == "Bearer user-token"
        assert "user-token" not in str(calls[0].url)
        assert gateway.status()["connected"]
    finally:
        gateway.close()
    for status in [302, 404, 503]:
        gateway = http_gateway(lambda request, code=status: httpx.Response(code, headers={"Location": "https://other.example"}))
        with pytest.raises(MealServiceError):
            gateway.snapshot("a", "Bearer user-token")
        gateway.close()
    gateway = http_gateway(lambda request: httpx.Response(200, json=meals.snapshot("a").model_dump(mode="json")))
    with pytest.raises(MealServiceError):
        gateway.snapshot("a", "Bearer user-token")
    gateway.close()


@pytest.mark.parametrize("solver_status,expected", [("INFEASIBLE", "NO_FEASIBLE_PLAN"), ("UNKNOWN", "SOLVER_UNRESOLVED"), ("MODEL_INVALID", "MODEL_INVALID")])
def test_solver_statuses_are_not_conflated(meals, solver_status, expected):
    value = http_snapshot(meals)
    value["plan"]["solverStatus"] = solver_status
    gateway = http_gateway(lambda request: httpx.Response(200, json=value))
    with pytest.raises(MealServiceError) as error:
        gateway.snapshot("a", "Bearer test")
    assert error.value.code == expected
    gateway.close()


def test_http_rejects_malformed_data_and_timeout(meals):
    value = http_snapshot(meals)
    value["plan"]["totals"]["energyKcal"] = 0
    gateway = http_gateway(lambda request: httpx.Response(200, json=value))
    with pytest.raises(MealServiceError):
        gateway.snapshot("a", "Bearer test")
    gateway.close()


def test_http_preview_and_apply_use_same_contract_and_no_implicit_commit(meals):
    before = meals.snapshot("a")
    proposed = meals.preview("a", swap_request(before))
    snapshot = http_snapshot(meals)
    preview = proposed.model_dump(mode="json")
    preview["dataMode"] = "http"
    preview["plan"]["solverStatus"] = "FEASIBLE"
    for item in preview["plan"]["items"]:
        item.update(state="cooked", nutritionBasis="as_consumed")
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.method == "GET":
            return httpx.Response(200, json=snapshot)
        if request.url.path.endswith("swap-preview"):
            return httpx.Response(200, json=preview)
        updated = {**snapshot, "plan": preview["plan"]}
        return httpx.Response(200, json=updated)

    gateway = http_gateway(handler)
    proposal = gateway.preview("a", swap_request(before), "Bearer test")
    assert not any(path.endswith("apply-swap") for path in calls)
    after = gateway.apply("a", ApplySwap(plan_id=before.plan.id, base_version=1, proposal_id=proposal.id), "Bearer test")
    assert after.plan.version == 2 and after.plan.totals.energy_kcal == 1781
    assert calls[-1] == "/api/me/meal-plans/apply-swap"
    gateway.close()

    def timeout(request):
        raise httpx.ReadTimeout("private internal details")

    gateway = http_gateway(timeout)
    with pytest.raises(MealServiceError) as error:
        gateway.snapshot("a", "Bearer test")
    assert "private" not in str(error.value)
    gateway.close()


def test_mock_is_rejected_in_production_before_startup():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", meal_service_mode="mock")


def test_http_configuration_rejects_tokens_and_userinfo():
    for url in ["https://backend.example/api?token=secret", "https://user:secret@backend.example/api", "file:///tmp/data"]:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, meal_service_mode="http", meal_api_base_url=url)
