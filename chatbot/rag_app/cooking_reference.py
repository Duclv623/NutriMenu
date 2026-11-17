"""Quick cooking suggestions with reviewed food-handling instructions."""

import re

from rag_app.domain import Citation
from rag_app.retrieval import fold

FSA_RICE_URL = (
    "https://www.food.gov.uk/sites/default/files/media/document/"
    "sfbb-chinese-05-cooking-04-rice_0.pdf"
)
FDA_EGG_URL = "https://www.fda.gov/media/82227/download"
USDA_MEAT_URL = "https://ask.fsis.usda.gov/article/What-is-a-safe-internal-temperature-for-cooking-meat-and-poultry"
PACKED_LUNCH_URL = (
    "https://www.udel.edu/content/dam/udelImages/canr/pdfs/extension/factsheets/"
    "Safe-Brown-Bag-Lunches.pdf"
)
CDC_PRODUCE_URL = "https://www.cdc.gov/cyclosporiasis/prevention/index.html"
VCE_VEGETABLES_URL = "https://www.pubs.ext.vt.edu/content/pubs_ext_vt_edu/en/348/348-960/348-960.html"

FSA_RICE = Citation(
    id="C1", chunk_id="fsa-safe-rice", source_id="fsa-food-safety",
    title="Food Standards Agency — Safe Method: Rice", section="Cooling, storing and reheating rice",
    pdf_pages=[1, 2], printed_pages=[], source_url=FSA_RICE_URL, document_url=FSA_RICE_URL,
    year=2026, version="Đoạn hướng dẫn đối chiếu ngày 17/11/2026",
    quote="Làm nguội cơm nhanh, trong vòng một giờ, rồi đậy kín và cất trong tủ lạnh. "
          "Dùng trong vòng 24 giờ. Khi hâm, làm nóng kỹ toàn bộ phần cơm.",
    document_format="pdf", locators=["Safe Method: Rice"],
)
FDA_EGG = Citation(
    id="C1", chunk_id="fda-cook-eggs", source_id="fda-egg-safety",
    title="FDA — What You Need to Know About Egg Safety", section="Preparing",
    pdf_pages=[2, 4], printed_pages=[], source_url=FDA_EGG_URL, document_url=FDA_EGG_URL,
    year=2022, version="May 2022",
    quote="Nấu trứng đến khi lòng trắng và lòng đỏ đông lại. Nấu chín kỹ món có trứng. "
          "Thịt, gia cầm và hải sản sống cần được nấu đến nhiệt độ an toàn.",
    document_format="pdf", locators=["Preparing", "Safe Food Handling / Cook"],
)
USDA_GROUND_MEAT = Citation(
    id="C1", chunk_id="usda-ground-meat-temperature", source_id="usda-fsis-food-safety",
    title="USDA FSIS - Safe Internal Temperature for Cooking Meat and Poultry",
    section="Safe internal temperatures", pdf_pages=[], printed_pages=[],
    source_url=USDA_MEAT_URL, document_url=USDA_MEAT_URL, year=2024, version="September 4, 2024",
    quote="Nấu thịt bò, heo, cừu và bê xay đến nhiệt độ bên trong 160 °F (71,1 °C). "
          "Với gia cầm, kể cả gia cầm xay, dùng nhiệt kế thực phẩm kiểm tra đạt 165 °F (73,9 °C).",
    document_format="curated", locators=["Knowledge Article"],
)
GROUND_MEAT_TEMPERATURE = (
    "Nếu dùng thịt xay sống, đo nhiệt độ ở phần thịt bằng nhiệt kế thực phẩm. "
    "Thịt bò, heo, cừu hoặc bê xay cần đạt 71,1 °C, còn gia cầm xay cần đạt 73,9 °C. [C1]"
)
PACKED_LUNCH = Citation(
    id="C1", chunk_id="udel-packed-lunch", source_id="udel-food-safety",
    title="University of Delaware Cooperative Extension — Safe Brown Bag Lunches",
    section="Pack Cold / Pack Without Temp Control",
    pdf_pages=[1], printed_pages=[], source_url=PACKED_LUNCH_URL, document_url=PACKED_LUNCH_URL,
    year=2026, version="Đoạn hướng dẫn đối chiếu ngày 17/11/2026",
    quote="Giữ lạnh thực phẩm dễ hỏng bằng túi cách nhiệt có đá hoặc túi gel đông lạnh. "
          "Khi không thể giữ lạnh, có thể mang bánh mì phết bơ đậu phộng, trái cây nguyên quả "
          "hoặc cá ngừ đóng hộp chưa mở.",
    document_format="pdf", locators=["Pack Cold", "Pack Without Temp Control"],
)
CDC_PRODUCE = Citation(
    id="C1", chunk_id="cdc-cut-produce-refrigeration", source_id="cdc-produce-safety",
    title="CDC - Preventing Cyclosporiasis", section="Refrigerate produce as soon as possible",
    pdf_pages=[], printed_pages=[], source_url=CDC_PRODUCE_URL, document_url=CDC_PRODUCE_URL,
    year=2026, version="September 11, 2026", document_format="curated", locators=["Actions to take"],
    quote="Bảo quản lạnh rau củ quả đã cắt, gọt vỏ hoặc nấu chín càng sớm càng tốt.",
)
VCE_VEGETABLES = Citation(
    id="C2", chunk_id="vce-vegetable-storage", source_id="vce-food-storage",
    title="Virginia Cooperative Extension - Food Storage Guidelines for Consumers",
    section="Table 5. Recommendations for storing vegetables", pdf_pages=[], printed_pages=[],
    source_url=VCE_VEGETABLES_URL, document_url=VCE_VEGETABLES_URL,
    year=2025, version="October 31, 2025", document_format="curated", locators=["Table 5"],
    quote="Bảng khuyến nghị cất lạnh bông cải xanh, bắp cải và cà rốt. Trong ba loại, bông cải xanh có "
          "khoảng bảo quản lạnh ngắn nhất, sau đó đến bắp cải rồi cà rốt.",
)
COOKING_SOURCE_IDS = {source.source_id for source in (
    FSA_RICE, FDA_EGG, PACKED_LUNCH, USDA_GROUND_MEAT, CDC_PRODUCE, VCE_VEGETABLES,
)}


