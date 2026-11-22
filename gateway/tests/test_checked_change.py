"""Gateway contract checks with controlled HTTP; not live Java/PostgreSQL."""

import copy

import pytest
from fastapi import HTTPException
from test_team_bridge import login

from gateway_app.integration import MealChange


def setup_change(bridge):
    _, session, _ = login(bridge)
    bridge.plan["version"] = 0
    bridge.team.state.put(session.account["id"], "plan:7", {"profileVersion": 1})
    body = MealChange(baseVersion=1, profileVersion=1, itemId="9", foodId="4", servings=1.5)
    return session, body


def intercept(bridge, monkeypatch, *, valid=True):
    original = bridge.team.call
    changes = []

    def call(client, method, path, **kwargs):
        if path.endswith(("change-preview", "change-apply")):
            changes.append((path, kwargs))
            result = copy.deepcopy(bridge.plan)
            result.update(validationPassed=valid, changeSignature="signature")
            result["mealsBySlot"]["LUNCH"][0]["servingMultiplier"] = 1.5
            if path.endswith("change-apply"):
                result["version"] = 1
            return result
        return original(client, method, path, **kwargs)

    monkeypatch.setattr(bridge.team, "call", call)
    return changes


def test_preview_and_apply_forward_versions_owner_and_signature(bridge, monkeypatch):
    session, body = setup_change(bridge)
    changes = intercept(bridge, monkeypatch)
    preview = bridge.team.checked_change(session, "7", body, preview=True)
    assert preview["version"] == 1 and preview["changeSignature"] == "signature"
    assert bridge.plan["version"] == 0  # preview did not modify our upstream plan
    body.previewSignature = preview["changeSignature"]
    applied = bridge.team.checked_change(session, "7", body, preview=False)
    assert applied["version"] == 2 and applied["validationPassed"]
    assert changes[0][1]["json"] == dict(
        expectedVersion=0,
        itemId=9,
        newDishId=4,
        newServingScaledX2=3,
        excludedDishIds=[],
        contraindications=[],
        previewSignature=None,
    )
    assert changes[1][1]["json"]["previewSignature"] == "signature"
    assert changes[1][1]["headers"]["X-User-Id"] == str(session.service_id)


@pytest.mark.parametrize(
    "scenario,code",
    [("stale", 409), ("profile", 409), ("legacy", 503), ("quarter", 422), ("no_preview", 422)],
)
def test_bad_changes_never_reach_optimizer(bridge, monkeypatch, scenario, code):
    session, body = setup_change(bridge)
    changes = intercept(bridge, monkeypatch)
    if scenario == "stale":
        body.baseVersion = 2
    if scenario == "profile":
        bridge.profile["version"] = 1
    if scenario == "legacy":
        bridge.plan.pop("version")
    if scenario == "quarter":
        body.servings = 1.25
    with pytest.raises(HTTPException) as error:
        bridge.team.checked_change(session, "7", body, preview=scenario != "no_preview")
    assert error.value.status_code == code
    assert changes == []


def test_unvalidated_upstream_result_is_not_reported_as_success(bridge, monkeypatch):
    session, body = setup_change(bridge)
    intercept(bridge, monkeypatch, valid=False)
    with pytest.raises(HTTPException) as error:
        bridge.team.checked_change(session, "7", body, preview=True)
    assert error.value.status_code == 502


def test_current_allergies_are_forwarded(bridge, monkeypatch):
    session, body = setup_change(bridge)
    bridge.profile["allergies"] = ["ALLERGEN_EGG"]
    changes = intercept(bridge, monkeypatch)
    bridge.team.checked_change(session, "7", body, preview=True)
    assert changes[0][1]["json"]["contraindications"] == ["ALLERGEN_EGG"]


def test_catalog_preparation_and_serving_rules_reach_frontend(bridge):
    bridge.dish.update(
        preparationSteps=["Step from catalog"],
        preparationGuideKind="method_based",
        minServingScaledX2=2,
        maxServingScaledX2=4,
        stepServingScaledX2=2,
    )
    food = bridge.team.food(bridge.dish)
    assert food["steps"] == ["Step from catalog"]
    assert food["preparationGuideKind"] == "method_based"
    assert food["servingRules"] == dict(min=1, max=2, step=1)


def test_chatbot_model_serializes_meal_context_with_camel_case(bridge):
    from rag_app.meal_models import MealSnapshot

    session, _ = setup_change(bridge)
    response = MealSnapshot.model_validate(bridge.team.snapshot(session, "7")).model_dump(
        by_alias=True
    )
    assert response["dataMode"] == "http"
    assert response["plan"]["id"] == "7"
    assert "data_mode" not in response


def test_workspace_advertises_swap_only_with_both_backend_capabilities(bridge, monkeypatch):
    session, _ = setup_change(bridge)
    original = bridge.team.call

    def call(client, method, path, **kwargs):
        if path.endswith("optimizer/capabilities"):
            return dict(validatedSwap=True, planVersions=True)
        return original(client, method, path, **kwargs)

    monkeypatch.setattr(bridge.team, "call", call)
    assert bridge.team.workspace(session)["capabilities"]["swap"] is True
