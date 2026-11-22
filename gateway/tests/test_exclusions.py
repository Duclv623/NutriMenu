import json

import pytest
from fastapi import HTTPException
from test_team_bridge import generation, login

from gateway_app.exclusions import resolve_excluded_dishes


def dishes():
    return [
        {
            "id": 1,
            "nameVi": "Bò xào",
            "recipeBreakdown": [
                {"ingredientNameVi": "Thịt thăn bò"},
                {"ingredientNameVi": "Hành tây"},
            ],
        },
        {
            "id": 2,
            "nameVi": "Bông cải luộc",
            "recipeBreakdown": [{"ingredientNameVi": "Bông cải xanh"}],
        },
        {
            "id": 3,
            "nameVi": "Canh nấm",
            "recipeBreakdown": [{"ingredientNameVi": "Nấm hương tươi"}],
        },
    ]


@pytest.mark.parametrize(
    "label,expected",
    [("thịt bò", [1]), ("thit bo", [1]), ("bò", [1]), ("nấm hương", [3]), ("BÔNG CẢI LUỘC", [2])],
)
def test_resolves_real_recipe_or_dish_names(label, expected):
    assert resolve_excluded_dishes([label], dishes()) == expected


def test_multiple_preferences_are_combined_and_missing_recipe_is_not_assumed_safe():
    catalog = [*dishes(), {"id": 4, "nameVi": "Chưa có công thức", "recipeBreakdown": []}]
    assert resolve_excluded_dishes(["bò", "nấm hương"], catalog) == [1, 3, 4]


def test_unknown_preference_requests_clarification_instead_of_ignoring_it():
    with pytest.raises(HTTPException) as error:
        resolve_excluded_dishes(["tên chưa có trong danh mục"], dishes())
    assert error.value.status_code == 422 and "Chưa nhận diện" in error.value.detail


def test_accents_distinguish_fish_from_tomato():
    catalog = [
        {"id": 1, "nameVi": "Cá hấp", "recipeBreakdown": [{"ingredientNameVi": "Cá hồi"}]},
        {"id": 2, "nameVi": "Canh cà", "recipeBreakdown": [{"ingredientNameVi": "Cà chua"}]},
    ]
    assert resolve_excluded_dishes(["cá"], catalog) == [1]


def test_generate_passes_resolved_exclusions_to_optimizer(bridge):
    _, session, _ = login(bridge)
    bridge.profile["restrictedIngredients"] = ["Nguyên liệu thử"]
    bridge.plans.clear()
    # The controlled optimizer returns an allowed different dish after filtering.
    bridge.plan["mealsBySlot"]["LUNCH"][0]["dishId"] = 99
    bridge.team.generate(session, generation(bridge, session))
    payload = next(json.loads(r.content) for r in bridge.calls if "generate-daily" in r.url.path)
    assert payload["excludedDishIds"] == [4]


def test_old_optimizer_is_detected_before_sending_a_filtered_generate(bridge, monkeypatch):
    _, session, _ = login(bridge)
    bridge.profile["restrictedIngredients"] = ["Nguyên liệu thử"]
    original = bridge.team.call

    def call(client, method, path, **kwargs):
        if path.endswith("/capabilities"):
            raise HTTPException(404, "Old optimizer")
        return original(client, method, path, **kwargs)

    monkeypatch.setattr(bridge.team, "call", call)
    with pytest.raises(HTTPException) as error:
        bridge.team.generate(session, generation(bridge, session))
    assert error.value.status_code == 503 and "khởi động lại" in error.value.detail
    assert not any("generate-daily" in r.url.path for r in bridge.calls)


def test_forbidden_result_is_not_shown_as_success(bridge):
    _, session, _ = login(bridge)
    bridge.profile["restrictedIngredients"] = ["Nguyên liệu thử"]
    bridge.plans.clear()
    with pytest.raises(HTTPException) as error:
        bridge.team.generate(session, generation(bridge, session))
    assert error.value.status_code == 502
