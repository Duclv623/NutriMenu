import json

import pytest

from rag_app.domain import AnswerBlock, GeneratedAnswer
from rag_app.food_data import FoodItem, FoodPlan
from rag_app.service import make_citations
from rag_app.supplements import SupplementCatalog


@pytest.fixture(scope="module")
def references():
    return SupplementCatalog()


def lookup(catalog, domain, name, amount=None, unit="g", question=""):
    return catalog.execute(
        domain,
        FoodPlan(operation="lookup", items=[FoodItem(name=name, amount=amount, unit=unit)]),
        question,
    )


def test_only_reviewed_labels_calculate_and_milliliters_do_not_become_grams(references):
    rid = "supp-th-product-sua-hat-macca-th-true-nut-180-ml"
    result = lookup(references, "label", rid, 200, "ml")["items"][0]
    assert result["payload"]["nutrients"]["sodium_mg"] == 10
    assert result["calculated_nutrients"]["sodium_mg"] == 20
    assert result["calculated_nutrients"]["carbohydrate_g"] == 7.4
    wrong = lookup(references, "label", rid, 200, "g")["items"][0]
    assert not wrong["calculation_available"] and wrong["calculated_nutrients"] is None
    assert "ml" in wrong["limitations"]


def test_moc_chau_undeclared_sugars_are_not_zero(references):
    result = lookup(references, "label", "supp-mcm-product-40-label-p4", 200, "g")["items"][0]
    assert result["calculated_nutrients"]["carbohydrate_g"] == 9
    assert result["calculated_nutrients"]["total_sugars_g"] is None
    assert result["calculated_nutrients"]["added_sugars_g"] is None


def test_all_flagged_labels_without_alternative_have_no_numeric_payload(references):
    blocked = [
        r
        for r in references.records.values()
        if r["domain"] == "label" and not r["calculation_enabled"]
    ]
    assert len(blocked) == 12
    for row in blocked:
        result = lookup(references, "label", row["id"], 200, "ml")
        item = result["items"][0]
        assert not item["calculation_available"] and "nutrients" not in item["payload"]
        assert "reason" in item["payload"]


def test_rice_bowl_filters_capacity_and_fill(references):
    result = lookup(
        references,
        "portion",
        "cơm gạo tẻ",
        question="Bát cơm gạo tẻ 250 ml đầy miệng nặng bao nhiêu gram?",
    )
    assert not result["unresolved"] and len(result["items"]) == 1
    payload = result["items"][0]["payload"]
    assert payload["cooked_food_component_g"] == 180
    assert payload["vessel_capacity_ml"] == 250 and payload["total_finished_dish_g"] is None
    ambiguous = lookup(
        references, "portion", "cơm gạo tẻ", question="Một bát cơm gạo tẻ nặng bao nhiêu gram?"
    )
    assert ambiguous["unresolved"] and not ambiguous["items"]


def test_references_do_not_generate_finished_recipe_mass(references):
    recipes = [r for r in references.records.values() if r["domain"] == "recipe"]
    assert len(recipes) == 54
    assert all(r["payload"]["finished_weight_g"] is None for r in recipes)
    hospital = [r for r in recipes if r["source_id"] == "vietduc-meal-specifications-2024"]
    assert len(hospital) == 15 and all(
        r["payload"]["minimum_finished_weight_g"] == 450 for r in hospital
    )
    assert all(not r["calculation_enabled"] for r in recipes)


def test_conflicting_gi_is_not_published_numerically(references):
    conflicted = [
        r
        for r in references.records.values()
        if r["domain"] == "gi"
        and ("custard apple" in r["name"].lower())
        and (
            r["source_id"] == "gi-vietnam-paper-2001"
            or "Chan" in r["payload"].get("Reference:", "")
        )
    ]
    assert len(conflicted) >= 2
    assert all(
        r["payload"].get("gi_all_subjects", r["payload"].get("GI")) in [None, ""]
        for r in conflicted
    )


def test_missing_gi_does_not_match_unrelated_rice(references):
    result = lookup(references, "gi", "phở bò", question="GI phở bò bao nhiêu?")
    assert not result["items"] and result["unresolved"]


