"""Contract tests against controlled HTTP upstreams; no live API/DB claims."""

import base64
import copy
import json
from contextlib import nullcontext
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from gateway_app.config import GatewaySettings
from gateway_app.integration import (
    Credentials,
    Generate,
    TeamIntegration,
    create_team_router,
    numeric,
    profile_revision,
)


class MemoryState:
    def __init__(self):
        self.ids = {}
        self.values = {}

    def service_id(self, account):
        return self.ids.setdefault(account, 1000000000 + len(self.ids))

    def get(self, account, key, default=None):
        return self.values.get((account, key), default)

    def put(self, account, key, value):
        self.values[account, key] = value

    def operation(self, account):
        return nullcontext()


@pytest.fixture
def bridge():
    account_a, account_b = str(uuid4()), str(uuid4())
    accounts = {"a@example.test": account_a, "b@example.test": account_b}
    calls = []
    dish = {
        "id": 4,
        "nameVi": "Món thử",
        "code": "QA_DISH",
        "role": "PROTEIN_DISH",
        "householdUnitLabel": "1 phần",
        "standardServingCookedG": 100,
        "caloriesKcal": 100,
        "netCarbG": 8,
        "proteinG": 10,
        "fatG": 3,
        "fiberG": 1,
        "sodiumMg": 20,
        "mealSlots": ["LUNCH"],
        "medicalTags": [],
        "recipeBreakdown": [
            {
                "ingredientId": 8,
                "ingredientNameVi": "Nguyên liệu thử",
                "rawWeightG": 120,
            }
        ],
    }
    profile = {
        "dateOfBirth": "1990-01-01",
        "age": date.today().year - 1990,
        "gender": "MALE",
        "height": 170,
        "weight": 70,
        "targetWeight": 65,
        "activityLevel": "LIGHT",
        "goal": "MAINTAIN_WEIGHT",
        "allergies": [],
        "restrictedIngredients": [],
        "preferences": [],
        "updatedAt": "2026-01-01T00:00:00Z",
        "confirmed": True,
        "pregnant": False,
        "specialDiet": False,
        "version": 0,
    }
    plan = {
        "planId": 7,
        "userId": 1000000000,
        "planDate": "2026-11-22",
        "solverStatus": "OPTIMAL",
        "targetCaloriesKcal": 1800,
        "medicalWarnings": [],
        "mealsBySlot": {
            "LUNCH": [
                {
                    "itemId": 9,
                    "dishId": 4,
                    "dishNameVi": "Món thử",
                    "servingMultiplier": 2,
                    "caloriesKcal": 200,
                    "netCarbG": 16,
                    "proteinG": 20,
                    "fatG": 6,
                    "fiberG": 2,
                    "sodiumMg": 40,
                    "isLocked": False,
                    "status": "PLANNED",
                }
            ]
        },
    }
    plans = [plan]

    def upstream(request):
        calls.append(request)
        path = request.url.path
        if request.url.host == "users.test":
            if path == "/api/auth/csrf":
                return httpx.Response(
                    200,
                    json={"headerName": "X-CSRF-TOKEN", "token": "csrf-test"},
                    headers={"Set-Cookie": "JSESSIONID=server-cookie; Path=/"},
                )
            if path == "/api/auth/register":
                assert request.headers.get("X-CSRF-TOKEN") == "csrf-test"
                assert "JSESSIONID=server-cookie" in request.headers.get("cookie", "")
                return httpx.Response(201, json={"success": True, "data": {}})
            auth = request.headers.get("authorization", "")
            decoded = (
                base64.b64decode(auth.removeprefix("Basic ")).decode()
                if auth.startswith("Basic ")
                else ""
            )
            email, _, password = decoded.partition(":")
            if password != "correct-password" or email not in accounts:
                return httpx.Response(401, json={"message": "Mật khẩu không đúng"})
            if path == "/api/users/me":
                return httpx.Response(
                    200,
                    json={
                        "success": True,
                        "data": {
                            "id": accounts[email],
                            "fullName": email,
                            "email": email,
                        },
                    },
                )
            if path == "/api/users/me/profile":
                if request.method == "PUT":
                    body = json.loads(request.content)
                    assert request.headers.get("X-CSRF-TOKEN") == "csrf-test"
                    assert body["expectedVersion"] == profile["version"]
                    profile.update({k: v for k, v in body.items() if k != "expectedVersion"})
                    profile["version"] += 1
                    profile["updatedAt"] = "2026-11-21T12:00:00.123457Z"
                    saved = copy.deepcopy(profile)
                    saved["updatedAt"] = "2026-11-21T12:00:00.123456789Z"
                    return httpx.Response(200, json={"success": True, "data": saved})
                return httpx.Response(200, json={"success": True, "data": profile})
        if path == "/api/v1/dishes/4":
            return httpx.Response(200, json=dish)
        if path == "/api/v1/internal/optimizer/capabilities":
            return httpx.Response(200, json={"excludedDishIds": True, "contractVersion": 1})
        if path == "/api/v1/dishes":
            return httpx.Response(200, json={"content": [dish], "last": True})
        if path == "/api/v1/users/me/food-preferences":
            return httpx.Response(200, json={"favoriteDishes": []})
        if path == "/api/v1/users/me/meal-plans":
            user_id = request.headers.get("X-User-Id")
            return httpx.Response(
                200,
                json={
                    "content": [p for p in plans if str(p["userId"]) == user_id],
                    "last": True,
                },
            )
        if path == "/api/v1/users/me/meal-plans/7":
            # Simulate a compromised/incorrect upstream that returns another user's plan.
            return httpx.Response(200, json=plan)
        if path == "/api/v1/users/me/meal-plans/generate-daily":
            generated = copy.deepcopy(plan)
            generated["planId"] = 8
            plans.append(generated)
            return httpx.Response(201, json=generated)
        return httpx.Response(404, json={"message": "Chưa có endpoint"})

    cfg = GatewaySettings(
        gateway_service_key="test-only-service-key-at-least-32-characters",
        _env_file=None,
        team_integration_enabled=True,
        meal_service_mode="team",
        team_user_url="http://users.test",
        team_catalog_url="http://catalog.test",
        team_optimizer_url="http://optimizer.test",
    )
    team = TeamIntegration(cfg, None, state=MemoryState(), transport=httpx.MockTransport(upstream))
    yield SimpleNamespace(
        team=team, calls=calls, plan=plan, plans=plans, profile=profile, dish=dish
    )
    team.close()


