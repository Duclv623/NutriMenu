"""Transferred writing patterns must continue to use current meal facts."""
import pytest

from rag_app.domain import AnswerBlock, GeneratedAnswer
from rag_app.meal_chat import handle_meal_chat
from rag_app.meal_gateway import MockMealGateway
from rag_app.meal_models import MealContext
from rag_app.provider import GroundingReview, apply_grounding_review


def test_single_nutrient_uses_changed_current_data_without_changing_plan():
    gateway = MockMealGateway()
    gateway.fixture["items"][0]["nutrients"]["energyKcal"] = 501.5
    before = gateway.snapshot("style-test")
    reply = handle_meal_chat(gateway, "style-test", "Món này có nhiêu calo vậy?",
                             MealContext(item_id="breakfast-1"))
    assert "501,5 kcal" in reply.answer and "476" not in reply.answer
    assert "mẫu toán học" in reply.answer
    assert gateway.snapshot("style-test").plan == before.plan
    assert not gateway.proposals


@pytest.mark.parametrize(("lunch", "dinner", "conclusion"), [
    (700, 600, "Bữa trưa"), (600, 700, "Bữa tối"), (650, 650, "Hai bữa"),
])
def test_comparison_conclusion_tracks_direction_and_ties(lunch, dinner, conclusion):
    gateway = MockMealGateway()
    gateway.fixture["items"][1]["nutrients"]["energyKcal"] = lunch
    gateway.fixture["items"][2]["nutrients"]["energyKcal"] = dinner
    plan = gateway.snapshot("style-test").plan
    reply = handle_meal_chat(gateway, "style-test", "Bữa trưa hay bữa tối nhiều calo hơn?",
                             MealContext(plan_id=plan.id, plan_version=plan.version))
    assert reply.answer.startswith(conclusion)
    assert f"{lunch} kcal" in reply.answer and f"{dinner} kcal" in reply.answer
    assert ("bằng nhau" in reply.answer) == (lunch == dinner)
    if lunch != dinner:
        assert "100 kcal" in reply.answer


def test_missing_nutrient_does_not_turn_into_zero_or_known_data():
    gateway = MockMealGateway()
    plan = gateway.snapshot("style-test").plan
    reply = handle_meal_chat(gateway, "style-test", "Thực đơn này đủ chất xơ chưa?",
                             MealContext(plan_id=plan.id, plan_version=plan.version))
    assert reply.status == "insufficient_evidence"
    assert "chưa có dữ liệu chất xơ" in reply.answer
    assert "0 g" not in reply.answer and "Đây là số" not in reply.answer


def test_fluent_health_rationale_needs_the_actual_supporting_line():
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(
        text="Ưu tiên rau xanh để giúp kiểm soát đường huyết sau khi ăn.",
        citation_ids=["C1"])], uncertainty="")
    excerpts = [{"id": "C1", "text": "- Nên ăn rau xanh trong bữa chính.\n"
                "- Thực phẩm giàu chất xơ ít làm tăng đường huyết sau ăn."}]

    def review(lines):
        return GroundingReview.model_validate({"accepted_blocks": [{
            "block_index": 0, "evidence": [{"citation_id": "C1", "line_ids": lines}]}]})

    rejected = apply_grounding_review(answer, review([0]), excerpts)
    assert not rejected.supported and rejected._grounding_review["server_rejections"]
    assert apply_grounding_review(answer, review([0, 1]), excerpts).supported
