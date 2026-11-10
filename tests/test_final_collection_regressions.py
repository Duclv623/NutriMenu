import json
from types import SimpleNamespace
from pathlib import Path
import pytest
from rag_app.domain import AnswerBlock, GeneratedAnswer
from rag_app.provider import GroundingReview, apply_grounding_review, example_noun
from rag_app.meal_chat import handle_meal_chat


def checked(texts, sources, accepted=None, question='Tôi chọn nguồn đạm thực vật nào?'):
    answer=GeneratedAnswer(supported=True,blocks=[AnswerBlock(text=t,citation_ids=['C1']) for t in texts],uncertainty='')
    if accepted is None: accepted=[{'block_index':i,'evidence':[{'citation_id':'C1','line_ids':[0]}]} for i in range(len(texts))]
    review=GroundingReview.model_validate({'accepted_blocks':accepted})
    excerpts=[{'id':f'C{i+1}','text':t,'language':lang} for i,(t,lang) in enumerate(sources)]
    return apply_grounding_review(answer,review,excerpts,question)


def test_translated_examples_are_not_literal_matched_to_english():
    result=checked(['Bạn có thể chọn đạm thực vật như các loại hạt và bơ hạt.'], [('Plant-based proteins include nuts and nut spreads.','en')])
    assert result.supported


def test_preserved_food_name_must_occur_in_selected_source():
    source=[('Plant proteins include tofu and tempeh.','en'),('Đậu garbanzo thuộc nhóm carbohydrate.','vi')]
    text=['Bạn có thể chọn thực phẩm như đậu garbanzo.']
    assert not checked(text,source).supported
    accepted=[{'block_index':0,'evidence':[{'citation_id':'C2','line_ids':[0]}]}]
    assert checked(text,source,accepted).supported


def test_nested_example_and_meal_suffix_are_not_food_names():
    assert example_noun('các nguồn đạm thực vật như đậu phụ')=='đậu phụ'
    assert example_noun('các sản phẩm từ đậu nành cho bữa trưa')=='các sản phẩm từ đậu nành'
    result=checked(['Bạn có thể chọn nguồn đạm như thịt gà bỏ da hoặc các nguồn đạm thực vật như đậu phụ cho bữa trưa.'], [('Chọn gà bỏ da và đậu phụ.','vi')])
    assert result.supported


def test_dropped_list_cannot_leave_a_plural_reference():
    result=checked(['Chọn đạm như thực phẩm bịa.', 'Dành một phần tư đĩa cho các thực phẩm giàu protein này.'], [('Nhóm protein chiếm một phần tư đĩa.','vi')])
    assert not result.supported
    assert result._grounding_review['rejected_dependencies']
    assert 'dangling_block_reference' in result._grounding_review['unresolved_goals']


def test_explicit_dependencies_are_pruned_but_user_reference_is_retained():
    accepted=[{'block_index':1,'depends_on_blocks':[0],'evidence':[{'citation_id':'C1','line_ids':[0]}]}]
    assert not checked(['Sai.', 'Nhóm đó chiếm một phần tư đĩa.'], [('Nhóm protein chiếm một phần tư đĩa.','vi')],accepted).supported
    assert checked(['Món này có thể chia khẩu phần.'], [('Có thể chia khẩu phần.','vi')],question='Món này nên ăn thế nào?').supported


def test_sugar_free_question_cannot_be_silently_replaced_with_no_added_sugar():
    result=checked(['Nhãn không thêm đường vẫn cần xem tổng carbohydrate.'], [('Đồ uống ít hoặc không thêm đường là một lựa chọn.','vi')],question='Sữa này không có đường thì không cần kiểm soát lượng đúng không?')
    assert not result.supported
    assert checked(['Cần phân biệt không đường với không thêm đường.'], [('Hai loại nhãn này khác nhau.','vi')],question='Sữa không có đường thì sao?').supported


def test_milk_carbohydrate_is_separate_from_plate_area():
    q='Sữa không đường có phải tính trong bữa sáng không?'
    source=[('Dairy contains carbohydrate.','en')]
    assert not checked(['Tổng thức ăn gồm sữa nằm trong một phần tư diện tích đĩa.'],source,question=q).supported
    assert checked(['Nếu đang đếm carbohydrate, cần tính carbohydrate trong sữa.'],source,question=q).supported


def test_capabilities_question_is_not_intercepted_by_disabled_meal_backend(system):
    result=system.client.post('/api/chat',json={'message':'Bạn có thể xử lý những việc nào: tra chất dinh dưỡng, tư vấn, tạo thực đơn và lưu thực đơn?'}).json()
    assert 'tra thành phần' in result['answer'] and 'Tạo, thay đổi và lưu' in result['answer']


def test_generate_request_does_not_report_a_read_failure():
    result=handle_meal_chat(SimpleNamespace(mode='disabled'), 'tester', 'Tôi có 50.000 đồng, bạn lập thực đơn cho tôi được không?')
    assert result and 'chưa lập hoặc lưu' in result.answer and 'chưa đọc' not in result.answer


def test_ada_source_language_is_english_in_manifest_and_fresh_corpus(corpus):
    manifest=json.loads(Path('config/sources.json').read_text(encoding='utf-8'))
    wanted={'ada-protein','ada-vegan-meals'}
    assert all(s['language']=='en' for s in manifest['sources'] if s['id'] in wanted)
    assert {c.source_id for c in corpus if c.source_id in wanted and c.language=='en'}==wanted

@pytest.mark.parametrize('mode,required', [('disabled','chưa được kết nối'),('mock','dữ liệu mẫu'),('http','dịch vụ kết nối')])
def test_general_capabilities_describe_configured_meal_mode(mode, required):
    result=handle_meal_chat(SimpleNamespace(mode=mode),'tester','Bạn có thể xử lý những việc nào: tra chất dinh dưỡng, tư vấn, tạo thực đơn và lưu thực đơn?')
    assert 'tra thành phần' in result.answer and required in result.answer
    assert 'Tạo thực đơn mới chưa được kết nối' in result.answer or mode=='disabled'


def test_verification_failure_is_not_reported_as_missing_sources(system):
    answer=GeneratedAnswer(supported=False,blocks=[],uncertainty='')
    answer._grounding_review={'server_rejections':['Ví dụ không có trong dòng bằng chứng đã chọn.']}
    system.provider.answer=answer
    result=system.client.post('/api/chat',json={'message':'Tôi ăn chay có thể chọn nguồn đạm nào thay thịt?'}).json()
    assert system.provider.generate_calls
    assert 'đã tìm được tài liệu liên quan' in result['answer']
    assert 'chưa kiểm chứng' in result['answer']
    assert 'chưa tìm thấy đủ bằng chứng' not in result['answer']


def test_meal_name_detection_always_returns_a_list_for_capability_text():
    from rag_app.meal_chat import mentioned_meals
    assert mentioned_meals('Khả năng xem bữa trưa là gì?') == ['LUNCH']
