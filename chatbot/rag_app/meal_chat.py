"""Plain-language meal questions backed by authenticated structured data."""
import re
import time
from collections import Counter
from dataclasses import dataclass

from rag_app.conversation import is_contextual_followup, is_rephrase_request, starts_new_topic
from rag_app.food_data import FoodItem, FoodPlan, get_catalog
from rag_app.meal_gateway import MealServiceError
from rag_app.meal_models import MealContext, Nutrients, SwapRequest, sum_nutrients
from rag_app.meal_requests import (
    NUTRIENTS,
    decimal,
    missing_nutrients,
    nutrient_fields,
    parse_meal_change,
    plain_name,
    swap_reference,
)
from rag_app.retrieval import fold
from rag_app.routing import culinary_request, label_reading_request

LABELS = {"BREAKFAST": "Bữa sáng", "LUNCH": "Bữa trưa", "DINNER": "Bữa tối", "SNACK": "Bữa phụ"}
UNITS = {"g": "g", "ml": "ml", "serving": "suất"}
ALL_DAY = r"\b(?:ca ngay|toan ngay|tron ngay|tong (?:calo|kcal|nang luong)?\s*(?:hom nay|trong ngay))\b"
KEEP = r"\b(?:dung (?:doi|thay)|khong (?:can |muon )?(?:doi|thay)|giu nguyen|(?:huy|bo) (?:phuong an|de xuat|xem truoc))\b"
NEW_EXCLUSION = r"\b(?:minh|toi|vua|moi)\b.*\b(?:bi di ung|di ung voi|di ung (?!gi\b|khong\b)|can tranh|khong the an)"
PROTECT_EXCLUSIONS = r"\bbo qua\b.*\b(?:di ung|gioi han|dieu kien)\b"
CHANGE = r"\b(?:doi|thay|chuyen sang|giam|tang|bot luong|chinh|dieu chinh|an it hon|an nhieu hon)\b"
ALTERNATIVE = r"\b(?:mon nao khac|mon (?:nao )?thay the|(?:doi|thay).*\bmon (?:de )?mang (?:di|theo))\b"
DISLIKE = r"\b(?:khong (?:muon |thich )?(?:an|dung)|khong thich)\b"


def mentioned_meals(message):
    text = fold(message)
    patterns = {"BREAKFAST": r"\bbua sang\b|\bbuoi sang\b|\bsang nay\b|\bmon sang\b",
                "LUNCH": r"\btrua\b", "DINNER": r"\bbua toi\b|\bbuoi toi\b|\btoi nay\b|\bmon toi\b",
                "SNACK": r"\bbua (?:phu|xe)\b|\ban xe\b"}
    matches = {key: match.start() for key, pattern in patterns.items() if (match := re.search(pattern, text))}
    # Preserve accents to distinguish evening (tối) from I (tôi).
    for key, word in [("BREAKFAST", "sáng"), ("DINNER", "tối")]:
        if key not in matches and (match := re.search(rf"\b{word}\b", message, re.I)):
            matches[key] = len(fold(message[:match.start()]))
    return sorted(matches, key=matches.get)


def saved_day_nutrition(message):
    text = fold(message)
    return bool(re.search(ALL_DAY, text) and nutrient_fields(text)
                and not re.search(r"\b(?:nen|can|nhu cau|nap|tieu thu)\b", text))


