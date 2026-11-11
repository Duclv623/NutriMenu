import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rag_app.config import Settings
from rag_app.domain import ChatRequest, Chunk
from rag_app.energy_reference import (RULE_CHUNKS, calculate_reference_range, is_daily_energy_question,
                                      reference_reply, verified_rule_hits)
from rag_app.main import create_app
from rag_app.meal_gateway import MockMealGateway
from rag_app.meal_models import DemoProfileUpdate, SwapRequest

QUESTION = 'với cân nặng của tôi thì một ngày ăn tầm bao nhiêu calo'


def updated(gateway, owner='a', **changes):
    old = gateway.snapshot(owner)
    profile = old.profile.model_copy(update=changes)
    return gateway.update_profile(owner, DemoProfileUpdate(base_version=old.profile.profile_version, profile=profile))


@pytest.fixture
def rules(corpus):
    ids = {r[0] for r in RULE_CHUNKS}
    return [c for c in corpus if c.id in ids]


def test_exact_approved_arithmetic_and_provenance(rules):
    cfg = Settings(_env_file=None)
    assert len(verified_rule_hits(cfg, rules)) == 2
    result = calculate_reference_range(175)
    assert result.ideal_weight_kg == Decimal('67.375')
    assert result.minimum_kcal == Decimal('1347.5')
    assert result.maximum_kcal == Decimal('2021.25')


@pytest.mark.parametrize('query', [QUESTION, 'Mỗi ngày nên ăn bao nhiêu kcal?', 'Nhu cầu năng lượng một ngày của tôi là bao nhiêu?'])
def test_energy_routing_positive(query):
    assert is_daily_energy_question(query)


@pytest.mark.parametrize('query', ['BMR là gì?', 'TDEE bao nhiêu calo mỗi ngày?', 'Mỗi ngày tôi đốt bao nhiêu calo?', 'Năng lượng tiêu hao khi chạy bộ mỗi ngày là bao nhiêu?', 'Tổng calo cả ngày trong thực đơn của tôi', '100g thịt gà có bao nhiêu calo?', 'Một ngày ăn 100 g cơm bao nhiêu calo?', 'Carbohydrate là gì?'])
def test_energy_routing_does_not_capture_other_quantities(query):
    assert not is_daily_energy_question(query)


def test_latest_profiles_exact_question_and_immutable_plan(system):
    service = system.app.state.service
    gateway = service.meals = MockMealGateway()
    a = gateway.snapshot('a')
    proposal = gateway.preview('a', SwapRequest(plan_id=a.plan.id,base_version=1,item_id='breakfast-1',instruction='Đổi món sáng'))
    first = service.chat(ChatRequest(message=QUESTION), 'a')
    assert first.answer.startswith('Khoảng tham khảo khởi đầu')
    assert '1130–1690 kcal/ngày' in first.answer
    assert first.answer_origin == 'static' and first.response_strategy == 'structured_lookup'
    assert [c.chunk_id for c in first.citations] == [r[0] for r in RULE_CHUNKS]
    assert all(c.source_id == 'byt5481-nutrition' and c.year == 2020 for c in first.citations)
    assert gateway.snapshot('a').plan == a.plan
    assert str(proposal.id) in gateway.proposals
    second = service.chat(ChatRequest(message=QUESTION,session_id=first.session_id), 'a')
    assert second.answer == first.answer
    updated(gateway, 'b', height=175, weight=82)
    b = service.chat(ChatRequest(message=QUESTION), 'b')
    assert '1350–2020 kcal/ngày' in b.answer and '67,375 kg' in b.answer
    assert 'phiên bản 2' in b.answer
    updated(gateway, 'b', weight=95)
    service.profile_changed('b')
    weight_only = service.chat(ChatRequest(message=QUESTION,session_id=b.session_id), 'b')
    assert '1350–2020 kcal/ngày' in weight_only.answer
    assert 'đổi cân nặng mà giữ chiều cao sẽ không đổi khoảng này' in weight_only.answer
    updated(gateway, 'b', height=180)
    service.profile_changed('b')
    taller = service.chat(ChatRequest(message=QUESTION,session_id=b.session_id), 'b')
    assert '1430–2140 kcal/ngày' in taller.answer and 'phiên bản 4' in taller.answer
    assert not system.provider.plan_calls and not system.provider.generate_calls and not system.provider.embed_calls


@pytest.mark.parametrize('changes,missing,status', [({'height':None},'chiều cao (cm)','needs_clarification'), ({'age':None},'tuổi','needs_clarification'), ({'scope_status':'unknown'},'xác nhận phạm vi','needs_clarification'), ({'age':16},'ngoài phạm vi','safety'), ({'scope_status':'out_of_scope'},'ngoài phạm vi','safety')])
def test_missing_or_unsupported_profile_never_calculates(rules, changes, missing, status):
    profile = MockMealGateway().snapshot('a').profile.model_copy(update=changes)
    reply = reference_reply(Settings(_env_file=None), rules, profile)
    assert reply.status == status and missing in reply.answer
    assert not reply.hits and 'kcal/ngày**' not in reply.answer
    if changes == {'height':None}:
        assert '60 kg' in reply.answer and 'tuổi' not in reply.question


