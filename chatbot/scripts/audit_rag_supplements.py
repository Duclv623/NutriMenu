"""Audit source hashes and independently observed CDC table transcription."""

import csv
import hashlib
import json
import re
from datetime import UTC, datetime

from scripts.collect_rag_supplements import DEST


def read(path):
    return json.loads((DEST / path).read_text(encoding="utf-8-sig"))


def fnv(text):
    data = re.sub(r"\s+", "", text).encode("utf-16-le")
    value = 2166136261
    for i in range(0, len(data), 2):
        value = ((value ^ int.from_bytes(data[i : i + 2], "little")) * 16777619) & 0xFFFFFFFF
    return value


def main():
    manifest = read("manifest.json")
    issues, checks = [], {}
    for entry in manifest["sources"]:
        for file_key, hash_key in [
            ("raw_file", "sha256"),
            ("extracted_file", "extracted_sha256"),
            ("ocr_file", "ocr_sha256"),
        ]:
            if file_key in entry:
                actual = hashlib.sha256((DEST / entry[file_key]).read_bytes()).hexdigest()
                if actual != entry[hash_key]:
                    issues.append(f"{entry['id']}: {file_key} checksum mismatch")
        if entry.get("ocr_file"):
            pages = read(entry["ocr_file"])["pages"]
            if {p["page"] for p in pages} != set(range(1, entry["pages"] + 1)):
                issues.append(entry["id"] + ": incomplete OCR pages")
            for page in pages:
                if (
                    hashlib.sha256((DEST / page["image_path"]).read_bytes()).hexdigest()
                    != page["image_sha256"]
                ):
                    issues.append(entry["id"] + ": OCR image hash differs")
    for item in manifest.get("derived_files", []):
        if hashlib.sha256((DEST / item["file"]).read_bytes()).hexdigest() != item["sha256"]:
            issues.append(item["file"] + ": derived file hash differs")
    checks["ocr_documents_complete"] = sum(bool(e.get("ocr_file")) for e in manifest["sources"])
    labels = read("structured/mcm-product-nutrition-reviewed.json")["records"]
    for label in labels:
        if (
            label["basis_amount"] != 100
            or label["basis_unit"] not in ["g", "ml"]
            or label["added_sugars_g"] is not None
        ):
            issues.append(label["record_id"] + ": incorrect label basis or inferred nutrient")
        if not (DEST / label["reviewed_crop"]).is_file():
            issues.append(label["record_id"] + ": missing reviewed crop")
    checks["mcm_reviewed_tables"] = len(labels)
    portions = read("structured/vietnamese-measured-portions.json")["records"]
    tables = read("extracted/nin-cooked-weight-reference-2017.tables.json")
    for portion in portions:
        table = next(t["rows"] for t in tables if t["page"] == portion["source_page"])
        row = table[portion["source_row"] - 1]
        if portion["source_page"] == 56:
            col = int(portion["record_id"].rsplit("c", 1)[-1]) + 4
        else:
            col = 2 if portion["preparation"] == "xào" else 4
        for name, idx in [
            ("cooked_food_component_g", col),
            ("raw_edible_equivalent_g", col + (3 if portion["source_page"] == 56 else 1)),
        ]:
            if float(row[idx].replace(",", ".")) != portion[name]:
                issues.append(portion["record_id"] + ": portion differs from source cell")
        if portion["total_finished_dish_g"] is not None:
            issues.append(portion["record_id"] + ": inferred total finished dish mass")
    checks["nin_portions_match_original_cells"] = len(portions)
    recipes = read("structured/vietnamese-reference-recipes.json")["records"]
    meals = read("structured/vietduc-minimum-yield-meal-specifications.json")["records"]
    if any(r["finished_weight_g"] is not None for r in recipes + meals):
        issues.append("Unmeasured Vietnamese finished yield exported as exact")
    checks["nin_reference_recipes_with_unmeasured_yield"] = len(recipes)
    checks["vietduc_minimum_yield_specs_not_exact"] = len(meals)
    overrides = read("structured/th-product-reviewed-overrides.json")["records"]
    reviews = read("structured/th-product-followup-review.json")
    for override in overrides:
        evidence = next(
            e
            for e in reviews["alternative_tables"]
            if e["source_id"] == override["source_review_id"]
        )
        source = next(e for e in manifest["sources"] if e["id"] == evidence["source_id"])
        original = next(
            b for b in read(source["extracted_file"]) if b["locator"] == evidence["table_locator"]
        )
        if (
            original["rows"] != evidence["rows_original"]
            or original["rows"][-1][1] != "10 mg"
            or override["nutrients"]["sodium_mg"] != 10
        ):
            issues.append("TH override differs from verified alternative source")
    checks["th_flagged_tables_reviewed"] = len(reviews["records"])
    if any(
        r["rag_enabled"]
        for r in portions + labels + recipes + meals + overrides + reviews["records"]
    ):
        issues.append("Followup record prematurely enabled for RAG")
    choices = read("structured/cdc-carb-choices.json")["records"]
    browser = read("structured/cdc-browser-row-hashes.json")
    local_hashes = [fnv(r["food_original"] + r["serving_original"]) for r in choices]
    if local_hashes != browser["row_hashes"]:
        issues.append("CDC food/serving transcription differs from browser DOM")
    checks["cdc_rows_match_browser"] = (
        len(choices) == browser["rows"] and local_hashes == browser["row_hashes"]
    )
    checks["cdc_group_count"] = browser["tables"]
    checks["cdc_native_serving_units_preserved"] = all(
        r["portion_weight_g"] is None for r in choices
    )
    products = read("structured/product-nutrition.json")["records"]
    for record in products:
        entry = next(e for e in manifest["sources"] if e["id"] == record["source_id"])
        original = next(
            b for b in read(entry["extracted_file"]) if b["locator"] == record["source_locator"]
        )
        if record["original_rows"] != original["rows"]:
            issues.append(record["record_id"] + ": original label table differs")
        for name, item in record["nutrients"].items():
            if not item:
                continue
            row = original["rows"][item["row"] - 1]
            if (
                item["original_label"] != row[0].strip()
                or item["original_value"] != " ".join(row[1:]).strip()
            ):
                issues.append(record["record_id"] + ": nutrient row differs: " + name)
            if (
                item["unit"].lower() != item["normalized_unit"]
                and item["normalized_value"] is not None
            ):
                issues.append(record["record_id"] + ": unverified unit published numerically")
    checks["product_original_tables_preserved"] = len(products)
    checks["product_basis_units"] = sorted({str(r["reference_unit"]) for r in products})
    checks["undeclared_nutrients_remain_null"] = all(
        r["nutrients"]["added_sugars_g"] is None for r in products
    )
    gi = read("structured/gi-sydney-all.json")["records"]
    table = next(
        b["rows"] for b in read("extracted/sydney-gi-search.blocks.json") if b["tag"] == "table"
    )
    if len(gi) != len(table) - 1 or any(
        [r[h] for h in table[0]] != values for r, values in zip(gi, table[1:], strict=True)
    ):
        issues.append("GI export differs from original table")
    checks["gi_table_rows_preserved"] = len(gi)
    for path, count in [
        ("structured/cdc-carb-choices.csv", 85),
        ("structured/product-nutrition.csv", 45),
        ("structured/gi-sydney-all.csv", 4384),
    ]:
        with (DEST / path).open(encoding="utf-8-sig", newline="") as stream:
            actual = len(list(csv.DictReader(stream)))
        if actual != count:
            issues.append(path + ": CSV row count differs")
    checks["no_new_source_marked_indexed"] = all(
        e["rag_enabled"] is False for e in manifest["sources"]
    )
    if not all(
        v
        for k, v in checks.items()
        if k
        in [
            "cdc_rows_match_browser",
            "cdc_native_serving_units_preserved",
            "undeclared_nutrients_remain_null",
            "no_new_source_marked_indexed",
        ]
    ):
        issues.append("One or more preservation checks failed")
    report = {
        "audited_at": datetime.now(UTC).isoformat(),
        "counts": manifest["counts"],
        "checks": checks,
        "errors": issues,
        "status": "pass" if not issues else "fail",
        "clinical_validation": False,
        "limits_vi": "Kiểm bảo toàn số liệu/cơ sở và nguồn; chưa kiểm thủ công mọi ô hoặc nghiệm thu chất lượng trả lời. CDC: dấu từng dòng lấy độc lập từ DOM, chỉ bỏ khoảng trắng.",
    }
    (DEST / "collection-audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if issues:
        raise ValueError(issues)


if __name__ == "__main__":
    main()