def login(bridge, email="a@example.test"):
    token, user = bridge.team.login(Credentials(email=email, password="correct-password"))
    return token, bridge.team.resolve_token(token), user


def test_login_checks_real_user_service_and_does_not_return_password(bridge):
    token, session, user = login(bridge)
    assert user["id"] == session.account["id"] and user["demo"] is False
    assert "correct-password" not in repr(session)
    assert not user.get("accessToken")
    assert len(token) >= 48
    with pytest.raises(HTTPException) as error:
        bridge.team.login(Credentials(email="a@example.test", password="wrong-password"))
    assert error.value.status_code == 401


def test_register_uses_upstream_csrf_and_cookie(bridge):
    token, user = bridge.team.login(
        Credentials(name="Test", email="a@example.test", password="correct-password"),
        register=True,
    )
    assert user["email"] == "a@example.test" and token
    assert any(r.url.path == "/api/auth/register" for r in bridge.calls)


def test_account_mapping_is_stable_and_not_shared(bridge):
    _, a, _ = login(bridge)
    _, a_again, _ = login(bridge)
    _, b, _ = login(bridge, "b@example.test")
    assert a.service_id == a_again.service_id != b.service_id
    assert a.service_id != 1


def test_unauthenticated_and_expired_sessions_are_denied(bridge):
    with pytest.raises(HTTPException) as error:
        bridge.team.resolve_token("invented")
    assert error.value.status_code == 401
    token, session, _ = login(bridge)
    session.expires = 0
    with pytest.raises(HTTPException):
        bridge.team.resolve_token(token)


def test_plan_owner_is_checked_even_if_upstream_returns_wrong_user(bridge):
    _, b, _ = login(bridge, "b@example.test")
    # Ensure b differs from the seeded plan owner.
    bridge.plan["userId"] = b.service_id + 1
    with pytest.raises(HTTPException) as error:
        bridge.team.raw_plan(b, "7")
    assert error.value.status_code == 404


def test_food_has_real_raw_ingredients_and_no_invented_time(bridge):
    food = bridge.team.food(bridge.dish)
    assert food["minutes"] is None
    assert food["ingredients"] == [{"id": "8", "name": "Nguyên liệu thử", "grams": 120}]
    assert food["steps"] == []
    assert food["ingredientBasis"] == "raw"


def test_missing_nutrition_is_not_replaced_with_zero(bridge):
    broken = dict(bridge.dish, sodiumMg=None)
    with pytest.raises(HTTPException):
        bridge.team.food(broken)


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -1, True, "missing"])
def test_invalid_quantities_rejected(value):
    with pytest.raises(HTTPException):
        numeric(value)