def test_vietnamese_question_word_does_not_trigger_gi_tool(references):
    assert references.detect("Đọc nhãn thực phẩm cần chú ý những gì?") is None
    assert references.detect("GI miến đậu xanh bao nhiêu?") == "gi"
    assert references.detect("GI là gì?") is None
    assert references.detect("Hệ số sống–chín là gì?") is None


def test_source_cell_locators_and_citation_preview_paths(references):
    result = lookup(references, "label", "supp-mcm-product-40-label-p4", 100, "g")
    citation = make_citations(references.hits(result))[0]
    assert citation.document_url == "/api/supplements/supp-mcm-product-40-label-p4/preview"
    assert citation.locators == ["PDF page 4"] and citation.source_id == "mcm-product-40"


def test_changed_export_hash_blocks_loading(tmp_path):
    (tmp_path / "records.json").write_text('{"records": []}', encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"files": {"records.json": "wrong"}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="checksum"):
        SupplementCatalog(tmp_path)


def test_reference_chat_uses_tool_and_keeps_selection_quantity(system):
    provider = system.provider
    provider.food_plan = FoodPlan(
        operation="lookup",
        items=[FoodItem(name="sữa tươi Mộc Châu", amount=200, unit="ml")],
        nutrients=["carbohydrate"],
    )
    provider.answer = GeneratedAnswer(
        supported=True,
        blocks=[AnswerBlock(text="Cần chọn loại sữa trong danh sách.", citation_ids=["C1"])],
        uncertainty="",
    )
    first = system.client.post(
        "/api/chat", json={"message": "200 ml sữa tươi Mộc Châu bao nhiêu carbohydrate?"}
    ).json()
    selected = next(
        c
        for c in first["reference_result"]["unresolved"][0]["candidates"]
        if "không đường" in c["name"] and "5 sao" in c["name"]
    )
    provider.answer = GeneratedAnswer(
        supported=True,
        blocks=[
            AnswerBlock(text="Theo nhãn, lượng hỏi có 9,4 g carbohydrate.", citation_ids=["C1"])
        ],
        uncertainty="",
    )
    second = system.client.post(
        "/api/chat", json={"message": selected["id"], "session_id": first["session_id"]}
    ).json()
    item = second["reference_result"]["items"][0]
    assert item["requested_amount"] == 200 and item["requested_unit"] == "ml"
    assert item["calculated_nutrients"]["carbohydrate_g"] == 9.4


def test_qualifiers_match_words_not_substrings(references):
    result = lookup(
        references,
        "label",
        "sữa tươi không đường Mộc Châu",
        200,
        "ml",
        "200 ml sữa tươi không đường Mộc Châu bao nhiêu carbohydrate?",
    )
    assert result["items"][0]["id"] == "supp-mcm-product-12-label-p5"


def test_supplement_api_has_source_downloads_and_pagination(system):
    response = system.client.get(
        "/api/supplements", params={"domain": "portion", "limit": 2, "offset": 2}
    )
    assert response.status_code == 200
    assert response.json()["total"] == 220 and len(response.json()["results"]) == 2
    response = system.client.get("/api/supplements/supp-mcm-product-40-label-p4/original")
    assert response.status_code == 200 and response.content.startswith(b"%PDF")
    assert system.client.get("/api/supplements/unknown/original").status_code == 404


def test_reference_api_pagination_and_source_download(system):
    result = system.client.get(
        "/api/supplements", params={"domain": "portion", "limit": 2, "offset": 3}
    ).json()
    assert result["total"] == 220 and len(result["results"]) == 2
    rid = "supp-mcm-product-40-label-p4"
    assert system.client.get(f"/api/supplements/{rid}/preview").status_code == 200
    response = system.client.get(f"/api/supplements/{rid}/original")
    assert response.status_code == 200 and response.content.startswith(b"%PDF-")
    assert system.client.get("/api/supplements/not-real/original").status_code == 404


def test_emergency_routing_precedes_reference_catalog(system):
    response = system.client.post(
        "/api/chat", json={"message": "Tôi đang bất tỉnh sau khi uống sữa Mộc Châu."}
    ).json()
    assert response["intent"] == "emergency" and response["reference_result"] is None
