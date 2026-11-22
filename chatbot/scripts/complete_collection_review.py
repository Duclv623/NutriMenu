"""Export reviewed evidence and explicit unresolved fields; do not invent yields."""

import hashlib
import json
from datetime import UTC, datetime

from scripts.collect_rag_supplements import DEST
from scripts.export_followup_data import read, write


def hospital_specs():
    records = []
    proteins = [
        "Thịt lợn nạc xay",
        "Thăn bò tươi xay",
        "Thịt gà ta xé",
        "Tôm đảo 90–110 con/kg",
        "Tim lợn",
    ]
    for code, page, title, vegetables, meat, oils in [
        ("BT04", 14, "Cháo các bệnh thông thường", 30, [50] * 5, [5] * 5),
        ("DD04", 15, "Cháo bệnh đái tháo đường", 100, [50, 40, 50, 40, 50], [5] * 5),
        ("TM04", 16, "Cháo bệnh tim mạch", 20, [50, 40, 50, 40, 50], [5, 6, 6, 7, 5]),
    ]:
        for i, protein in enumerate(proteins):
            records.append(
                {
                    "record_id": f"vietduc-{code}.{i + 1}",
                    "name": title + " — " + protein,
                    "source_id": "vietduc-meal-specifications-2024",
                    "source_page": page,
                    "source_menu_code": f"{code}.{i + 1}",
                    "ingredients": [
                        {
                            "name": name,
                            "declared_weight_g": weight,
                            "weighing_state": "not_explicitly_declared",
                        }
                        for name, weight in [
                            ("Gạo tám thái", 50),
                            (protein, meat[i]),
                            ("Rau", vegetables),
                            ("Dầu đậu tương", oils[i]),
                        ]
                    ],
                    "separate_dessert_original": (
                        [
                            "Sữa chua uống 65 (cột g; yêu cầu riêng ghi 65 ml)",
                            "Dưa hấu 300 g",
                            "Sữa chua uống 65 (cột g; yêu cầu riêng ghi 65 ml)",
                            "Chuối tiêu 126 g",
                            "Sữa chua uống 65 (cột g; yêu cầu riêng ghi 65 ml)",
                        ][i]
                        if code == "BT04"
                        else None
                    ),
                    "minimum_finished_weight_g": 450,
                    "minimum_finished_volume_ml": 500,
                    "minimum_energy_density_kcal_per_ml": 0.6,
                    "finished_weight_g": None,
                    "cooking_water_g": None,
                    "seasoning_g": None,
                    "cooking_steps": None,
                    "yield_status": "procurement_minimum_not_measured_exact_yield",
                    "review_status": "ingredients_and_minimum_yield_visually_checked",
                    "requires_clinical_review": True,
                    "rag_enabled": False,
                }
            )
    write(
        "structured/vietduc-minimum-yield-meal-specifications.json",
        {
            "notes_vi": "15 quy cách thuộc 3 chế độ, cùng 5 loại đạm; không phải 15 món độc lập hay công thức đầy đủ. 450 g/500 ml là mức thành phẩm tối thiểu được yêu cầu, không phải phép cân thực nghiệm. Không tính dinh dưỡng chính xác/100 g từ mức tối thiểu. Nước/gia vị/cách nấu và trạng thái cân nguyên liệu chưa đầy đủ. Giữ tráng miệng riêng.",
            "records": records,
        },
    )
    for sid, title in [
        (
            "vietduc-meal-specifications-2024",
            "Bệnh viện Việt Đức — thư mời báo giá suất ăn dinh dưỡng 2024–2025",
        ),
        ("vietduc-meal-decision-5267", "Bệnh viện Việt Đức — quyết định 5267 về suất ăn"),
    ]:
        entry = read(f"entries/{sid}.json")
        path = f"extracted/{sid}.ocr.pages.json"
        entry.update(
            title=title,
            ocr_file=path,
            ocr_sha256=hashlib.sha256((DEST / path).read_bytes()).hexdigest(),
            ocr_pages=len(read(path)["pages"]),
            status="ocr_complete_meal_specification_reference_only",
        )
        write(f"entries/{sid}.json", entry)
    return {
        "vietduc_ocr_documents": 2,
        "vietduc_ocr_pages": 52,
        "vietduc_minimum_yield_specifications": 15,
        "vietduc_distinct_protein_variants": 5,
        "vietnamese_complete_recipes_with_measured_finished_yield": 0,
    }


