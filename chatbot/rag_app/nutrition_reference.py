"""Reviewed lookups for common nutrition questions with local evidence."""

import hashlib
import json
import re
from functools import lru_cache
from decimal import Decimal

from rag_app.config import ROOT
from rag_app.domain import Citation, Hit
from rag_app.food_data import FoodItem, FoodPlan, food_hits
from rag_app.ingestion import load_manifest
from rag_app.retrieval import fold
from rag_app.routing import label_reading_request

CDC_REFERENCES = {
    "carbohydrate": (
        "cdc-carb-counting",
        "What are the different kinds of carbs?",
        "Carbohydrate (carb) là nhóm chất gồm đường, tinh bột và chất xơ. "
        "Ví dụ, cơm có tinh bột, trái cây có đường tự nhiên và rau có chất xơ. [C1]",
    ),
    "plate": (
        "cdc-meal-planning",
        "The plate method",
        "Bạn có thể nhớ quy tắc chia đĩa: ½ rau ít tinh bột, ¼ đạm nạc và ¼ thực phẩm chứa carb. "
        "Ví dụ một đĩa có rau luộc, cá hấp và cơm theo ba phần đó. [C1]",
    ),
}
RICE_RECORDS = ("usda:168877", "usda:168878")
SUGAR_LABEL_SECTION = ("nin-labels", "Đọc nhãn: 100 g, 100 ml, khẩu phần và lượng thực tế")
PORTION_RECORDS = {"banana": "usda:173944", "sweetcorn": "usda:169999"}
PORTION_SIZES = {"nho": ("small", "nhỏ"), "vua": ("medium", "vừa"), "lon": ("large", "lớn")}
SEASONING_SECTION = ("ada-cooking", "Nêm món ăn: thảo mộc, gia vị, nước xốt, đường và natri")
# Match the reviewed excerpt, including the portion basis and provenance.
PORTION_ENERGY_SHA256 = "b4e707e66bafd9d020d59f1638c9460cbf13b11bcf5e68b0ab149f9b961dd6ef"


@lru_cache(maxsize=1)
def portion_energy_source():
    path = ROOT / "config/portion_energy_v1.json"
    try:
        raw = path.read_bytes().replace(b"\r\n", b"\n")
    except FileNotFoundError:
        return None
    if hashlib.sha256(raw).hexdigest() != PORTION_ENERGY_SHA256:
        return None
    return json.loads(raw)


def published_portion_energy(message):
    question = re.fullmatch(
        r"(?:(?:cho hoi|cho minh hoi) )?(?:mot|1) (.+?) (?:co |khoang )*(?:bao nhieu|may) "
        r"(?:calo|kcal)(?: (?:vay|nhi|a))?", fold(message).strip(" .?!"),
    )
    if not question:
        return None
    source = portion_energy_source()
    if source is None:
        return None
    portion = next((p for p in source["portions"] if fold(p["name"]) == question[1]), None)
    if not portion:
        return None
    name, kcal = portion["description"], portion["energy_kcal"]
    citation = Citation(
        id="C1", source_id=source["source_id"], chunk_id="mitc-table2-" + question[1].replace(" ", "-"),
        title=source["title"], section="Bảng 2, năng lượng theo phần mẫu",
        quote=f"1 {name}: {kcal} kcal.", pdf_pages=[], printed_pages=[source["printed_page"]], locators=["Bảng 2", name],
        source_url=source["source_url"], document_url=source["source_url"], year=source["year"], version=source["version"],
        document_format="curated",
    )
    return (f"Bảng tham khảo ghi {kcal} kcal cho một {name}. [C1] "
            "Phần bạn mua có thể khác về kích cỡ và nguyên liệu.", [citation])


LABEL_FIELDS = {
    "duong": "đường", "duong tong": "đường", "protein": "protein", "chat dam": "đạm", "dam": "đạm",
    "natri": "natri", "sodium": "natri", "carb": "carb", "carbohydrate": "carb", "chat bot duong": "carb",
    "chat beo": "chất béo", "lipid": "chất béo", "chat xo": "chất xơ",
}
LABEL_FIELD_PATTERN = "|".join(sorted(LABEL_FIELDS, key=len, reverse=True))
LABEL_ROW = re.compile(
    r"\b(?P<package>hop|hu|goi|chai) (?P<name>[a-z]) (?:nang |co dung tich )?"
    r"(?P<size>\d+(?:[.,]\d+)?)\s*(?P<unit>g|gam|gram|ml)\s*(?:,\s*)?"
    rf"(?:ghi|co|la)\s+(?P<rate>\d+(?:[.,]\d+)?)\s*(?P<measure>mg|g|gam|gram) (?P<field>{LABEL_FIELD_PATTERN})\s*"
    r"(?:tren|moi|/)\s*100\s*(?P<basis>g|gam|gram|ml)\b"
)


