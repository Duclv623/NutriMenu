"""Real RAG router against controlled Java snapshot; editor hints never write."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from rag_app.meal_chat import handle_meal_chat, meal_action
from rag_app.meal_models import MealContext, MealSnapshot, sum_nutrients
from test_team_bridge import login


def java_context(bridge):
    _, session, _ = login(bridge)
    bridge.plan["version"] = 0
    bridge.plan["mealsBySlot"]["DINNER"] = bridge.plan["mealsBySlot"].pop("LUNCH")
    bridge.plan["mealsBySlot"]["DINNER"][0]["dishNameVi"] = "Cá thu nướng sả"
    bridge.team.state.put(session.account["id"], "plan:7", {"profileVersion": 1})
    snapshot = MealSnapshot.model_validate(bridge.team.snapshot(session, "7"))
    gateway = SimpleNamespace(
        mode="http", snapshot=Mock(return_value=snapshot), preview=Mock(), apply=Mock()
    )
    return gateway, snapshot


@pytest.mark.parametrize(
    "message",
    [
        "Tôi không muốn ăn cá buổi tối",
        "Tôi muốn đổi món bữa tối",
        "Tôi không thích cá ở bữa tối",
    ],
)
def test_real_menu_change_opens_checked_editor_instead_of_rag_fallback(bridge, message):
    gateway, snapshot = java_context(bridge)
    context = MealContext(plan_id="7", plan_version=1)
    assert meal_action(message, context) == "swap"
    reply = handle_meal_chat(gateway, "owner", message, context)
    assert reply.payload["editor"]["planId"] == "7"
    assert reply.payload["editor"]["itemIds"] == ["9"]
    assert reply.payload["editor"]["baseVersion"] == 1
    assert "chưa thay đổi" in reply.answer
    assert reply.payload["proposal"] is None
    gateway.preview.assert_not_called()
    gateway.apply.assert_not_called()


def test_fish_preference_uses_accented_token_and_is_not_a_profile_write(bridge):
    gateway, _ = java_context(bridge)
    reply = handle_meal_chat(
        gateway, "owner", "Tôi không muốn ăn cá buổi tối", MealContext(plan_id="7", plan_version=1)
    )
    assert reply.payload["editor"]["excludedTerms"] == ["cá"]
    assert bridge.profile["restrictedIngredients"] == []


def test_explicit_portion_is_carried_into_the_editor(bridge):
    gateway, _ = java_context(bridge)
    reply = handle_meal_chat(
        gateway,
        "owner",
        "Giảm khẩu phần bữa tối xuống 0,5 suất",
        MealContext(plan_id="7", plan_version=1),
    )
    assert reply.payload["editor"]["requestedServings"] == 0.5
    gateway.apply.assert_not_called()


def test_stale_menu_never_emits_editable_card(bridge):
    gateway, _ = java_context(bridge)
    reply = handle_meal_chat(
        gateway, "owner", "Đổi món bữa tối", MealContext(plan_id="7", plan_version=8)
    )
    assert "editor" not in reply.payload
    assert reply.status == "needs_clarification"


def test_general_chat_requires_selecting_a_menu_before_showing_edit_controls(bridge):
    gateway, _ = java_context(bridge)
    reply = handle_meal_chat(gateway, "owner", "Tôi muốn đổi món bữa tối")
    assert "chọn thực đơn" in reply.answer
    assert not reply.payload.get("editor")
    gateway.apply.assert_not_called()


def test_new_allergy_still_requires_profile_update_before_editor(bridge):
    gateway, _ = java_context(bridge)
    reply = handle_meal_chat(
        gateway,
        "owner",
        "Tôi vừa dị ứng với cá trong thực đơn",
        MealContext(plan_id="7", plan_version=1),
    )
    assert reply.cancel_pending
    assert not (reply.payload or {}).get("editor")
    gateway.preview.assert_not_called()


def test_dinner_numbers_remain_a_structured_read_after_handoff(bridge):
    gateway, _ = java_context(bridge)
    context = MealContext(plan_id="7", plan_version=1)
    first = handle_meal_chat(gateway, "owner", "Tôi không muốn ăn cá buổi tối", context)
    reply = handle_meal_chat(
        gateway,
        "owner",
        "Bữa tối có bao nhiêu calo?",
        context,
        history=[
            {
                "question": "Tôi không muốn ăn cá buổi tối",
                "response": {"meal_result": first.payload},
            }
        ],
    )
    assert "200 kcal" in reply.answer
    assert not reply.payload.get("editor")


def test_typing_accept_does_not_apply_a_form_that_was_not_confirmed(bridge):
    gateway, _ = java_context(bridge)
    context = MealContext(plan_id="7", plan_version=1)
    first = handle_meal_chat(gateway, "owner", "Đổi món bữa tối", context)
    reply = handle_meal_chat(
        gateway,
        "owner",
        "Áp dụng đi",
        context,
        history=[{"question": "Đổi món bữa tối", "response": {"meal_result": first.payload}}],
    )
    assert "bấm Áp dụng thay đổi" in reply.answer
    gateway.apply.assert_not_called()


def lunch_context(bridge, *, duplicate_chicken=False):
    gateway, snapshot = java_context(bridge)
    template = snapshot.plan.items[0]
    dishes = [
        ('1', 'BREAKFAST', 'Cháo gạo lứt đậu đen và nấm'),
        ('2', 'LUNCH', 'Bắp cải trộn chanh và đậu phộng'),
        ('3', 'LUNCH', 'Cơm gạo lứt trộn đậu lăng'),
        ('4', 'LUNCH', 'Canh rau muống chua nhẹ'),
        ('5', 'LUNCH', 'Ức gà kho gừng'),
        ('6', 'DINNER', 'Cá thu nướng sả'),
    ]
    if duplicate_chicken:
        dishes.append(('7', 'DINNER', 'Ức gà hấp nấm'))
    items = [template.model_copy(update={'id': id_, 'recipe_id': id_, 'meal_type': meal, 'name': name})
             for id_, meal, name in dishes]
    plan = snapshot.plan.model_copy(update={'items': items, 'totals': sum_nutrients(items)})
    gateway.snapshot.return_value = snapshot.model_copy(update={'plan': plan})
    return gateway, MealContext(plan_id='7', plan_version=1)


def lunch_history(gateway, context):
    question = 'Bữa trưa của tôi có những món gì?'
    reply = handle_meal_chat(gateway, 'owner', question, context)
    assert 'Ức gà kho gừng' in reply.answer
    assert reply.payload['context']['meal_type'] == 'LUNCH'
    return [{'question': question, 'response': {'meal_result': reply.payload}}]


def test_typo_sang_does_not_choose_an_unrelated_breakfast_dish(bridge):
    gateway, context = lunch_context(bridge)
    reply = handle_meal_chat(gateway, 'owner', 'tôi muốn đổi món ức gà sáng cá', context,
                             history=lunch_history(gateway, context))
    assert reply.status == 'needs_clarification'
    assert 'Ức gà kho gừng ở bữa trưa sang cá, đúng không?' in reply.answer
    assert [choice['itemId'] for choice in reply.payload['choices']] == ['5']
    assert not reply.payload.get('editor')
    gateway.preview.assert_not_called()
    gateway.apply.assert_not_called()


@pytest.mark.parametrize('compact', [False, True])
@pytest.mark.parametrize('click_choice', [False, True])
def test_confirmation_keeps_the_source_and_fish_preference(bridge, compact, click_choice):
    gateway, context = lunch_context(bridge)
    instruction = 'tôi muốn đổi món ức gà sáng cá'
    first = handle_meal_chat(gateway, 'owner', instruction, context,
                             history=lunch_history(gateway, context))
    response = {'meal_result': first.payload}
    if compact:
        response = {'meal_context': first.payload['context'], 'meal_choices': first.payload['choices'],
                    'meal_choice_instruction': first.payload['choiceInstruction']}
    if click_choice:
        context = context.model_copy(update={'item_id': '5', 'meal_type': 'LUNCH'})
    reply = handle_meal_chat(gateway, 'owner', 'Bữa trưa · Ức gà kho gừng' if click_choice else 'Đúng rồi',
                             context, action='swap' if click_choice else None,
                             history=[{'question': instruction, 'response': response}])
    assert reply.payload['editor']['itemIds'] == ['5']
    assert reply.payload['editor']['preferredTerms'] == ['cá']
    assert reply.payload['editor']['instruction'] == instruction
    assert 'bữa trưa' in reply.answer
    gateway.preview.assert_not_called()
    gateway.apply.assert_not_called()


@pytest.mark.parametrize('message', [
    'Tôi muốn đổi món ức gà sang cá',
    'Đổi món ức gà ở bữa trưa sang món cá nhé',
    'Đổi Ức gà kho gừng sang Cá thu nướng sả',
])
def test_replacement_is_never_mistaken_for_the_source(bridge, message):
    gateway, context = lunch_context(bridge)
    reply = handle_meal_chat(gateway, 'owner', message, context)
    assert reply.payload['editor']['itemIds'] == ['5']
    assert reply.payload['editor']['preferredTerms'][0].startswith(('cá', 'Cá'))
    assert 'Cháo' not in reply.answer


def test_duplicate_short_names_require_a_choice_without_meal_context(bridge):
    gateway, context = lunch_context(bridge, duplicate_chicken=True)
    reply = handle_meal_chat(gateway, 'owner', 'Đổi ức gà sang cá', context)
    assert reply.status == 'needs_clarification'
    assert {choice['itemId'] for choice in reply.payload['choices']} == {'5', '7'}
    assert not reply.payload.get('editor')


def test_previous_lunch_disambiguates_duplicate_short_names(bridge):
    gateway, context = lunch_context(bridge, duplicate_chicken=True)
    reply = handle_meal_chat(gateway, 'owner', 'Đổi ức gà sang cá', context,
                             history=lunch_history(gateway, context))
    assert reply.payload['editor']['itemIds'] == ['5']


def test_explicit_conflicting_meal_asks_instead_of_selecting_porridge(bridge):
    gateway, context = lunch_context(bridge)
    reply = handle_meal_chat(gateway, 'owner', 'Đổi ức gà ở bữa sáng sang cá', context)
    assert reply.status == 'needs_clarification'
    assert not reply.payload.get('editor')
    assert [choice['itemId'] for choice in reply.payload['choices']] == ['5']


def test_numeric_item_ids_are_not_inferred_from_portion_amounts(bridge):
    gateway, context = lunch_context(bridge)
    reply = handle_meal_chat(gateway, 'owner', 'Giảm khẩu phần bữa trưa xuống 1 suất', context)
    assert reply.payload['editor']['itemIds'] == ['2', '3', '4', '5']
    assert reply.payload['editor']['requestedServings'] == 1


@pytest.mark.parametrize('message', ['Đổi món bữa sáng giúp mình nhé.', 'Đổi món sáng giúp mình nhé.'])
def test_a_real_breakfast_request_is_not_a_replacement_typo(bridge, message):
    gateway, context = lunch_context(bridge)
    reply = handle_meal_chat(gateway, 'owner', message, context)
    assert reply.payload['editor']['itemIds'] == ['1']
    assert not reply.payload['editor'].get('preferredTerms')
