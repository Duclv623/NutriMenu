"""Reviewed reference tables, kept separate from generic NIN food composition."""

import hashlib
import json
import re
from collections import Counter
from decimal import Decimal
from html import escape
from pathlib import Path

from rag_app.config import ROOT
from rag_app.domain import Chunk, Hit
from rag_app.food_data import FoodPlan, canonical, normalized
from rag_app.retrieval import fold
from rag_app.safety import is_intake_advice

DATA = ROOT / "data/structured/supplements"
NUTRIENTS = {
    "energy_kcal": ("Năng lượng", "kcal", "energy"),
    "protein_g": ("Chất đạm", "g", "protein"),
    "fat_g": ("Chất béo", "g", "fat"),
    "carbohydrate_g": ("Carbohydrate", "g", "carbohydrate"),
    "total_sugars_g": ("Đường tổng số", "g", "sugar"),
    "added_sugars_g": ("Đường thêm", "g", "added_sugars"),
    "fiber_g": ("Chất xơ", "g", "fiber"),
    "sodium_mg": ("Natri", "mg", "sodium"),
    "calcium_mg": ("Canxi", "mg", "calcium"),
}


def search_text(value):
    value = normalized(value)
    value = value.replace("macca", "mac ca").replace("mcc", "moc chau")
    return re.sub(r"\b(?:tiet trung|tu nhien|th true|trong nghien cuu)\b", " ", value)