def label_calculation(message, history, *, previous_turn=None):
    """Calculate only the requested label field on an explicitly matching basis."""
    text = fold(message)
    if previous_turn and previous_turn.get('response', {}).get('clarification_question'):
        previous = fold(previous_turn['question'])
        rows = list(LABEL_ROW.finditer(previous))
        rate = re.fullmatch(r"(?:(?:tren )?nhan (?:ghi|co) )?(\d+(?:[.,]\d+)?)\s*(mg|g|gam|gram) "
                            rf"({LABEL_FIELD_PATTERN})\s*(?:tren|moi|/)\s*100\s*(g|gam|gram|ml)", text.strip(" .!?"))
        if rate and len(rows) == 1 and (rate[4] == 'ml') == (rows[0]['unit'] == 'ml'):
            row = rows[0]
            # Reuse the explicitly named package and size, then check the
            # requested nutrient against the new declaration below as usual.
            text = (f"{row['package']} {row['name']} {row['size']} {row['unit']} co "
                    f"{rate[1]} {rate[2]} {rate[3]}/100 {rate[4]}. " + LABEL_ROW.sub(" ", previous))
    if not re.search(r"\b(?:an het|uong het|nua|nguyen|ca) (?:hop|hu|goi|chai)\b", text):
        return None
    if re.search(r"\b(?:di ung|tieu duong|dai thao duong|duong huyet|moi ngay|phu hop|an toan)\b", text):
        return None
    data = {}
    for question in [*(turn['question'] for turn in history), text]:
        for row in LABEL_ROW.finditer(fold(question)):
            size = Decimal(row['size'].replace(',', '.'))
            if (row['unit'] == 'ml') != (row['basis'] == 'ml') or size <= 0:
                continue
            field = LABEL_FIELDS[row['field']]
            if field == 'đạm':
                field = 'protein'
            unit = 'mg' if row['measure'] == 'mg' else 'g'
            rate = Decimal(row['rate'].replace(',', '.'))
            data.setdefault(row['name'], {})[field] = (row['package'], unit, size * rate / 100)
    if not 1 <= len(data) <= 2:
        return None
    requested = {name: portion == 'nua' for portion, name in re.findall(
        r'\b(nua|nguyen|ca|het) (?:hop|hu|goi|chai) ([a-z])\b', text)}
    if requested.keys() - data.keys() or 'nua ' in text and not requested:
        return None
    requested = requested or dict.fromkeys(data, False)
    # Strip the label declaration before interpreting the actual question.
    ask = LABEL_ROW.sub(" ", text)
    targets = {LABEL_FIELDS[key] for key in re.findall(rf"\b({LABEL_FIELD_PATTERN})\b", ask)}
    if len(targets) > 1 or re.search(r"\b(?:vitamin|calo|kcal|canxi|kali|duong them|duong bo sung)\b", ask):
        return None
    if not targets:
        # Infer the sole label field only in an elliptical portion comparison.
        neutral = re.sub(r"\b(?:hop|hu|goi|chai) [a-z]\b", "hop", ask)
        allowed = set("neu an uong het ca nua nguyen mot hop hu goi chai thi sao con so voi the nao vay minh toi".split())
        if set(re.findall(r"[a-z0-9]+", neutral)) - allowed:
            return None
        available = set.intersection(*(set(data[name]) for name in requested))
        if len(available) != 1 or not re.search(r"\b(?:thi sao|so voi|the nao|nhieu hon|bao nhieu)\b", ask):
            return None
        targets = available
    target = next(iter(targets))
    field = "protein" if target == "đạm" else target
    package_names = {"hop": "hộp", "hu": "hũ", "goi": "gói", "chai": "chai"}
    portions = []
    for name, half in requested.items():
        if field not in data[name]:
            clarification = f"Bạn cho mình số {target} trên 100 g hoặc 100 ml ghi trên nhãn {name.upper()} nhé?"
            return f"Để tính {target} cho phần này, mình cần đúng dòng {target} trên nhãn.", clarification
        package, unit, value = data[name][field]
        description = f"{'nửa' if half else 'cả'} {package_names[package]} {name.upper()}"
        portions.append((description, value / 2 if half else value, unit))
    # Compare on the same unit even if one label reports milligrams.
    if len({unit for _, _, unit in portions}) > 1:
        portions = [(name, value * (1000 if unit == 'g' else 1), 'mg') for name, value, unit in portions]
    portions.sort(key=lambda portion: portion[1], reverse=True)
    first, a, unit = portions[0]
    a_text = f"{a.normalize():f}".replace(".", ",")
    if len(portions) == 1:
        return f"Theo số bạn ghi, {first} có {a_text} {unit} {target}.", None
    second, b, _ = portions[1]
    b_text = f"{b.normalize():f}".replace(".", ",")
    if a == b:
        return f"Theo số bạn ghi, {first} và {second} có cùng lượng {target}, mỗi phần {a_text} {unit}.", None
    return (f"Theo số bạn ghi, {first} có nhiều {target} hơn {second}. "
            f"{first[0].upper() + first[1:]} có {a_text} {unit} {target}, còn {second} có {b_text} {unit}.", None)


