import re

from rag_app.domain import Intent
from rag_app.retrieval import fold

DISCLAIMER = (
    "Thông tin phục vụ giáo dục dinh dưỡng, không thay thế tư vấn của bác sĩ/chuyên gia dinh dưỡng."
    " Các mức dinh dưỡng và vận động trong tài liệu là tham khảo, không tự áp dụng cho cá nhân khi chưa được chuyên gia đánh giá."
)

SPECIAL_CONDITIONS = (
    "suy than", "chay than", "loc mau", "mang thai", "thai ky", "co bau",
    "dang bau", "mang bau", "benh than", "bau bi", "tieu duong thai", "tre em", "type 1", "tip 1", "typ 1", "tiep 1", "tip mot", "type mot",
)
EMERGENCY_SYMPTOMS = (
    "bat tinh", "co giat", "kho tho", "dau nguc", "hon me", "khong tinh",
    "ngat", "cap cuu", "khong nuot duoc", "lo mo", "lu lan",
)


def asserted_conditions(message: str) -> str:
    """Remove explicitly denied conditions, without removing positive clauses."""
    q = fold(message)
    terms = "|".join(re.escape(t) for t in (*SPECIAL_CONDITIONS, *EMERGENCY_SYMPTOMS))
    q = re.sub(
        rf'\b(?:khong|chua)(?: he| con)?\s+(?:(?:bi|mac|dang|co|phai)\s+)?'
        rf'(?:{terms})(?:\s+(?:hay|hoac|va)\s+(?:{terms}))*\b', '', q,
    )
    q = re.sub(
        rf"\b(?:khong|chua)(?: con)?\s+(?:(?:bi|mac|dang|co|phai)\s+)?(?:{terms})\b",
        "", q,
    )
    return q


def has_emergency_symptoms(message: str) -> bool:
    q = re.sub(r"\bngat quang\b", "", asserted_conditions(message))
    return any(re.search(r"\b" + re.escape(term) + r"\b", q) for term in EMERGENCY_SYMPTOMS)


def emergency_answer(message: str) -> str:
    if has_emergency_symptoms(message):
        return (
            "Nếu tình trạng này đang xảy ra, hãy gọi cấp cứu 115 ngay và nhờ người ở gần hỗ trợ. "
            "Không cho người bất tỉnh hoặc không nuốt được ăn hay uống. "
            "Chatbot không thể đánh giá hoặc hướng dẫn điều trị cấp cứu từ xa."
        )
    return (
        "Số đo đường huyết bạn nêu đang thấp và cần được hỗ trợ ngay. "
        "Hãy nhờ người ở gần hỗ trợ và liên hệ nhân viên y tế ngay để được hướng dẫn; không tự đổi thuốc. "
        "Nếu có bất tỉnh, co giật, lú lẫn, khó thở hoặc không nuốt được, hãy gọi cấp cứu 115 ngay. "
        "Chatbot không thể đánh giá mức độ nguy hiểm hoặc hướng dẫn điều trị từ xa."
    )


def is_diagnosis_request(message: str) -> bool:
    q = fold(message)
    return bool(re.search(
        r"\b(?:toi|minh|em|bo|me)\b.*\b(?:da bi|co bi|co mac)\b"
        r".*\b(?:tieu duong|dai thao duong)\b\s*(?:hay\s+)?(?:chua|khong)\b"
        r"|\b(?:chan doan|ket luan)\b.*\b(?:toi|minh|benh|xet nghiem)\b", q,
    ) and re.search(r"\b(?:duong huyet|glucose|hba1c|xet nghiem|tieu duong|dai thao duong)\b", q))


def is_intake_advice(message: str) -> bool:
    """Recommended intake/suitability is not a food composition lookup."""
    q = re.sub(r'\bko\b', 'khong', fold(message))
    return bool(
        is_elliptical_intake_followup(message)
        or re.search(r'\b(?:an|uong)\s+bao nhieu\b', q)
        or re.search(r'\b(?:nen|can)\s+(?:an|uong)\b.*\b(?:may|bao nhieu)\s+(?:to|bat|phan|ly|coc)\b', q)
        or
        re.search(r'\b(?:phu hop|thich hop|an toan|nen chon)\b', q)
        or
        re.search(r'\b(?:nen|can|duoc phep)\s+(?:an|uong|dung|nap|tieu thu)\b', q)
        or re.search(r'\b(?:an|uong|nap|tieu thu)\b.*\b(?:duoc khong|co duoc|co on|thoai mai|khong gioi han)\b', q)
        or re.search(r'\b(?:an|uong|nap|tieu thu)\b.*\bbao nhieu\b.*\b(?:moi|mot|hang)\s+(?:ngay|bua)\b', q)
        or re.search(r'\b(?:moi|mot|hang)\s+(?:ngay|bua)\b.*\b(?:an|uong|nap|tieu thu)\b.*\bbao nhieu\b', q)
    )


