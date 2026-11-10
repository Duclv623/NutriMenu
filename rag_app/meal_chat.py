"""Plain-language meal questions backed by authenticated structured data."""
import re
from dataclasses import dataclass

from rag_app.meal_gateway import MealServiceError
from rag_app.meal_models import MealContext, Nutrients, SwapRequest, sum_nutrients
from rag_app.retrieval import fold

LABELS = {"BREAKFAST": "Bữa sáng", "LUNCH": "Bữa trưa", "DINNER": "Bữa tối", "SNACK": "Bữa phụ"}
NUTRIENTS = {
    "energy_kcal": ("Năng lượng", "kcal", r"calo|kcal|nang luong"),
    "carbohydrate_g": ("Carbohydrate (carb)", "g", r"carb|carbohydrate|glucid|tinh bot"),
    "protein_g": ("Chất đạm", "g", r"protein|dam"),
    "fat_g": ("Chất béo", "g", r"lipid|chat beo|fat"),
    "fiber_g": ("Chất xơ", "g", r"chat xo|fiber"),
    "sodium_mg": ("Natri", "mg", r"natri|sodium"),
}


def mentioned_meals(message):
    text = fold(message)
    patterns = {"BREAKFAST": r"\bbua sang\b|\bbuoi sang\b|\bsang nay\b|\bmon sang\b",
                "LUNCH": r"\btrua\b", "DINNER": r"\bbua toi\b|\bbuoi toi\b|\btoi nay\b|\bmon toi\b", "SNACK": r"\bbua phu\b"}
    result = [key for key, pattern in patterns.items() if re.search(pattern, text)]
    # Preserve accents to distinguish evening (tối) from I (tôi).
    for key, word in [("BREAKFAST", "sáng"), ("DINNER", "tối")]:
        if key not in result and re.search(r"\b" + word + r"\b", message, re.I):
            result.append(key)
    return result


def meal_action(message, context=None, explicit=None):
    if explicit:
        return explicit
    text = fold(message)
    if re.search(r"\b(?:la gi|co vai tro|tac dung|loi ich|khai niem|nguyen tac|khuyen cao|theo tai lieu|dan nguon)\b", text):
        return None
    meals, menu = mentioned_meals(message), "thuc don" in text
    # A question about changing an eating habit does not edit a stored plan.
    # Explicit actions above and queries that name the stored menu retain their
    # structured path, including when a meal context is already open.
    if (not menu and meals and re.search(
            r'\b(?:co on|on khong|duoc khong|dc ko|co the|co phai|bat buoc|nen|co can)\b', text)
            and re.search(r'\b(?:an|uong|bo bua|doi|thay|doi bung|hay doi)\b', text)
            and not re.search(r'\b(?:dang xem|mon nay|mon do|trong (?:bua|ke hoach)|doi giup|thay giup|doi mon|thay mon)\b', text)):
        return None
    personal = re.search(r'\b(?:cua toi|hom nay|sang nay|trua nay|toi nay|dang xem)\b', text)
    operation = re.search(r'\b(?:doi|thay|tao|sinh|lap|them|bo|xem)\b', text)
    stored_lookup = meals and re.search(r'\b(?:co bao nhieu|may gam)\b', text) and not re.search(r'\b(?:nen|can)\b', text)
    if not (context or (menu or meals) and (personal or operation) or stored_lookup):
        return None
    for action, pattern in [
        ("protect_exclusions", r"\bbo qua\b.*\b(?:di ung|gioi han|dieu kien)\b"),
        ("keep", r"\b(?:dung (?:doi|thay)|khong (?:can |muon )?(?:doi|thay)|giu nguyen|thoi.*doi)\b"),
        ("change_status", r"\b(?:da (?:doi|luu|ap dung)|luu chua|doi chua)\b"),
        ("capabilities", r"\b(?:lam (?:duoc )?gi|lam duoc nhung gi|chuc nang|kha nang)\b"),
        ("structure", r"\b(?:them|bo|bot)\b.*\bbua\b"),
        ("new_exclusion", r"\b(?:minh|toi|vua|moi)\b.*\bdi ung\b"),
        ("profile", r"\bho so\b"),
        ("summary", r"\b(?:tom tat|hai cau|2 cau)\b"),
        ("rephrase", r"\b(?:de hieu hon|noi ngan|noi don gian|khong hieu.*chuyen mon)\b"),
        ("missing_value", r"\b(?:khong ghi|thieu|chua co)\b.*\b(?:0|bang khong)\b"),
        ("source", r"\b(?:tu dau|lay.*nguon|nguon so|can cu)\b"),
        ("basis", r"\b(?:can song|song hay chin|can chin|truoc nau|sau nau)\b"),
        ("portion", r"\b(?:suat|phan)\b.*\b(?:gram|gam|bao nhieu g)\b"),
    ]:
        if re.search(pattern, text):
            return action
    if menu and re.search(r"\b(?:tao|sinh|lap|len)\b.*\bthuc don\b", text) and not re.search(r"\b(?:vi sao|tai sao|cach|ai)\b", text):
        return "generate"
    if len(meals) >= 2 and re.search(r"\b(?:hon|so sanh|chenh|hay)\b", text):
        return "compare"
    if "muc tieu" in text:
        return "targets"
    if re.search(r"\b(?:doi|thay|bo bot|giam luong|tang luong)\b", text):
        return "swap"
    if re.search(r"\b(?:vi sao|tai sao|sao lai|phu hop|hop ly|co hop)\b", text):
        return "explain"
    if re.search(r"\b(?:bao nhieu|nhieu|may gam|tong|calo|kcal|carb|carbohydrate|protein|dam|lipid|chat beo|fat|chat xo|natri|cholesterol)\b", text) or re.search(r"\bGI\b", message):
        return "nutrition"
    if re.search(r"\b(?:nguyen lieu|thanh phan|gom gi|chua gi)\b", text):
        return "ingredients"
    if menu or meals or re.search(r"\b(?:xem|hien|mon nay|mon do)\b", text):
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
    return f"{value:g}".replace(".", ",")