def nutrition_reference_topic(message):
    text = re.sub(r"[^\w]+", " ", fold(message)).strip()
    if (re.search(r"\b(?:kho|rim|ham)\b", text)
            and re.search(r"\b(?:nem|uop)\b", text)
            and re.search(r"\b(?:bot man|it man|giam do man)\b", text)
            and not re.search(r"\b(?:lo tay|qua man|bi man|da man|cach cuu|di ung|theo)\b", text)):
        return "less_salty_stew"
    if (label_reading_request(message)
            and not re.search(r'\b(?:theo (?:quy dinh|luat|tieu chuan|bo y te|fda)|'
                              r'\d+\s*(?:g|gram|ml))\b', text)):
        if "khong duong" in text and "it duong" in text and "phan biet" in text:
            return "sugar_label_claims"
        if re.search(r"\b(?:loai nao nhieu duong hon|so sanh luong duong|hop nao nhieu duong hon)\b", text):
            return "sugar_label_comparison"
    portion = re.fullmatch(
        r"(?:(?:cho minh biet|cho hoi|tinh giup minh) )?(?:mot |1 )?"
        r"(?P<food>(?:(?:qua|trai) )?chuoi(?: tuoi)?|(?:bap|ngo)(?: ngo| ngot| ngot vang)? luoc)"
        r" (?:co |kich thuoc )?(?P<size>nho|vua|lon)(?: co)?"
        r" (?:(?:co |khoang |tam |chung )*(?:bao nhieu|may|nhieu) (?:calo|kcal)|"
        r"(?:calo|kcal) (?:khoang |tam )?bao nhieu)(?: (?:vay|nhi|nhe|a))?",
        text,
    )
    if portion:
        food = "banana" if "chuoi" in portion["food"] else "sweetcorn"
        return (food, portion["size"])
    if re.fullmatch(
        r"(?:giai thich )?(?:carbohydrates?|carbs?|chat bot duong|glucid) "
        r"(?:la gi|nghia la gi)(?: (?:vay|nhe|ban giai thich de hieu duoc khong|giai thich de hieu))?",
        text,
    ):
        return "carbohydrate"
    if re.fullmatch(
        r"(?:(?:cho (?:minh|em|toi) )?(?:(?:mot |1 )?nguyen tac(?: de nho)? khi chon bua an|"
        r"(?:huong dan )?cach chia dia(?: an)?) cho nguoi (?:tieu duong|dai thao duong)(?: type 2)?|"
        r"phuong phap chia dia(?: an)? la gi)(?: (?:nhe|vay))?",
        text,
    ):
        return "plate"
    if re.fullmatch(
        r"(?:so sanh(?: dinh duong)? )?100 ?(?:g|gam|gram) gao(?: trang)? song "
        r"(?:va|voi|so voi) 100 ?(?:g|gam|gram) com(?: trang)? chin"
        r"(?: co (?:dinh duong )?(?:giong nhau|nhu nhau|bang nhau) khong| khac nhau the nao)?",
        text,
    ):
        return "rice"
    return None


