"""Export the public NIN food lookup; no credentials, LLM or inferred nutrients."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx

PAGE_URL = "https://viendinhduong.vn/vi/cong-cu-va-tien-ich/gia-tri-dinh-duong-thuc-pham"
API_URL = "https://viendinhduong.vn/api/fe/foodNatunal/getPageFoodData"
DISH_PAGE_URL = "https://viendinhduong.vn/vi/cong-cu-va-tien-ich/gia-tri-dinh-duong-mon-an"
DISH_API_URL = "https://viendinhduong.vn/api/fe/tool/getPageFoodData"
CORE = {
    "protein_g": ("protein", "g"),
    "fat_g": ("total-lipid-fat", "g"),
    "carbohydrate_g": ("carbohydrate-by-difference", "g"),
    "dietary_fiber_g": ("fibre-total-dietary", "g"),
    "sodium_mg": ("na", "mg"),
}


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    # BOM allows Excel on Windows to read Vietnamese correctly.
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def download(output: Path, page_size: int, delay: float, dataset: str = "foods") -> tuple[list[dict], dict]:
    raw = output / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    foods, requests = [], []
    total, per_page = None, None
    with httpx.Client(timeout=45, follow_redirects=True, headers={
        "Accept": "application/json",
        "User-Agent": "DATN-food-data-collector/1.0 (public nutrition lookup)",
    }) as client:
        page = 1
        while True:
            params = {"page": page, "pageSize": page_size}
            for attempt in range(3):
                try:
                    response = client.get(DISH_API_URL if dataset == "dishes" else API_URL, params=params)
                    # Do not bypass denied access or repeatedly retry rate limiting.
                    if response.status_code in (401, 403, 429):
                        response.raise_for_status()
                    if response.status_code >= 500 and attempt < 2:
                        time.sleep(2 ** (attempt + 1))
                        continue
                    response.raise_for_status()
                    break
                except httpx.TransportError:
                    if attempt == 2:
                        raise
                    time.sleep(2 ** (attempt + 1))
            data = response.json()
            if int(data["current_page"]) != page:
                raise ValueError(f"Unexpected page: {data.get('current_page')}")
            current_total, current_size = int(data["total"]), int(data["per_page"])
            if total is None:
                total, per_page = current_total, current_size
                if total <= 0 or per_page <= 0:
                    raise ValueError("Empty or invalid pagination")
            elif (current_total, current_size) != (total, per_page):
                raise ValueError("Pagination changed during collection; repeat export")
            entries = data["data"]
            expected = min(per_page, total - (page - 1) * per_page)
            if not isinstance(entries, list) or len(entries) != expected:
                raise ValueError(f"Page {page}: expected {expected} rows")
            for food in entries:
                nutrient_field = "nutritional_components" if dataset == "dishes" else "nutrition"
                if not food.get("_id") or not food.get("code") or not isinstance(food.get(nutrient_field), list):
                    raise ValueError("Unexpected food schema")
            filename = f"page_{page:03d}.json"
            (raw / filename).write_bytes(response.content)
            requests.append({
                "url": str(response.url), "file": "raw/" + filename,
                "retrieved_at": datetime.now(UTC).isoformat(),
                "sha256": hashlib.sha256(response.content).hexdigest(), "rows": len(entries),
            })
            foods.extend(entries)
            print(f"Page {page}: {len(foods)}/{total}", flush=True)
            if page >= math.ceil(total / per_page):
                break
            page += 1
            time.sleep(delay)
    if len(foods) != total or len({f["_id"] for f in foods}) != total:
        raise ValueError("Incomplete or duplicate records")
    duplicates = [code for code, count in Counter(f["code"] for f in foods).items() if count > 1]
    if duplicates:
        raise ValueError(f"Duplicate food codes: {duplicates}")
    return foods, {"dataset": dataset, "expected_total": total, "per_page": per_page, "requests": requests}


def export(output: Path, foods: list[dict], manifest: dict) -> dict:
    issues, long_rows, core_rows, wide_rows = [], [], [], []
    dictionary = {}
    for food in foods:
        code = str(food["code"])
        base = {
            "food_code": code, "source_record_id": food["_id"],
            "name_vi": food.get("name_vi", ""), "name_en": food.get("name_en", ""),
            "category_vi": food.get("category", ""), "category_en": food.get("categoryEn", ""),
            "reference_amount_g": 100, "edible_basis": True,
            "state": "",  # The API has no explicit raw/cooked field.
            "energy_kcal": food.get("energy"), "source_url": PAGE_URL,
        }
        core_row, wide_row = dict(base), dict(base)
        nutrients = {}
        for index, nutrient in enumerate(food["nutrition"]):
            key, unit, value = nutrient.get("key", ""), nutrient.get("unit", ""), nutrient.get("value")
            pair = (key, unit)
            if not key or pair in nutrients:
                issues.append({"food_code": code, "issue": "missing_or_duplicate_nutrient_key", "key": key, "unit": unit})
            nutrients[pair] = None if pair in nutrients else value
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                issues.append({"food_code": code, "issue": "non_numeric_value", "key": key, "value": value})
            elif isinstance(value, (int, float)) and value < 0:
                issues.append({"food_code": code, "issue": "negative_value", "key": key, "value": value})
            if not unit:
                issues.append({"food_code": code, "issue": "missing_unit", "key": key})
            column = f"nutrient__{key}__{unit}"
            wide_row[column] = nutrients[pair]
            entry = dictionary.setdefault(column, {"key": key, "unit": unit, "labels_vi": set(), "labels_en": set()})
            entry["labels_vi"].add(nutrient.get("name", ""))
            entry["labels_en"].add(nutrient.get("name_en", ""))
            long_rows.append({
                "food_code": code, "source_record_id": food["_id"], "nutrient_index": index,
                "nutrient_key": key, "nutrient_name_vi": nutrient.get("name", ""),
                "nutrient_name_en": nutrient.get("name_en", ""), "value": value, "unit": unit,
                "reference_amount_g": 100, "source_url": PAGE_URL,
            })
        for column, pair in CORE.items():
            core_row[column] = nutrients.get(pair)
        core_rows.append(core_row)
        wide_rows.append(wide_row)
    for entry in dictionary.values():
        entry["labels_vi"] = sorted(entry["labels_vi"])
        entry["labels_en"] = sorted(entry["labels_en"])
    write_json(output / "foods_full.json", foods)
    write_json(output / "foods_core.json", core_rows)
    write_json(output / "nutrient_dictionary.json", dictionary)
    write_csv(output / "foods_core.csv", list(core_rows[0]), core_rows)
    write_csv(output / "foods_all_nutrients.csv", list(base) + sorted(dictionary), wide_rows)
    write_csv(output / "nutrients_long.csv", list(long_rows[0]), long_rows)
    missing = {column: sum(row.get(column) is None for row in core_rows) for column in ["energy_kcal", *CORE]}
    quality = {
        "records": len(foods), "unique_food_codes": len({f['code'] for f in foods}),
        "nutrient_rows": len(long_rows), "nutrient_columns": len(dictionary),
        "categories": dict(sorted(Counter(f.get('category', '') for f in foods).items())),
        "missing_core_values": missing, "issues": issues,
        "core_macros_present_nonnegative": sum(all(row.get(k) is not None and isinstance(row[k], (int, float)) and row[k] >= 0
                                                   for k in ("energy_kcal", "protein_g", "fat_g", "carbohydrate_g")) for row in core_rows),
        "validated_against": "API pagination, unique IDs/codes, schema and value/unit checks; not clinical validation",
    }
    write_json(output / "quality_report.json", quality)
    manifest.update({
        "dataset": "foods",
        "source_title": "Viện Dinh dưỡng — Tra cứu giá trị dinh dưỡng thực phẩm",
        "source_url": PAGE_URL, "api_url": API_URL,
        "reference_basis": "100 g phần ăn được, theo nhãn giao diện nguồn",
        "reference_amount_g": 100,
        "reference_basis_verification": {
            "method": "source_interface_and_dataset_owner_confirmation", "date": "2026-10-08",
            "note": "Dataset owner confirmed all 853 NIN foods are per 100 g; source nutrient values are unchanged",
        },
        "raw_cooked_state": "not supplied as a structured API field; requires manual review",
        "normalization": "No nutrient inference, rounding, replacement of missing values or correction of source data",
        "clinical_review": False,
    })
    manifest["exports"] = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.iterdir()) if path.is_file() and path.name != "manifest.json"
    }
    write_json(output / "manifest.json", manifest)
    return quality


def export_dishes(output: Path, dishes: list[dict], manifest: dict) -> dict:
    def number(value: object) -> float | int | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return None
        try:
            numeric = float(value)
        except (ValueError, TypeError):
            return None
        return numeric if math.isfinite(numeric) else None

    rows, long_rows, issues, dictionary = [], [], [], {}
    core_mapping = {"protein_g": ("chat-dam", "g"), "fat_g": ("chat-beo", "g"),
                    "carbohydrate_g": ("chat-bot-duong", "g"), "sodium_mg": ("natri", "mg")}
    wide_rows = []
    for dish in dishes:
        base = {
            "dish_code": dish["code"], "source_record_id": dish["_id"],
            "name_vi": dish.get("name_vi", ""), "name_en": dish.get("name_en", ""),
            "category_vi": dish.get("category_name", ""), "category_en": dish.get("category_name_en", ""),
            "description": dish.get("description", ""), "food_area_id": dish.get("food_area_id", ""),
            "reference_amount_g": 100, "reference_basis": "100 g món ăn",
            "energy_kcal": None, "source_url": DISH_PAGE_URL,
            "source_updated_at": dish.get("updated_at", ""),
            "dish_components_count": len(dish.get("dish_components", [])),
        }
        values = {}
        for nutrient in dish["nutritional_components"]:
            items = [(nutrient, "")]
            items += [(child, nutrient.get("key", "")) for child in nutrient.get("equivalenceComponents", [])]
            for item, parent_key in items:
                key, unit = item.get("key", ""), item.get("unit_name", item.get("unit", ""))
                raw_value = item.get("amount", item.get("value"))
                value = number(raw_value)
                if raw_value not in (None, "") and value is None:
                    issues.append({"dish_code": dish["code"], "issue": "non_numeric_value", "key": key, "value": raw_value})
                if value is not None and value < 0:
                    issues.append({"dish_code": dish["code"], "issue": "negative_value", "key": key, "value": value})
                pair = (key, unit)
                if not key or pair in values:
                    issues.append({"dish_code": dish["code"], "issue": "missing_or_duplicate_nutrient_key", "key": key, "unit": unit})
                if not unit:
                    issues.append({"dish_code": dish["code"], "issue": "missing_unit", "key": key})
                values[pair] = None if pair in values else value
                column = f"nutrient__{key}__{unit}"
                entry = dictionary.setdefault(column, {"key": key, "unit": unit, "labels_vi": set(), "labels_en": set()})
                entry["labels_vi"].add(item.get("name", ""))
                entry["labels_en"].add(item.get("nameEn", item.get("name_en", "")))
                long_rows.append({"dish_code": dish["code"], "source_record_id": dish["_id"],
                                  "nutrient_key": key, "nutrient_name_vi": item.get("name", ""),
                                  "nutrient_name_en": item.get("nameEn", item.get("name_en", "")),
                                  "value": value, "raw_value": raw_value, "unit": unit,
                                  "parent_nutrient_key": parent_key, "reference_amount_g": 100,
                                  "source_url": DISH_PAGE_URL})
        base["energy_kcal"] = values.get(("nang-luong", "Kcal"))
        row = dict(base)
        for column, pair in core_mapping.items():
            row[column] = values.get(pair)
        rows.append(row)
        wide_rows.append(dict(base, **{f"nutrient__{key}__{unit}": value for (key, unit), value in values.items()}))
    for entry in dictionary.values():
        entry["labels_vi"], entry["labels_en"] = sorted(entry["labels_vi"]), sorted(entry["labels_en"])
    write_json(output / "dishes_full.json", dishes)
    write_json(output / "dishes_core.json", rows)
    write_json(output / "nutrient_dictionary.json", dictionary)
    write_csv(output / "dishes_core.csv", list(rows[0]), rows)
    write_csv(output / "dishes_all_nutrients.csv", list(base) + sorted(dictionary), wide_rows)
    write_csv(output / "nutrients_long.csv", list(long_rows[0]), long_rows)
    quality = {
        "records": len(dishes), "unique_dish_codes": len({d['code'] for d in dishes}),
        "nutrient_rows": len(long_rows), "nutrient_columns": len(dictionary),
        "categories": dict(sorted(Counter(d.get('category_name', '') for d in dishes).items())),
        "missing_core_values": {column: sum(r.get(column) is None for r in rows) for column in ["energy_kcal", *core_mapping]},
        "records_with_dish_components": sum(bool(d.get("dish_components")) for d in dishes),
        "reference_amount_requires_review": 0, "issues": issues,
        "validated_against": "Pagination, unique IDs/codes and value checks; 100 g basis confirmed by dataset owner on 2026-10-08; clinical accuracy not validated",
    }
    write_json(output / "quality_report.json", quality)
    manifest.update({"source_title": "Viện Dinh dưỡng — Tra cứu giá trị dinh dưỡng món ăn",
                     "source_url": DISH_PAGE_URL, "api_url": DISH_API_URL,
                     "reference_basis": "100 g món ăn",
                     "reference_amount_g": 100,
                     "reference_basis_verification": {
                         "method": "dataset_owner_confirmation", "date": "2026-10-08",
                         "note": "Dataset owner confirmed all 1250 NIN dishes are per 100 g; source nutrient values are unchanged",
                     },
                     "normalization": "Empty values become null; numeric strings parsed; nested salt equivalents preserved; no nutrient inference",
                     "clinical_review": False})
    manifest["exports"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())
                           if p.is_file() and p.name != "manifest.json"}
    write_json(output / "manifest.json", manifest)
    return quality


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=["foods", "dishes"], default="foods")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--from-cache", action="store_true", help="Re-export saved pages without network")
    args = parser.parse_args()
    if args.output is None:
        args.output = Path(f"data/structured/nin_{args.dataset}_2026-10-06")
    if not 1 <= args.page_size <= 100 or args.delay < 0.5:
        parser.error("page-size must be 1..100; delay at least 0.5 seconds")
    if args.from_cache:
        manifest = json.loads((args.output / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("dataset", "foods") != args.dataset:
            raise ValueError("Cached dataset does not match --dataset")
        foods = []
        for request in manifest["requests"]:
            raw = (args.output / request["file"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != request["sha256"]:
                raise ValueError("Cached page hash mismatch")
            foods.extend(json.loads(raw)["data"])
        if len(foods) != manifest["expected_total"] or len({f["_id"] for f in foods}) != len(foods):
            raise ValueError("Incomplete cache")
    else:
        if args.output.exists() and any(args.output.iterdir()):
            parser.error("Output is nonempty; choose a new snapshot directory or --from-cache")
        args.output.mkdir(parents=True, exist_ok=True)
        foods, manifest = download(args.output, args.page_size, args.delay, args.dataset)
    quality = (export_dishes if args.dataset == "dishes" else export)(args.output, foods, manifest)
    print(json.dumps({k: quality[k] for k in ("records", "nutrient_rows", "missing_core_values")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
