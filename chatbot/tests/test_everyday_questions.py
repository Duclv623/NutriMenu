import pytest

from rag_app.domain import AnswerBlock, ChatRequest, GeneratedAnswer
from rag_app.meal_chat import handle_meal_chat, meal_action
from rag_app.meal_gateway import MockMealGateway
from rag_app.meal_models import MealContext
from rag_app.nutrition_reference import nutrition_reference_topic
from rag_app.provider import backend_profile_payload
from rag_app.routing import ResponsePlan, constrain_plan


@pytest.mark.parametrize("question", [
    "Buổi tối có món gì nấu nhanh với cà chua không?",
    "Trưa nay có mỗi nồi cơm điện, nấu gì cho gọn nhỉ?",
    "Đồ ăn trưa mang đi mà không hâm được thì chuẩn bị món gì?",
    "Hai chai sữa khác cỡ thì xem trên nhãn để biết loại nào nhiều đường hơn?",
    "Khoai luộc với khoai nướng có vị khác nhiều không?",
])
def test_ordinary_questions_do_not_take_over_the_saved_plan(question):
    context = MealContext(plan_id="named-demo", item_id="lunch-rice")
    assert meal_action(question, context) is None


def test_new_ordinary_question_stays_on_its_topic_with_a_meal_open(system):
    service = system.app.state.service
    service.meals = MockMealGateway("named")
    system.provider.response_plan = ResponsePlan(
        strategy="direct_llm", goal="practical_steps", focus="Món đơn giản cho buổi tối",
    )
    first = service.chat(ChatRequest(message="Xem thực đơn mẫu hôm nay"), "alice")
    question = "Tối nay mình có cà chua, nấu món gì nhanh được nhỉ?"
    result = service.chat(ChatRequest(message=question, session_id=first.session_id), "alice")
    planned_question, prior_turns = system.provider.plan_calls[-1]
    profile = backend_profile_payload(planned_question)["profile"]
    assert planned_question == question and not prior_turns
    assert set(profile) == {"allergies", "restrictedIngredients", "preferences"}
    assert result.response_strategy == "direct_llm" and result.meal_result is None


def test_taste_and_convenience_are_distinct_from_health_assessment():
    draft = ResponsePlan(strategy="direct_llm", goal="comparison", focus="So sánh về vị")
    question = "Mình muốn đổi vị, khoai nướng khác khoai luộc thế nào?"
    assert constrain_plan(draft, question).strategy == "direct_llm"
    health_question = "Mình bị tiểu đường, đổi vị sang khoai nướng có tốt hơn không?"
    assert constrain_plan(draft, health_question).strategy == "evidence_rag"


def test_making_a_drink_less_sweet_is_not_a_medical_lookup():
    draft = ResponsePlan(strategy="practical_rag", goal="practical_steps", focus="Cách gọi nước")
    question = "Mình thích cacao đá nhưng muốn bớt ngọt, lúc gọi nên nói sao?"
    assert constrain_plan(draft, question).strategy == "direct_llm"
    assert constrain_plan(draft, "Người bệnh tiểu đường " + question).strategy == "practical_rag"
    assert constrain_plan(draft, question + " Như vậy còn bao nhiêu gram đường?").strategy == "evidence_rag"


def test_birthday_mention_does_not_request_new_meal_plan():
    gateway = MockMealGateway("named")
    snapshot = gateway.snapshot("alice")
    result = handle_meal_chat(
        gateway, "alice", "Mình có tiệc sinh nhật chiều nay, xem bữa xế trong thực đơn có gì nhé.",
    )
    assert result.payload["view"] == "show"
    assert "Bữa phụ" in result.answer or "bữa phụ" in result.answer
    assert gateway.snapshot("alice") == snapshot


def test_alternative_question_respects_named_demo_capability():
    gateway = MockMealGateway("named")
    snapshot = gateway.snapshot("alice")
    result = handle_meal_chat(
        gateway, "alice", "Bữa trưa trong thực đơn hôm nay, có món nào khác để mình chọn không?",
    )
    assert result.status == "integration_required"
    assert result.payload["view"] == "swap" and result.payload["proposal"] is None
    assert "Bữa trưa mẫu đang có" in result.answer
    assert "chưa hỗ trợ đổi món" in result.answer
    assert gateway.snapshot("alice") == snapshot