GROUND_MEAT = r"(?:thit(?: (?:bo|heo|lon|ga|vit|gia cam|cuu|be))?|bo|heo|lon|ga|vit|gia cam|cuu|be) (?:bam|xay|nghien)"
COOK_GROUND_MEAT = re.compile(
    rf"\b(?:nau|xao|luoc|hap|rim|om|rang) (?:het |phan )?(?:{GROUND_MEAT}|thit) "
    rf"(?:(?:cho|den|toi)(?: khi)? )?chin\b|\b(?:nau|xao|luoc|hap|rim|om|rang) chin(?: ky)? (?:{GROUND_MEAT}|thit)\b"
    rf"|\b(?:den khi|toi khi|kiem tra|dam bao) (?:{GROUND_MEAT}|thit) (?:da )?chin\b"
    rf"|\b{GROUND_MEAT} (?:can |phai )?chin (?:ky|hoan toan|truoc khi)\b"
)
ONION = r"hanh(?: (?:tay|la|tim|cu|kho|phi))?"
ONION_RESTRICTION = re.compile(rf"\b(?:khong (?:the )?(?:an|dung|bo)(?: duoc)?|tranh|kieng|di ung(?: voi)?) +{ONION}\b")
COLD_TRAVEL = re.compile(r"\b(?:mang|dem|chuan bi)\b.*\b(?:di lam|van phong|bua trua|com hop)\b.*"
                         r"\b(?:khong co lo vi song|khong (?:the )?ham|khong ham lai|an nguoi)\b")


def uses_ground_meat(text):
    q = fold(text)
    return bool(re.search(r"\b(?:nau|xao|luoc|hap|rim|om|rang|cho|tron|them|dung)\b", q)
                and re.search(rf"\b{GROUND_MEAT}\b", re.sub(
                    rf"\b{GROUND_MEAT} (?:da )?(?:(?:nau|xao|hap|luoc) )?chin\b", "", q)))


def direct_cooking_revision(text, question, history):
    q = fold(text)
    if uses_ground_meat(text) and not COOK_GROUND_MEAT.search(q):
        return ("Nếu dùng thịt băm/xay sống, ghi rõ bước nấu chín kỹ thịt trước khi ăn. "
                "Nếu món nhanh hoặc chỉ có nồi cơm điện, ưu tiên nguyên liệu đã chín.")
    if (re.search(r"\b(?:uc ga|thit ga|ga (?:da nau|luoc|ap chao))\b", q)
            and any(COLD_TRAVEL.search(fold(turn)) for turn in [question, *(t['question'] for t in history)])
            and not re.search(r"\b(?:da gel|tui giu nhiet|tui cach nhiet|giu lanh)\b", q)):
        return ("Với phần gà mang đi ăn nguội, thêm cách để nguội rồi cất lạnh, "
                "đóng vào túi cách nhiệt với đá gel đã đông và giữ lạnh đến khi ăn.")
    if re.search(r"\btỏi\b", text, re.IGNORECASE):
        for user_turn in [question, *(turn['question'] for turn in reversed(history))]:
            turn = fold(user_turn)
            if re.search(r"\b(?:van |co the )?(?:an|dung) duoc toi\b", turn) and not re.search(
                r"\bkhong (?:the )?(?:an|dung) duoc toi\b", turn
            ):
                break
            if ONION_RESTRICTION.search(turn):
                return ("Người dùng tránh hành và chưa xác nhận dùng được tỏi. "
                        "Gợi ý rau thơm hoặc gia vị khác, không tự suy là dị ứng.")
    return ""