def is_elliptical_intake_followup(message: str) -> bool:
    """A subject-free intake question refers to the previous user topic."""
    q = fold(message).strip(' ?!.,')
    return bool(re.fullmatch(
        r'(?:(?:vay|the|toi|minh)\s+)*(?:(?:nen|can|phai)\s+)?'
        r'(?:(?:an|uong)\s+(?:nhu the nao|the nao|ra sao)|'
        r'(?:(?:an|uong)\s+)?(?:bao nhieu|may\s+(?:to|bat|phan|ly|coc))'
        r'(?:\s+(?:thi|la)\s+(?:on|vua|du|hop ly|phu hop|duoc|tot))?)', q,
    ))


def is_intake_quantity_request(message: str) -> bool:
    q = fold(message)
    return bool(re.search(r'\b(?:an|uong)\b.*\b(?:bao nhieu|may\s+(?:to|bat|phan|ly|coc))\b', q)
                or is_elliptical_intake_followup(message) and re.search(r'\b(?:bao nhieu|may)\b', q))


def current_low_glucose(message: str) -> bool:
    """Route a present personal low-glucose report to the existing urgent boundary.

    CDC: <70 mg/dL is low, <55 mg/dL severely low. NIDDK lists
    shaking/sweating as symptoms requiring prompt action. This only routes;
    it does not calculate treatment or medication doses.
    """
    q = fold(message)
    if not re.search(r'\b(?:duong huyet|duong mau|glucose)\b', q):
        return False
    if re.search(r'\b(?:theo tai lieu|gia su|vi du|ly thuyet|dinh nghia|co nghia la|nguong)\b', q):
        return False
    current = bool(re.search(r'\b(?:dang|bay gio|hien tai|luc nay|vua do)\b', q))
    historical = bool(re.search(r'\b(?:hom qua|truoc day|lan truoc|da tung)\b', q))
    if historical and not current:
        return False
    if historical and re.search(r'\b(?:hien|gio|nay)\s+(?:da\s+)?(?:on|het|binh thuong)\b', q):
        return False
    if not current and not re.search(r'\b(?:toi|minh)\b', q):
        return False
    for value, unit in re.findall(r'(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(mmol\s*/\s*l|mg\s*/\s*dl)\b', q):
        glucose = float(value.replace(',', '.'))
        mg_dl = glucose * 18 if unit.startswith('mmol') else glucose
        if 0 < mg_dl < 70:
            return True
    return False


def outside_nutrition_scope(message: str) -> bool:
    """Catch explicit finance requests without rejecting nutrition context."""
    q = fold(message)
    return bool(re.search(r'\b(?:co phieu|chung khoan|bitcoin|tien ao|crypto|forex|code|lap trinh|python|javascript)\b', q)
                and not re.search(r'\b(?:an|uong|dinh duong|duong huyet|tieu duong|dai thao duong)\b', q))


def classify(message: str) -> Intent:
    q = asserted_conditions(message)
    medication_q = re.sub(r"\b(?:(?:hut|bo|ngung|dung)\s+)?thuoc la\b", "", q)
    if current_low_glucose(message) or has_emergency_symptoms(message):
        return "emergency"
    if any(
        term in medication_q for term in ("insulin", "metformin", "thuoc", "glimepiride", "gliclazide")
    ) and (any(
        re.search(r"\b" + re.escape(term) + r"\b", medication_q)
        for term in (
            "doi lieu",
            "lieu dung",
            "lieu insulin",
            "lieu thuoc",
            "tang lieu",
            "giam lieu",
            "ngung",
            "ke don",
            "thuoc gi",
            "dung thuoc nao",
            "uong thuoc nao",
            "nen tiem",
            "tiem truoc",
            "tiem sau",
            "uong truoc",
            "uong sau",
            "bao nhieu don vi",
            "may don vi",
            "bao nhieu vien",
            "tinh insulin",
            "bo thuoc",
            "uong them",
            "tiem them",
            "chich them",
            "dung them",
            "bot lieu",
            "bot thuoc",
            "bo lieu",
            "doi thuoc",
        )
    ) or re.search(r"\bliều\b|dừng\s+(?:thuốc|insulin)", message.lower())
       or re.search(r'\b(?:tiem|chich|uong|dung)\b.*\b\d+(?:[.,]\d+)?\s*(?:don vi|vien|mg)\b.*\b(?:duoc khong|may lan|bao nhieu lan|nen|truoc|sau)\b', medication_q)):
        return "medication"
    if any(re.search(r"\b" + re.escape(term) + r"\b", q) for term in SPECIAL_CONDITIONS) or re.search(r"\b([1-9]|1[0-7])\s*tuoi\b", q):
        return "special_population"
    source_example = any(term in q for term in ("thuc don tham khao", "thuc don mau", "bang cua vien", "bang thuc don")) and not any(term in q for term in ("tao thuc don", "lap thuc don", "doi mon", "thay mon"))
    if not source_example and any(
        term in q
        for term in (
            "lap thuc don",
            "tao thuc don",
            "sinh thuc don",
            "doi mon",
            "thay mon",
            "goi y thuc don",
            "len thuc don",
            "menu cho",
            "thuc don cho",
            "thuc don 7",
        )
    ):
        return "menu_request"
    if is_intake_advice(message):
        return "knowledge"
    food_context = re.search(
        r"\b(sua|gao|com|pho|bun|chuoi|tao|cam|trung|thit|ca|dau phu|mon an|thuc pham|bua trua|bua sang|bua toi|thuc don)\b",
        q,
    )
    if not source_example and any(
        term in q
        for term in (
            "kcal",
            "calo",
            "carbohydrate",
            "protein",
            "natri",
            "chat beo",
            "dinh duong",
            "carb",
            "chat xo",
            "dam",
        )
    ) and (
        re.search(r"\b\d+\s*(g|gram|ml)\b", q)
        or (
            food_context
            and any(term in q for term in ("bao nhieu", "tong", "ham luong", "tra cuu"))
        )
    ):
        return "food_lookup"
    if q.strip(" !?.") in {"chao", "xin chao", "hello", "hi", "cam on", "ban la ai", "alo", "ok", "oke", "tam biet", "bye", "thanks", "thank you", "cam on ban", "chao ban", "ban giup duoc gi", "ban lam duoc gi", "ban co the lam gi", "ban ten gi", "hey", "xin chao ban", "cam on nhe", "uh", "vang", "duoc roi"}:
        return "greeting"
    return "knowledge"