def meal_action(message, context=None, explicit=None):
    text = fold(message)
    meals, menu = mentioned_meals(message), "thuc don" in text
    if not explicit and starts_new_topic(message) and (not menu or "hoi ngoai thuc don" in text):
        return None
    stored_reference = menu or re.search(
        r"\b(?:mon (?:nay|do)|phan (?:nay|do)|dang (?:luu|xem)|"
        r"demo:[\w.-]+|(?:doi|thay) (?:mon|bua))\b", text
    )
    if re.search(PROTECT_EXCLUSIONS, text):
        return "protect_exclusions"
    if (context or menu or meals or explicit) and re.search(NEW_EXCLUSION, text) and (
        explicit or stored_reference or not culinary_request(message)
    ):
        return "new_exclusion"
    if (context or menu or meals or explicit) and re.search(KEEP, text):
        return "keep"
    if explicit:
        return explicit
    if (not stored_reference and re.search(r"\b(?:tinh|cong) (?:ca )?vao\b", text)
            and re.search(r"\b(?:khau phan|ca ngay|tong nang luong)\b", text)):
        return None
    if re.search(r"\b(?:theo|huong dan cua|khuyen nghi cua) (?:bo y te|qd|quyet dinh|vien dinh duong|niddk|ada|cdc)\b", text):
        return None
    if re.search(r"\b(?:la gi|co vai tro|tac dung|loi ich|khai niem|nguyen tac|khuyen cao|theo tai lieu|dan nguon)\b", text):
        return None
    # The visible plan provides a default target for plan questions. It does
    # not turn shopping, cooking, or ordering ideas into plan operations.
    if not stored_reference and (
        culinary_request(message) or label_reading_request(message) or is_rephrase_request(message)
        or re.search(r"\b(?:an (?:nhe|lot da) (?:mon )?gi|"
                     r"goi y (?:mon|bua)|(?:goi|dat) (?:mon|to) .*\bgi)\b", text)
    ):
        return None
    # A question about changing an eating habit does not edit a stored plan.
    # Explicit actions above and queries that name the stored menu retain their
    # structured path, including when a meal context is already open.
    if (not menu and meals and re.search(
            r'\b(?:co on|on khong|duoc khong|dc ko|co the|co phai|bat buoc|nen|co can)\b', text)
            and re.search(r'\b(?:an|uong|bo bua|doi|thay|doi bung|hay doi)\b', text)
            and not re.search(r'\b(?:dang xem|mon nay|mon do|trong (?:bua|ke hoach)|doi giup|thay giup|doi mon|thay mon|doi bua)\b', text)):
        return None
    if (context or stored_reference or meals) and re.search(DISLIKE, text):
        return "swap"
    personal = re.search(r'\b(?:cua (?:toi|minh|em)|hom nay|sang nay|trua nay|toi nay|dang xem)\b', text)
    operation = re.search(r'\b(?:doi|thay|tao|sinh|lap|len|them|bo|xem|giam|tang)\b', text)
    fields, unknown = nutrient_fields(text), missing_nutrients(message)
    stored_lookup = meals and (fields or unknown or re.search(r'\b(?:co bao nhieu|may gam|co gi|co mon gi|an gi|gom nhung mon|gom mon gi)\b', text)) and not re.search(r'\b(?:nen|can)\b', text)
    fixture_ref = re.search(r"\bdemo:[\w.-]+\b|\bmon [a-d][0-9]*\b", text)
    direct_change = re.search(r"\b(?:doi|thay) (?:mon|bua)\b", text)
    nutrient_choice = re.search(r"\b(?:muon|lua chon|phuong an)\b", text) and re.search(r"\bhon\b", text) and bool(fields)
    menu_lookup = menu and (fields or unknown or re.search(r"\b(?:co|cua|hien tai|nay)\b", text))
    if not (context or (menu or meals) and (personal or operation or nutrient_choice) or menu_lookup or stored_lookup or fixture_ref or direct_change or saved_day_nutrition(message) or personal and "muc tieu" in text):
        return None
    for action, pattern in [
        ("change_status", r"\b(?:da (?:doi|luu|ap dung)|luu chua|doi chua|ap dung chua|chi la xem truoc|dang cho ap dung)\b"),
        ("accept", r"\b(?:ap dung|luu|chot)(?: (?:phuong an(?: nay| do)?|di|nhe|giup minh|luon|cai nay|cai do))?[.!?\s]*$"),
        ("capabilities", r"\b(?:lam (?:duoc )?gi|lam duoc nhung gi|chuc nang|kha nang)\b"),
        ("structure", r"\b(?:them|bo|bot)\s+(?:(?:cho|toi|minh|mot|hai)\s+)*bua\b"),
        ("profile", r"\bho so\b"),
        ("summary", r"\b(?:tom tat|hai cau|2 cau)\b"),
        ("rephrase", r"\b(?:de hieu hon|noi ngan|noi don gian|khong hieu.*chuyen mon)\b"),
        ("missing_value", r"\b(?:khong ghi|thieu|chua co)\b.*\b(?:0|bang khong)\b"),
        ("source", r"\b(?:tu dau|lay.*nguon|nguon so|can cu)\b"),
        ("basis", r"\b(?:can song|song hay chin|can chin|truoc nau|sau nau)\b"),
    ]:
        if re.search(pattern, text):
            return action
    if menu and re.search(
        r"\b(?:tao|sinh|lap|len)(?: (?:giup|cho|minh|toi|mot|moi|1))* thuc don\b", text
    ) and not re.search(r"\b(?:vi sao|tai sao|cach|ai)\b", text):
        return "generate"
    if (nutrient_choice or menu and re.search(ALTERNATIVE, text)
        or re.search(CHANGE, text) and not re.search(r"\b(?:da|co bi|vi sao|tai sao) (?:giam|tang|doi|thay)\b", text)):
        return "swap"
    if re.search(r"\b(?:bua|mon) nao\b", text) and re.search(r"\bnhat\b", text):
        return "rank"
    if len(meals) >= 2 and re.search(r"\b(?:hon|so sanh|chenh|hay)\b", text):
        return "compare"
    if "muc tieu" in text:
        return "targets"
    if re.search(r"\b(?:vi sao|tai sao|sao lai|phu hop|hop ly|co hop)\b", text):
        return "explain"
    if re.search(r"\b(?:suat|phan|luong an)\b.*\b(?:gram|gam|bao nhieu g)\b|\b(?:bao nhieu|may) (?:gram|gam|suat|ml|g)\b", text) and not fields and not unknown:
        return "portion"
    if re.search(r"\b(?:nguyen lieu|thanh phan|chua gi)\b", text) and not fields and not unknown:
        return "ingredients"
    if fields or unknown or re.search(r"\b(?:bao nhieu|may gam|tong|dinh duong)\b", text):
        return "nutrition"
    if menu or fixture_ref or meals and re.search(r"\b(?:mon|gom|gi|con|xem|nay|thi sao|co)\b", text) or re.search(r"\b(?:xem|hien|mon nay|mon do)\b", text):
        return "show"
    return None


@dataclass
class MealReply:
    answer: str
    payload: dict | None = None
    question: str | None = None
    status: str = "answered"
    cancel_pending: bool = False
    profile_recheck_version: int | None = None


def number(value):
    return f"{value:.8f}".rstrip("0").rstrip(".").replace(".", ",")


def portion(item):
    return f"{number(item.amount)} {UNITS[item.unit]}"


def referenced_items(plan, text):
    catalog = get_catalog() if plan.catalog_version == "named-demo-v1" else None
    matches = []
    name_starts = Counter(plain_name(item).partition(' ')[0] for item in plan.items) if catalog else {}
    for item in plan.items:
        # Bare integer database IDs must not match quantities such as '1 suất'.
        names = {plain_name(item), *[fold(value) for value in (item.recipe_id, item.id) if not value.isdecimal()]}
        if catalog:
            names.update(fold(alias) for alias in catalog.get(item.recipe_id).get("aliases", []))
            head = plain_name(item).partition(' ')[0]
            if name_starts[head] > 1:
                names.add(head)
        for name in filter(None, names):
            matches.extend((match.start(), match.end(), item.id) for match in re.finditer(
                r"(?<![\w:-])" + re.escape(name) + r"(?![\w:-])", text
            ))
    # A complete phrase wins over a shorter alias inside it. A short reference
    # shared by two current items stays ambiguous until the meal is selected.
    kept = {item_id for start, end, item_id in matches if not any(
        other_start <= start <= end <= other_end and other_end - other_start > end - start
        for other_start, other_end, _ in matches
    )}
    return [item for item in plan.items if item.id in kept]


def pending_meal(history, plan):
    for turn in reversed(history or []):
        response = turn.get("response", {})
        result = response.get("meal_result") or {}
        pending = response.get("meal_pending") or result.get("proposal") or result.get("pending")
        if pending and pending.get("planId", plan.id) == plan.id:
            return pending
        if response.get("meal_edit_cancelled"):
            break
    return None


def named_portion_reply(item, change, payload):
    amount = change.requested_amount(item)
    if (item.unit != "g" or amount is None or not 0 < amount <= 100000 or change.dish or change.exclusion
            or change.unknown or change.numeric_nutrient or item.nutrients.energy_kcal is None
            or change.amount_direction and change.amount_direction * (amount - decimal(item.amount)) <= 0):
        return None
    result = get_catalog().execute(FoodPlan(operation="lookup", items=[
        FoodItem(name=item.recipe_id, amount=float(amount), unit="g")]))
    if result["unresolved"] or len(result["items"]) != 1:
        return None
    record = result["items"][0]
    if record["id"] != item.recipe_id or record.get("review_status") != "verified" or not record["calculation_available"]:
        return None
    energy = next((n["amount_value"] for n in record["nutrients"] if n["key"] == "energy" and n["unit"].lower() == "kcal"), None)
    if energy is None:
        return None
    payload["view"] = "portion"
    payload["nutrientKeys"] = ["energy_kcal"]
    return MealReply(
        f"Nếu dùng {number(amount)} g {item.name.lower()} thì phần đó có khoảng {number(energy)} kcal. "
        f"Phần {portion(item)} đang hiển thị có {number(item.nutrients.energy_kcal)} kcal. Mình chỉ tính để bạn tham khảo, chưa sửa thực đơn.",
        payload, cancel_pending=True,
    )


