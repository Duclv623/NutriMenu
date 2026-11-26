import re
from pathlib import Path

from fastapi.testclient import TestClient

from gateway_app.integration import COOKIE
from gateway_app.main import create_app
from gateway_app.service_actions import ACTIONS
from test_team_bridge import login


ROOT = Path(__file__).resolve().parents[2]


def normalized(path):
    path = re.sub(r"internal/optimizer/users/\{\w+\}/recent-dishes",
                  "internal/optimizer/users/me/recent-dishes", path)
    return re.sub(r"\{\w+\}", "{}", path).strip("/")


def test_frontend_and_gateway_cover_every_java_controller_mapping():
    java = set()
    for service, project in (("catalog", "foodcatalogservice"), ("optimizer", "mealoptimizerservice")):
        for file in (ROOT / project / "src/main/java").rglob("*Controller.java"):
            source = file.read_text(encoding="utf-8")
            prefix = re.search(r'@RequestMapping\("/api/v1(.*?)"\)', source)[1]
            for method, suffix in re.findall(r'@(Get|Post|Put|Patch|Delete)Mapping(?:\("(.*?)"\))?', source):
                java.add((service, method.upper(), normalized(prefix + suffix)))
    gateway = {(service, method, normalized(path))
               for service, entries in ACTIONS.items() for method, path, _, _ in entries}
    source = (ROOT / "frontend/src/services/serviceActions.ts").read_text(encoding="utf-8")
    constructors = {
        "catalog": ("catalog", ""), "optimizer": ("optimizer", ""),
        "meal": ("optimizer", "users/me/meal-plans"), "settings": ("optimizer", "admin/optimizer/"),
    }
    frontend = {
        (constructors[name][0], method, normalized(constructors[name][1] + path))
        for name, method, path in re.findall(
            r'\b(catalog|optimizer|meal|settings)\(\s*"(GET|POST|PUT|PATCH|DELETE)",\s*"([^"]*)"', source,
        )
    }
    assert len(java) == 61
    assert java == gateway == frontend


def test_identity_comes_from_user_service_and_admin_role_is_checked_on_each_request(bridge, monkeypatch):
    cookie, session, _ = login(bridge)
    app = create_app(bridge.team.settings, integration=bridge.team)
    client = TestClient(app, cookies={COOKIE: cookie})
    assert client.get("/api/service-actions/catalog/admin/ingredients").status_code == 403
    assert client.get("/api/service-actions/catalog/unlisted").status_code == 404
    assert client.get("/api/service-actions/catalog/dishes?userId=42", headers={"X-User-Id": "42"}).status_code == 200
    request = bridge.calls[-1]
    assert request.headers["X-User-Id"] == str(session.service_id)
    assert "userId" not in request.url.params

    original = bridge.team.call

    def upstream(service, method, path, **kwargs):
        if path == "api/users/me":
            account = original(service, method, path, **kwargs)
            account["data"]["role"] = "ADMIN"
            return account
        if path == "api/v1/admin/ingredients":
            return {"content": [], "last": True}
        return original(service, method, path, **kwargs)

    monkeypatch.setattr(bridge.team, "call", upstream)
    assert client.get("/api/service-actions/access").json() == {"role": "ADMIN"}
    assert client.get("/api/service-actions/catalog/admin/ingredients").status_code == 200
    assert TestClient(app).get("/api/service-actions/catalog/dishes").status_code == 401


def test_generation_from_profile_uses_authoritative_fields_and_filters(bridge, monkeypatch):
    cookie, _, _ = login(bridge)
    bridge.profile["allergies"] = ["Trứng"]
    bridge.profile["restrictedIngredients"] = ["Nguyên liệu thử"]
    client = TestClient(create_app(bridge.team.settings, integration=bridge.team), cookies={COOKIE: cookie})
    original = bridge.team.call
    generated = {**bridge.plan, "planId": 8, "planDate": "2026-11-29", "mealsBySlot": {}}
    captured = []

    def upstream(service, method, path, **kwargs):
        if path == "api/v1/internal/optimizer/capabilities":
            return {"profilePolicyActions": True}
        if path.endswith("/generate-from-profile"):
            captured.append(kwargs)
            return {"optimalMealPlan": generated}
        return original(service, method, path, **kwargs)

    monkeypatch.setattr(bridge.team, "call", upstream)
    response = client.post("/api/service-actions/optimizer/users/me/meal-plans/generate-from-profile", json={
        "planDate": "2026-11-29", "profileVersion": 1, "gender": "FEMALE",
        "heightMeters": 1.5, "actualWeightKg": 120, "hasHypertension": True,
    })
    assert response.status_code == 200, response.text
    assert captured[0]["headers"]["X-User-Id"] == "1000000000"
    assert captured[0]["json"] == {
        "planDate": "2026-11-29", "gender": "MALE", "heightMeters": 1.7, "actualWeightKg": 70,
        "activityLevel": "LIGHT", "hasHypertension": True,
        "additionalAllergens": ["ALLERGEN_EGG"], "excludedDishIds": [4],
    }


def test_catalog_candidates_and_recent_dishes_use_the_session_owner(bridge, monkeypatch):
    login(bridge)
    cookie, session, _ = login(bridge, "b@example.test")
    client = TestClient(create_app(bridge.team.settings, integration=bridge.team), cookies={COOKIE: cookie})
    original = bridge.team.call
    captured = []

    def upstream(service, method, path, **kwargs):
        if path.endswith(("/candidates", "/recent-dishes")):
            captured.append((path, kwargs))
            return []
        return original(service, method, path, **kwargs)

    monkeypatch.setattr(bridge.team, "call", upstream)
    candidates = client.post("/api/service-actions/catalog/internal/dishes/candidates", json={"userId": 42})
    recent = client.get("/api/service-actions/optimizer/internal/optimizer/users/me/recent-dishes?days=2&userId=42")
    assert candidates.status_code == recent.status_code == 200
    assert captured[0][1]["json"]["userId"] == session.service_id
    assert captured[1][0].endswith(f"/users/{session.service_id}/recent-dishes")
    assert captured[1][1]["params"] == {"days": "2"}
    assert client.get("/api/service-actions/optimizer/users/me/meal-plans/7").status_code == 404


def test_workspace_keeps_skipped_items_available_for_restore_and_preserves_existing_totals(bridge):
    _, session, _ = login(bridge)
    item = bridge.plan["mealsBySlot"]["LUNCH"][0]
    item["status"] = "SKIPPED"
    bridge.plan["userRating"] = 4
    bridge.plan["userFeedback"] = "Bữa trưa vừa khẩu phần."
    workspace = bridge.team.workspace(session)
    plan = workspace["plans"][0]
    assert plan["items"] == []
    assert plan["skippedItems"][0]["id"] == str(item["itemId"])
    assert plan["skippedItems"][0]["name"] == item["dishNameVi"]
    assert plan["rating"] == 4
    assert plan["feedback"] == bridge.plan["userFeedback"]
    assert workspace["role"] == "USER"
    assert workspace["foods"][0]["listed"] is True