def static_answer(intent: Intent) -> str:
    return {
        "emergency": "Nếu đây là tình trạng đang xảy ra, hãy gọi cấp cứu 115 hoặc đến cơ sở cấp cứu ngay và nhờ người ở gần hỗ trợ. Chatbot không thể đánh giá hay hướng dẫn điều trị cấp cứu từ xa.",
        "medication": "Mình không kê thuốc hoặc hướng dẫn tăng, giảm, ngừng liều thuốc/insulin. Bạn cần trao đổi với bác sĩ điều trị. Mình có thể giúp tra cứu kiến thức dinh dưỡng chung từ tài liệu.",
        "special_population": "Trường hợp bạn nêu cần hướng dẫn chuyên biệt. Mình chỉ hỗ trợ giáo dục dinh dưỡng cho người trưởng thành mắc đái tháo đường type 2, chưa hỗ trợ khẩu phần cho trẻ em, thai kỳ, type 1 hoặc suy thận/lọc máu. Hãy hỏi bác sĩ hoặc chuyên gia dinh dưỡng.",
        "menu_request": "Tính năng tạo và thay đổi thực đơn chưa được kết nối, nên mình chưa thể lập thực đơn cho bạn. Bạn vẫn có thể hỏi về nguyên tắc lựa chọn thực phẩm hoặc tra thành phần dinh dưỡng.",
        "food_lookup": "Mình có thể tra thành phần thực phẩm và món ăn trong dữ liệu đã nạp. Cần chọn đúng loại, trạng thái và đơn vị; khi nguồn chưa xác định cơ sở khẩu phần hoặc thiếu quy đổi, mình không đoán số liệu theo lượng bạn hỏi.",
        "greeting": "Chào bạn! Mình giúp tra cứu kiến thức dinh dưỡng cho người trưởng thành mắc đái tháo đường type 2, kèm nguồn tài liệu. Bạn có thể hỏi về trái cây, chất xơ, chất béo hoặc cách phân bố bữa ăn.",
    }.get(
        intent,
        "Mình chưa tìm thấy đủ bằng chứng trong tài liệu đã duyệt để trả lời câu hỏi này. Bạn có thể hỏi rõ hơn hoặc bổ sung nguồn chuyên môn phù hợp.",
    )


def social_answer(message: str) -> str:
    q = fold(message).strip(" !?.")
    if q in {"cam on", "cam on ban", "cam on nhe", "thanks", "thank you"}:
        return "Rất vui được giúp bạn. Khi cần, bạn cứ hỏi thêm về dinh dưỡng và mình sẽ tìm nguồn để đối chiếu."
    if q in {"tam biet", "bye"}:
        return "Tạm biệt bạn! Khi cần tìm hiểu thêm về dinh dưỡng, bạn có thể quay lại cuộc trò chuyện."
    if q.startswith("ban "):
        return "Mình là NutriGuide, trợ lý tra cứu tài liệu dinh dưỡng cho người trưởng thành mắc đái tháo đường típ 2, trả lời kèm nguồn. Mình có thể tra thành phần thực phẩm và món ăn trong dữ liệu đã nạp; nếu nguồn thiếu cơ sở khẩu phần hoặc quy đổi đơn vị, mình sẽ nói rõ giới hạn. Hiện mình chưa hỗ trợ sinh/đổi thực đơn."
    if q in {"ok", "oke", "vang", "uh", "duoc roi"}:
        return "Mình sẵn sàng giúp bạn tra cứu tiếp. Bạn muốn tìm hiểu nội dung dinh dưỡng nào thì cứ nói rõ nhé."
    return static_answer("greeting")