def error_reply(error, *, mock=False, payload=None):
    answers = {
        "NO_FEASIBLE_PLAN": "Mình chưa có món thay phù hợp cho phần bạn chọn. Thực đơn đang lưu vẫn giữ nguyên nhé." if not mock else "Bộ thực đơn mẫu chưa có phương án thay phù hợp cho món này. Mình giữ nguyên thực đơn đang lưu nhé.",
        "REQUEST_MISMATCH": "Phương án trả về chưa đáp ứng yêu cầu bạn vừa nêu, nên mình chưa đưa ra để áp dụng. Thực đơn đang lưu vẫn giữ nguyên.",
        "PROFILE_INCOMPLETE": "Mình chưa đủ thông tin để đổi món. Bạn hãy mở hồ sơ, xác nhận dị ứng và những thực phẩm cần tránh rồi thử lại nhé; chưa khai báo không có nghĩa là không dị ứng.",
        "NOT_FOUND": "Mình không mở được thực đơn hoặc phương án này. Bạn hãy chọn lại thực đơn thuộc tài khoản của mình nhé.",
        "AUTH_REQUIRED": "Bạn cần đăng nhập để mình đọc thực đơn của đúng tài khoản nhé.",
        "DATA_INCOMPLETE": "Phương án này chưa đủ dữ liệu để kiểm tra, nên mình chưa áp dụng. Thực đơn đang lưu vẫn giữ nguyên nhé.",
        "STALE_PLAN": "Thực đơn hoặc hồ sơ đã thay đổi. Bạn hãy tải lại bản mới rồi chọn món muốn đổi nhé; mình chưa áp dụng thay đổi nào.",
        "SERVICE_UNAVAILABLE": "Mình chưa kết nối được dịch vụ thực đơn lúc này. Bạn thử lại sau nhé; mình chưa áp dụng thay đổi nào.",
    }
    return MealReply(answers.get(error.code, error.message), payload, status="needs_clarification")


def mixed_scope_nutrition(message, plan):
    parts = re.split(r"[,;]|\bvà\s+(?=(?:bữa|cả ngày|toàn ngày)\b)", message, flags=re.I)
    if len(parts) < 2:
        return None
    scopes = []
    for part in parts:
        text = fold(part)
        fields, meals = nutrient_fields(text), mentioned_meals(part)
        if not fields or not (re.search(ALL_DAY, text) or meals):
            return None
        scopes.append(([] if re.search(ALL_DAY, text) else meals, fields))
    if len({tuple(meals) for meals, _ in scopes}) < 2:
        return None
    lines, keys, ids = [], [], []
    for meals, fields in scopes:
        items = [item for item in plan.items if item.meal_type in meals]
        ids.extend(item.id for item in items)
        keys.extend(fields)
        if meals and not items:
            lines.append("Thực đơn chưa có " + " và ".join(LABELS[meal].lower() for meal in meals) + ".")
            continue
        totals = sum_nutrients(items) if meals else plan.totals
        subject = " và ".join(LABELS[meal] for meal in meals) if meals else "Cả ngày"
        values, unknown = [], []
        for key in fields:
            label, unit, _ = NUTRIENTS[key]
            value = getattr(totals, key)
            if value is None:
                unknown.append(label.lower())
            else:
                values.append(f"{number(value)} {unit}" + (f" {label.lower()}" if key != "energy_kcal" else ""))
        clauses = (["có " + " và ".join(values)] if values else []) + (["chưa có số liệu " + " và ".join(unknown)] if unknown else [])
        lines.append(subject + " " + ", ".join(clauses) + ".")
    return " ".join(lines), list(dict.fromkeys(keys)), list(dict.fromkeys(ids))