def nutrition_reference_reply(topic, source_manifest, store, foods):
    if topic == "less_salty_stew":
        hits = nutrition_reference_hits(*SEASONING_SECTION, source_manifest, store)
        if not hits:
            return "Mình chưa có đoạn hướng dẫn nêm nấu đã duyệt để đối chiếu câu này.", []
        return (
            "Khi kho, bạn cho ít nước mắm hoặc muối ngay từ đầu, rồi thêm tiêu, gừng hoặc sả để món thơm hơn. "
            "Gần cuối mới nếm lại và thêm chút gia vị mặn nếu cần. [C1]",
            hits,
        )

    if isinstance(topic, tuple):
        food, size = topic
        record_id = PORTION_RECORDS[food]
        size_key, size_label = PORTION_SIZES[size]
        record = foods.records.get(record_id)
        portion_data = record.get("common_portions", {}).get(size_key) if record else None
        if not portion_data:
            return "Mình chưa có số liệu đã kiểm tra cho cỡ phần ăn này.", []
        grams, energy = portion_data["amount_g"], portion_data["energy_kcal"]
        result = foods.execute(FoodPlan(
            operation="lookup", items=[FoodItem(name=record_id, amount=grams)],
            nutrients=["calo"], dataset="usda",
        ))
        if not result["items"] or result["items"][0]["id"] != record_id or not result["items"][0]["calculation_available"]:
            return "Mình chưa xác minh được số liệu của cỡ phần ăn này.", []
        result["items"][0]["source_portion"] = {**portion_data, "label": size_label}
        if food == "banana":
            subject, basis = "Một quả chuối", "thịt quả đã bóc vỏ"
        else:
            subject, basis = "Một bắp ngô ngọt luộc không muối", "hạt, bỏ lõi"
        answer = (f"{subject} cỡ {size_label} có khoảng {energy} kcal. "
                  f"Mẫu USDA tính theo {grams} g {basis}. [C1]")
        return answer, food_hits(result)[:1]

    if topic in {"sugar_label_claims", "sugar_label_comparison"}:
        hits = nutrition_reference_hits(*SUGAR_LABEL_SECTION, source_manifest, store)
        if not hits:
            return "Mình chưa có đoạn hướng dẫn đọc nhãn đã duyệt để đối chiếu câu này.", []
        if topic == "sugar_label_claims":
            answer = (
                "Đọc tên phiên bản trên mặt hộp rồi tìm dòng “đường tổng” trong bảng dinh dưỡng. "
                "Nếu cả hai hộp đều có số, hãy so ở cùng lượng ghi trên nhãn, chẳng hạn trên 100 ml. "
                "Nếu hộp chỉ ghi “không đường” hoặc “ít đường” mà thiếu dòng này, bạn chưa đối chiếu được số gram đường từ hai nhãn. [C1]"
            )
        else:
            answer = (
                "Bạn tìm dòng “đường tổng” trên hai nhãn. Muốn biết loại nào có nhiều đường hơn khi ăn cùng lượng, "
                "so số gram đường trên cùng 100 g. Muốn biết ăn hết hộp nào nạp nhiều đường hơn, "
                "tính theo khối lượng cả hộp hoặc nhân số đường mỗi khẩu phần với số khẩu phần trong hộp. [C1]"
            )
        return answer, hits

    if topic == "rice":
        plan = FoodPlan(
            operation="compare",
            items=[FoodItem(name=record_id, amount=100) for record_id in RICE_RECORDS],
            nutrients=["calo", "carbohydrate"],
            dataset="usda",
        )
        result = foods.execute(plan)
        items = result["items"]
        if result["unresolved"] or tuple(item["id"] for item in items) != RICE_RECORDS:
            return "Mình chưa có đủ hai bản ghi USDA cho gạo sống và cơm chín để so sánh số liệu.", []
        rows = [{n["key"]: n["amount_value"] for n in item["display_nutrients"]} for item in items]
        if any(row.get(key) is None for row in rows for key in ("energy", "carbohydrate")):
            return "Mình chưa có đủ số năng lượng và carbohydrate cho cả hai trạng thái.", []
        raw, cooked = rows
        raw_carb = f"{raw['carbohydrate']:g}".replace(".", ",")
        cooked_carb = f"{cooked['carbohydrate']:g}".replace(".", ",")
        answer = (
            "Khác nhau. Gạo hút nước khi nấu, nên 100 g cơm chín chứa nhiều nước hơn 100 g gạo sống. "
            "Ví dụ với gạo trắng hạt dài theo USDA:\n\n"
            f"- 100 g gạo sống có {raw['energy']:g} kcal và {raw_carb} g carbohydrate. [C1]\n"
            f"- 100 g cơm chín có {cooked['energy']:g} kcal và {cooked_carb} g carbohydrate. [C2]\n\n"
            "Đây là hai mẫu cùng khối lượng. Lượng cơm thu được từ một mẻ gạo còn tùy lượng nước và cách nấu."
        )
        return answer, food_hits(result)

    source_id, section, answer = CDC_REFERENCES[topic]
    hits = nutrition_reference_hits(source_id, section, source_manifest, store)
    if hits:
        return answer, hits
    return "Mình chưa có đoạn nguồn CDC đã duyệt trong chỉ mục để dẫn chứng cho câu hỏi này.", []


def nutrition_reference_hits(source_id, section, source_manifest, store):
    sources = load_manifest(source_manifest)["sources"]
    approved = next((source for source in sources if source["id"] == source_id and source["enabled"]), None)
    if approved:
        chunks, _, _ = store.load_index(include_vectors=False)
        chunk = next((chunk for chunk in chunks if chunk.source_id == source_id and chunk.section == section
                      and chunk.sha256 == approved["sha256"] and chunk.document_format == approved["format"]), None)
        if chunk:
            return [Hit(chunk=chunk, score=1)]
    return []