def product_reviews():
    issues = read("structured/product-quality-issues.json")
    records = []
    evidence = []
    for kind in ["macca", "dao", "oi", "tac", "vai"]:
        sid = f"thmart-{kind}-current-review"
        entry = read(f"entries/{sid}.json")
        blocks = read(entry["extracted_file"])
        table = next(b for b in blocks if b["tag"] == "table")
        evidence.append(
            {
                "source_id": sid,
                "url": entry["final_url"],
                "sha256": entry["sha256"],
                "table_locator": table["locator"],
                "rows_original": table["rows"],
                "basis_blocks": [b for b in blocks if "100 ml" in b["text"]],
            }
        )
    for issue in issues:
        rid = issue["record_id"]
        disposition = "unresolved_source_evidence"
        notes = "Bảng gốc chưa đủ cơ sở xác minh; giữ ô nghi vấn null, chưa dùng phép tính."
        refs = [rid]
        if "children_product_outside_adult_corpus" in issue["notes"]:
            disposition = "excluded_children_product"
            notes = "Giữ để kiểm kê, loại khỏi phạm vi khuyến nghị cho người trưởng thành."
        elif "macca" in rid:
            disposition = "resolved_using_current_official_alternative"
            refs.append("thmart-macca-current-review")
            notes = "TH true mart hiện tại ghi natri 10 mg/100 ml; năm chất còn lại khớp bảng THmilk. Giữ nguyên bản THmilk ghi 10 g và tạo bản đối chiếu riêng."
        elif any(x in rid for x in ["tra-dao-tu", "tra-oi-tu", "tra-tac-tu", "tra-vai-tu"]):
            kind = next(x for x in ["dao", "oi", "tac", "vai"] if f"tra-{x}-" in rid)
            refs.append(f"thmart-{kind}-current-review")
            notes = "Website TH true mart hiện tại vẫn ghi Natri 10 g. Nguồn thứ hai lặp lại lỗi không chứng minh 10 mg; cần nhãn/công bố đúng sản phẩm."
        elif "mozzarella" in rid:
            refs.append("thfood-mozzarella-review")
            notes = "Trang TH true FOOD có số đạm/carb khác THmilk và vẫn không nêu rõ cơ sở lượng. Hai nguồn mâu thuẫn; HTTP tải trang đối chiếu bị 403, lưu trích đoạn chọn lọc đã đọc, không gọi là HTML đầy đủ."
        elif "ca-cao" in rid:
            notes = "THmilk ghi đường tổng 12,2 mg. Danh mục sữa chua hiện tại của TH true mart không có đúng sản phẩm cacao; chưa tìm được nhãn chính hãng đối chiếu đơn vị."
        elif "khong-duong" in rid:
            notes = "Bảng THmilk thiếu cơ sở tính. Danh mục trà TH true mart hiện tại không liệt kê đúng hai bản không đường; URL cũ trà đào trả 404. Không dùng tên 350 ml làm cơ sở bảng dinh dưỡng."
        records.append(
            {
                **issue,
                "reviewed_at": datetime.now(UTC).isoformat(),
                "disposition": disposition,
                "review_notes_vi": notes,
                "evidence_source_ids": refs,
                "rag_enabled": False,
            }
        )
    write(
        "structured/th-product-followup-review.json",
        {"records": records, "alternative_tables": evidence},
    )
    original = next(
        r for r in read("structured/product-nutrition.json")["records"] if "macca" in r["record_id"]
    )
    source = next(e for e in evidence if "macca" in e["source_id"])
    assert source["rows_original"][-1][1] == "10 mg"
    resolved = {
        key: original[key] for key in ["record_id", "name_vi", "reference_amount", "reference_unit"]
    }
    resolved.update(
        nutrients={
            k: v["normalized_value"] if v else None for k, v in original["nutrients"].items()
        },
        source_original_id=original["source_id"],
        source_review_id=source["source_id"],
        review_locator=source["table_locator"],
        review_status="official_source_crosschecked",
        rag_enabled=False,
    )
    resolved["nutrients"]["sodium_mg"] = 10
    write("structured/th-product-reviewed-overrides.json", {"records": [resolved]})
    return {
        "th_flagged_tables_reviewed": 13,
        "th_flagged_excluded_children": 4,
        "th_flagged_resolved_alternative": 1,
        "th_flagged_still_unresolved": 8,
    }