def handle_meal_chat(gateway, owner, message, context=None, action=None, authorization=None, *, history=None, blocked_profile_version=None):
    if not action and re.search(r'\b(?:xu ly nhung viec|ban co the lam gi|chuc nang|kha nang)\b', fold(message)):
        common = 'Mình có thể giải thích dinh dưỡng phổ thông, giúp chọn món theo nguyên tắc có nguồn và tra thành phần thực phẩm. '
        if gateway.mode == 'disabled':
            detail = 'Tạo, thay đổi và lưu thực đơn hiện chưa được kết nối. Lưu lịch sử chat là một chức năng riêng, không phải lưu thực đơn.'
        elif gateway.mode == 'mock':
            detail = ('Phần thực đơn đang dùng món mẫu có tên và lượng ăn cụ thể: bạn có thể xem các bữa, hỏi số dinh dưỡng và nguồn số liệu, hoặc cập nhật hồ sơ mẫu. Thực đơn này chưa cá nhân hóa và chưa hỗ trợ đổi món.'
                      if getattr(gateway, 'named_demo', False) else
                      'Phần thực đơn đang dùng dữ liệu mẫu: bạn có thể xem số liệu, xem trước đổi món và áp dụng thay đổi trên bản mẫu. Tạo thực đơn mới chưa được kết nối; thay đổi bản mẫu không phải lưu thực đơn cá nhân thật.')
        else:
            detail = 'Thực đơn được đọc từ dịch vụ kết nối. Bạn có thể hỏi về thực đơn đã lưu và yêu cầu đổi món qua bảng xem trước trong hội thoại. Tạo thực đơn mới chưa được kết nối qua chat; bạn dùng nút Tạo thực đơn ở trang Thực đơn. Mình chỉ báo đã lưu sau khi dịch vụ xác nhận.'
        return MealReply(common + detail)
    task = meal_action(message, context, action)
    last = history[-1].get("response", {}) if history else {}
    last_result = last.get("meal_result") or {}
    previous_choices = last.get("meal_choices") or last_result.get("choices") or []
    explicit_choice = bool(context and action and any(
        choice['itemId'] == context.item_id and choice['action'] == action for choice in previous_choices
    ))
    affirm_single = bool(len(previous_choices) == 1 and not action and re.fullmatch(
        r'(?:dung(?: roi| vay)?|dong y|ok|oke|phai|chinh xac)[.!?\s]*', fold(message)))
    continuation = explicit_choice or affirm_single or bool(previous_choices and not action and re.fullmatch(
        r"(?:minh |toi )?(?:(?:chon|doi|thay) )?(?:(?:bua )?(?:sang|trua|toi|phu)|mon [a-z0-9-]+|(?:mon |lua chon )?(?:so )?\d+)(?: (?:di|nhe|nha|giup minh))?[.!?\s]*",
        fold(message),
    ))
    if continuation:
        task = previous_choices[0]["action"]
    if task is None:
        return None
    # The web client can keep a plan selected while the user discusses a
    # recipe. A passive plan selection cannot resolve a referent from that talk.
    if (not action and task in {"show", "nutrition", "ingredients", "portion", "source", "basis", "summary", "rephrase", "explain"}
            and history and not (last.get("meal_context") or last_result.get("context"))
            and is_contextual_followup(message, history) and meal_action(message) is None):
        return None
    if task in {"generate", "structure"}:
        if gateway.mode == 'http':
            return MealReply('Bạn tạo thực đơn mới ở trang Thực đơn bằng nút Tạo thực đơn. Trong chat, mình giúp đọc bữa ăn, số dinh dưỡng và mở bảng đổi từng món/khẩu phần để bạn kiểm tra rồi xác nhận. Hiện chưa hỗ trợ thêm hoặc bỏ cả bữa qua chat; mình chưa thay đổi thực đơn của bạn.', status='integration_required')
        answer = ("Phần tạo thực đơn mới hoặc thêm/bớt bữa chưa được kết nối, nên mình chưa lập hoặc lưu thực đơn cho bạn. Bạn vẫn có thể hỏi nguyên tắc chọn món hoặc tra thành phần thực phẩm."
                  if gateway.mode == 'disabled' else
                  "Hiện mình giúp xem và đề xuất đổi món trong thực đơn đã có. Phần tạo thực đơn mới hoặc thêm/bớt bữa chưa được kết nối, nên mình chưa thay đổi thực đơn của bạn nhé.")
        return MealReply(answer, status="integration_required")
    if gateway.mode == "disabled":
        return MealReply("Mình chưa đọc được thực đơn cá nhân vì phần này chưa được kết nối. Bạn vẫn có thể hỏi kiến thức dinh dưỡng hoặc tra từng thực phẩm nhé.", status="integration_required")
    if task == "protect_exclusions":
        return MealReply("Mình cần giữ các điều kiện dị ứng khi đổi món để tránh đề xuất không phù hợp. Mình chưa thay đổi thực đơn nhé.", status="safety")
    context = context or MealContext()
    try:
        snapshot = gateway.snapshot(owner, authorization, context.plan_id)
    except MealServiceError as error:
        return error_reply(error, mock=gateway.mode == "mock")
    profile, plan = snapshot.profile, snapshot.plan
    team_payload = {'dataMode': snapshot.data_mode, 'plan': plan.model_dump(mode='json'),
                    'view': task, 'context': {'plan_id': plan.id, 'plan_version': plan.version},
                    'choices': [], 'proposal': None}
    if plan.catalog_version == 'java-catalog-unversioned' and task in {'explain', 'targets'} and 'energy_kcal' not in plan.target.bounds:
        target = plan.target.point_targets.get('energy_kcal')
        actual = plan.totals.energy_kcal
        return MealReply(
            (f'Thực đơn đang lưu có {number(actual)} kcal. ' if actual is not None else '')
            + (f'Mục tiêu backend ghi nhận là {number(target)} kcal. ' if target is not None else '')
            + 'Backend chưa cung cấp khoảng mục tiêu và kết quả kiểm tra đầy đủ, nên mình chưa thể kết luận thực đơn đã đáp ứng mọi ràng buộc cá nhân.', team_payload)
    if task == "new_exclusion":
        return MealReply("Mình đã hiểu bạn vừa nêu thêm dị ứng, nhưng chưa cập nhật thông tin đó vào hồ sơ. Bạn hãy bổ sung dị ứng trong hồ sơ trước khi đổi món nhé; mình dừng phương án xem trước trong cuộc trò chuyện này và chưa áp dụng thay đổi nào.", status="needs_clarification", cancel_pending=True, profile_recheck_version=profile.profile_version)
    if task == "swap" and blocked_profile_version is not None and profile.profile_version <= blocked_profile_version:
        return MealReply("Bạn vừa báo thêm dị ứng, nhưng hồ sơ chưa có bản cập nhật. Mình tạm dừng đổi món; bạn hãy cập nhật dị ứng trong hồ sơ rồi thử lại nhé.", status="needs_clarification")
    if profile.scope_status == "out_of_scope" or profile.age is not None and profile.age < 18:
        return MealReply("Trường hợp của bạn cần hướng dẫn dinh dưỡng riêng từ bác sĩ hoặc chuyên gia. Mình chưa hỗ trợ đổi thực đơn cho hồ sơ này nhé.", status="safety")
    payload = {"dataMode": snapshot.data_mode, "plan": plan.model_dump(mode="json"), "view": task,
               "selectedItemIds": [], "context": {"plan_id": plan.id, "plan_version": plan.version}, "choices": [], "proposal": None,
               "notice": "Đây là dữ liệu mẫu để thử ứng dụng, chưa phải khẩu phần được xác minh cho người dùng thật." if snapshot.data_mode == "mock" else "Số liệu theo thực đơn đang lưu trong tài khoản."}
    stale = context.plan_version is not None and context.plan_version != plan.version or profile.profile_version != plan.profile_version
    if stale and task in {"swap", "ingredients", "source", "basis", "portion"}:
        return MealReply(f"Bản bạn đang xem đã cũ. Thực đơn hiện tại là phiên bản {plan.version}; bạn kiểm tra bản này rồi chọn món muốn đổi nhé. Mình chưa áp dụng thay đổi nào.", payload, status="needs_clarification")
    text, meals = fold(message), mentioned_meals(message)
    previous_context = last.get('meal_context') or last_result.get('context') or {}
    previous_meal = previous_context.get('meal_type') if previous_context.get('plan_id') == plan.id else None
    if not meals and re.search(r'\bbua (?:do|nay|ay)\b', text):
        prior_item = next((item for item in plan.items if item.id == previous_context.get('item_id')), None)
        previous_meal = previous_meal or (prior_item.meal_type if prior_item else context.meal_type)
        if previous_meal in LABELS:
            meals = [previous_meal]
    whole_day = bool(re.search(ALL_DAY, text))
    swap_message = (last.get("meal_choice_instruction") or last_result.get("choiceInstruction") or history[-1]["question"]) if continuation else message
    change = parse_meal_change(swap_message) if task == "swap" else None
    reference = swap_reference(swap_message) if task == 'swap' else None
    by_id = {item.id: item for item in plan.items}
    if context.item_id and context.item_id not in by_id:
        return error_reply(MealServiceError("NOT_FOUND"))
    match_text = text
    if change and change.dish and not continuation and change.dish in text:
        match_text = text[:text.rindex(change.dish)]
    named = referenced_items(plan, match_text)
    if reference and reference.source and not continuation:
        source_matches = [item for item in plan.items if re.search(
            r'(?<!\w)' + re.escape(reference.source) + r'(?!\w)', plain_name(item))]
        scoped = [item for item in source_matches if not meals or item.meal_type in meals]
        if reference.ambiguous_connector:
            # Do not let a likely 'sang' typo redirect a named lunch dish to
            # whichever unrelated recipe happens to occupy breakfast.
            scoped = source_matches
            if previous_meal:
                prior = [item for item in scoped if item.meal_type == previous_meal]
                scoped = prior or scoped
        elif not meals and previous_meal and len(scoped) > 1:
            prior = [item for item in scoped if item.meal_type == previous_meal]
            scoped = prior or scoped
        if reference.ambiguous_connector or len(scoped) != 1:
            choices = scoped or source_matches or [item for item in plan.items if not meals or item.meal_type in meals]
            payload['choices'] = [{'itemId': item.id, 'label': f'{LABELS[item.meal_type]} · {item.name}', 'action': 'swap'} for item in choices]
            payload['choiceInstruction'] = swap_message
            if len(scoped) == 1:
                item = scoped[0]
                payload['context'].update(item_id=item.id, meal_type=item.meal_type)
                question = f'Bạn muốn đổi {item.name} ở {LABELS[item.meal_type].lower()} sang {reference.replacement}, đúng không?'
            elif source_matches and meals and not scoped:
                question = 'Món bạn nêu không có trong bữa đó. Bạn muốn đổi món nào trong các lựa chọn bên dưới?'
            else:
                question = 'Mình chưa xác định chắc món cần đổi. Bạn chọn đúng món và bữa ăn bên dưới nhé.'
            return MealReply(question, payload, status='needs_clarification')
        named = scoped
    stored_reference = re.search(r"\b(?:thuc don|mon nay|mon do|phan nay|dang luu|dang xem)\b", text)
    if (not action and task in {"nutrition", "ingredients", "compare", "basis"} and not (named or meals or whole_day or stored_reference)
            and get_catalog().looks_like_lookup(message)):
        return None
    meal_items = [item for item in plan.items if not meals or item.meal_type in meals]
    specific_item = by_id.get(context.item_id)
    if continuation:
        allowed = {choice["itemId"] for choice in previous_choices}
        eligible = [by_id[choice["itemId"]] for choice in previous_choices if choice["itemId"] in by_id]
        selection = re.search(r"\b(\d+)\b", text)
        if explicit_choice:
            items = [by_id[context.item_id]] if context.item_id in by_id and context.item_id in allowed else []
        elif affirm_single:
            items = eligible
        elif selection:
            index = int(selection[1]) - 1
            items = [eligible[index]] if 0 <= index < len(eligible) else []
        else:
            items = [item for item in (named or meal_items) if item.id in allowed] if named or meals else []
        if not items:
            payload["choices"] = previous_choices
            payload["choiceInstruction"] = swap_message
            return MealReply("Mình chưa nhận ra lựa chọn đó. Bạn chọn một món trong danh sách bên dưới nhé.", payload, status="needs_clarification")
    elif task == "compare":
        items = meal_items
    elif whole_day and task != "swap":
        items = []
    elif named:
        items = [item for item in named if not meals or item.meal_type in meals]
        if not items:
            return MealReply("Món bạn nêu không có trong bữa đó. Bạn chọn lại bữa hoặc món muốn hỏi nhé.", payload, status="needs_clarification")
    elif specific_item and (not meals or action and specific_item.meal_type in meals) and task not in {"rank", "summary", "targets"}:
        items = [specific_item]
    else:
        items = meal_items if meals else []
    if meals and not items and not whole_day and task not in {"keep", "accept", "change_status"}:
        return MealReply("Thực đơn đang lưu chưa có " + ", ".join(LABELS[key].lower() for key in meals) + ".", payload)
    if change and action == "swap" and specific_item and specific_item not in items:
        return MealReply("Món bạn vừa chọn nằm ngoài yêu cầu đổi. Hãy chọn món thuộc bữa bạn muốn đổi nhé.", payload, status="needs_clarification")
    if len(items) == 1:
        payload["context"]["item_id"] = items[0].id
        payload["context"]["meal_type"] = items[0].meal_type
    elif len(meals) == 1:
        payload["context"]["meal_type"] = meals[0]
    payload["selectedItemIds"] = [item.id for item in items]
    pending = pending_meal(history, plan)
    previous_view = last.get("meal_view") or (last.get("meal_result") or {}).get("view")
    if task == "keep":
        return MealReply("Được nhé, mình giữ nguyên thực đơn đang lưu và dừng phương án xem trước trong cuộc trò chuyện này.", payload, cancel_pending=True)
    if task in {"change_status", "accept"}:
        if plan.catalog_version == 'java-catalog-unversioned' and last_result.get('editor'):
            return MealReply('Thay đổi không được lưu chỉ bằng lời nhắn đồng ý. Bạn bấm chọn món trong thẻ đổi món, chọn phương án, xem trước rồi bấm Áp dụng thay đổi. Bạn có thể mở Xem thực đơn để đối chiếu bản đang lưu.', payload)
        if pending and plan.version == pending.get("baseVersion") and pending.get("expiresAt", 0) > time.time():
            payload["pending"] = pending
            return MealReply("Chưa nhé, phương án vẫn đang chờ. Bạn bấm Áp dụng trên thẻ xem trước để lưu thay đổi.", payload)
        if pending and plan.version == pending.get("baseVersion"):
            return MealReply("Phương án xem trước đã hết hạn. Bạn có thể yêu cầu một phương án mới để xem và áp dụng.", payload)
        return MealReply(f"Thực đơn đang lưu là phiên bản {plan.version}. Hiện cuộc trò chuyện không có phương án chờ áp dụng.", payload)
    if task == "capabilities":
        if plan.catalog_version == "named-demo-v1":
            return MealReply("Bạn có thể xem các bữa, hỏi số dinh dưỡng hoặc nguồn của từng món. Bản minh họa hiện chưa lưu thay đổi món hay khẩu phần.", payload)
        return MealReply("Mình giúp bạn xem thực đơn đang lưu, hỏi số liệu và thành phần món ăn, rồi xem trước phương án đổi một món. Bạn kiểm tra và bấm Áp dụng khi muốn lưu. Phần tạo thực đơn mới chưa được kết nối nhé.", payload)
    if task == "profile":
        return MealReply(f"Mình đang đọc hồ sơ phiên bản {profile.profile_version} gắn với thực đơn này. Hồ sơ và mục tiêu do dịch vụ của nhóm cung cấp; mình chưa tự cập nhật chúng qua lời nhắn trong chat.", payload)
    if task == "missing_value":
        return MealReply("Không nhé. Ô chưa có dữ liệu khác với số 0, nên mình sẽ ghi rõ là chưa biết và chưa kết luận đủ hay thiếu chất đó.", payload)
    if task == "summary" or task == "rephrase" and previous_view != "explain":
        count, energy = len({item.meal_type for item in plan.items}), plan.totals.energy_kcal
        summary = f"Thực đơn mẫu này có {count} bữa" + (f", tổng {number(energy)} kcal." if energy is not None else ".") + (" Bạn có thể hỏi về từng món và số dinh dưỡng; lượng ăn chưa được cá nhân hóa theo hồ sơ." if plan.catalog_version == "named-demo-v1" else " Bạn có thể xem từng món và thử đổi món; các số này chưa phải khẩu phần cá nhân đã được xác minh.")
        return MealReply(summary if snapshot.data_mode == "mock" else f"Thực đơn đang lưu có {count} bữa. Bạn có thể xem từng món và đề xuất đổi trước khi áp dụng.", payload)
    if task == "swap" and plan.catalog_version == "named-demo-v1" and re.search(ALTERNATIVE, text):
        current = items or plan.items
        when = LABELS[meals[0]] if len(meals) == 1 else "Thực đơn"
        names = ", ".join(item.name for item in current)
        return MealReply(
            f"{when} mẫu đang có {names}. Bản minh họa chưa hỗ trợ đổi món, "
            "nên mình chưa có phương án khác để bạn chọn.",
            payload, status="integration_required", cancel_pending=bool(pending),
        )
    if task == "swap" and plan.catalog_version == 'java-catalog-unversioned':
        # This is an editor handoff, not an optimizer proposal or a write.
        # The shared frontend form calls Gateway checked preview/apply only
        # after the user selects a catalog dish/portion and confirms.
        if not context.plan_id:
            return MealReply('Bạn chọn thực đơn muốn đổi ở đầu trang trước nhé. Sau đó mình sẽ hiện các món để bạn chọn, xem trước và xác nhận; hiện chưa thay đổi thực đơn.', payload, status='needs_clarification')
        candidates = items or plan.items
        excluded = []
        dislike = re.search(r"(?:không\s+(?:(?:muốn|thích)\s+)?(?:ăn|dùng)|không\s+thích|khong\s+(?:(?:muon|thich)\s+)?(?:an|dung)|khong\s+thich)\s+(.+)", swap_message, re.I)
        if dislike:
            term = re.split(r"\s+(?:vào|buổi|bữa|hôm|nữa|trong|vao|buoi|bua|hom|nua|trong)\b|[,;.!?]", dislike[1], maxsplit=1, flags=re.I)[0].strip()
            if term:
                excluded = [term]
                matching = [item for item in candidates if any(
                    re.search(r"(?<!\w)"+re.escape(fold(term) if term.isascii() else term)+r"(?!\w)", fold(name) if term.isascii() else name, re.I)
                    for name in [item.name, *[ingredient.name for ingredient in item.ingredients]]
                )]
                if matching:
                    candidates = matching
        amount = change.amount if change else None
        payload['editor'] = {'planId': plan.id, 'baseVersion': plan.version,
                             'itemIds': [item.id for item in candidates], 'instruction': swap_message,
                             'excludedTerms': excluded,
                             **({'preferredTerms': [reference.replacement]} if reference and change and change.dish else {}),
                             **({'requestedServings': float(amount[0])} if amount and amount[1] == 'serving' else {})}
        payload['choices'] = []
        subject = f'món {candidates[0].name} ở {LABELS[candidates[0].meal_type].lower()}' if len(candidates) == 1 else 'món muốn thay trong danh sách bên dưới'
        return MealReply(f"Mình hiểu bạn muốn đổi {subject}. Chọn món hoặc khẩu phần thay thế để xem trước. Sau khi hệ thống kiểm tra, bạn bấm Áp dụng thay đổi để lưu; hiện thực đơn chưa thay đổi.", payload)
    if task in {"swap", "ingredients", "source", "basis", "portion"} and len(items) != 1:
        choices = items or plan.items
        payload["choices"] = [{"itemId": item.id, "label": f"{LABELS[item.meal_type]} · {item.name}", "action": task} for item in choices]
        payload["choiceInstruction"] = swap_message
        question = "Bạn muốn đổi món nào?" if task == "swap" else "Bạn muốn xem thông tin của món nào?"
        return MealReply(question + " Chọn một món bên dưới nhé.", payload, status="needs_clarification",
                         cancel_pending=task == "swap" and bool(pending))
    if task in {"source", "basis", "portion"}:
        item = items[0]
        if task == "source":
            answer = "Số của món này lấy từ ví dụ trong tài liệu recom.docx để thử ứng dụng, chưa phải số đo dinh dưỡng món ăn thật nhé." if snapshot.data_mode == "mock" and plan.catalog_version != "named-demo-v1" else "Nguồn số liệu được lưu cùng món này: " + "; ".join(item.source_refs)
        elif task == "basis":
            states = {"cooked": "khối lượng đã nấu chín", "raw": "khối lượng nguyên liệu sống", "ready_to_eat": "lượng ăn ngay", "unknown": "chưa xác định là sống hay chín"}
            answer = f"Phần ăn này được ghi là {states[item.state]}. " + ("Vì vậy mình chưa thể dùng số của một suất để tính cho gram nguyên liệu trước nấu nhé." if item.state == "unknown" else "Khi cân thực phẩm, bạn cần dùng đúng trạng thái này để đối chiếu.")
        else:
            asking_grams = re.search(r"\b(?:gram|gam|bao nhieu g|may g)\b", text)
            answer = f"Phần {item.name} đang lưu là {portion(item)}."
            if asking_grams and item.unit != "g":
                answer += " Mình chưa có khối lượng tính bằng gram cho phần ăn này."
            prior_item = by_id.get(previous_context.get('item_id')) if previous_context.get('plan_id') == plan.id else None
            if prior_item and prior_item.id != item.id and re.search(r'\b(?:cung|giong|khac) loai\b', text):
                relation = 'Cùng loại với' if prior_item.recipe_id == item.recipe_id else 'Khác loại với'
                answer += (f" {relation} {prior_item.name.lower()} ở "
                           f"{LABELS[prior_item.meal_type].lower()} ({portion(prior_item)}).")
        return MealReply(answer, payload)
    if task == "swap":
        item = items[0]
        if plan.catalog_version == "named-demo-v1":
            hypothetical = named_portion_reply(item, change, payload)
            if hypothetical:
                return hypothetical
            return MealReply(
                f"Phần đang hiển thị là {portion(item)} {item.name.lower()}. Bản minh họa chưa đủ dữ liệu thành phần để đổi món. "
                "Bạn có thể hỏi số kcal của một lượng cụ thể để so với phần hiện tại.",
                payload, status="integration_required", cancel_pending=bool(pending),
            )
        if change.keep_recipe and change.requested_amount(item) is None and (not change.amount_direction or change.amount) and not change.exclusion:
            direction = {-1: "giảm", 1: "tăng", 0: "chỉnh"}[change.amount_direction]
            question = f"Phần {item.name} đang là {portion(item)}. Bạn muốn {direction} còn bao nhiêu {UNITS[item.unit]}?"
            if change.amount and change.amount[1] != item.unit:
                question = f"Món này được lưu theo {UNITS[item.unit]}. Bạn cho mình số lượng theo đơn vị này để kiểm tra nhé."
            return MealReply(question, payload, status="needs_clarification", cancel_pending=bool(pending))
        try:
            proposal = gateway.preview(owner, SwapRequest(plan_id=plan.id, base_version=plan.version, item_id=item.id, instruction=swap_message), authorization)
        except MealServiceError as error:
            if error.code == "NO_FEASIBLE_PLAN" and change.keep_recipe:
                reply = MealReply(f"Mình chưa tìm được phương án thay đổi phần {item.name} đến lượng bạn yêu cầu trong các giới hạn hiện tại. Phần đang lưu là {portion(item)}.", payload, status="needs_clarification")
            elif error.code == "NO_FEASIBLE_PLAN" and (change.dish or change.nutrient_directions or change.unknown or change.exclusion or change.numeric_nutrient):
                reply = MealReply(f"Mình chưa tìm được món thay vừa đáp ứng yêu cầu đó, vừa giữ các điều kiện của thực đơn. {item.name} vẫn là món đang lưu.", payload, status="needs_clarification")
            elif error.code == "NO_FEASIBLE_PLAN" and snapshot.data_mode == "mock":
                reply = MealReply(
                    f"Bản mẫu chưa có món thay cho {item.name.lower()} ở {LABELS[item.meal_type].lower()}. "
                    f"Phần đang lưu là {portion(item)}. Nếu muốn thay đổi lượng, bạn có thể cho mình số {UNITS[item.unit]} mới để kiểm tra.",
                    payload, status="needs_clarification",
                )
            else:
                reply = error_reply(error, mock=snapshot.data_mode == "mock", payload=payload)
            reply.cancel_pending = bool(pending)
            return reply
        payload["proposal"] = proposal.model_dump(mode="json")
        replacement = next(after for after in proposal.plan.items if after.id == item.id)
        fields = [key for key, _ in change.nutrient_directions] or ["energy_kcal"]
        payload["nutrientKeys"] = fields
        scope = "Tổng cả ngày" if change.whole_day else LABELS[item.meal_type]
        before_values, after_values = (plan.totals, proposal.plan.totals) if change.whole_day else (item.nutrients, replacement.nutrients)
        differences = [
            f"{NUTRIENTS[key][0].lower()} từ {number(getattr(before_values, key))} xuống {number(getattr(after_values, key))} {NUTRIENTS[key][1]}"
            if getattr(after_values, key) < getattr(before_values, key)
            else f"{NUTRIENTS[key][0].lower()} từ {number(getattr(before_values, key))} lên {number(getattr(after_values, key))} {NUTRIENTS[key][1]}"
            for key in fields if getattr(before_values, key) is not None and getattr(after_values, key) is not None
            and getattr(before_values, key) != getattr(after_values, key)
        ]
        label = "Xem trước bản mẫu" if snapshot.data_mode == "mock" else "Xem trước"
        if snapshot.data_mode == "mock" and change.keep_recipe and change.requested_amount(item) is None:
            label = "Xem trước một mức thử trên bản mẫu"
        description = f"{item.name} → {replacement.name}"
        if item.recipe_id == replacement.recipe_id and item.amount != replacement.amount:
            direction = "xuống" if replacement.amount < item.amount else "lên"
            description = f"{item.name} từ {portion(item)} {direction} {portion(replacement)}"
        summary = f"{label} – {description}."
        if differences:
            summary += f" {scope} có " + " và ".join(differences) + "."
        total_before, total_after = plan.totals.energy_kcal, proposal.plan.totals.energy_kcal
        if not change.whole_day and "energy_kcal" in fields and total_before is not None and total_after is not None and total_before != total_after:
            summary += f" Tổng cả ngày từ {number(total_before)} xuống {number(total_after)} kcal." if total_after < total_before else f" Tổng cả ngày từ {number(total_before)} lên {number(total_after)} kcal."
        return MealReply(summary + " Mình chưa lưu thay đổi. Bấm Áp dụng nếu bạn chọn phương án này.", payload,
                         cancel_pending=bool(pending))
    if task == "ingredients":
        item = items[0]
        if not item.ingredients:
            return MealReply(f'Chưa có danh sách nguyên liệu của {item.name}. Mình không suy đoán thành phần hoặc dị ứng từ tên món.', payload, status='insufficient_evidence')
        if plan.catalog_version == "named-demo-v1":
            return MealReply(f"Mình có bản ghi dinh dưỡng của {item.name}, nhưng chưa có danh sách nguyên liệu đầy đủ để xác nhận thành phần hoặc dị ứng. Bạn có thể xem nguồn số liệu trong chi tiết món.", payload)
        return MealReply(f"{item.name} gồm: " + ", ".join(i.name for i in item.ingredients) + (". Đây là nguyên liệu giả lập của bản thử nhé." if snapshot.data_mode == "mock" else ".") + (" Danh sách còn thiếu nên chưa đủ để kiểm tra dị ứng." if not item.ingredients_complete else ""), payload)
    if task in {"nutrition", "compare", "rank"}:
        requested = nutrient_fields(text)
        unknown = missing_nutrients(message)
        if task == "nutrition" and not unknown and (mixed := mixed_scope_nutrition(message, plan)):
            answer, payload["nutrientKeys"], payload["selectedItemIds"] = mixed
            if re.search(ALL_DAY, text):
                payload["selectedItemIds"] = []
            return MealReply(answer, payload)
        if task == "nutrition" and not requested and not unknown and history and previous_view in {"nutrition", "compare"} and meals:
            requested = nutrient_fields(fold(history[-1]["question"]))
        payload["nutrientKeys"] = requested or ([] if unknown else list(Nutrients.model_fields))
        if unknown and not requested:
            return MealReply("Mình chưa có dữ liệu " + ", ".join(unknown) + " của thực đơn này nên chưa trả con số được."
                + (" Mình cũng không suy lượng đường từ carbohydrate nhé." if "đường tổng" in unknown else ""), payload, status="insufficient_evidence")
        requested = requested or (["energy_kcal"] if task in {"compare", "rank"} else list(Nutrients.model_fields))
        payload["nutrientKeys"] = requested
        if task == "rank":
            key = requested[0]
            label, unit, _ = NUTRIENTS[key]
            if re.search(r"\bmon nao\b", text):
                groups = [(item.name, item.nutrients) for item in items or plan.items]
            else:
                groups = [(LABELS[meal], sum_nutrients([item for item in plan.items if item.meal_type == meal]))
                          for meal in LABELS if any(item.meal_type == meal for item in plan.items)]
            values = [(name, getattr(totals, key)) for name, totals in groups]
            if any(value is None for _, value in values):
                return MealReply(f"Mình chưa có đủ số liệu {label.lower()} để xếp theo yêu cầu.", payload, status="insufficient_evidence")
            least = bool(re.search(r"\b(?:it|thap) nhat\b", text))
            limit = (min if least else max)(value for _, value in values)
            names = " và ".join(name for name, value in values if value == limit)
            return MealReply(f"{names} {'ít' if least else 'nhiều'} {label.lower()} nhất, với {number(limit)} {unit} theo phần ăn đang lưu.", payload)
        if task == "compare":
            key = requested[0]
            label, unit, _ = NUTRIENTS[key]
            values = [(meal, getattr(sum_nutrients([item for item in plan.items if item.meal_type == meal]), key)) for meal in meals]
            if len(values) == 2 and all(value is not None for _, value in values):
                (a, av), (b, bv) = values
                higher, lower = (a, b) if av > bv else (b, a)
                conclusion = (f"{LABELS[higher]} có {label.lower()} nhiều hơn {LABELS[lower].lower()} {number(abs(av - bv))} {unit}."
                              if av != bv else f"Hai bữa có lượng {label.lower()} bằng nhau.")
                return MealReply(f"{conclusion} {LABELS[a]} có {number(av)} {unit}, còn {LABELS[b].lower()} có {number(bv)} {unit}.", payload)
            return MealReply("Mình chưa có đủ số liệu cùng một chỉ tiêu của hai bữa để so sánh nhé.", payload, status="insufficient_evidence")
        values = sum_nutrients(items) if items else plan.totals
        if len(requested) == 1 and not unknown:
            key = requested[0]
            label, unit, _ = NUTRIENTS[key]
            value = getattr(values, key)
            if meals and len(meals) == 1 and (len(items) > 1 or not named and not specific_item):
                subject = LABELS[meals[0]]
            else:
                subject = " và ".join(item.name for item in items) if items else "Cả ngày"
            if value is None:
                return MealReply(f"Mình chưa có dữ liệu {label.lower()} của {subject.lower()} nên chưa đánh giá được đã đủ hay chưa, hoặc nhiều hay ít.", payload, status="insufficient_evidence")
            basis = "theo phần ăn đang lưu" if items else "theo thực đơn đang lưu"
            nutrient = "" if key == "energy_kcal" else f" {label.lower()}"
            detail = ""
            if items and re.search(r"\b(?:mon gi|nhung mon|gom gi|gom mon)\b", text):
                detail = " gồm " + ", ".join(f"{portion(item)} {item.name.lower()}" for item in items) + " và"
            return MealReply(f"{subject}{detail} có {number(value)} {unit}{nutrient} {basis}.", payload)
        lines = [("; ".join(item.name for item in items) if items else "Cả ngày") + ":"]
        for key in requested:
            label, unit, _ = NUTRIENTS[key]
            value = getattr(values, key)
            lines.append(f"• {label}: " + ("chưa có dữ liệu để kết luận đã đủ hay chưa, hoặc nhiều hay ít" if value is None else f"{number(value)} {unit}"))
        if unknown:
            lines.append("Mình chưa có dữ liệu " + ", ".join(unknown) + ".")
        return MealReply("\n".join(lines) + "\nĐây là số theo phần ăn đang lưu nhé.", payload)
    if task == "targets":
        if plan.catalog_version == "named-demo-v1":
            return MealReply("Thực đơn minh họa này chưa có mục tiêu dinh dưỡng cá nhân. Tổng kcal chỉ là tổng các phần ăn mẫu đang hiển thị, không phải mức bạn được khuyến nghị ăn mỗi ngày.", payload)
        energy, bounds = plan.totals.energy_kcal, plan.target.bounds["energy_kcal"]
        if energy is None:
            return MealReply("Mình chưa có đủ tổng năng lượng để so với mục tiêu nhé.", payload, status="insufficient_evidence")
        low, high = bounds.minimum, bounds.maximum
        within = (low is None or energy >= low) and (high is None or energy <= high)
        span = f"{number(low)}–{number(high)} kcal" if low is not None and high is not None else f"từ {number(low)} kcal" if low is not None else f"không quá {number(high)} kcal"
        return MealReply(f"Cả ngày có {number(energy)} kcal, {'nằm trong' if within else 'chưa nằm trong'} khoảng mục tiêu {span}. " + ("Đây là mục tiêu ví dụ để thử ứng dụng, chưa phải mức đã xác định riêng cho sức khỏe của bạn." if snapshot.data_mode == "mock" else "Mục tiêu này do dịch vụ hồ sơ cung cấp, mình không tự thay đổi."), payload)
    if task == "rephrase":
        if plan.catalog_version == "named-demo-v1":
            return MealReply("Đây là các món và lượng ăn được chọn sẵn để demo. Mình cộng số dinh dưỡng từ dữ liệu nguồn; chưa kết luận lượng ăn này phù hợp riêng với bạn.", payload)
        return MealReply("Nói ngắn gọn nhé: bản thử chọn món để cộng lại vừa khoảng đã đặt cho cả ngày. Điều đó chưa đủ để nói món này hợp riêng với bạn.", payload)
    if task == "explain":
        if plan.catalog_version == "named-demo-v1":
            return MealReply("Các món được chọn sẵn để demo hỏi đáp, chưa được tối ưu theo hồ sơ, sở thích hoặc dị ứng của bạn. Thay đổi thông tin người dùng không tự đổi các lượng ăn mẫu này.", payload)
        return MealReply("Trong bản thử, món này được chọn để tổng cả ngày nằm trong khoảng đã đặt. Mình chưa biết nó có hợp riêng với sức khỏe và sở thích của bạn hay không." if snapshot.data_mode == "mock" else "Mình xem được thực đơn đang lưu, nhưng chưa có lý do chọn riêng từng món nên chưa thể giải thích vì sao món này được chọn cho bạn.", payload)
    displayed = items or plan.items
    groups = {meal: [item for item in displayed if item.meal_type == meal] for meal in LABELS}
    detail = "\n".join(f"{LABELS[meal]} gồm " + ", ".join(f"{portion(item)} {item.name}" for item in group) + "." for meal, group in groups.items() if group)
    return MealReply(("Trong thực đơn mẫu:\n" if snapshot.data_mode == "mock" else "") + detail, payload)
