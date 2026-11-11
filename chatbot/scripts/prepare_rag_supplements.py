"""Offline exports and integrity checks for the supplementary source pack."""

import csv
import hashlib
import json
import re
from datetime import UTC, datetime

from lxml import html

from scripts.collect_rag_supplements import DEST


def read(path):
    return json.loads((DEST / path).read_text(encoding="utf-8-sig"))


def write(path, value):
    (DEST / path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def csv_export(path, records):
    with (DEST / path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def gi_exports():
    blocks = read("extracted/sydney-gi-search.blocks.json")
    table = next(b for b in blocks if b["tag"] == "table")
    header, *rows = table["rows"]
    assert len(header) == 13 and all(len(row) == 13 for row in rows)
    records = [
        {"source_row": i, **dict(zip(header, row, strict=True))} for i, row in enumerate(rows, 1)
    ]
    csv_export("structured/gi-sydney-all.csv", records)
    write(
        "structured/gi-sydney-all.json",
        {"source_id": "sydney-gi-search", "source_locator": table["locator"], "records": records},
    )
    related = [r for r in records if "vietnam" in " ".join(str(v) for v in r.values()).lower()]
    study = [r for r in related if "Vietnamese foods" in r["Reference:"]]
    products = [r for r in related if r["Country of food production"].lower() == "vietnam"]
    csv_export("structured/gi-vietnam-related.csv", related)
    write(
        "structured/gi-vietnam-related.json",
        {
            "source_id": "sydney-gi-search",
            "study_rows": study,
            "vietnam_product_rows": products,
            "notes_vi": [
                "Các bản ghi liên quan Việt Nam gồm nghiên cứu món Việt và sản phẩm sản xuất tại Việt Nam; không phải mọi dòng đều có xuất xứ Việt Nam.",
                "Giữ riêng các bản ghi lặp hoặc khác điều kiện. Không nối theo tên vào NIN khi chưa xác minh tương đương.",
                "Ô khẩu phần trống vẫn là chuỗi trống; GL gốc dựa trên lượng carbohydrate của chính bản ghi.",
                "Custard apple: Sydney ghi GI 54, Table 2 bản bài báo ghi 58 cho nhóm gộp; chưa giải quyết khác biệt, không duyệt để trả số.",
            ],
            "rag_enabled": False,
            "clinical_review": False,
        },
    )
    return {
        "gi_rows": len(records),
        "gi_vietnam_related_rows": len(related),
        "gi_chan_study_rows": len(study),
        "gi_vietnam_product_rows": len(products),
    }


NUTRIENTS = [
    ("energy_kcal", ["năng lượng", "energy"]),
    ("protein_g", ["chất đạm", "protein"]),
    ("carbohydrate_g", ["carbohydrat", "carbonhydrat"]),
    ("total_sugars_g", ["đường tổng", "total sugars"]),
    ("added_sugars_g", ["đường bổ sung", "added sugars"]),
    ("fiber_g", ["chất xơ", "fibre", "fiber"]),
    ("fat_g", ["chất béo", "total fat"]),
    ("sodium_mg", ["natri", "sodium"]),
]


def product_exports():
    records, long_rows, problems = [], [], []
    for path in sorted((DEST / "entries").glob("th-product-*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        if entry["id"] == "th-product-catalog":
            continue
        blocks = read(entry["extracted_file"])
        document = html.fromstring((DEST / entry["raw_file"]).read_bytes())
        tables = [b for b in blocks if b["tag"] == "table"]
        for table in tables:
            node = document.xpath(table["xpath"])[0]
            context = " ".join(node.getparent().getparent().text_content().split())
            # Require a nutrition heading, never infer the basis from the package size.
            basis = re.search(
                r"(?:dinh dưỡng[^:]{0,65}?(?:trong|per)|nutrition information per)\s*(\d+(?:[.,]\d+)?)\s*(ml|g)\b",
                context,
                re.I,
            )
            package = re.search(
                r"(?:Khối lượng|Thể tích)\s*:?\s*(\d+(?:[.,]\d+)?)\s*(ml|kg|g|l)\b", context, re.I
            )
            product = {
                "record_id": entry["id"],
                "name_vi": entry["title"] or entry["html_title"],
                "source_id": entry["id"],
                "source_url": entry["final_url"],
                "source_sha256": entry["sha256"],
                "source_locator": table["locator"],
                "reference_amount": float(basis[1].replace(",", ".")) if basis else None,
                "reference_unit": basis[2].lower() if basis else None,
                "reference_text": basis[0] if basis else None,
                "package_amount": float(package[1].replace(",", ".")) if package else None,
                "package_unit": package[2].lower() if package else None,
                "package_source_text": package[0] if package else None,
                "servings_per_package_declared": None,
                "nutrients": {},
                "original_rows": table["rows"],
                "rag_enabled": False,
                "clinical_review": False,
                "quality_notes": [],
            }
            for row_index, row in enumerate(table["rows"], 1):
                if len(row) < 2:
                    continue
                label = row[0].strip()
                raw = " ".join(row[1:]).strip()
                match = re.fullmatch(
                    r"([<>≤≥]?)\s*(\d+(?:[.,]\d+)?)\s*(kcal|mg|g|µg|mcg|ug|kJ)", raw, re.I
                )
                if not match:
                    continue
                nutrient = next(
                    (key for key, aliases in NUTRIENTS if any(a in label.lower() for a in aliases)),
                    None,
                )
                parsed = {
                    "value": float(match[2].replace(",", ".")),
                    "qualifier": match[1] or None,
                    "unit": match[3],
                    "original_label": label,
                    "original_value": raw,
                    "row": row_index,
                }
                if nutrient:
                    expected_unit = (
                        "kcal"
                        if nutrient == "energy_kcal"
                        else ("mg" if nutrient.endswith("_mg") else "g")
                    )
                    if parsed["unit"].lower() != expected_unit:
                        product["quality_notes"].append("unit_mismatch:" + nutrient)
                    parsed["normalized_value"] = (
                        parsed["value"] if parsed["unit"].lower() == expected_unit else None
                    )
                    parsed["normalized_unit"] = expected_unit
                    if nutrient in product["nutrients"]:
                        product["quality_notes"].append("duplicate_nutrient:" + nutrient)
                    else:
                        product["nutrients"][nutrient] = parsed
                long_rows.append(
                    {
                        "record_id": entry["id"],
                        "table": table["locator"],
                        "row": row_index,
                        "original_label": label,
                        "original_value": raw,
                        "value": parsed["value"],
                        "qualifier": parsed["qualifier"] or "",
                        "unit": parsed["unit"],
                    }
                )
            for nutrient, _ in NUTRIENTS:
                product["nutrients"].setdefault(nutrient, None)
            if not basis:
                product["quality_notes"].append("nutrition_reference_amount_unresolved")
            if "top-kid" in entry["url"] or "topkid" in entry["url"] or "creamy" in entry["url"]:
                product["quality_notes"].append("children_product_outside_adult_corpus")
            if "banh-gao-mozzarella-" in entry["id"]:
                product["quality_notes"].append(
                    "source_lists_protein_44g_carbohydrate_3g_needs_label_crosscheck"
                )
            carb = product["nutrients"]["carbohydrate_g"]
            sugars = product["nutrients"]["total_sugars_g"]
            if (
                carb
                and sugars
                and not carb["qualifier"]
                and not sugars["qualifier"]
                and sugars["value"] > carb["value"]
            ):
                product["quality_notes"].append("total_sugars_exceed_carbohydrate")
            if not carb:
                product["quality_notes"].append("carbohydrate_not_declared_or_unparsed")
            product["status"] = (
                "needs_source_review"
                if product["quality_notes"]
                else "structured_pending_integration"
            )
            if product["quality_notes"]:
                problems.append(
                    {"record_id": product["record_id"], "notes": product["quality_notes"]}
                )
            records.append(product)
    write(
        "structured/product-nutrition.json",
        {
            "records": records,
            "notes_vi": "Dữ liệu web của nhà sản xuất, chưa là OCR nhãn vật lý. Không dùng nội dung quảng cáo làm khuyến nghị bệnh học. Không đồng nhất 100 ml với 100 g.",
        },
    )
    csv_export("structured/product-nutrients-long.csv", long_rows)
    flat = []
    for product in records:
        row = {
            k: product[k]
            for k in [
                "record_id",
                "name_vi",
                "source_url",
                "source_locator",
                "reference_amount",
                "reference_unit",
                "package_amount",
                "package_unit",
                "status",
            ]
        }
        for nutrient, _ in NUTRIENTS:
            item = product["nutrients"][nutrient]
            row[nutrient] = item["normalized_value"] if item and not item["qualifier"] else None
            row[nutrient + "_original"] = item["original_value"] if item else None
        row["quality_notes"] = "|".join(product["quality_notes"])
        flat.append(row)
    csv_export("structured/product-nutrition.csv", flat)
    write("structured/product-quality-issues.json", problems)
    return {
        "product_web_tables": len(records),
        "product_needs_review": len(problems),
        "product_no_blocking_issue": len(records) - len(problems),
        "product_nutrient_rows": len(long_rows),
    }


def cooking_exports():
    with (DEST / "raw/usda-cooking-yields.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    write(
        "structured/usda-cooking-yields.json",
        {
            "source_id": "usda-cooking-yields-csv",
            "records": rows,
            "notes_vi": "Dữ liệu thịt/gia cầm và quy trình USDA. Không tự áp dụng thành hệ số chung cho món Việt hoặc mọi miếng thịt.",
        },
    )
    with (DEST / "raw/usda-retention.txt").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter="^", quotechar="~")
        retention = []
        header = [
            "retention_code",
            "food_group_code",
            "food_description",
            "nutrient_number",
            "nutrient_description",
            "retention_percent",
            "source_date",
        ]
        for i, row in enumerate(reader, 1):
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError(f"Retention row {i}: unexpected field count {len(row)}")
            retention.append(dict(zip(header, row, strict=True)))
    csv_export("structured/usda-retention.csv", retention)
    write(
        "structured/usda-retention.json", {"source_id": "usda-retention-txt", "records": retention}
    )
    return {
        "cooking_yield_rows": len(rows),
        "retention_rows": len(retention),
        "retention_food_preparation_codes": len({r["retention_code"] for r in retention}),
    }


def recipe_exports():
    pages = read("extracted/cdc-recipes.pages.json")
    recipes = []
    for page_number in range(16, 38, 2):
        first, second = pages[page_number - 1], pages[page_number]
        servings = re.search(r"Total Servings:\s*(\d+)", second["text"])
        recipes.append(
            {
                "record_id": f"cdc-recipe-p{page_number}",
                "source_id": "cdc-recipes",
                "source_locator": f"PDF pages {page_number}-{page_number + 1}",
                "ingredients_directions_original": first["text"],
                "nutrition_original": second["text"],
                "total_servings_declared": int(servings[1]) if servings else None,
                "finished_weight_g": None,
                "language": "en",
                "rag_enabled": False,
                "is_vietnamese_recipe": False,
                "clinical_review": False,
            }
        )
    write(
        "structured/cdc-recipes.json",
        {
            "notes_vi": "Công thức mẫu quốc tế từ booklet CDC; giữ số liệu theo suất gốc. Chưa quy đổi sang 100 g hoặc dùng cho món Việt cùng tên.",
            "records": recipes,
        },
    )
    return {"international_sample_recipes": len(recipes)}


def main():
    counts = {**gi_exports(), **product_exports(), **cooking_exports(), **recipe_exports()}
    if (DEST / "structured/followup-counts.json").exists():
        counts.update(read("structured/followup-counts.json"))
    sources = [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted((DEST / "entries").glob("*.json"))
    ]
    data_sources = read("structured/usda-data-downloads.json")
    for entry in data_sources:
        entry.update(
            language="en",
            topic="cooking_reference",
            retrieved_at=datetime.now(UTC).isoformat(),
            status="collected_pending_integration",
            rag_enabled=False,
            clinical_review=False,
        )
    sources.extend(data_sources)
    for entry in sources:
        if entry["id"] == "gi-vietnam-paper-2001":
            entry.update(
                publisher_url="https://www.nature.com/articles/1601265",
                doi="10.1038/sj.ejcn.1601265",
                download_is_public_mirror=True,
                review_notes=[
                    "Title/authors/journal and DOI checked against publisher bibliographic record; Table 1/2 visually checked",
                    "Custard apple GI differs from Sydney database; do not resolve by guessing",
                ],
            )
        if entry["id"] == "baclieu-diet":
            entry.update(
                status="reference_only_content_quality_concerns",
                review_notes=[
                    "Page 3: compulsory specialist product claim and sweetened-drink paragraph not approved; other diagnostic/meal prescriptions require review"
                ],
            )
        if entry["id"] == "nin-labels":
            entry.update(
                proposed_locators=["block-0159", "block-0161", "block-0163", "block-0180"],
                excluded_locators=["block-0173", "block-0184", "block-0164"],
                review_notes=[
                    "Selected serving/basis paragraphs only; legal thresholds and universal nutrient targets not approved"
                ],
            )
        if entry["id"].startswith("mcm-product-") and not entry.get("ocr_file"):
            entry.update(status="scanned_label_needs_ocr_and_cell_review")
        entry.setdefault("full_document_saved", True)
    errors = []
    for entry in sources:
        for file_key, hash_key in [("raw_file", "sha256"), ("extracted_file", "extracted_sha256")]:
            if file_key not in entry:
                continue
            actual = hashlib.sha256((DEST / entry[file_key]).read_bytes()).hexdigest()
            if actual != entry[hash_key]:
                errors.append(
                    {"source_id": entry["id"], "file": entry[file_key], "error": "sha256_mismatch"}
                )
    counts.update(
        source_snapshots=len(sources),
        vietnamese_sources=sum(e["language"] == "vi" for e in sources),
        pdf_files=sum(e.get("raw_file", "").endswith(".pdf") for e in sources),
        pdf_pages=sum(e.get("pages", 0) for e in sources),
        scanned_product_pdfs=sum(
            e["id"].startswith("mcm-product-")
            and e.get("pages", 0) > 0
            and e.get("text_pages") == 0
            for e in sources
        ),
    )
    counts["unique_source_urls"] = len({e["final_url"] for e in sources})
    prepared = [
        {
            "file": p.relative_to(DEST).as_posix(),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "language": "vi",
            "status": "prepared_pending_integration",
            "clinical_review": False,
            "rag_enabled": False,
        }
        for p in sorted((DEST / "reviewed").glob("*.md"))
    ]
    counts["vietnamese_prepared_documents"] = len(prepared)
    counts["cdc_choice_rows"] = len(read("structured/cdc-carb-choices.json")["records"])
    counts["gi_primary_study_foods"] = len(read("structured/gi-vietnam-study-2001.json")["records"])
    write(
        "manifest.json",
        {
            "schema_version": 2,
            "generated_at": datetime.now(UTC).isoformat(),
            "sources": sources,
            "counts": counts,
            "prepared_documents": prepared,
            "derived_files": [
                {
                    "file": p.relative_to(DEST).as_posix(),
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                }
                for folder in ["structured", "extracted", "qa"]
                for p in sorted((DEST / folder).rglob("*"))
                if p.is_file()
            ],
            "integrity_errors": errors,
            "active_rag_index_changed": False,
            "scope_vi": "Thu thập gốc, bản tóm lược tiếng Việt có định vị nguồn và export bảng. Chưa nạp nguồn mới vào index/tool đang chạy.",
        },
    )
    write(
        "collection-audit.json",
        {"counts": counts, "integrity_errors": errors, "clinical_review": False},
    )
    if errors:
        raise ValueError(errors)
    print(json.dumps(counts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