def test_plan_and_chat_preserve_item_snapshot_without_double_servings(bridge):
    _, a, _ = login(bridge)
    plan = bridge.team.plan(a, bridge.plan)
    assert plan["items"][0]["servings"] == 2
    assert plan["items"][0]["nutrition"]["energy"] == 200
    snapshot = bridge.team.snapshot(a, "7")
    assert snapshot["dataMode"] == "http"
    assert snapshot["plan"]["totals"]["energyKcal"] == 200
    assert snapshot["plan"]["items"][0]["amount"] == 2
    assert snapshot["plan"]["validationPassed"] is False
    assert snapshot["plan"]["target"]["bounds"] == {}
    assert snapshot["plan"]["target"]["pointTargets"]["energy_kcal"] == 1800


def test_absent_today_does_not_silently_select_a_historical_plan(bridge):
    _, a, _ = login(bridge)
    bridge.plan["planDate"] = "2000-01-01"
    with pytest.raises(HTTPException) as error:
        bridge.team.snapshot(a)
    assert error.value.status_code == 404


def test_workspace_contains_backend_data_and_no_sample_checkins(bridge):
    _, a, _ = login(bridge)
    workspace = bridge.team.workspace(a)
    assert workspace["profile"]["dateOfBirth"] == "1990-01-01"
    assert workspace["checkIns"] == [] and workspace["conversations"] == []
    assert workspace["plans"][0]["id"] == "7"
    assert workspace["capabilities"]["swap"] is False


def generation(bridge, session, **overrides):
    bridge.team.state.put(
        session.account["id"],
        "profileMeta",
        {"revision": profile_revision(bridge.profile), "confirmed": True},
    )
    return Generate.model_validate(
        {
            "date": "2026-11-22",
            "target": 1800,
            "snacks": True,
            "maxMinutes": 0,
            "excludeRepeat": False,
            "profileVersion": profile_revision(bridge.profile),
            **overrides,
        }
    )


def test_generate_never_calls_unsafe_overwrite_for_existing_day(bridge):
    _, a, _ = login(bridge)
    with pytest.raises(HTTPException) as error:
        bridge.team.generate(a, generation(bridge, a))
    assert error.value.status_code == 409
    assert not any(r.method == "POST" and "generate-daily" in r.url.path for r in bridge.calls)
    assert bridge.plans[0]["solverStatus"] == "OPTIMAL"


def test_generate_new_day_calls_real_optimizer_contract(bridge):
    _, a, _ = login(bridge)
    request = generation(bridge, a)
    bridge.plans.clear()
    plan = bridge.team.generate(a, request)
    assert plan["id"] == "8" and plan["profileVersion"] == profile_revision(bridge.profile)
    request = next(r for r in bridge.calls if r.method == "POST" and "generate-daily" in r.url.path)
    assert request.headers["X-User-Id"] == str(a.service_id)
    assert b"STANDARD_4_MEALS" in request.content


@pytest.mark.parametrize(
    "overrides",
    [
        {"snacks": False},
        {"maxMinutes": 30},
        {"excludeRepeat": True},
        {"profileVersion": 1},
    ],
)
def test_unsupported_or_stale_generate_is_rejected_before_solver(bridge, overrides):
    _, a, _ = login(bridge)
    with pytest.raises(HTTPException):
        bridge.team.generate(a, generation(bridge, a, **overrides))
    assert not any("generate-daily" in r.url.path for r in bridge.calls)


def test_unresolved_allergy_is_not_ignored(bridge):
    _, a, _ = login(bridge)
    bridge.profile["allergies"] = ["Lúa mì"]
    with pytest.raises(HTTPException) as error:
        bridge.team.generate(a, generation(bridge, a))
    assert error.value.status_code == 422
    assert not any("generate-daily" in r.url.path for r in bridge.calls)


def test_logout_revokes_server_session(bridge):
    token, _, _ = login(bridge)
    router = create_team_router(bridge.team)
    endpoint = next(
        route.endpoint for route in router.routes if route.path.endswith("/auth/logout")
    )
    request = SimpleNamespace(cookies={"nutriguide_session": token})
    response = endpoint(request)
    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    with pytest.raises(HTTPException):
        bridge.team.resolve_token(token)


def test_router_exposes_valid_fastapi_contract(bridge):
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(create_team_router(bridge.team))
    schema = app.openapi()
    assert "/api/workspace" in schema["paths"]
    assert "/api/meal-plans/{plan_id}/items/{item_id}/lock" in schema["paths"]
    assert (
        schema["components"]["schemas"]["UIProfile"]["properties"]["dateOfBirth"]["format"]
        == "date"
    )
