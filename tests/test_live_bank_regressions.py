import pytest
from rag_app.meal_chat import meal_action
from rag_app.meal_models import MealContext
from rag_app.routing import ResponsePlan, constrain_plan
from rag_app.dialogue import context_response
from rag_app.food_data import FoodCatalog, FoodPlan, FoodItem
from rag_app.provider import GroundingReview, apply_grounding_review
from rag_app.domain import AnswerBlock, GeneratedAnswer

@pytest.mark.parametrize('question', [
 'Tôi ăn trái cây thay hẳn bữa tối có ổn không?',
 'Buổi sáng tôi vội đi làm, có thể bỏ bữa sáng rồi ăn bù buổi trưa không?',
 'Tôi hay đói lúc 10 giờ sáng, có phải cứ tiểu đường là bắt buộc ăn bữa phụ không?',
 'Tôi uống sữa thay bữa sáng được không?'])
@pytest.mark.parametrize('context', [None, MealContext()])
def test_nutrition_questions_do_not_edit_meals(question, context):
    assert meal_action(question, context) is None

@pytest.mark.parametrize('question', ['Thực đơn của tôi có bữa phụ không?', 'Đổi món bữa trưa giúp tôi', 'Bữa sáng có bao nhiêu calo?'])
def test_stored_meal_queries_stay_structured(question):
    assert meal_action(question, MealContext()) is not None
    assert meal_action('Tôi ăn trái cây thay bữa tối có ổn không?', explicit='swap') == 'swap'

@pytest.mark.parametrize('question', [
 'Tôi thích xoài và mít, có cần bỏ hoàn toàn cả hai không?',
 'Ăn chay thì chọn nhóm thực phẩm nào thay thịt?',
 'Tôi ngồi liên tục 8 giờ, nên thay đổi vận động như thế nào?',
 'Đổi chiên sang hấp hoặc nướng có lợi gì, vì sao?',
 'an pho sang dc ko, toi bi tieu duong?',
 'Tôi dị ứng sữa bò, sữa không đường có dùng được không?',
 'Tôi vận động nhiều; câu trả lời có khác người ngồi văn phòng không?'])
def test_nutrition_decisions_require_sources(question):
    plan = ResponsePlan(strategy='direct_llm', goal='explanation', focus='Trả lời')
    assert constrain_plan(plan, question).strategy != 'direct_llm'

@pytest.mark.parametrize('question', ['Chuẩn bị hộp đồ ăn mang đi cần chú ý gì?', 'Làm sao ghi danh sách đồ cần mang từ tối hôm trước?', 'Carbohydrate là gì?'])
def test_ordinary_logistics_and_limited_concepts_remain_direct(question):
    plan = ResponsePlan(strategy='direct_llm', goal='explanation', focus='Trả lời')
    assert constrain_plan(plan, question).strategy == 'direct_llm'


def test_profile_activity_comparison_is_not_intercepted_as_quantity_request():
    assert context_response('Tôi là nam, 30 tuổi, cao 170 cm, nặng 70 kg và vận động nhiều; câu trả lời có khác người ngồi văn phòng không?', []) is None
    assert context_response('Tôi 45 tuổi, nặng 65 kg, sáng ăn bao nhiêu phở là vừa?', []) is not None


def check(block, evidence, question='Tôi ăn bánh mì vào bữa sáng được không?'):
    answer = GeneratedAnswer(supported=True, blocks=[AnswerBlock(text=block,citation_ids=['C1'])], uncertainty='')
    excerpts = [{'id':f'C{i+1}','text':text,'language':'en'} for i,text in enumerate(evidence)]
    review = GroundingReview.model_validate({'accepted_blocks':[{'block_index':0,'evidence':[{'citation_id':e['id'],'line_ids':[0]} for e in excerpts]}]})
    return apply_grounding_review(answer,review,excerpts,question)


def test_conditional_snack_does_not_support_pairing_at_breakfast():
    result = check('Có thể ăn bánh mì kèm thêm đạm và chất xơ.', ['Có thể ăn khẩu phần nhỏ hơn.', 'Khi bữa ăn bị trễ, ăn nhẹ có đạm và chất xơ.'])
    assert not result.supported
    assert any('bữa chính' in reason for reason in result._grounding_review['server_rejections'])


def test_valid_pairing_source_is_not_discarded_due_to_extra_snack_citation():
    result = check('Có thể ăn kèm thêm đạm.', ['Eating protein with carb foods helps to slow digestion.', 'If your meal will be later, have a snack with protein.'])
    assert result.supported
    assert not any('bữa chính' in reason for reason in result._grounding_review['server_rejections'])


def test_snack_pairing_in_actual_snack_question_is_retained():
    assert check('Có thể ăn nhẹ kèm đạm và chất xơ.', ['Khi bữa ăn bị trễ, ăn nhẹ có đạm và chất xơ.'], 'Bữa tối trễ, ăn nhẹ thế nào?').supported


def test_intake_decision_cannot_be_only_preparation_instructions():
    result = check('Khi ăn phở, chọn nước dùng trong.', ['When having noodles, choose clear soup.'], 'an pho sang dc ko, toi bi tieu duong?')
    assert result._grounding_review['server_rejections']
    assert not check('Mình chưa đủ căn cứ khẳng định món này phù hợp riêng cho bạn. Nếu ăn món sợi, chọn nước dùng trong.', ['When having noodles, choose clear soup.'], 'an pho sang dc ko, toi bi tieu duong?')._grounding_review['server_rejections']


def test_cooked_rice_state_synonyms_resolve_both_verified_snapshots():
    catalog = FoodCatalog()
    result = catalog.execute(FoodPlan(operation='compare', items=[FoodItem(name='cơm trắng đã nấu', amount=100), FoodItem(name='cơm gạo lứt đã nấu', amount=100)], nutrients=['carb']))
    assert not result['unresolved']
    assert {i['id'] for i in result['items']} == {'usda:168878','usda:169704'}
    carbs = {i['id']: next(n['amount_value'] for n in i['display_nutrients'] if n['key']=='carbohydrate') for i in result['items']}
    assert carbs['usda:168878'] == 28.17
    assert carbs['usda:169704'] == 25.58
    raw = catalog.search('gạo lứt sống')
    assert not any(r['id'] == 'usda:169704' and r['match_score'] >= 65 for r in raw)


def test_allergy_examples_never_imply_verified_product_safety():
    result = check('Seitan là ví dụ nguồn đạm thực vật.', ['Seitan is a source of plant protein.'], 'Tôi ăn chay và dị ứng đậu nành, chọn đạm thay thế thế nào?')
    assert 'chưa xác minh nguyên liệu' in result.uncertainty
    assert 'chưa thể bảo đảm' in result.uncertainty