def error_reply(error, *, mock=False, payload=None):
    answers = {
        "NO_FEASIBLE_PLAN": "Mình chưa có món thay phù hợp cho phần bạn chọn. Thực đơn đang lưu vẫn giữ nguyên nhé." if not mock else "Bộ thực đơn mẫu chưa có phương án thay phù hợp cho món này. Mình giữ nguyên thực đơn đang lưu nhé.",
        "PROFILE_INCOMPLETE": "Mình chưa đủ thông tin để đổi món. Bạn hãy mở hồ sơ, xác nhận dị ứng và những thực phẩm cần tránh rồi thử lại nhé; chưa khai báo không có nghĩa là không dị ứng.",
        "NOT_FOUND": "Mình không mở được thực đơn hoặc phương án này. Bạn hãy chọn lại thực đơn thuộc tài khoản của mình nhé.",
        "AUTH_REQUIRED": "Bạn cần đăng nhập để mình đọc thực đơn của đúng tài khoản nhé.",
        "DATA_INCOMPLETE": "Phương án này chưa đủ dữ liệu để kiểm tra, nên mình chưa áp dụng. Thực đơn đang lưu vẫn giữ nguyên nhé.",
        "STALE_PLAN": "Thực đơn hoặc hồ sơ đã thay đổi. Bạn hãy tải lại bản mới rồi chọn món muốn đổi nhé; mình chưa áp dụng thay đổi nào.",
        "SERVICE_UNAVAILABLE": "Mình chưa kết nối được dịch vụ thực đơn lúc này. Bạn thử lại sau nhé; mình chưa áp dụng thay đổi nào.",
    }
    return MealReply(answers.get(error.code, error.message), payload, status="needs_clarification")