def cooking_reference_reply(message, profile, *, followup=False):
    q = fold(message)
    # Open-ended recipe suggestions go through the regular route when there
    # are exclusions, requested nutrition details, or a clinical question.
    if profile and (profile.allergies or profile.restricted_ingredients or profile.preferences
                    or profile.excluded_ingredient_ids):
        return None
    if (re.search(r"\bdua (?:leo|chuot)\b", q) and re.search(r"\bde chung\b", q)
            and re.search(r"\bbanh(?: mi)? (?:bi )?(?:mem|am|nhun)\b", q)
            and not re.search(r"\b(?:di ung|tieu duong|dai thao duong|calo|kcal)\b", q)):
        return (
            "Có thể, vì dưa leo làm bánh dễ bị ẩm. Bạn thấm khô lát dưa, để riêng với bánh mì "
            "rồi kẹp vào lúc ăn để bánh giữ được độ giòn.",
            [],
        )
    if (re.search(r"\btui (?:giu nhiet|cach nhiet)\b", q) and re.search(r"\bda gel\b", q)
            and re.search(r"\b(?:nen xep|xep do|dong goi|dat da)\b", q)
            and not re.search(r"\b(?:bao lau|bao nhieu|nhiet do|may gio|di ung|tieu duong|dai thao duong)\b", q)):
        return (
            "Giữ phần nhân đã nấu chín trong tủ lạnh đến lúc đóng gói. "
            "Sáng hôm sau, đặt hộp nhân đã lạnh trong túi giữ nhiệt, sát túi đá gel đã đông. "
            "Giữ túi đóng kín đến bữa. Nếu không thể giữ lạnh, chọn đồ chưa mở có thể bảo quản ở nhiệt độ phòng. [C1]",
            [PACKED_LUNCH],
        )
    if (re.search(r"\bca rot\b", q) and re.search(r"\bbap cai\b", q) and re.search(r"\btu lanh\b", q)
            and re.search(r"\b(?:uu tien|cat cai nao|cat.*truoc|bao quan.*truoc)\b", q)
            and not re.search(r"\b(?:da hong|moc|qua han|bao lau|bao nhieu|nhiet do|di ung)\b", q)):
        return (
            "Nếu một loại đã cắt, cất phần đó trước. Nếu cả hai đã cắt, nên giữ lạnh cả hai. [C1]\n\n"
            "Nếu cả hai còn nguyên, ưu tiên bắp cải vì thời gian bảo quản lạnh ngắn hơn cà rốt. "
            "Khi có chỗ, cất lạnh cả hai. [C2]",
            [CDC_PRODUCE, VCE_VEGETABLES],
        )
    if followup:
        return None
    if (re.search(r"\b(?:ba|3) loai rau(?: cu)?\b", q) and re.search(r"\b(?:goi y|di cho|mua)\b", q)
            and re.search(r"\b(?:lan luot|thu tu|dung truoc|nau truoc)\b", q)
            and not re.search(r"\b(?:co san|da co|nha (?:dang |con )?co|khong (?:co|an|dung)|"
                              r"di ung|tieu duong|dai thao duong|dinh duong|calo|kcal)\b", q)):
        return (
            "Bạn có thể mua bông cải xanh, bắp cải và cà rốt. Nếu cất lạnh khi còn nguyên, "
            "dùng bông cải xanh vào bữa đầu, bắp cải bữa sau và cà rốt cuối cùng. "
            "Bảng bảo quản xếp bông cải xanh có thời gian giữ lạnh ngắn nhất trong ba loại. [C1]",
            [VCE_VEGETABLES.model_copy(update={"id": "C1"})],
        )
    budget = re.search(r"\b(?:co|ngan sach|toi da|khong qua|duoi)\s*(\d[\d.,]*)\s*(k|nghin|ngan|dong)\b", q)
    if (budget and re.search(r"\b(?:quan com|suat com)\b", q)
            and re.search(r"\b(?:goi|chon|mua)\b", q) and re.search(r"\bmon man\b.*\brau\b|\brau\b.*\bmon man\b", q)
            and not re.search(r"\b(?:di ung|tieu duong|dai thao duong|nguon|tai lieu|dinh duong|calo|kcal)\b", q)):
        unit = 'đồng' if budget[2] == 'dong' else 'nghìn'
        return (
            f"Bạn có thể hỏi “Quán có suất nào gồm món mặn và rau trong {budget[1]} {unit} không? "
            "Nếu rau tính riêng thì tổng suất là bao nhiêu ạ?” Chọn suất sau khi quán báo tổng giá.",
            [],
        )
    if (ONION_RESTRICTION.search(q) and re.search(r"\bcanh bi(?: (?:do|xanh|dao))?\b", q)
            and re.search(r"\b(?:cho thom|gi vao|mua gi|nguyen lieu|them gi)\b", q)
            and not re.search(r"\b(?:di ung|tieu duong|dai thao duong|calo|kcal|bao nhieu|theo tai lieu)\b", q)):
        return (
            "Bạn có thể dùng vài lát gừng khi nấu canh bí và rắc chút tiêu hoặc mùi tàu lúc tắt bếp. "
            "Nếu đi chợ, chỉ cần chọn bí, gừng và một ít mùi tàu nếu thích.",
            [],
        )
    if re.search(r"\b(?:an chay|an kieng|di ung|khong an|khong dung|tieu duong|dai thao duong|tranh|"
                 r"khong (?:co|them|lay) (?:trung|thit|rau|ca|dua leo|tao)|"
                 r"duong huyet|calo|kcal|khau phan|bao nhieu|theo tai lieu)\b", q):
        return None
    if re.search(r"\bcom (?:nguoi|thua|tu hom qua|qua dem)\b", q) and re.search(
        r"\b(?:nau|lam|che bien|rang)(?: mon| gi| voi| cho| de| com| nhe| the nao)\b", q
    ):
        if re.search(r"\btrung\b", q):
            dish = "cơm rang trứng"
            steps = "Đảo trứng cho chín rồi thêm cơm, đảo đến khi cả phần cơm nóng bốc hơi đều."
            if "ca chua" in q:
                dish += " cà chua"
                steps = "Xào cà chua cho mềm, đảo trứng đến chín rồi cho cơm vào. Đảo đến khi cả phần cơm nóng bốc hơi đều."
        else:
            dish = "cơm rang với rau củ có sẵn"
            steps = "Xào rau củ trước rồi cho cơm vào đảo đến khi cả phần cơm nóng bốc hơi đều."
        return (
            f"Bạn có thể làm {dish} nếu cơm đã được làm nguội trong vòng một giờ sau khi nấu "
            "và cất tủ lạnh chưa quá 24 giờ. Nếu cơm đã để ngoài lâu hoặc bạn không rõ đã cất thế nào, "
            f"dùng cơm mới. [C1]\n\n{steps}",
            [FSA_RICE],
        )
    if re.search(r"\b(?:up (?:goi |to |ly )?mi|mi (?:goi |an lien )?up|"
                 r"(?:do|che) nuoc soi (?:vao |len )?mi)\b", q) and re.search(
        r"\b(?:them|bo|cho|an kem|tron)\b", q
    ):
        return (
            "Úp mì như thường, rồi thêm trứng luộc cắt đôi và ít rau cải đã luộc. "
            "Nếu có thịt đã nấu chín, bạn cũng có thể dùng vài lát. "
            "Trứng hoặc thịt còn sống thì nấu chín riêng trước khi cho vào tô. [C1]",
            [FDA_EGG],
        )
    if (
        COLD_TRAVEL.search(q)
        and re.search(r"\b(?:mon gi|nau gi|mang gi|goi y|chuan bi gi)\b", q)
        and not re.search(r"\b(?:nha (?:con )?co|(?:minh|toi) (?:chi |dang |con )?co|co san)\b", q)
    ):
        return (
            "Bạn có thể mang bánh mì kẹp gà đã nấu chín và một quả táo. "
            "Giữ bánh mì trong túi giữ nhiệt có đá khi mang đi. Nếu chỗ làm có tủ lạnh, hãy cất vào khi tới nơi. "
            "Nếu không giữ lạnh được, mang bánh mì, hộp cá ngừ còn nguyên và một quả táo. "
            "Đến bữa mới mở hộp cá. [C1]",
            [PACKED_LUNCH],
        )
    bread_choices = re.search(r"\bbanh mi\s+(.+?)\s+(?:hay|voi|va)\s+banh mi\s+([^,.?!]+)", q)
    if bread_choices and re.search(r"\b(?:it|bot|do) ngay hon\b", q):
        return (
            "Độ ngấy còn tùy quán dùng bao nhiêu dầu, bơ và sốt. "
            "Nếu trứng được làm ít dầu thì bánh mì trứng là một lựa chọn. "
            "Bạn có thể hỏi quán ổ nào làm ít dầu hơn rồi dặn bớt bơ hoặc sốt.",
            [],
        ) if any("trung" in filling.split() for filling in bread_choices.groups()) else (
            "Bạn hỏi xem ổ nào có nhân được làm ít dầu hơn rồi chọn ổ đó. "
            "Dặn bớt bơ hoặc sốt nếu quán có dùng.",
            [],
        )
    return None