@pytest.mark.parametrize(("question", "energy", "grams", "record_id"), [
    ("Quả chuối cỡ nhỏ tầm bao nhiêu kcal?", 90, 101, "usda:173944"),
    ("Một trái chuối cỡ vừa khoảng bao nhiêu calo vậy?", 105, 118, "usda:173944"),
    ("Một bắp ngọt luộc cỡ lớn có bao nhiêu calo nhỉ?", 113, 118, "usda:169999"),
])
def test_standard_portions_cite_actual_reference_weight_and_energy(system, question, energy, grams, record_id):
    response = system.client.post("/api/chat", json={"message": question}).json()
    assert response["status"] == "answered" and response["answer_origin"] == "static"
    assert f"{energy} kcal" in response["answer"] and f"{grams} g" in response["answer"]
    citation, = response["citations"]
    assert citation["chunk_id"] == record_id
    assert f"{energy} kcal" in citation["quote"] and f"{grams} g phần ăn được" in citation["quote"]
    assert not system.provider.plan_calls


@pytest.mark.parametrize("question", [
    "Một quả chuối chiên cỡ vừa bao nhiêu kcal?",
    "Một bắp ngô nếp luộc cỡ vừa bao nhiêu calo?",
    "Tôi nên ăn một quả chuối cỡ vừa mỗi ngày không?",
    "Hai quả chuối cỡ vừa bao nhiêu calo?",
])
def test_other_preparations_and_intake_advice_do_not_use_reference_portion(question):
    assert nutrition_reference_topic(question) is None


def test_sugar_label_comparison_distinguishes_same_weight_and_whole_package(system):
    response = system.client.post("/api/chat", json={
        "message": "Xem nhãn hai hộp sữa chua khác cỡ để biết hộp nào nhiều đường hơn thế nào?",
    }).json()
    assert response["status"] == "answered" and response["answer_origin"] == "static"
    assert all(term in response["answer"] for term in ("đường tổng", "cùng 100 g", "cả hộp"))
    citation, = response["citations"]
    assert citation["source_id"] == "nin-labels"
    assert not system.provider.plan_calls


def test_safety_precedes_ordinary_cooking_even_with_plan_context(system):
    response = system.client.post("/api/chat", json={
        "message": "Mình đang mang thai, tối nay có món gì nấu nhanh?",
        "meal_context": {"plan_id": "named-demo"},
    }).json()
    assert response["status"] == "safety" and not system.provider.plan_calls


@pytest.mark.parametrize(("question", "source_id", "instructions"), [
    ("Còn ít cơm thừa với trứng thì làm món gì?",
     "fsa-food-safety", ("trong vòng một giờ", "24 giờ", "nóng bốc hơi đều")),
    ("Úp tô mì ăn tối thì thêm gì cho ngon?",
     "fda-egg-safety", ("trứng luộc", "nấu chín riêng trước khi cho")),
    ("Có gợi ý món gì mang đi làm mà không cần hâm lại vì không có lò vi sóng?",
     "udel-food-safety", ("túi giữ nhiệt có đá", "Nếu không giữ lạnh được")),
])
def test_quick_cooking_references_include_relevant_safety_instructions(system, question, source_id, instructions):
    response = system.client.post("/api/chat", json={"message": question}).json()
    assert response["status"] == "answered" and response["answer_origin"] == "static"
    assert all(instruction in response["answer"] for instruction in instructions)
    citation, = response["citations"]
    assert citation["source_id"] == source_id and citation["document_url"].startswith("https://")
    assert not system.provider.plan_calls


def test_reference_cooking_suggestions_do_not_override_ingredient_exclusion(system):
    response = system.client.post("/api/chat", json={
        "message": "Úp mì mà mình dị ứng trứng thì có thể thêm gì?",
    }).json()
    assert response["answer_origin"] != "static" and system.provider.plan_calls


def test_seasoning_reference_answers_before_cooking_without_assuming_dish_is_already_salty(system):
    response = system.client.post("/api/chat", json={
        "message": "Mình định kho cá, nêm sao cho bớt mặn mà vẫn thơm?",
    }).json()
    assert response["status"] == "answered" and response["answer_origin"] == "static"
    assert "ít nước mắm hoặc muối ngay từ đầu" in response["answer"]
    assert response["citations"][0]["source_id"] == "ada-cooking"
    assert nutrition_reference_topic("Lỡ tay nêm nồi cá kho quá mặn, làm sao cứu cho bớt mặn?") is None


def test_contextual_recipe_edits_keep_recent_constraints_and_reset_on_topic_change(system):
    system.provider.response_plan = ResponsePlan(
        strategy='direct_llm', goal='practical_steps', focus='Điều chỉnh món đang nấu',
    )
    conversation = [
        'Tối có cà chua và trứng, làm món gì cả nhà ăn chung?',
        'À có một người không ăn trứng. Vẫn làm chung một món được không?',
        'Mình có thêm nửa bìa đậu hũ, cho vào lúc nào thì đỡ nát?',
        'Tóm lại giúp mình theo thứ tự để dễ làm.',
        'Tiện hỏi chuyện khác: Mua chuối ăn dần thì chọn nải màu nào?',
        'Vậy chọn loại nào?',
    ]
    service = system.app.state.service
    service.meals = MockMealGateway('named')
    session = None
    for question in conversation:
        reply = service.chat(ChatRequest(message=question, session_id=session), 'alice')
        assert reply.meal_result is None and reply.status == 'answered'
        session = reply.session_id
    resolved, _, history = system.provider.direct_calls[3]
    assert resolved.startswith(conversation[0] + '\nCâu hỏi tiếp: ')
    assert [turn['question'] for turn in history] == conversation[:3]
    assert not system.provider.direct_calls[4][2]
    assert [turn['question'] for turn in system.provider.direct_calls[5][2]] == conversation[4:5]