def test_absent_profile_has_actionable_missing_fields(rules):
    reply = reference_reply(Settings(_env_file=None), rules, None)
    assert reply.status == 'needs_clarification'
    assert 'tuổi' in reply.question and 'chiều cao' in reply.question
    assert not reply.hits


@pytest.mark.parametrize('change', ['text','unit','sha','missing','pages','source'])
def test_invalid_rule_or_unit_fails_closed(rules, change):
    changed = list(rules)
    chunk = next(c for c in changed if c.id == RULE_CHUNKS[1][0])
    if change == 'missing':
        changed.remove(chunk)
    else:
        updates = {'text':chunk.text+' ', 'unit':chunk.text.replace('kcal/kg','kJ/kg'), 'sha':'0'*64,
                   'pages':[1], 'source':'nin2015-dtd2'}
        field = {'text':'text','unit':'text','sha':'sha256','pages':'pages','source':'source_id'}[change]
        changed[changed.index(chunk)] = chunk.model_copy(update={field:updates[change]})
    reply = reference_reply(Settings(_env_file=None), changed, MockMealGateway().snapshot('a').profile)
    assert reply.status == 'insufficient_evidence' and not reply.hits
    assert 'kcal/ngày**' not in reply.answer


@pytest.mark.parametrize('change', ['disabled','hash','role'])
def test_withdrawn_or_changed_manifest_fails_closed(tmp_path, rules, change):
    cfg = Settings(_env_file=None)
    manifest = json.loads(cfg.source_manifest.read_text(encoding='utf-8'))
    source = next(s for s in manifest['sources'] if s['id'] == 'byt5481-nutrition')
    field, value = {'disabled':('enabled',False),'hash':('sha256','0'*64),'role':('role','other')}[change]
    source[field] = value
    path = tmp_path / 'sources.json'
    path.write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
    cfg.source_manifest = path
    assert not verified_rule_hits(cfg, rules)


def test_changed_original_pdf_fails_closed(tmp_path, rules, monkeypatch):
    import rag_app.energy_reference as module
    (tmp_path/'data').mkdir()
    (tmp_path/'data'/'dinh-kem-16.pdf').write_bytes(b'changed source')
    monkeypatch.setattr(module,'ROOT',tmp_path)
    assert not verified_rule_hits(Settings(_env_file=None), rules)


@pytest.mark.parametrize('message', [QUESTION+', tôi đang lú lẫn vã mồ hôi run tay', QUESTION+', tôi nên tăng liều insulin thế nào?', QUESTION+', tôi đang mang thai'])
def test_clinical_safety_wins_over_reference(system, message):
    service = system.app.state.service
    service.meals = MockMealGateway()
    reply = service.chat(ChatRequest(message=message), 'a')
    assert reply.status == 'safety' and not reply.citations
    assert '**' not in reply.answer
    assert not system.provider.generate_calls


def test_meal_total_and_food_composition_keep_their_existing_routes(system):
    service = system.app.state.service
    service.meals = MockMealGateway()
    meal = service.chat(ChatRequest(message='Tổng calo cả ngày trong thực đơn của tôi'), 'a')
    assert meal.meal_result and '1767' in meal.answer
    assert not meal.citations
    food = service.chat(ChatRequest(message='100g thịt gà có bao nhiêu calo?'), 'a')
    assert food.intent == 'food_lookup' and not food.meal_result
    assert not any(c.chunk_id in {r[0] for r in RULE_CHUNKS} for c in food.citations)


def test_profile_change_during_reference_is_discarded(system, monkeypatch):
    import rag_app.service as module
    service = system.app.state.service
    gateway = service.meals = MockMealGateway()
    original = module.reference_reply
    def racing(*args, **kwargs):
        reply = original(*args, **kwargs)
        updated(gateway, height=180)
        service.profile_changed('a')
        return reply
    monkeypatch.setattr(module,'reference_reply',racing)
    reply = service.chat(ChatRequest(message=QUESTION), 'a')
    assert reply.status == 'needs_clarification'
    assert 'Hồ sơ đã thay đổi' in reply.answer and not reply.citations


@pytest.mark.parametrize('height', [0.5, 1.75, 50, 119.9, 220.1, 300])
def test_height_unit_mistakes_or_unsupported_height_fail_closed(rules, height):
    profile = MockMealGateway().snapshot('a').profile.model_copy(update={'height':height})
    with pytest.raises(ValueError):
        calculate_reference_range(height)
    reply = reference_reply(Settings(_env_file=None), rules, profile)
    assert reply.status == 'needs_clarification' and not reply.hits
    assert '120–220 cm' in reply.answer and 'không phải ngưỡng chẩn đoán' in reply.answer
    assert 'kiểm tra' in reply.question and 'cm' in reply.question
    assert profile.height == height


@pytest.mark.parametrize('height', [120, 220])
def test_technical_input_boundaries_are_explicit_and_nonzero(height):
    result = calculate_reference_range(height)
    assert result.minimum_kcal > 0 and result.maximum_kcal > result.minimum_kcal