class SupplementCatalog:
    def __init__(self, root=DATA):
        self.root = Path(root)
        self.records = {}
        self.manifest = {}
        if not (self.root / "manifest.json").exists():
            return
        self.manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        base = ROOT / "data/collected/rag_supplements_2026-10-08"
        for source in self.manifest.get("sources", {}).values():
            path = (base / source["raw_file"]).resolve()
            if (
                not path.is_relative_to(base.resolve())
                or hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]
            ):
                raise ValueError("Nguồn gốc dữ liệu bổ sung đã thay đổi")
        for name, expected in self.manifest["files"].items():
            path = (self.root / name).resolve()
            if (
                not path.is_relative_to(self.root.resolve())
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected
            ):
                raise ValueError("Dữ liệu bổ sung đổi checksum: " + name)
        for row in json.loads((self.root / "records.json").read_text(encoding="utf-8"))["records"]:
            if row["id"] in self.records or row["calculation_enabled"] and row["domain"] != "label":
                raise ValueError("Bản ghi bổ sung trùng hoặc cho phép tính chưa được duyệt")
            self.records[row["id"]] = row
        self._terms = {
            rid: [search_text(row["name"]), *[search_text(a) for a in row["aliases"]]]
            for rid, row in self.records.items()
        }

    def status(self):
        return {
            "ready": bool(self.records),
            "release": self.manifest.get("release"),
            "records": len(self.records),
            "domains": dict(Counter(r["domain"] for r in self.records.values())),
            "usable_labels": sum(
                r["domain"] == "label" and r["calculation_enabled"] for r in self.records.values()
            ),
            "blocked_labels": sum(
                r["domain"] == "label" and not r["calculation_enabled"]
                for r in self.records.values()
            ),
        }

    def detect(self, question):
        q = fold(question)
        if is_intake_advice(question):
            return None
        explicit = re.search(r"\bsupp-[a-z0-9-]+\b", q)
        if explicit and explicit[0] in self.records:
            return self.records[explicit[0]]["domain"]
        if (
            re.search(
                r"\b(?:moc chau|mcc|th true|th truefood|th true food|th true nut|topkid)\b", q
            )
            or re.search(r"\bth\b", q)
            and re.search(r"\b(?:sua|tra|nuoc|banh|gio)\b", q)
        ):
            return "label"
        if re.search(r"\b(?:cong thuc|nguyen lieu|thanh pham|quy cach chao|bt04|dd04|tm04)\b", q):
            return "recipe"
        definition = bool(re.search(r"\b(?:la gi|dinh nghia|nghia la|phuong phap|do the nao)\b", q))
        if re.search(r"\b(?:giu chat|retention)\b", q) and not definition:
            return "retention"
        if re.search(r"\b(?:he so song.?chin|hssc|cooking yield|yield)\b", q) and not definition:
            return "yield"
        # Vietnamese 'gì' is a question word, not the GI abbreviation.
        if (
            re.search(r"\b(?:gi|gl)\b", question, re.I) or "chi so duong huyet" in q
        ) and not definition:
            return "gi"
        if re.search(r"\b(?:bat|to|gap|quy doi)\b", q) and re.search(
            r"\b(?:gram|gam|nang|khoi luong|250|280|bao nhieu g)\b", q
        ):
            return "portion"
        if "cdc" in q and re.search(r"\b(?:bang|tra|khau phan|cup|oz)\b", q):
            return "carb_choice"
        return None

    def search(self, query, domain=None, limit=8):
        exact = self.records.get(query)
        if exact and (not domain or domain == exact["domain"]):
            return [{**exact, "match_score": 200}]
        q = search_text(query)
        words = set(q.split()) - {
            "gi",
            "gl",
            "he",
            "so",
            "khau",
            "phan",
            "cong",
            "thuc",
            "tra",
            "cuu",
            "cua",
            "theo",
            "nin",
            "usda",
            "cdc",
        }
        if not words:
            return []
        ranked = []
        for rid, row in self.records.items():
            if domain and row["domain"] != domain:
                continue
            score = max(
                100
                if q.strip() == name.strip()
                else 75 + len(words) * 0.2
                if words.issubset(set(name.split()))
                else 55 * len(words & set(name.split())) / len(words)
                for name in self._terms[rid]
            )
            if score >= 55:
                ranked.append((score, rid, row))
        ranked.sort(
            key=lambda x: (-x[0], 0 if x[2]["source_id"] == "gi-vietnam-paper-2001" else 1, x[1])
        )
        return [{**row, "match_score": round(score, 2)} for score, _, row in ranked[:limit]]

    def execute(self, domain, plan, question):
        result = {
            "domain": domain,
            "items": [],
            "unresolved": [],
            "notes": [],
            "request": plan.model_dump(),
        }
        if plan.clarification:
            result["notes"].append(plan.clarification)
        q = fold(question)
        for requested in plan.items:
            matches = self.search(requested.name, domain, 100)
            if domain == "portion":
                capacity = re.search(r"\b(250|280)\s*ml\b", q)
                if capacity:
                    matches = [
                        r for r in matches if r["payload"]["vessel_capacity_ml"] == int(capacity[1])
                    ]
                for text in ["1/2", "2/3", "miệng", "xào", "luộc"]:
                    if fold(text) in q:
                        matches = [r for r in matches if fold(text) in fold(r["name"])]
                if re.search(r"\b(?:day|day mieng)\b", q) and "2/3" not in q and "1/2" not in q:
                    matches = [r for r in matches if "mieng" in fold(r["name"])]
            if domain in ["label", "gi", "recipe", "yield"]:
                # Never match an explicitly qualified type to the opposite type.
                for qualifier in [
                    "không đường",
                    "ít đường",
                    "có đường",
                    "5 sao",
                    "nếp",
                    "tẻ",
                    "khô",
                    "tươi",
                    "luộc",
                    "xào",
                ]:
                    if re.search(r"\b" + re.escape(fold(qualifier)) + r"\b", q):
                        matches = [
                            r
                            for r in matches
                            if fold(qualifier) in fold(r["name"])
                            or any(fold(qualifier) in fold(a) for a in r["aliases"])
                        ]
            if not matches:
                result["unresolved"].append(
                    {
                        "query": requested.name,
                        "reason": "Không có bản ghi khớp đủ thực phẩm/trạng thái/nguồn được hỏi. Không suy từ món khác.",
                        "candidates": [],
                    }
                )
                continue
            # Shared names are alternatives, not one interchangeable measurement.
            best = matches[0]
            peers = [r for r in matches if r["match_score"] >= best["match_score"] - 1]
            if len(peers) > 1:
                result["unresolved"].append(
                    {
                        "query": requested.name,
                        "reason": "Có nhiều loại, quy cách hoặc nghiên cứu. Cần chọn đúng bản ghi trước khi dùng số.",
                        "candidates": [
                            {"id": r["id"], "name": r["name"], "source_id": r["source_id"]}
                            for r in peers[:8]
                        ],
                    }
                )
                continue
            item = {k: v for k, v in best.items() if k != "match_score"}
            item.update(
                requested_name=requested.name,
                requested_amount=requested.amount,
                requested_unit=requested.unit,
                calculation_available=False,
                calculated_nutrients=None,
            )
            if domain == "label":
                payload = item["payload"]
                if payload["usable"]:
                    amount = requested.amount
                    unit = fold(requested.unit)
                    if unit in ["gram", "gam"]:
                        unit = "g"
                    if unit in ["lit", "l"] and amount is not None:
                        amount = amount * 1000
                        unit = "ml"
                    if unit == "kg" and amount is not None:
                        amount = amount * 1000
                        unit = "g"
                    if (
                        amount is not None
                        and unit == payload["basis_unit"]
                        and item["calculation_enabled"]
                    ):
                        factor = Decimal(str(amount)) / Decimal(str(payload["basis_amount"]))
                        item["calculated_nutrients"] = {
                            k: None
                            if v is None
                            else float((Decimal(str(v)) * factor).quantize(Decimal(".000001")))
                            for k, v in payload["nutrients"].items()
                        }
                        item["calculation_available"] = True
                    elif amount is not None:
                        item["limitations"] += (
                            " Chưa có quy đổi từ "
                            + requested.unit
                            + " sang "
                            + payload["basis_unit"]
                            + "; không đồng nhất ml với gram."
                        )
            result["items"].append(item)
        if not plan.items:
            result["notes"].append("Cần tên thực phẩm, món hoặc mã bản ghi để tra đúng bảng.")
        if plan.operation == "sum":
            result["notes"].append(
                "Công cụ bổ sung chưa hỗ trợ tổng bữa; không tự cộng nhãn/công thức khác đơn vị."
            )
        return result

    def resolve_selection(self, question, history):
        previous = history[-1].get("response", {}).get("reference_result") if history else None
        if not previous:
            return None
        matching = [
            (pending, candidate)
            for pending in previous.get("unresolved", [])
            for candidate in pending.get("candidates", [])
            if question.strip() == candidate["id"]
            or question.strip().lower() == candidate["name"].lower()
        ]
        if len(matching) != 1:
            return None
        pending, candidate = matching[0]
        plan = FoodPlan.model_validate(previous["request"])
        for item in plan.items:
            if item.name == pending["query"]:
                item.name = candidate["id"]
        return previous["domain"], plan

    def hits(self, result):
        hits = []
        for item in result["items"]:
            payload = item["payload"]
            lines = [
                f"Bản ghi: {item['name']}.",
                f"Nguồn: {item['source_title']}; vị trí: {item['locator']}.",
                f"Lượng người hỏi: {item['requested_amount']} {item['requested_unit']}.",
                "Giới hạn: " + item["limitations"],
            ]
            if item["domain"] == "label" and payload["usable"]:
                lines.append(f"Cơ sở nhãn: {payload['basis_amount']} {payload['basis_unit']}.")
                lines.append(
                    "Tính theo lượng hỏi được: " + str(item["calculation_available"]) + "."
                )
                wanted = {canonical(n, "") for n in result["request"]["nutrients"]}
                wanted.update(
                    "carbohydrate" for n in result["request"]["nutrients"] if fold(n) == "carb"
                )
                for key in NUTRIENTS:
                    value = payload['nutrients'].get(key)
                    name, unit, canonical_key = NUTRIENTS[key]
                    if wanted and canonical_key not in wanted:
                        continue
                    original = "không công bố" if value is None else str(value)
                    computed = item["calculated_nutrients"]
                    amount = (
                        "chưa tính được"
                        if computed is None or computed.get(key) is None
                        else str(computed[key])
                    )
                    lines.append(
                        f"- {name}: trên cơ sở nhãn {original} {unit}; theo lượng hỏi {amount} {unit}."
                    )
            elif item["domain"] == "portion":
                lines.extend(
                    [
                        f"Phần thực phẩm chín: {payload['cooked_food_component_g']} g; sống sạch tương đương: {payload['raw_edible_equivalent_g']} g.",
                        f"Dụng cụ: {payload['vessel_capacity_ml']} ml; mức/phần: {payload['portion_description']}; cách nấu: {payload['preparation']}.",
                        "Đây là gram của đơn vị tham khảo trong nguồn; không tự nhân số bát hoặc tính kcal món từ đây.",
                    ]
                )
            elif item["domain"] == "gi":
                gi = payload.get("gi_all_subjects", payload.get("GI"))
                lines.append(
                    f"GI được phép trả trong bản ghi: {gi if gi not in [None, ''] else 'chưa xác minh, không trả trị số'}."
                )
                lines.append(
                    "Không suy GI của món cùng tên tại Việt Nam. Không suy so sánh đáp ứng cá nhân."
                )
                lines.append(
                    "Phương pháp/đối tượng/mốc so sánh và dữ liệu gốc: "
                    + json.dumps(payload, ensure_ascii=False)
                )
            else:
                lines.append(
                    "Dữ liệu nguyên bản (null hoặc ô trống là thiếu, không phải 0): "
                    + json.dumps(payload, ensure_ascii=False)
                )
            body = "\n".join(lines)
            hits.append(
                Hit(
                    score=1,
                    chunk=Chunk(
                        id=item["id"],
                        source_id=item["source_id"],
                        title=item["source_title"],
                        section=item["name"],
                        text=body,
                        pages=[],
                        printed_pages=[],
                        filename="",
                        source_url=item["source_url"],
                        year=2026,
                        version="Nguồn/bảng thu 08/10/2026; giữ năm nghiên cứu trong dữ liệu",
                        sha256=item["source_sha256"],
                        token_count=0,
                        document_format="structured",
                        locators=[item["locator"]],
                    ),
                )
            )
        extra = []
        for unresolved in result["unresolved"]:
            extra.append(
                f"Yêu cầu {unresolved['query']}: {unresolved['reason']} Lựa chọn: "
                + json.dumps(unresolved["candidates"], ensure_ascii=False)
            )
        extra.extend(result["notes"])
        if extra:
            body = "\n".join(extra)
            hits.append(
                Hit(
                    score=1,
                    chunk=Chunk(
                        id="supp-lookup-context",
                        source_id="supplement-tool",
                        title="Kết quả tra cứu dữ liệu bổ sung",
                        section="Điều kiện và giới hạn tra cứu",
                        text=body,
                        pages=[],
                        printed_pages=[],
                        filename="",
                        source_url="/api/supplements",
                        year=2026,
                        version="2026-10-08",
                        sha256=hashlib.sha256(body.encode()).hexdigest(),
                        token_count=0,
                        document_format="structured",
                        locators=[],
                    ),
                )
            )
        return hits


def render_reference(record):
    body = json.dumps(record["payload"], ensure_ascii=False, indent=2)
    return (
        '<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dữ liệu tham khảo</title><link rel="stylesheet" href="/static/styles.css"><link rel="stylesheet" href="/static/source-preview.css"><body class="source-preview"><main><h1>'
        + escape(record["name"])
        + "</h1><p>"
        + escape(record["source_title"] + " · " + record["locator"])
        + '</p><a target="_blank" rel="noopener" href="'
        + escape(record["source_url"], quote=True)
        + '">Mở nguồn gốc</a><p>'
        + escape(record["limitations"])
        + '</p><p><a href="/api/supplements/'
        + escape(record["id"], quote=True)
        + '/original">Tải file gốc đã lưu</a></p><pre>'
        + escape(body)
        + "</pre></main></body></html>"
    )
