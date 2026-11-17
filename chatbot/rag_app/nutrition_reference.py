"""Reviewed lookups for common nutrition questions with local evidence."""

import re
from decimal import Decimal

from rag_app.domain import Hit
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
LABEL_ROW = re.compile(
    r"\b(?P<package>hop|hu|goi|chai) (?P<name>[a-z]) (?:nang |co dung tich )?"
    r"(?P<size>\d+(?:[.,]\d+)?)\s*(?P<unit>g|gam|gram|ml)\s*(?:,\s*)?"
    r"(?:ghi|co|la)\s+(?P<sugar>\d+(?:[.,]\d+)?)\s*(?:g|gam|gram) duong(?: tong)?\s*"
    r"(?:tren|moi|/)\s*100\s*(?P<basis>g|gam|gram|ml)\b"
)


def label_sugar_calculation(message, history):
    """Compare two packages using only the label numbers the user supplied."""
    text = fold(message)
    if not re.search(r"\b(?:an het|uong het|nua|nguyen|ca) (?:hop|hu|goi|chai)\b", text):
        return None
    if re.search(r"\b(?:di ung|tieu duong|dai thao duong|duong huyet|bao nhieu(?: gam)? moi ngay|phu hop|an toan)\b", text):
        return None
    data = {}
    for question in [*(turn['question'] for turn in history), message]:
        for row in LABEL_ROW.finditer(fold(question)):
            if (row['unit'] == 'ml') != (row['basis'] == 'ml'):
                continue
            size = Decimal(row['size'].replace(',', '.'))
            rate = Decimal(row['sugar'].replace(',', '.'))
            if size > 0:
                data[row['name']] = (row['package'], size * rate / 100)
    if not 1 <= len(data) <= 2:
        return None
    requested = dict((name, portion == 'nua') for portion, name in re.findall(
        r'\b(nua|nguyen|ca|het) (?:hop|hu|goi|chai) ([a-z])\b', text))
    if requested.keys() - data.keys() or 'nua ' in text and not requested:
        return None
    if not requested and not re.search(r'\b(?:an|uong) het (?:hop|hu|goi|chai)\b', text):
        return None
    requested = requested or dict.fromkeys(data, False)
    package_names = {'hop': 'hộp', 'hu': 'hũ', 'goi': 'gói', 'chai': 'chai'}
    portions = []
    for name, half in requested.items():
        package, value = data[name]
        description = f"{'nửa' if half else 'cả'} {package_names[package]} {name.upper()}"
        portions.append((description, value / 2 if half else value))
    portions.sort(key=lambda portion: portion[1], reverse=True)
    if len(portions) == 1:
        name, value = portions[0]
        amount = f'{value.normalize():f}'.replace('.', ',')
        return f"Theo số bạn ghi, {name} có {amount} g đường."
    (first, a), (second, b) = portions
    a_text, b_text = (f'{v.normalize():f}'.replace('.', ',') for v in (a, b))
    if a == b:
        return f"Theo số bạn ghi, {first} và {second} có cùng lượng đường, mỗi phần {a_text} g."
    return (f"Theo số bạn ghi, {first} có nhiều đường hơn {second}. "
            f"{first[0].upper() + first[1:]} có {a_text} g đường, còn {second} có {b_text} g.")


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
