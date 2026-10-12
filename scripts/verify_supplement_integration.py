"""Exercise the running local app and its configured real provider; no test doubles."""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/supplement-integration-2026-10-08/live-verification.json"
CASES = [
    ("knowledge", "Theo Viện Dinh dưỡng, đọc nhãn thực phẩm cần chú ý những gì?"),
    ("label", "200 ml sữa hạt mắc ca TH true NUT 180 ml có bao nhiêu natri và carbohydrate?"),
    ("label", "200 g sữa chua không đường Mộc Châu có bao nhiêu carbohydrate và đường tổng số?"),
    (
        "portion",
        "Theo bảng Viện Dinh dưỡng 2017, bát cơm gạo tẻ 250 ml đầy miệng nặng bao nhiêu gram?",
    ),
    ("gi", "Theo nghiên cứu Chan năm 2001 ở Việt Nam, GI miến đậu xanh bằng bao nhiêu?"),
    (
        "recipe",
        "Tra công thức tham khảo phở bò trong sách Viện Dinh dưỡng 2017: đã có khối lượng thành phẩm xác minh chưa?",
    ),
    ("label", "100 ml Trà Đào Tự Nhiên TH true TEA có bao nhiêu natri theo nhãn?"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    result = (
        json.loads(OUT.read_text(encoding="utf-8"))
        if args.retry_failed and OUT.exists()
        else {"cases": [], "all_passed": False}
    )
    result["checked_at"] = datetime.now(UTC).isoformat()
    indices = (
        [i for i, row in enumerate(result["cases"]) if not row["passed"]]
        if args.retry_failed
        else list(range(len(CASES)))
    )
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=180) as client:
        response = client.get("/api/status")
        response.raise_for_status()
        result["status"] = response.json()
        for index in indices:
            domain, question = CASES[index]
            start = time.perf_counter()
            response = client.post("/api/chat", json={"message": question, "save_history": False})
            data = response.json()
            checked = (
                response.status_code == 200
                and data.get("status") == "answered"
                and bool(data.get("provider_response_ids"))
            )
            reference = data.get("reference_result") or {}
            if domain != "knowledge":
                checked = checked and reference.get("domain") == domain
            if "mắc ca" in question:
                checked = checked and any(
                    r.get("calculated_nutrients", {}).get("sodium_mg") == 20
                    and r.get("calculated_nutrients", {}).get("carbohydrate_g") == 7.4
                    for r in reference.get("items", [])
                )
            if "sữa chua" in question:
                checked = checked and any(
                    r.get("calculated_nutrients", {}).get("carbohydrate_g") == 9
                    and r.get("calculated_nutrients", {}).get("total_sugars_g") is None
                    for r in reference.get("items", [])
                )
            if domain == "portion":
                checked = checked and any(
                    r["payload"].get("cooked_food_component_g") == 180
                    for r in reference.get("items", [])
                )
            if domain == "gi":
                checked = checked and any(
                    r["source_id"] == "gi-vietnam-paper-2001"
                    and r["payload"].get("gi_all_subjects") == 39
                    for r in reference.get("items", [])
                )
            if domain == "recipe":
                checked = checked and (
                    bool(reference.get("items")) or bool(reference.get("unresolved"))
                )
                checked = checked and all(
                    r["payload"].get("finished_weight_g") is None and not r["calculation_available"]
                    for r in reference.get("items", [])
                )
            if "trà đào" in question.lower():
                checked = checked and any(
                    not r["calculation_available"] and "nutrients" not in r["payload"]
                    for r in reference.get("items", [])
                )
            if domain == "knowledge":
                checked = checked and any(
                    r["source_id"] == "nin-labels" for r in data.get("citations", [])
                )
            row = {
                "question": question,
                "expected_domain": domain,
                "http_status": response.status_code,
                "elapsed_seconds": round(time.perf_counter() - start, 2),
                "passed": checked,
                "response": data,
            }
            if index < len(result["cases"]):
                result.setdefault("previous_attempts", []).append(result["cases"][index])
                result["cases"][index] = row
            else:
                result["cases"].append(row)
            OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(
                json.dumps(
                    {
                        "question": question,
                        "http_status": response.status_code,
                        "passed": checked,
                        "answer": data.get("answer", data.get("detail")),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    result["all_passed"] = all(r["passed"] for r in result["cases"])
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if not result["all_passed"]:
        raise SystemExit("Live verification has failing cases; inspect saved evidence.")


if __name__ == "__main__":
    main()