def main():
    for ocr_path in (DEST / "extracted").glob("*.ocr.pages.json"):
        draft = json.loads(ocr_path.read_text(encoding="utf-8-sig"))
        for page in draft["pages"]:
            page["image_path"] = (
                "qa/ocr/" + page["image_path"].replace("\\", "/").rsplit("/", 1)[-1]
            )
        relative = ocr_path.relative_to(DEST).as_posix()
        write(relative, draft)
        entry = read(f"entries/{draft['source_id']}.json")
        entry.update(
            ocr_file=relative,
            ocr_sha256=hashlib.sha256(ocr_path.read_bytes()).hexdigest(),
            ocr_pages=len(draft["pages"]),
        )
        write(f"entries/{draft['source_id']}.json", entry)
    sid = "thfood-mozzarella-review"
    url = "https://thtruefood.com.vn/product/banh-gao-mozzarella-xot-pho-mai-th-true-food-300g/"
    path = f"raw/{sid}.selected-nutrition.vi.json"
    write(
        path,
        {
            "product_name": "Bánh Gạo Mozzarella Xốt Phô Mai TH true FOOD 300 g",
            "source_section": "Giá trị dinh dưỡng",
            "basis_amount": None,
            "basis_unit": None,
            "declared_values": {
                "energy_kcal": 255.4,
                "protein_g": 9.6,
                "carbohydrate_g": 20.5,
                "fat_g": 15,
                "salt_mg": 800,
            },
            "note": "Muối, không phải natri. Cơ sở tính chưa nêu; không tự chuyển sang 100 g.",
        },
    )
    write(
        f"entries/{sid}.json",
        {
            "id": sid,
            "title": "TH true FOOD — bảng dinh dưỡng bánh gạo Mozzarella chọn lọc",
            "language": "vi",
            "topic": "label_crosscheck",
            "url": url,
            "final_url": url,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "raw_file": path,
            "sha256": hashlib.sha256((DEST / path).read_bytes()).hexdigest(),
            "bytes": (DEST / path).stat().st_size,
            "acquisition_method": "web_reader_selected_nutrition_transcription",
            "full_document_saved": False,
            "direct_download_issue": "HTTP 403 in Python and Windows HTTPS",
            "status": "conflicting_reference_basis_unresolved",
            "rag_enabled": False,
            "clinical_review": False,
        },
    )
    counts = read("structured/followup-counts.json")
    counts.update(hospital_specs())
    counts.update(product_reviews())
    write("structured/followup-counts.json", counts)
    entry = read("entries/nin-cooked-weight-reference-2017.json")
    entry.update(
        download_is_public_mirror=True,
        original_publisher="Nhà xuất bản Y học / Viện Dinh dưỡng",
        publication_year=2017,
        isbn="978-604-66-3067-8",
        authors=["Lê Bạch Mai", "Tuấn Thị Mai Phương", "Đỗ Thị Phương Hà"],
        bibliography_source_id="nin-weight-reference-bibliography",
        status="measured_portion_reference_extracted_with_source_quality_exclusions",
    )
    write("entries/nin-cooked-weight-reference-2017.json", entry)
    write(
        "structured/nin-reference-quality-issues.json",
        {
            "source_id": "nin-cooked-weight-reference-2017",
            "excluded_from_portion_export": [
                {
                    "pages": [54, 55],
                    "reason": "Thể tích bát trong đoạn và tiêu đề bảng không khớp; mã thực phẩm có chỗ không khớp tên.",
                },
                {
                    "pages": [56],
                    "rows": "cháo",
                    "reason": "Có hàng chưa ghi dụng cụ và ô 14 g sống cần làm rõ; chỉ xuất cơm có bát xác định.",
                },
            ],
            "recipe_limits": "13/28 bảng thành phần có lượng thiếu hoặc đơn vị không được ghi; 28/28 chưa có gram thành phẩm cân xác minh.",
            "ratio_notes": "Văn bản có chỗ nêu 175 và 176 hệ số; giữ số hàng thực trích 176, không sửa văn bản gốc.",
        },
    )
    print(json.dumps(counts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