def test_requested_sugar_label_arithmetic_uses_user_values_not_reference_foods(system):
    first = system.client.post('/api/chat', json={'message': (
        'Hộp A 120 g ghi 8 g đường trên 100 g. Hộp B 180 g ghi 7 g đường trên 100 g. '
        'Nếu ăn hết hộp thì sao?'
    )}).json()
    followup = system.client.post('/api/chat', json={
        'message': 'Còn nếu ăn nửa hộp B thì so với cả hộp A thế nào?',
        'session_id': first['session_id'],
    }).json()
    for reply in (first, followup):
        assert reply['status'] == 'answered' and reply['answer_origin'] == 'static'
        assert not reply['citations'] and not reply['provider_response_ids']
    assert '12,6 g' in first['answer'] and '9,6 g' in first['answer']
    assert '6,3 g' in followup['answer'] and 'cả hộp A có nhiều đường hơn nửa hộp B' in followup['answer']
    assert not system.provider.plan_calls


def test_implicit_label_question_identifies_total_sugar_and_comparison_basis(system):
    reply = system.client.post('/api/chat', json={
        'message': 'Hai hộp sữa chua khác cỡ, nhìn dòng nào để biết loại nào nhiều đường hơn?',
    }).json()
    assert reply['status'] == 'answered' and 'đường tổng' in reply['answer']
    assert 'cùng 100 g' in reply['answer'] and reply['citations'][0]['source_id'] == 'nin-labels'
    assert not system.provider.plan_calls


def test_scope_and_recipe_type_follow_a_saved_meal_portion_lookup(system):
    service = system.app.state.service
    service.meals = MockMealGateway('named')
    first = service.chat(ChatRequest(message='Xem bữa trưa trong thực đơn của mình.'), 'alice')
    session = first.session_id
    second = service.chat(ChatRequest(message='Phần cơm trong bữa đó là mấy gam?', session_id=session), 'alice')
    third = service.chat(ChatRequest(message='Còn bữa tối, cơm mấy gam, có cùng loại không?', session_id=session), 'alice')
    pinned_meal = MealContext.model_validate(third.meal_result['context'])
    outside = service.chat(ChatRequest(
        message='Cho mình hỏi ngoài thực đơn: mua gì để nấu canh bí đỏ không bỏ hành?', session_id=session,
        meal_context=pinned_meal,
    ), 'alice')
    assert second.meal_result['selectedItemIds'] == ['lunch-rice']
    assert third.meal_result['selectedItemIds'] == ['dinner-rice']
    assert 'Khác loại' in third.answer and '150 g' in third.answer
    assert outside.status == 'answered' and outside.meal_result is None
    assert 'gừng' in outside.answer and 'tỏi' not in outside.answer
    system.provider.response_plan = ResponsePlan(
        strategy='direct_llm', goal='practical_steps', focus='Cách nấu món vừa chọn',
    )
    followup = service.chat(ChatRequest(
        message='Món đó làm sao?', session_id=session, meal_context=pinned_meal,
    ), 'alice')
    assert followup.meal_result is None and followup.response_strategy == 'direct_llm'
    assert system.provider.direct_calls[-1][2][-1]['question'] == 'Cho mình hỏi ngoài thực đơn: mua gì để nấu canh bí đỏ không bỏ hành?'
    reopened = service.chat(ChatRequest(
        message='Tiện hỏi chuyện khác, xem bữa sáng trong thực đơn đang lưu.', session_id=session,
        meal_context=pinned_meal,
    ), 'alice')
    assert reopened.meal_result['selectedItemIds'] == ['breakfast-pho']


def test_direct_recipe_with_ground_meat_includes_reviewed_temperature_source(system):
    system.provider.response_plan = ResponsePlan(
        strategy='direct_llm', goal='practical_steps', focus='Nấu canh',
    )
    system.provider.answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(
        text='Nấu canh cải thịt băm. Nấu chín kỹ thịt băm trước khi thêm rau cải.', citation_ids=[],
    )], uncertainty='')
    reply = system.client.post('/api/chat', json={'message': 'Nấu món gì với cải và thịt băm?'}).json()
    assert reply['status'] == 'answered' and reply['response_strategy'] == 'direct_llm'
    assert '71,1 °C' in reply['answer'] and '73,9 °C' in reply['answer']
    citation, = reply['citations']
    assert citation['source_id'] == 'usda-fsis-food-safety' and citation['id'] == 'C1'


