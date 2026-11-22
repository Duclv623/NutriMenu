"""Build a reproducible, hash-locked deployment from the reviewed collection."""

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "data/collected/rag_supplements_2026-10-08"

OUT = ROOT / "data/structured/supplements"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    collection = read(DEST / "manifest.json")
    if read(DEST / "collection-audit.json")["status"] != "pass":
        raise ValueError("Collection has not passed its preservation audit")
    sources = {e["id"]: e for e in collection["sources"]}
    for entry in sources.values():
        if digest(DEST / entry["raw_file"]) != entry["sha256"]:
            raise ValueError("Source changed: " + entry["id"])
    for entry in collection["derived_files"]:
        if digest(DEST / entry["file"]) != entry["sha256"]:
            raise ValueError("Derived data changed: " + entry["file"])
    config_path = ROOT / "config/sources.json"
    manifest = read(config_path)
    backup = ROOT / "config/sources.before-supplements-2026-10-08.json"
    if not backup.exists():
        backup.write_bytes(config_path.read_bytes())
    manifest["sources"] = [s for s in manifest["sources"] if not s.get("collection_release")]
    decisions = {
        sid: {
            "source_id": sid,
            "deployment": "reference_only",
            "reason": "Giữ nguồn gốc; danh mục, metadata, hoặc nội dung chưa chọn để trả lời.",
        }
        for sid in sources
    }
    for sid, reason in {
        'baclieu-diet': 'PDF có nội dung chẩn đoán, định lượng cho cá nhân và mục giới thiệu sản phẩm ổn định đường huyết; chưa duyệt làm bằng chứng trả lời. Không đưa toàn văn vào index.',
        'cdc-hypoglycemia': 'Tài liệu rà soát nhánh an toàn; chưa triển khai hướng dẫn xử trí hạ đường huyết trong chat dinh dưỡng.',
        'niddk-hypoglycemia': 'Tài liệu rà soát nhánh an toàn; chưa triển khai hướng dẫn xử trí hạ đường huyết trong chat dinh dưỡng.',
        'nin-weight-reference-bibliography': 'Thông tin xuất bản xác minh nguồn sách NIN; không phải bằng chứng dinh dưỡng độc lập.',
        'vietduc-meal-decision-5267': 'Quyết định hành chính đi kèm bộ quy cách suất ăn; không dùng làm số dinh dưỡng hoặc khối lượng cân.',
        'th-product-sua-hat-macca-th-true-nut-180-ml': 'Snapshot cũ có số natri cần sửa; công cụ dùng bản THMart được rà soát và ghi nguồn riêng, không dùng số cũ.',
    }.items():
        if sid in decisions:
            decisions[sid]['reason'] = reason
    knowledge = []

    def add(sid, segments):
        entry = sources[sid]
        if any(s.get("url") == entry["url"] and s.get("enabled") for s in manifest["sources"]):
            decisions[sid].update(
                deployment="existing_source", reason="URL đã có trong corpus; không index lặp."
            )
            return
        filename = "supplement-" + sid + ".json"
        value = {
            "schema_version": 1,
            "source_id": sid,
            "original_url": entry["url"],
            "original_sha256": entry["sha256"],
            "segments": segments,
        }
        write(ROOT / "data" / filename, value)
        year = (
            2017
            if sid == "nin-cooked-weight-reference-2017"
            else 2001
            if sid == "gi-vietnam-paper-2001"
            else 2026
        )
        source = {
            "id": sid,
            "filename": filename,
            "format": "curated",
            "title": entry["title"],
            "url": entry["url"],
            "year": year,
            "version": "Bản chọn lọc thu 08/10/2026; năm 2026 là ngày thu nếu nguồn không nêu năm.",
            "enabled": True,
            "role": "knowledge",
            "language": "vi",
            "sha256": digest(ROOT / "data" / filename),
            "collection_release": "2026-10-08",
            "segments": [{"section": s["section"]} for s in segments],
            "warnings": [
                "Nội dung giáo dục/tóm lược có nguồn; chưa thẩm định lâm sàng.",
                "Chỉ phần chọn lọc được index, không phải toàn bộ tài liệu gốc.",
            ],
            "original_raw_file": entry["raw_file"],
            "original_sha256": entry["sha256"],
        }
        if entry.get("download_is_public_mirror") or sid == "nin-cooked-weight-reference-2017":
            source["warnings"].append(
                "Bản tải gốc là mirror công khai; giữ thông tin xuất bản riêng."
            )
        manifest["sources"].append(source)
        knowledge.append(sid)
        decisions[sid].update(
            deployment="knowledge_index",
            reason="Đoạn chọn lọc có locator và bản diễn đạt tiếng Việt.",
        )

    # Seven scenario digests have a source section and selected original excerpt.
    for sid in [
        "cdc-carb-counting",
        "cdc-carb-choices",
        "cdc-meal-planning",
        "cdc-eating-out",
        "cdc-dessert",
        "cdc-holidays",
        "cdc-shift-work",
    ]:
        text = (DEST / f"reviewed/{sid}.vi.md").read_text(encoding="utf-8")
        original = read(DEST / sources[sid]["raw_file"])
        segments = []
        for item, section in zip(original, re.split(r"(?m)^## ", text)[1:], strict=True):
            heading, body = section.split("\n", 1)
            segments.append(
                {
                    "section": heading.strip(),
                    "text": body.strip()
                    + "\nĐoạn gốc chọn lọc: "
                    + item["selected_original_excerpt"],
                    "locators": [item["source_section"]],
                    "pages": [],
                }
            )
        add(sid, segments)
    digest_text = (DEST / "reviewed/vi-supplement-nutrition.md").read_text(encoding="utf-8")
    sections = {
        s.split("\n", 1)[0].strip(): s.split("\n", 1)[1].strip()
        for s in re.split(r"(?m)^## ", digest_text)[1:]
    }

    def summary(heading):
        value = sections[heading]
        value = re.sub(r"(?m)^\*\*Nguồn:\*\*.*\n?", "", value).strip()
        return re.split(r"\n\*\*(?:Phạm vi|Chưa duyệt)", value)[0].strip()

    def html_selected(sid, locators, section, vi=""):
        blocks = read(DEST / sources[sid]["extracted_file"])
        selected = [b for b in blocks if b["locator"] in locators]
        if len(selected) != len(locators):
            raise ValueError("Missing approved HTML locator: " + sid)
        add(
            sid,
            [
                {
                    "section": section,
                    "text": vi + "\nĐoạn gốc:\n" + "\n".join(b["text"] for b in selected),
                    "locators": locators,
                    "pages": [],
                }
            ],
        )

    html_selected(
        "nin-labels",
        ["block-0159", "block-0161", "block-0163", "block-0180"],
        "Đọc nhãn: 100 g, 100 ml, khẩu phần và lượng thực tế",
        summary("Đọc đúng cơ sở trên nhãn"),
    )
    html_selected(
        "binhchanh-plate",
        ["block-0080", "block-0082", "block-0084", *[f"block-{i:04d}" for i in range(87, 93)]],
        "Chia đĩa theo nhóm thực phẩm",
    )
    html_selected("nin-balanced-meals", ["block-0171", "block-0172"], "Bữa ăn cân đối")
    html_selected(
        "fda-sweeteners",
        ["block-0064", "block-0065"],
        "Chất tạo ngọt và danh sách thành phần",
        "FDA mô tả chất tạo ngọt dùng trong thực phẩm. Xem tên chất trong danh sách thành phần trên nhãn. Một nhận định về chất tạo ngọt không xác định tổng carbohydrate của mọi sản phẩm.",
    )
    html_selected(
        "sydney-about-gi",
        ["block-0036"],
        "Phương pháp đo GI — carbohydrate khả dụng",
        "GI cần phép thử với thực phẩm và cách chuẩn bị cụ thể; không suy từ kcal hoặc gram carb. Phương pháp trong nguồn dùng ít nhất 10 người khỏe mạnh và 50 g carbohydrate khả dụng; mốc so sánh là glucose.",
    )
    for sid, heading in [
        ("ada-plate", "Chia đĩa và lựa chọn nhóm thực phẩm"),
        ("ada-grocery", "Mua thực phẩm thực hành"),
        ("fda-polyols", "Chất tạo ngọt và polyol"),
        ("ada-vegetarian-plate", "Ăn chay vẫn cần tính nguồn carb"),
    ]:
        pages = read(DEST / sources[sid]["extracted_file"])
        # The composite vegetarian digest mentions other sources; use only a
        # narrow plate description here, preserve each PDF's original wording.
        vi = (
            summary(heading)
            if sid != "ada-vegetarian-plate"
            else (
                "Đĩa ăn chay phối hợp rau, nguồn đạm thực vật và nhóm carbohydrate; phần đĩa không phải gram món ăn. Xem đúng thực phẩm và lượng trong nguồn."
            )
        )
        add(
            sid,
            [
                {
                    "section": heading,
                    "text": vi + "\nNguyên bản:\n" + "\n".join(p["text"] for p in pages),
                    "locators": [f"PDF page {p['page']}" for p in pages],
                    "pages": [p["page"] for p in pages],
                }
            ],
        )
    for sid, needles in [
        ("ada-protein", ["plant-based proteins"]),
        ("ada-vegan-meals", ["protein", "carbohydrates"]),
    ]:
        blocks = read(DEST / sources[sid]["extracted_file"])
        selected = []
        for i, block in enumerate(blocks):
            if block["tag"] in ["h2", "h3", "h4"] and block["text"].lower() in needles:
                selected.append(block)
                for follow in blocks[i + 1 :]:
                    if follow["tag"] in ["h2", "h3", "h4"]:
                        break
                    selected.append(follow)
        if selected:
            add(
                sid,
                [
                    {
                        "section": "Đạm thực vật, ăn chay và carbohydrate",
                        "text": "\n".join(b["text"] for b in selected),
                        "locators": [b["locator"] for b in selected],
                        "pages": [],
                    }
                ],
            )
    nin_pages = read(DEST / sources["nin-cooked-weight-reference-2017"]["extracted_file"])
    add(
        "nin-cooked-weight-reference-2017",
        [
            {
                "section": "Phương pháp cân và giới hạn quy đổi bát Việt",
                "text": "Phương pháp trong sách dùng giá trị trung bình cân 4 hộ, gồm 2 hộ nông thôn và 2 hộ thành thị. Dung tích bát ml không phải gram thực phẩm. Cần đúng thực phẩm, mức đầy và cách chế biến; dùng công cụ khẩu phần để tra từng hàng.\n"
                + nin_pages[26]["text"],
                "locators": ["PDF page 27"],
                "pages": [27],
            }
        ],
    )
    gi_pages = read(DEST / sources["gi-vietnam-paper-2001"]["extracted_file"])
    add(
        "gi-vietnam-paper-2001",
        [
            {
                "section": "GI nghiên cứu món Việt 2001 — phương pháp và giới hạn",
                "text": summary("GI/GL và điều kiện đo")
                + "\nPhương pháp gốc:\n"
                + gi_pages[2]["text"],
                "locators": ["PDF page 3; methods; Table 1/2 qua công cụ tra cứu"],
                "pages": [3],
            }
        ],
    )
    for sid, pages, heading in [
        ("usda-cooking-yields", [3, 4, 5], "Hệ số khối lượng khi nấu — phương pháp USDA"),
        ("usda-retention", [3, 4, 5], "Hệ số giữ chất — phương pháp USDA"),
    ]:
        original = read(DEST / sources[sid]["extracted_file"])
        add(
            sid,
            [
                {
                    "section": heading,
                    "text": summary("Tính món từ nguyên liệu cần hệ số đúng")
                    + "\nNguyên bản phương pháp:\n"
                    + "\n".join(original[p - 1]["text"] for p in pages),
                    "locators": [f"PDF page {p}" for p in pages],
                    "pages": pages,
                }
            ],
        )

    records = []

    def add_record(domain, rid, name, payload, sid, locator="", aliases=None, limitations=""):
        entry = sources[sid]
        records.append(
            {
                "id": "supp-"
                + re.sub(
                    r"[^a-z0-9-]+",
                    "-",
                    "".join(
                        c
                        for c in unicodedata.normalize("NFD", rid.lower().replace("đ", "d"))
                        if not unicodedata.combining(c)
                    ),
                ),
                "domain": domain,
                "name": name,
                "aliases": aliases or [],
                "payload": {k: v for k, v in payload.items() if k != "rag_enabled"},
                "source_id": sid,
                "source_title": entry["title"],
                "source_url": entry["url"],
                "source_sha256": entry["sha256"],
                "locator": str(locator),
                "limitations": limitations,
                "calculation_enabled": False,
            }
        )
        if decisions[sid]["deployment"] == "reference_only":
            decisions[sid].update(
                deployment="structured_tool",
                reason="Dữ liệu bảng truy xuất theo bản ghi/đơn vị, không vector hóa toàn bảng.",
            )
        elif decisions[sid]["deployment"] == "knowledge_index":
            decisions[sid]["deployment"] = "knowledge_and_structured_tool"

    flags = {
        r["record_id"]: r
        for r in read(DEST / "structured/th-product-followup-review.json")["records"]
    }
    override = read(DEST / "structured/th-product-reviewed-overrides.json")["records"][0]
    for row in read(DEST / "structured/product-nutrition.json")["records"]:
        flag = flags.get(row["record_id"])
        if flag and flag["disposition"] != "resolved_using_current_official_alternative":
            payload = {"usable": False, "reason": flag["review_notes_vi"]}
        else:
            nutrients = {
                k: v["normalized_value"] if v else None for k, v in row["nutrients"].items()
            }
            if flag:
                nutrients = override["nutrients"]
            payload = {
                "usable": True,
                "basis_amount": row["reference_amount"],
                "basis_unit": row["reference_unit"],
                "nutrients": nutrients,
                "nutrition_source_locator": row["source_locator"],
            }
        sid = override["source_review_id"] if flag and payload["usable"] else row["source_id"]
        add_record(
            "label",
            row["record_id"],
            row["name_vi"],
            payload,
            sid,
            override["review_locator"]
            if sid == override["source_review_id"]
            else row["source_locator"],
            [
                row["record_id"].replace("th-product-", "").replace("-", " "),
                "TH true " + row["name_vi"],
            ],
        )
        records[-1]["calculation_enabled"] = payload["usable"]
        if flag and not payload["usable"]:
            decisions[row["source_id"]].update(
                deployment="blocked_label_metadata_only", reason=flag["review_notes_vi"]
            )
    for row in read(DEST / "structured/mcm-product-nutrition-reviewed.json")["records"]:
        fields = {
            k: row[k]
            for k in [
                "energy_kcal",
                "protein_g",
                "fat_g",
                "carbohydrate_g",
                "total_sugars_g",
                "added_sugars_g",
                "fiber_g",
                "sodium_mg",
                "calcium_mg",
            ]
        }
        name = row["product_name"].replace("MCC", "Mộc Châu")
        add_record(
            "label",
            row["record_id"],
            name,
            {
                "usable": True,
                "basis_amount": 100,
                "basis_unit": row["basis_unit"],
                "nutrients": fields,
            },
            row["source_id"],
            f"PDF page {row['source_page']}",
            [name.replace("tiệt trùng ", "")],
            "Chỉ bảng nhãn được so tại trang nêu; không đồng nhất mọi quy cách bao bì.",
        )
        records[-1]["calculation_enabled"] = True
    for row in read(DEST / "structured/vietnamese-measured-portions.json")["records"]:
        name = row["food_name"] + " " + row["preparation"] + " " + row["portion_description"]
        aliases = ["Cơm " + row["food_name"]] if row["preparation"] == "nấu cơm" else []
        add_record(
            "portion",
            row["record_id"],
            name,
            row,
            "nin-cooked-weight-reference-2017",
            f"PDF page {row['source_page']}, table {row['source_table']}, row {row['source_row']}",
            aliases,
            "Số trung bình tham khảo đúng dụng cụ/mức đầy/cách nấu. Gram rau là phần rau; không phải tổng món có dầu/gia vị. Không áp bát này cho bát khác.",
        )
    for row in read(DEST / "structured/nin-raw-cooked-ratios.json")["records"]:
        add_record(
            "yield",
            f"nin-ratio-{row['source_page']}-{row['source_table']}-{row['source_row']}",
            str(row["food_name"]) + " " + row["preparation"],
            row,
            "nin-cooked-weight-reference-2017",
            f"PDF page {row['source_page']}, extracted table {row['source_table']}, row {row['source_row']}",
            limitations="HSSC = gram sống sạch / gram chín; không tự gán hệ số cho món cùng tên hoặc đảo chiều hệ số.",
        )
    for row in read(DEST / "structured/gi-vietnam-study-2001.json")["records"]:
        if "custard apple" in row["food_original"].lower():
            row = {
                **row,
                "gi_all_subjects": None,
                "gi_sem": None,
                "quality_note": "Có khác biệt 54/58 giữa Sydney và bài gốc; chưa chọn trị số để trả lời.",
            }
        add_record(
            "gi",
            row["record_id"],
            row["food_name_vi_for_search"],
            row,
            "gi-vietnam-paper-2001",
            row["source_locator"],
            [row["food_original"]],
            "Chỉ thực phẩm/cách chuẩn bị trong nghiên cứu 2001; không ánh xạ sang mọi món Việt hoặc NIN, không suy tác động cá nhân.",
        )
    for row in read(DEST / "structured/gi-sydney-all.json")["records"]:
        if "custard apple" in row["Food Name"].lower() and "Chan" in row["Reference:"]:
            row = {
                **row,
                "GI": "",
                "GL (based on average carbohydrate potion)": "",
                "quality_issue": "Conflicting 54/58 across primary study and Sydney; value blocked.",
            }
        add_record(
            "gi",
            f"sydney-gi-{row['source_row']}",
            row["Food Name"],
            row,
            "sydney-gi-search",
            f"block-0027, row {row['source_row']}",
            limitations="Trị số gắn đúng sản phẩm, cách nấu và nghiên cứu; thiếu ô không phải 0. Không tự tính GL theo phần ăn khác.",
        )
    for row in read(DEST / "structured/cdc-carb-choices.json")["records"]:
        add_record(
            "carb_choice",
            row["record_id"],
            row["food_original"],
            row,
            "cdc-carb-choices",
            row["source_locator"],
            limitations="Carb xấp xỉ theo nhóm và phần trong bảng CDC/ADA; giữ cup/oz, không đổi thành bát Việt hoặc dinh dưỡng nhãn hiệu.",
        )
    for row in read(DEST / "structured/vietnamese-reference-recipes.json")["records"]:
        add_record(
            "recipe",
            row["record_id"],
            row["name"],
            row,
            "nin-cooked-weight-reference-2017",
            f"PDF page {row['source_page']}",
            limitations="Bảng thành phần tham khảo, không phải công thức hoàn chỉnh. Chưa có gram thành phẩm; không tính dinh dưỡng chính xác/100 g.",
        )
    for row in read(DEST / "structured/vietduc-minimum-yield-meal-specifications.json")["records"]:
        add_record(
            "recipe",
            row["record_id"],
            row["name"],
            row,
            row["source_id"],
            f"PDF page {row['source_page']}; {row['source_menu_code']}",
            [row["source_menu_code"]],
            "Quy cách suất ăn bệnh viện, không kê chế độ cho cá nhân. 450 g/500 ml là tối thiểu, không phải cân thành phẩm chính xác; chưa đủ nước/gia vị/cách nấu.",
        )
    for row in read(DEST / "structured/cdc-recipes.json")["records"]:
        name = row["ingredients_directions_original"].split("\n")[0]
        add_record(
            "recipe",
            row["record_id"],
            name,
            row,
            "cdc-recipes",
            row["source_locator"],
            limitations="Công thức quốc tế theo suất nguồn, không phải món Việt cùng tên; chưa có gram thành phẩm.",
        )
    for i, row in enumerate(read(DEST / "structured/usda-cooking-yields.json")["records"], 1):
        add_record(
            "yield",
            f"usda-yield-{i}",
            row["Yield Description"] + " " + row["Preparation Method1"],
            row,
            "usda-cooking-yields-csv",
            f"CSV row {i + 1}",
            limitations="USDA: cooking yield % = chín/sống ×100, khác chiều HSSC NIN. Phải khớp phần cắt và phương pháp, không tự áp cho món Việt.",
        )
    groups = defaultdict(list)
    for row in read(DEST / "structured/usda-retention.json")["records"]:
        groups[row["retention_code"]].append(row)
    for code, rows in groups.items():
        add_record(
            "retention",
            "usda-retention-" + code,
            rows[0]["food_description"],
            {"nutrient_rows": rows},
            "usda-retention-txt",
            "retention_code " + code,
            limitations="Hệ số giữ chất %, không phải hệ số khối lượng; phải đúng chất/thực phẩm/cách nấu. Không dùng hệ số cho chất thiếu trong nguyên liệu.",
        )
    OUT.mkdir(parents=True, exist_ok=True)
    write(OUT / "records.json", {"schema_version": 1, "records": records})
    release = {
        "schema_version": 1,
        "release": "2026-10-08",
        "built_at": datetime.now(UTC).isoformat(),
        "files": {"records.json": digest(OUT / "records.json")},
        "knowledge_sources": knowledge,
        "domains": dict(Counter(r["domain"] for r in records)),
        "usable_labels": sum(r["domain"] == "label" and r["calculation_enabled"] for r in records),
        "source_decisions": list(decisions.values()),
        "source_collection_manifest_sha256": digest(DEST / "manifest.json"),
        "sources": {
            sid: {"raw_file": sources[sid]["raw_file"], "sha256": sources[sid]["sha256"]}
            for sid in sorted({r["source_id"] for r in records} | set(knowledge))
        },
        "automatically_prescribes_or_builds_menus": False,
    }
    write(OUT / "manifest.json", release)
    write(config_path, manifest)
    write(ROOT / "docs/supplement-integration-2026-10-08/deployment.json", release)
    print(
        json.dumps(
            {k: release[k] for k in ["knowledge_sources", "domains", "usable_labels"]},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