def handle_meal_chat(gateway, owner, message, context=None, action=None, authorization=None, *, history=None, blocked_profile_version=None):
    if not action and re.search(r'\b(?:xu ly nhung viec|ban co the lam gi|chuc nang|kha nang)\b', fold(message)):
        common = 'Mình có thể giải thích dinh dưỡng phổ thông, giúp chọn món theo nguyên tắc có nguồn và tra thành phần thực phẩm. '
        if gateway.mode == 'disabled':
            detail = 'Tạo, thay đổi và lưu thực đơn hiện chưa được kết nối. Lưu lịch sử chat là một chức năng riêng, không phải lưu thực đơn.'
        elif gateway.mode == 'mock':
            detail = 'Phần thực đơn đang dùng dữ liệu mẫu: bạn có thể xem số liệu, xem trước đổi món và áp dụng thay đổi trên bản mẫu. Tạo thực đơn mới chưa được kết nối; thay đổi bản mẫu không phải lưu thực đơn cá nhân thật.'
        else:
            detail = 'Phần thực đơn được cấu hình dùng dịch vụ kết nối: bạn có thể yêu cầu xem thực đơn đã lưu, xem trước đổi món và áp dụng thay đổi. Tạo thực đơn mới chưa được kết nối; mình chỉ báo đã lưu sau khi dịch vụ xác nhận.'
        return MealReply(common + detail)
    task = meal_action(message, context, action)
    if task is None:
        return None
    if task in {"generate", "structure"}:
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
    if task == "new_exclusion":
        return MealReply("Mình đã hiểu bạn vừa nêu thêm dị ứng, nhưng chưa cập nhật thông tin đó vào hồ sơ. Bạn hãy bổ sung dị ứng trong hồ sơ trước khi đổi món nhé; mình dừng phương án xem trước trong cuộc trò chuyện này và chưa áp dụng thay đổi nào.", status="needs_clarification", cancel_pending=True, profile_recheck_version=profile.profile_version)
    if task == "swap" and blocked_profile_version is not None and profile.profile_version <= blocked_profile_version:
        return MealReply("Bạn vừa báo thêm dị ứng, nhưng hồ sơ chưa có bản cập nhật. Mình tạm dừng đổi món; bạn hãy cập nhật dị ứng trong hồ sơ rồi thử lại nhé.", status="needs_clarification")
    if profile.scope_status == "out_of_scope" or profile.age is not None and profile.age < 18:
        return MealReply("Trường hợp của bạn cần hướng dẫn dinh dưỡng riêng từ bác sĩ hoặc chuyên gia. Mình chưa hỗ trợ đổi thực đơn cho hồ sơ này nhé.", status="safety")
    payload = {"dataMode": snapshot.data_mode, "plan": plan.model_dump(mode="json"), "view": task,
               "selectedItemIds": [], "context": {"plan_id": plan.id, "plan_version": plan.version}, "choices": [], "proposal": None,
               "notice": "Đây là dữ liệu mẫu để thử ứng dụng, chưa phải khẩu phần được xác minh cho người dùng thật." if snapshot.data_mode == "mock" else "Số liệu theo thực đơn đang lưu trong tài khoản."}
    if (context.plan_version and context.plan_version != plan.version) or profile.profile_version != plan.profile_version:
        return MealReply(f"Bản bạn đang xem đã cũ. Thực đơn hiện tại là phiên bản {plan.version}; bạn kiểm tra bản này rồi chọn món muốn đổi nhé. Mình chưa áp dụng thay đổi nào.", payload, status="needs_clarification")
    text, meals = fold(message), mentioned_meals(message)
    by_id = {item.id: item for item in plan.items}
    if context.item_id and context.item_id not in by_id:
        return error_reply(MealServiceError("NOT_FOUND"))
    named = [item for item in plan.items if re.search(r"(?<!\w)" + re.escape(fold(item.name.split("(")[0].strip())) + r"(?!\w)", text)
             or item.recipe_id.lower() in message.lower() or item.id.lower() in message.lower()]
    whole_day = bool(re.search(r"\b(?:ca ngay|toan ngay)\b", text))
    items = [] if whole_day else named or ([by_id[context.item_id]] if context.item_id and not meals else [])
    if meals:
        items = [item for item in items if item.meal_type in meals] if items else [item for item in plan.items if item.meal_type in meals]
        if not items:
            return MealReply("Thực đơn đang lưu chưa có " + ", ".join(LABELS[key].lower() for key in meals) + ". Mình chưa tự thêm bữa nhé.", payload)
    if len(items) == 1:
        payload["context"]["item_id"] = items[0].id
    payload["selectedItemIds"] = [item.id for item in items]
    last = history[-1].get("response", {}) if history else {}
    pending = last.get("meal_pending") or (last.get("meal_result") or {}).get("proposal")
    previous_view = last.get("meal_view") or (last.get("meal_result") or {}).get("view")
    if task == "keep":
        return MealReply("Được nhé, mình giữ nguyên thực đơn đang lưu và dừng phương án xem trước trong cuộc trò chuyện này.", payload, cancel_pending=True)
    if task == "change_status":
        if pending and plan.version == pending.get("baseVersion"):
            payload["pending"] = pending
            return MealReply("Chưa nhé, mình mới đưa ra phương án xem trước. Thực đơn đang lưu vẫn giữ nguyên; chỉ khi bạn bấm Áp dụng thì phương án mới được lưu.", payload)
        return MealReply(f"Thực đơn đang lưu hiện là phiên bản {plan.version}. Mình không tự lưu thay đổi chỉ vì bạn hỏi trong chat; bạn có thể xem lại bản đang lưu nhé.", payload)
    if task == "capabilities":
        return MealReply("Mình giúp bạn xem thực đơn đang lưu, hỏi số liệu và thành phần món ăn, rồi xem trước phương án đổi một món. Bạn kiểm tra và bấm Áp dụng khi muốn lưu. Phần tạo thực đơn mới chưa được kết nối nhé.", payload)
    if task == "profile":
        return MealReply(f"Mình đang đọc hồ sơ phiên bản {profile.profile_version} gắn với thực đơn này. Hồ sơ và mục tiêu do dịch vụ của nhóm cung cấp; mình chưa tự cập nhật chúng qua lời nhắn trong chat.", payload)
    if task == "missing_value":
        return MealReply("Không nhé. Ô chưa có dữ liệu khác với số 0, nên mình sẽ ghi rõ là chưa biết và chưa kết luận đủ hay thiếu chất đó.", payload)
    if task == "summary" or task == "rephrase" and previous_view != "explain":
        count, energy = len({item.meal_type for item in plan.items}), plan.totals.energy_kcal
        summary = f"Thực đơn mẫu này có {count} bữa" + (f", tổng {number(energy)} kcal." if energy is not None else ".") + " Bạn có thể xem từng món và thử đổi món; các số này chưa phải khẩu phần cá nhân đã được xác minh."
        return MealReply(summary if snapshot.data_mode == "mock" else f"Thực đơn đang lưu có {count} bữa. Bạn có thể xem từng món và đề xuất đổi trước khi áp dụng.", payload)
    if task in {"source", "basis", "portion"}:
        if len(items) != 1:
            return MealReply("Bạn chọn một món trong thực đơn để mình xem đúng thông tin nhé.", payload, status="needs_clarification")
        item = items[0]
        if task == "source":
            answer = "Số của món này lấy từ ví dụ trong tài liệu recom.docx để thử ứng dụng, chưa phải số đo dinh dưỡng món ăn thật nhé." if snapshot.data_mode == "mock" else "Nguồn số liệu được lưu cùng món này: " + "; ".join(item.source_refs)
        elif task == "basis":
            states = {"cooked": "khối lượng đã nấu chín", "raw": "khối lượng nguyên liệu sống", "ready_to_eat": "lượng ăn ngay", "unknown": "chưa xác định là sống hay chín"}
            answer = f"Phần ăn này được ghi là {states[item.state]}. " + ("Vì vậy mình chưa thể dùng số của một suất để tính cho gram nguyên liệu trước nấu nhé." if item.state == "unknown" else "Khi cân thực phẩm, bạn cần dùng đúng trạng thái này để đối chiếu.")
        else:
            answer = f"Phần ăn đang lưu là {number(item.amount)} g nhé." if item.unit == "g" else "Món này chưa có số gram tương ứng. Mình chưa thể đổi một suất ra gram; cần bổ sung khối lượng phần ăn trước nhé."
        return MealReply(answer, payload)
    if task in {"swap", "ingredients"} and len(items) != 1:
        payload["choices"] = [{"itemId": item.id, "label": f"{LABELS[item.meal_type]} · {item.name}", "action": task} for item in items or plan.items]
        return MealReply("Bạn muốn " + ("đổi" if task == "swap" else "xem thành phần") + " món nào? Chọn một món bên dưới để mình " + ("xem phương án đổi." if task == "swap" else "xem thành phần."), payload, status="needs_clarification")
    if task == "swap":
        requested_change = text.replace("bua sang", "buasang").replace("mon sang", "monsang")
        if snapshot.data_mode == "mock" and (re.search(r"\b(?:giam|tang|it calo|bot luong)\b", text) or re.search(r"\b(?:bang|thanh|sang)\s+", requested_change) and not re.search(r"demo:(?:a2|d)\b", text)):
            return MealReply("Bản thử hiện chỉ có phương án đổi mẫu ở bữa sáng, chưa đổi sang món cụ thể hoặc tăng/giảm lượng theo ý bạn được. Mình giữ nguyên thực đơn đang lưu nhé.", payload, status="integration_required")
        try:
            proposal = gateway.preview(owner, SwapRequest(plan_id=plan.id, base_version=plan.version, item_id=items[0].id, instruction=message), authorization)
        except MealServiceError as error:
            return error_reply(error, mock=snapshot.data_mode == "mock", payload=payload)
        payload["proposal"] = proposal.model_dump(mode="json")
        return MealReply("Mình đã có phương án để bạn xem trước. Thực đơn đang lưu chưa đổi nhé; bạn xem phần trước/sau rồi bấm Áp dụng nếu muốn lưu.", payload)
    if task == "ingredients":
        item = items[0]
        return MealReply(f"{item.name} gồm: " + ", ".join(i.name for i in item.ingredients) + (". Đây là nguyên liệu giả lập của bản thử nhé." if snapshot.data_mode == "mock" else ".") + (" Danh sách còn thiếu nên chưa đủ để kiểm tra dị ứng." if not item.ingredients_complete else ""), payload)
    if task in {"nutrition", "compare"}:
        requested = [key for key, (_, _, pattern) in NUTRIENTS.items() if re.search(r"\b(?:" + pattern + r")\b", text)]
        unknown = [label for label, pattern in [("đường tổng", r"\bduong\b"), ("muối", r"\bmuoi\b"), ("cholesterol", r"\bcholesterol\b"), ("kali", r"\bkali\b"), ("canxi", r"\bcanxi\b")] if re.search(pattern, text)]
        if re.search(r"\bGI\b|\bGL\b", message):
            unknown.append("GI/GL")
        if unknown and not requested:
            return MealReply("Mình chưa có dữ liệu " + ", ".join(unknown) + " của thực đơn này nên chưa trả con số được."
                + (" Mình cũng không suy lượng đường từ carbohydrate nhé." if "đường tổng" in unknown else ""), payload, status="insufficient_evidence")
        requested = requested or list(Nutrients.model_fields)
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
            subject = "; ".join(item.name for item in items) if items else "Cả ngày"
            if value is None:
                return MealReply(f"Mình chưa có dữ liệu {label.lower()} của {subject.lower()} nên chưa đánh giá được đã đủ hay chưa, hoặc nhiều hay ít.", payload, status="insufficient_evidence")
            basis = "theo phần ăn đang lưu" if items else "theo thực đơn đang lưu"
            nutrient = "" if key == "energy_kcal" else f" {label.lower()}"
            return MealReply(f"{subject} có {number(value)} {unit}{nutrient} {basis}.", payload)
        lines = [("; ".join(item.name for item in items) if items else "Cả ngày") + ":"]
        for key in requested:
            label, unit, _ = NUTRIENTS[key]
            value = getattr(values, key)
            lines.append(f"• {label}: " + ("chưa có dữ liệu để kết luận đã đủ hay chưa, hoặc nhiều hay ít" if value is None else f"{number(value)} {unit}"))
        if unknown:
            lines.append("Mình chưa có dữ liệu " + ", ".join(unknown) + ".")
        return MealReply("\n".join(lines) + "\nĐây là số theo phần ăn đang lưu nhé.", payload)
    if task == "targets":
        energy, bounds = plan.totals.energy_kcal, plan.target.bounds["energy_kcal"]
        if energy is None:
            return MealReply("Mình chưa có đủ tổng năng lượng để so với mục tiêu nhé.", payload, status="insufficient_evidence")
        low, high = bounds.minimum, bounds.maximum
        within = (low is None or energy >= low) and (high is None or energy <= high)
        span = f"{number(low)}–{number(high)} kcal" if low is not None and high is not None else f"từ {number(low)} kcal" if low is not None else f"không quá {number(high)} kcal"
        return MealReply(f"Cả ngày có {number(energy)} kcal, {'nằm trong' if within else 'chưa nằm trong'} khoảng mục tiêu {span}. " + ("Đây là mục tiêu ví dụ để thử ứng dụng, chưa phải mức đã xác định riêng cho sức khỏe của bạn." if snapshot.data_mode == "mock" else "Mục tiêu này do dịch vụ hồ sơ cung cấp, mình không tự thay đổi."), payload)
    if task == "rephrase":
        return MealReply("Nói ngắn gọn nhé: bản thử chọn món để cộng lại vừa khoảng đã đặt cho cả ngày. Điều đó chưa đủ để nói món này hợp riêng với bạn.", payload)
    if task == "explain":
        return MealReply("Trong bản thử, món này được chọn để tổng cả ngày nằm trong khoảng đã đặt. Mình chưa biết nó có hợp riêng với sức khỏe và sở thích của bạn hay không." if snapshot.data_mode == "mock" else "Mình xem được thực đơn đang lưu, nhưng chưa có lý do chọn riêng từng món nên chưa thể giải thích vì sao món này được chọn cho bạn.", payload)
    detail = "; ".join(f"{LABELS[item.meal_type].lower()}: {item.name}, {number(item.amount)} " + {"g": "g", "ml": "ml", "serving": "suất"}[item.unit] for item in items or plan.items)
    return MealReply(("Trong bản mẫu, " if snapshot.data_mode == "mock" else "Thực đơn đang lưu có ") + detail + ". Bạn có thể bấm vào món để xem số liệu hoặc đề xuất đổi nhé.", payload)