def test_cost_constrains_ordinary_ordering_without_waiving_nutrition_sources():
    plan = ResponsePlan(strategy='practical_rag', goal='decision', focus='Chọn món ở quán')
    assert constrain_plan(plan, 'Có 40k, gọi cơm với rau thế nào?').strategy == 'direct_llm'
    assert constrain_plan(plan, 'Có 40k, gọi cơm nào và chứa bao nhiêu kcal?').strategy == 'evidence_rag'
    assert constrain_plan(plan, 'Có 40k, tài liệu nào khuyến cáo cách chọn món?').strategy == 'evidence_rag'


def test_budget_and_packed_lunch_suggestions_have_grounded_defaults(system):
    budget = system.client.post('/api/chat', json={
        'message': 'Có 40k, đi quán cơm gọi sao để có món mặn với rau?',
    }).json()
    assert budget['status'] == 'answered' and '40 nghìn' in budget['answer']
    assert 'tổng suất' in budget['answer'] and budget['meal_result'] is None
    packed = system.client.post('/api/chat', json={
        'message': 'Dùng túi giữ nhiệt với đá gel thì nên xếp đồ ăn thế nào?',
    }).json()
    assert packed['status'] == 'answered' and 'đá gel đã đông' in packed['answer']
    assert 'hộp nhân đã lạnh' in packed['answer'] and packed['citations'][0]['source_id'] == 'udel-food-safety'


def test_vegetable_storage_prioritizes_cut_produce_and_cites_both_conditions(system):
    reply = system.client.post('/api/chat', json={
        'message': 'Tủ lạnh chỉ còn một chỗ. Nên ưu tiên cất bắp cải hay cà rốt trước?',
    }).json()
    assert reply['status'] == 'answered' and 'đã cắt' in reply['answer']
    assert 'còn nguyên, ưu tiên bắp cải' in reply['answer']
    assert [c['source_id'] for c in reply['citations']] == ['cdc-produce-safety', 'vce-food-storage']


def test_multiday_shopping_prioritizes_the_shorter_keeping_vegetable(system):
    reply = system.client.post('/api/chat', json={
        'message': 'Gợi ý ba loại rau củ mua một lần, nấu lần lượt trong ba bữa tối đầu tuần.',
    }).json()
    assert reply['status'] == 'answered'
    assert 'bông cải xanh vào bữa đầu, bắp cải bữa sau và cà rốt cuối cùng' in reply['answer']
    citation, = reply['citations']
    assert citation['id'] == 'C1' and citation['source_id'] == 'vce-food-storage'


def test_shopping_followup_compares_calories_using_the_food_catalog(system):
    first = system.client.post('/api/chat', json={
        'message': 'Chủ nhật mình mới đi chợ được. Gợi ý ba loại rau củ để nấu lần lượt trong mấy bữa tối đầu tuần với.',
    }).json()
    reply = system.client.post('/api/chat', json={
        'message': 'bắp cải với cà rốt cái nào nhiều calo hơn', 'session_id': first['session_id'],
    }).json()

    assert first['status'] == 'answered' and reply['session_id'] == first['session_id']
    assert reply['status'] == 'answered' and reply['intent'] == 'food_lookup'
    assert reply['answer_origin'] == 'static' and not reply['provider_response_ids']
    assert reply['answer'].startswith('Củ cà rốt tươi nhiều calo hơn.')
    assert '100 g phần ăn được' in reply['answer']
    assert '36 kcal [C1]' in reply['answer'] and '44 kcal [C2]' in reply['answer']
    assert [c['chunk_id'] for c in reply['citations']] == ['nin_foods:4010', 'nin_foods:4007']


def test_broad_meat_comparison_uses_lean_cuts_as_an_example(system):
    reply = system.client.post('/api/chat', json={
        'message': 'thịt bò với thịt lợn loại nào nhiều calo hơn',
    }).json()

    assert reply['status'] == 'answered' and reply['answer_origin'] == 'static'
    assert reply['answer'].startswith('Còn tùy phần thịt và lượng mỡ.')
    assert '100 g phần ăn được khi còn sống' in reply['answer']
    assert 'thịt bò lưng nạc tươi có 121 kcal [C1]' in reply['answer']
    assert 'thịt lợn nạc tươi có 139 kcal [C2]' in reply['answer']
    assert [c['chunk_id'] for c in reply['citations']] == ['nin_foods:7005', 'nin_foods:7017']
