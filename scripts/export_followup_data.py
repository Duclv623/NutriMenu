"""Preserve source tables and export measured Vietnamese reference portions.

Never equate a raw ingredient mass, vessel volume, or minimum yield with an
exact measured finished dish mass. Label transcription is visually reviewed.
"""

import csv
import hashlib
import json
import re

import pdfplumber

from scripts.collect_rag_supplements import DEST

SID = "nin-cooked-weight-reference-2017"


def read(path):
    return json.loads((DEST / path).read_text(encoding="utf-8-sig"))


def write(path, data):
    (DEST / path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def number(s):
    return float(str(s).replace(",", ".")) if re.fullmatch(r"\d+(?:[.,]\d+)?", str(s)) else None


def csvwrite(path, rows):
    with (DEST / path).open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def portions():
    pdf = pdfplumber.open(DEST / f"raw/{SID}.pdf")
    all_tables = []
    for page in pdf.pages:
        for tid, table in enumerate(page.extract_tables(), 1):
            all_tables.append(
                {"source_id": SID, "page": page.page_number, "table": tid, "rows": table}
            )
    write(f"extracted/{SID}.tables.json", all_tables)
    records = []
    for page_number in range(34, 54):
        table = next(t["rows"] for t in all_tables if t["page"] == page_number)
        food = clean(table[0][0])
        code = clean(table[0][1]).replace("Mã ", "").replace("MÃ ", "")
        for row_index, row in enumerate(table[4:], 5):
            if not row[0]:
                continue
            for method, cooked, raw in [("xào", 2, 3), ("luộc", 4, 5)]:
                if number(row[cooked]) is None or number(row[raw]) is None:
                    continue
                vessel = re.search(r"(\d+)\s*ml", clean(row[0]))
                oil = salt = None
                if method == "xào" and row[1]:
                    following = table[row_index : row_index + 2]
                    for next_row in following:
                        if any(w in clean(next_row[1]).lower() for w in ["dầu", "mỡ"]):
                            oil = number(next_row[cooked])
                        if "gia vị" in clean(next_row[1]).lower():
                            salt = number(next_row[cooked])
                records.append(
                    {
                        "record_id": f"nin-portion-p{page_number}-r{row_index}-{method}",
                        "food_name": food,
                        "source_food_code": code,
                        "preparation": method,
                        "portion_description": clean(row[0]),
                        "vessel_capacity_ml": int(vessel[1]) if vessel else None,
                        "cooked_food_component_g": number(row[cooked]),
                        "raw_edible_equivalent_g": number(row[raw]),
                        "oil_fat_g": oil,
                        "salty_seasoning_g": salt,
                        "total_finished_dish_g": None,
                        "source_id": SID,
                        "source_page": page_number,
                        "source_table": 11,
                        "source_row": row_index,
                        "review_status": "extracted_source_cells_with_row_locators",
                        "rag_enabled": False,
                    }
                )
    table = next(t["rows"] for t in all_tables if t["page"] == 56)
    # Only rice rows with an explicit vessel. Porridge has an unlabeled vessel
    # row and a 14 g raw value requiring source clarification; retained in raw.
    for idx, row in enumerate(table[2:6], 3):
        food = "Gạo nếp" if idx < 5 else "Gạo tẻ"
        for j, fill in enumerate(["Miệng bát", "2/3 bát", "1/2 bát"]):
            records.append(
                {
                    "record_id": f"nin-portion-p56-r{idx}-c{j}",
                    "food_name": food,
                    "source_food_code": "01002" if idx < 5 else "01004",
                    "preparation": "nấu cơm",
                    "portion_description": fill + "; " + clean(row[3]),
                    "vessel_capacity_ml": int(re.search(r"(\d+)\s*ml", row[3])[1]),
                    "cooked_food_component_g": number(row[4 + j]),
                    "raw_edible_equivalent_g": number(row[7 + j]),
                    "oil_fat_g": None,
                    "salty_seasoning_g": None,
                    "total_finished_dish_g": None,
                    "source_id": SID,
                    "source_page": 56,
                    "source_table": 14,
                    "source_row": idx,
                    "review_status": "visually_checked_source_cells",
                    "rag_enabled": False,
                }
            )
    write(
        "structured/vietnamese-measured-portions.json",
        {
            "source_id": SID,
            "measurement_method_page": 27,
            "notes_vi": "Số tham khảo từ bảng NIN: trung bình cân 4 hộ (2 nông thôn, 2 thành thị). Gram rau chín là riêng phần rau, không tự cộng thành khối lượng cả món. Mức đầy/kích thước bát và cách chế biến phải khớp; không mặc định mọi bát có cùng khối lượng. Bảng canh p54/55 có mâu thuẫn thể tích và mã, bảng cháo p56 có ô cần làm rõ nên chưa xuất thành quy đổi dùng được.",
            "records": records,
        },
    )
    csvwrite("structured/vietnamese-measured-portions.csv", records)
    yields = []
    for t in all_tables:
        if not 12 <= t["page"] <= 21:
            continue
        last_code = last_name = None
        for idx, row in enumerate(t["rows"][1:], 2):
            last_code = clean(row[1]) or last_code
            last_name = clean(row[2]) or last_name
            if number(row[4]) is not None:
                yields.append(
                    {
                        "source_page": t["page"],
                        "source_table": t["table"],
                        "source_row": idx,
                        "food_code": last_code,
                        "food_name": last_name,
                        "preparation": clean(row[3]),
                        "raw_to_cooked_mass_ratio": number(row[4]),
                        "source_id": SID,
                        "review_status": "table_extracted_not_all_cells_visually_reviewed",
                        "rag_enabled": False,
                    }
                )
    write(
        "structured/nin-raw-cooked-ratios.json",
        {
            "definition": "HSSC = raw edible mass / cooked mass; not cooked / raw.",
            "records": yields,
        },
    )
    csvwrite("structured/nin-raw-cooked-ratios.csv", yields)
    recipes = []
    for page in read(f"extracted/{SID}.pages.json")[67:77]:
        for idx, section in enumerate(re.split(r"Tên món ăn:\s*", page["text"])[1:], 1):
            name = clean(section.split("\n")[0])
            basis = re.search(r"Mô tả:\s*(.+?)\nThành", section, re.S)
            original_basis = (
                clean(basis[1])
                if basis
                else clean(re.search(r"Thành\s*phần\s*/\s*([^\n]+)", section)[1])
                if re.search(r"Thành\s*phần\s*/\s*([^\n]+)", section)
                else None
            )
            split = re.split(r"Trọng\s*lượng\s*sống\s*sạch", section, maxsplit=1)
            ingredients = re.findall(r"^-\s*(.+)$", split[0], re.M)
            quantities = re.findall(r"^-\s*(.+)$", split[1], re.M) if len(split) > 1 else []
            items = []
            for i, ingredient in enumerate(ingredients):
                quantity = clean(quantities[i]) if i < len(quantities) else None
                match = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(g|ml)", quantity or "")
                items.append(
                    {
                        "name": clean(ingredient),
                        "quantity_original": quantity,
                        "value": number(match[1]) if match else None,
                        "unit": match[2] if match else None,
                        "weight_basis_original": "Trọng lượng sống sạch (source heading)",
                        "quantity_status": "declared" if match else "missing_or_unit_unspecified",
                    }
                )
            recipes.append(
                {
                    "record_id": f"nin-recipe-p{page['page']}-{idx}",
                    "name": name,
                    "source_id": SID,
                    "source_page": page["page"],
                    "serving_description_original": original_basis,
                    "ingredients": items,
                    "finished_weight_g": None,
                    "finished_yield_status": "portion_count_or_vessel_description_only_no_finished_grams",
                    "cooking_steps": None,
                    "complete_quantities": len(ingredients) == len(quantities)
                    and all(x["value"] is not None for x in items),
                    "source_text_original": section.strip(),
                    "review_status": "ingredient_columns_visually_checked_pages_68_77",
                    "status": "reference_composition_not_complete_yield_verified_recipe",
                    "rag_enabled": False,
                }
            )
    write(
        "structured/vietnamese-reference-recipes.json",
        {
            "notes_vi": "Phụ lục thành phần món ăn p68–77, không phải bộ công thức nấu đầy đủ. Giữ nguyên lượng sống sạch theo tiêu đề; không cộng nguyên liệu để coi là gram thành phẩm. Các suất/bát trong nguồn chưa có khối lượng món chín xác minh.",
            "records": recipes,
        },
    )
    return {
        "vietnamese_measured_portion_rows": len(records),
        "vietnamese_portion_food_types": len({r["food_name"] for r in records}),
        "nin_raw_cooked_ratio_rows": len(yields),
        "vietnamese_reference_recipe_rows": len(recipes),
        "vietnamese_recipe_complete_quantity_rows": sum(r["complete_quantities"] for r in recipes),
    }


def milk_labels():
    # These numbers were read from the saved page crops and compared with the
    # full PDF label, not accepted from the English OCR draft alone.
    labels = [
        ("01", 4, "Sữa tươi nguyên chất tiệt trùng MCC", "ml", 64.1, 3.0, 3.7, 4.7, None, 29, 110),
        ("10", 6, "Sữa tươi tiệt trùng ít đường MCC", "ml", 72.4, 3.0, 3.6, 7.0, 5.8, 29, 109),
        ("11", 6, "Sữa tươi tiệt trùng có đường MCC", "ml", 77.1, 2.9, 3.5, 8.5, 8.2, 28, 110),
        ("12", 5, "Sữa tươi tiệt trùng không đường MCC", "ml", 64.1, 3.0, 3.7, 4.7, None, 29, 110),
        (
            "13",
            4,
            "Sữa tươi tiệt trùng có đường Mộc Châu 5 sao",
            "ml",
            78.4,
            3.0,
            3.6,
            8.5,
            8.2,
            28,
            110,
        ),
        (
            "14",
            4,
            "Sữa tươi tiệt trùng không đường Mộc Châu 5 sao",
            "ml",
            64.1,
            3.0,
            3.7,
            4.7,
            None,
            29,
            110,
        ),
        ("37", 5, "Sữa chua ít đường MCC", "g", 87.1, 3.1, 3.5, 10.8, 9.0, 40, 100),
        ("39", 4, "Sữa chua có đường MCC", "g", 101.4, 3.1, 3.4, 14.6, 12.6, 24, 100),
        ("40", 4, "Sữa chua không đường MCC", "g", 62.3, 3.2, 3.5, 4.5, None, 26, 115),
    ]
    records = []
    for sid, page, name, unit, energy, protein, fat, carb, sugars, sodium, calcium in labels:
        source_id = "mcm-product-" + sid
        entry = read(f"entries/{source_id}.json")
        records.append(
            {
                "record_id": source_id + "-label-p" + str(page),
                "source_id": source_id,
                "product_name": name,
                "source_page": page,
                "source_url": entry["final_url"],
                "source_sha256": entry["sha256"],
                "basis_amount": 100,
                "basis_unit": unit,
                "energy_kcal": energy,
                "protein_g": protein,
                "fat_g": fat,
                "carbohydrate_g": carb,
                "total_sugars_g": sugars,
                "added_sugars_g": None,
                "fiber_g": None,
                "sodium_mg": sodium,
                "calcium_mg": calcium,
                "reviewed_crop": f"qa/mcm-table-{sid}.png",
                "review_status": "visually_checked_nutrition_table",
                "all_pack_variants_reviewed": False,
                "rag_enabled": False,
            }
        )
        ocr_file = f"extracted/{source_id}.ocr.pages.json"
        entry.update(
            ocr_file=ocr_file,
            ocr_sha256=hashlib.sha256((DEST / ocr_file).read_bytes()).hexdigest(),
            ocr_pages=len(read(ocr_file)["pages"]),
            status="ocr_complete_selected_nutrition_table_visually_checked",
            reviewed_label_page=page,
            structured_label_file="structured/mcm-product-nutrition-reviewed.json",
        )
        write(f"entries/{source_id}.json", entry)
    write(
        "structured/mcm-product-nutrition-reviewed.json",
        {
            "notes_vi": "9 bảng nhãn đã so ảnh, OCR toàn bộ 48 trang. Số theo 100 ml hoặc 100 g ghi trên nhãn; chất không công bố là null. Chỉ bảng tại trang/crop được nêu đã so từng ô; không khẳng định mọi quy cách/nhãn khác trong PDF đều đã so.",
            "records": records,
        },
    )
    csvwrite("structured/mcm-product-nutrition-reviewed.csv", records)
    return {
        "mcm_ocr_documents": 9,
        "mcm_ocr_pages": 48,
        "mcm_visually_checked_nutrition_tables": len(records),
    }


def main():
    counts = {**portions(), **milk_labels()}
    write("structured/followup-counts.json", counts)
    print(json.dumps(counts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
