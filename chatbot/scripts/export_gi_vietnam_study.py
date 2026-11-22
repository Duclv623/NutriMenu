"""Table 1/2 transcription, visually checked against the eight-page 2001 paper."""

import csv
import json

from scripts.collect_rag_supplements import DEST

DATA = [
    (
        "Rice noodles, dried",
        "Bún gạo khô trong nghiên cứu",
        "Thailand",
        81.5,
        61.3,
        600,
        61,
        6,
        12,
        "Soaked in hot water for 5 min; drained",
    ),
    (
        "Rice noodles, fresh",
        "Bún gạo tươi trong nghiên cứu",
        "Australia",
        45.5,
        110,
        622,
        40,
        5,
        12,
        "Soaked in hot water for 5 min; drained",
    ),
    (
        "Mung bean noodles",
        "Miến đậu xanh trong nghiên cứu",
        "China",
        82.8,
        60.4,
        494,
        39,
        9,
        11,
        "Soaked in hot water for 8 min; drained",
    ),
    (
        "Glutinous rice",
        "Gạo nếp trong nghiên cứu",
        "Thailand",
        76.3,
        65.5,
        612,
        94,
        6,
        11,
        "Cooked fresh in an electric rice cooker",
    ),
    (
        "Jasmine rice, long grain",
        "Gạo jasmine hạt dài trong nghiên cứu",
        "Thailand",
        79.1,
        63.2,
        612,
        109,
        10,
        12,
        "Cooked fresh in an electric rice cooker",
    ),
    (
        "Broken rice",
        "Gạo tấm trong nghiên cứu",
        "Thailand",
        79.1,
        63.2,
        616,
        86,
        8,
        11,
        "Cooked fresh in an electric rice cooker",
    ),
    (
        "Lychee, canned and drained",
        "Vải đóng hộp đã chắt nước trong nghiên cứu",
        "China",
        17.1,
        292.4,
        466,
        79,
        8,
        12,
        "Drained; syrup not consumed",
    ),
    (
        "Custard apple",
        "Custard apple trong nghiên cứu (không tự gán giống Việt)",
        "Australia",
        15.8,
        316.5,
        439,
        58,
        5,
        12,
        "Ripe; peeled and seedless flesh; remaining juice consumed",
    ),
    (
        "Milk, condensed sweetened",
        "Sữa đặc có đường trong nghiên cứu",
        "Australia",
        55.4,
        90.2,
        683,
        61,
        6,
        11,
        "Sweetened full-cream condensed milk",
    ),
]


def main():
    records = []
    keys = [
        "food_original",
        "food_name_vi_for_search",
        "country_of_origin",
        "available_carbohydrate_g_per_100g_raw_product",
        "raw_product_weight_for_50g_available_carbohydrate_g",
        "additional_water_ml",
        "gi_all_subjects",
        "gi_sem",
        "n_analyzed",
        "test_preparation",
    ]
    for i, values in enumerate(DATA, 1):
        record = {
            "record_id": f"chan2001-{i:02d}",
            **dict(zip(keys, values, strict=True)),
            "study_subjects_recruited": 12,
            "reference_glucose_gi": 100,
            "source_id": "gi-vietnam-paper-2001",
            "source_doi": "10.1038/sj.ejcn.1601265",
            "source_locator": "PDF page 2 Table 1; page 3 methods; page 6 Table 2",
            "is_household_portion_conversion": False,
            "rag_enabled": False,
            "quality_note": "Sydney database GI 54 differs from paper Table 2 GI 58; not approved"
            if i == 8
            else "Study food only; no automatic mapping to NIN foods",
        }
        records.append(record)
    (DEST / "structured/gi-vietnam-study-2001.json").write_text(
        json.dumps(
            {
                "publisher_url": "https://www.nature.com/articles/1601265",
                "download_url": "https://www.naturaleater.com/science-articles/GI-Vietnamese.pdf",
                "download_is_public_mirror": True,
                "source_year": 2001,
                "clinical_review": False,
                "notes_vi": "Cân nặng Table 1 là lượng sản phẩm trước chuẩn bị phần thử, không là trọng lượng một bát cơm/bún chín. Không dùng làm dữ liệu món Việt phổ quát. Tên tiếng Việt chỉ hỗ trợ tìm kiếm.",
                "records": records,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    with (DEST / "structured/gi-vietnam-study-2001.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    print("Saved 9 measured foods with preparation, basis and study size.")


if __name__ == "__main__":
    main()
