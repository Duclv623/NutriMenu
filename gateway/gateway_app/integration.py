"""Authenticated BFF for the team's existing Java APIs.

Uses User Service Basic + CSRF server-side. The browser receives only an opaque
HttpOnly session. UUID accounts map durably to the Long IDs currently required
by Catalog/Optimizer. Unsupported Java contracts fail explicitly, never to mock.
"""

import hashlib
import json
import math
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from gateway_app.exclusions import resolve_excluded_dishes
from gateway_app.rate_limit import RateLimiter
from gateway_app.store import TeamStore

COOKIE = "nutriguide_session"
ROLES = {
    "COMPOSITE_DISH": "Món hỗn hợp",
    "MAIN_STARCH": "Cơm và tinh bột",
    "PROTEIN_DISH": "Món đạm",
    "SNACK": "Bữa phụ",
    "SOUP": "Món canh",
    "VEGGIE_DISH": "Món rau",
}
SLOTS = {
    "BREAKFAST": "breakfast",
    "LUNCH": "lunch",
    "DINNER": "dinner",
    "AFTERNOON_SNACK": "snack",
}
NUTRIENTS = {
    "energy": "caloriesKcal",
    "carbs": "netCarbG",
    "protein": "proteinG",
    "fat": "fatG",
    "fiber": "fiberG",
    "sodium": "sodiumMg",
}
MEAL_NUTRIENTS = {
    "energy_kcal": "energy",
    "carbohydrate_g": "carbs",
    "protein_g": "protein",
    "fat_g": "fat",
    "fiber_g": "fiber",
    "sodium_mg": "sodium",
}


def camel(value):
    head, *tail = value.split("_")
    return head + "".join(word.title() for word in tail)


def revision(value):
    # Stable content revision, NOT a substitute for an atomic backend @Version.
    return (
        int(
            hashlib.sha256(
                json.dumps(
                    value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
                ).encode()
            ).hexdigest()[:12],
            16,
        )
        + 1
    )


def numeric(value):
    if isinstance(value, bool) or value is None:
        raise HTTPException(502, "Backend thiếu số liệu dinh dưỡng hoặc định lượng.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise HTTPException(502, "Backend trả số liệu không hợp lệ.") from None
    if not math.isfinite(number) or number < 0:
        raise HTTPException(502, "Backend trả số liệu không hợp lệ.")
    return number


def profile_revision(raw):
    if not all(key in raw for key in ("version", "confirmed", "pregnant", "specialDiet")):
        raise HTTPException(
            503,
            "User Service chưa cập nhật hồ sơ bền vững. Cần chạy migration V2 và khởi động lại User Service.",
        )
    if (
        isinstance(raw["version"], bool)
        or not isinstance(raw["version"], int)
        or raw["version"] < 0
    ):
        raise HTTPException(502, "Phiên bản hồ sơ backend không hợp lệ.")
    # UI uses zero for "no profile"; JPA begins persisted versions at zero.
    return raw["version"] + 1


def numeric_id(value):
    value = str(value)
    if not value.isascii() or not value.isdigit() or not 0 < int(value) < 2**63:
        raise HTTPException(422, "ID phải là ID gốc do backend cấp.")
    return value


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Credentials(Body):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=100)


class UIProfile(Body):
    name: str = Field(min_length=1, max_length=100)
    dateOfBirth: date
    age: int = Field(ge=18, le=120)
    gender: str
    height: float = Field(ge=80, le=250)
    weight: float = Field(ge=20, le=400)
    targetWeight: float = Field(ge=20, le=400)
    activity: str
    goal: str
    allergies: list[str] = Field(max_length=100)
    excludedFoods: list[str] = Field(max_length=100)
    preferences: str = Field(max_length=2000)
    pregnant: bool
    specialDiet: bool
    confirmed: bool
    version: int = Field(ge=0)


class Generate(Body):
    date: date
    target: float = Field(ge=1000, le=3500)
    snacks: bool
    maxMinutes: int = Field(ge=0, le=240)
    excludeRepeat: bool
    profileVersion: int = Field(ge=1)


class LockItem(Body):
    baseVersion: int = Field(ge=1)
    locked: bool


class MealChange(Body):
    baseVersion: int = Field(ge=1)
    profileVersion: int = Field(ge=1)
    itemId: str
    foodId: str
    servings: float = Field(ge=0.5, le=3)
    previewSignature: str | None = Field(default=None, max_length=100)


class MealLog(Body):
    key: str = Field(max_length=150)
    completed: bool


class Shopping(Body):
    checkedIds: list[Annotated[str, Field(max_length=150)]] = Field(max_length=2000)


class CheckIn(Body):
    id: UUID
    date: date
    weight: float = Field(ge=20, le=400)
    glucose: float | None = Field(default=None, gt=0, le=100)
    note: str = Field(max_length=2000)


@dataclass(repr=False)
class Session:
    client: httpx.Client
    account: dict
    service_id: int
    expires: float
    lock: threading.RLock = field(default_factory=threading.RLock)


class TeamIntegration:
    def __init__(self, settings, history, *, transport=None, state=None):
        self.settings = settings
        self.state = state or TeamStore(history)
        self.transport = transport
        self.sessions = {}
        self.lock = threading.RLock()
        self.limiter = RateLimiter(12)
        self.catalog = httpx.Client(
            base_url=settings.team_catalog_url.rstrip("/") + "/",
            timeout=settings.meal_api_timeout,
            trust_env=False,
            follow_redirects=False,
            transport=transport,
        )
        self.optimizer = httpx.Client(
            base_url=settings.team_optimizer_url.rstrip("/") + "/",
            timeout=30,
            trust_env=False,
            follow_redirects=False,
            transport=transport,
        )

    def call(self, client, method, path, **kwargs):
        try:
            response = client.request(method, path, **kwargs)
        except httpx.HTTPError:
            raise HTTPException(
                503, "Không kết nối được dịch vụ backend. Không sử dụng dữ liệu mẫu."
            ) from None
        if response.status_code >= 300:
            try:
                body = response.json()
            except ValueError:
                body = {}
            status = (
                response.status_code
                if response.status_code in {400, 401, 403, 404, 409, 422, 429, 503}
                else 502
            )
            message = body.get("message") or "Dịch vụ backend chưa xử lý được yêu cầu."
            raise HTTPException(status, message)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise HTTPException(502, "Backend trả dữ liệu không đúng định dạng JSON.") from None

    @staticmethod
    def unwrap(data):
        if not isinstance(data, dict) or data.get("success") is False or "data" not in data:
            raise HTTPException(502, "User Service trả hợp đồng không hợp lệ.")
        return data["data"]

    def expire(self):
        with self.lock:
            for key in list(self.sessions):
                if self.sessions[key].expires <= time.monotonic():
                    session = self.sessions.pop(key)
                    with session.lock:
                        session.client.close()

    def login(self, body, register=False):
        self.expire()
        client = httpx.Client(
            base_url=self.settings.team_user_url.rstrip("/") + "/",
            timeout=self.settings.meal_api_timeout,
            trust_env=False,
            follow_redirects=False,
            transport=self.transport,
        )
        try:
            if register:
                if not body.name or not body.name.strip() or len(body.password) < 8:
                    raise HTTPException(422, "Cần họ tên và mật khẩu từ 8 ký tự.")
                csrf = self.call(client, "GET", "api/auth/csrf")
                self.call(
                    client,
                    "POST",
                    "api/auth/register",
                    headers={csrf["headerName"]: csrf["token"]},
                    json={
                        "email": body.email.strip(),
                        "password": body.password,
                        "fullName": body.name.strip(),
                    },
                )
            client.auth = httpx.BasicAuth(body.email.strip(), body.password)
            account = self.unwrap(self.call(client, "GET", "api/users/me"))
            account_id = str(UUID(account["id"]))
            service_id = self.state.service_id(account_id)
            session = Session(
                client,
                account,
                service_id,
                time.monotonic() + self.settings.team_session_seconds,
            )
            token = secrets.token_urlsafe(48)
            with self.lock:
                if len(self.sessions) >= 1000:
                    raise HTTPException(503, "Máy chủ đã đạt giới hạn phiên đăng nhập.")
                self.sessions[token] = session
            return token, self.user(session)
        except Exception:
            client.close()
            raise

    @staticmethod
    def user(session):
        return {
            "id": session.account["id"],
            "name": session.account["fullName"],
            "email": session.account["email"],
            "demo": False,
        }

    def resolve_token(self, token):
        self.expire()
        with self.lock:
            session = self.sessions.get(token)
        if not session:
            raise HTTPException(401, "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.")
        with session.lock:
            account = self.unwrap(self.call(session.client, "GET", "api/users/me"))
            if account["id"] != session.account["id"]:
                raise HTTPException(401, "Danh tính phiên đăng nhập không hợp lệ.")
        return session

    @staticmethod
    def headers(session):
        return {"X-User-Id": str(session.service_id)}

    def raw_profile(self, session):
        try:
            with session.lock:
                return self.unwrap(self.call(session.client, "GET", "api/users/me/profile"))
        except HTTPException as error:
            if error.status_code != 404:
                raise
            return None

    def profile(self, session, raw=None):
        raw = raw if raw is not None else self.raw_profile(session)
        if not raw:
            return {
                "name": session.account["fullName"],
                "dateOfBirth": "",
                "age": 0,
                "gender": "",
                "height": 0,
                "weight": 0,
                "targetWeight": 0,
                "activity": "",
                "goal": "",
                "allergies": [],
                "excludedFoods": [],
                "preferences": "",
                "pregnant": False,
                "specialDiet": False,
                "confirmed": False,
                "version": 0,
            }
        version = profile_revision(raw)
        return {
            "name": session.account["fullName"],
            "dateOfBirth": raw["dateOfBirth"],
            "age": raw["age"],
            "gender": raw["gender"].lower(),
            "height": raw["height"],
            "weight": raw["weight"],
            "targetWeight": raw.get("targetWeight") or raw["weight"],
            "activity": {"HIGH": "active", "VERY_HIGH": "very_active"}.get(
                raw["activityLevel"], raw["activityLevel"].lower()
            ),
            "goal": {
                "LOSE_WEIGHT": "lose",
                "MAINTAIN_WEIGHT": "maintain",
                "GAIN_WEIGHT": "gain",
            }[raw["goal"]],
            "allergies": sorted(raw.get("allergies") or []),
            "excludedFoods": sorted(raw.get("restrictedIngredients") or []),
            "preferences": ", ".join(sorted(raw.get("preferences") or [])),
            "pregnant": raw["pregnant"],
            "specialDiet": raw["specialDiet"],
            "confirmed": raw["confirmed"],
            "version": version,
        }

    def save_profile(self, session, body):
        current = self.raw_profile(session)
        if (profile_revision(current) if current else 0) != body.version:
            raise HTTPException(409, "Hồ sơ đã thay đổi. Hãy tải lại trước khi lưu.")
        born = body.dateOfBirth
        today = date.today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        if age != body.age or born >= today or age < 18:
            raise HTTPException(422, "Ngày sinh và tuổi không khớp hoặc ngoài phạm vi hỗ trợ.")
        activity = {
            "sedentary": "SEDENTARY",
            "light": "LIGHT",
            "moderate": "MODERATE",
            "active": "HIGH",
            "very_active": "VERY_HIGH",
        }
        goals = {
            "lose": "LOSE_WEIGHT",
            "maintain": "MAINTAIN_WEIGHT",
            "gain": "GAIN_WEIGHT",
        }
        if (
            body.gender not in {"male", "female", "other"}
            or body.activity not in activity
            or body.goal not in goals
        ):
            raise HTTPException(422, "Giới tính, vận động hoặc mục tiêu không hợp lệ.")
        payload = {
            "dateOfBirth": born.isoformat(),
            "gender": body.gender.upper(),
            "height": body.height,
            "weight": body.weight,
            "targetWeight": body.targetWeight,
            "activityLevel": activity[body.activity],
            "goal": goals[body.goal],
            "allergies": body.allergies,
            "restrictedIngredients": body.excludedFoods,
            "preferences": [p.strip() for p in body.preferences.split(",") if p.strip()],
            "confirmed": body.confirmed,
            "pregnant": body.pregnant,
            "specialDiet": body.specialDiet,
            "expectedVersion": current["version"] if current else None,
        }
        with session.lock:
            csrf = self.call(session.client, "GET", "api/auth/csrf")
            saved = self.unwrap(
                self.call(
                    session.client,
                    "PUT",
                    "api/users/me/profile",
                    headers={csrf["headerName"]: csrf["token"]},
                    json=payload,
                )
            )
        return self.profile(session, saved)

    def pages(self, client, path, session):
        items = []
        for page in range(100):
            data = self.call(
                client,
                "GET",
                path,
                headers=self.headers(session),
                params={"size": 100, "page": page},
            )
            if not isinstance(data, dict) or not isinstance(data.get("content"), list):
                raise HTTPException(502, "Backend trả danh sách không đúng hợp đồng.")
            items.extend(data["content"])
            if data.get("last") is True or page + 1 >= data.get("totalPages", 1):
                return items
        raise HTTPException(502, "Danh sách backend vượt giới hạn tải; cần API phân trang.")

    def dish(self, session, dish_id):
        return self.call(
            self.catalog,
            "GET",
            "api/v1/dishes/" + numeric_id(dish_id),
            headers=self.headers(session),
        )

    def food(self, dish):
        nutrients = {key: numeric(dish.get(value)) for key, value in NUTRIENTS.items()}
        recipe = dish.get("recipeBreakdown") or []
        return {
            "id": str(dish["id"]),
            "name": dish["nameVi"],
            "category": ROLES.get(dish["role"], "Món ăn"),
            "description": (dish.get("householdUnitLabel") or "")
            + (" · Dữ liệu thử nghiệm QA" if (dish.get("code") or "").startswith("QA_") else ""),
            "emoji": "🥗",
            "color": "#81b29a",
            "image": dish.get("imageUrl") or "",
            "minutes": None,
            "grams": numeric(dish.get("standardServingCookedG")),
            "meals": [SLOTS[s] for s in dish.get("mealSlots", []) if s in SLOTS],
            "allergens": [s for s in dish.get("medicalTags", []) if s.startswith("ALLERGEN_")],
            "ingredients": [
                {
                    "id": str(i["ingredientId"]),
                    "name": i["ingredientNameVi"],
                    "grams": numeric(i["rawWeightG"]),
                }
                for i in recipe
            ],
            "nutrition": nutrients,
            "steps": dish.get("preparationSteps")
            or ([dish["diabeticCookingTip"]] if dish.get("diabeticCookingTip") else []),
            "preparationGuideKind": dish.get("preparationGuideKind"),
            "role": dish["role"],
            "servingRules": {
                "min": dish.get("minServingScaledX2", 1) / 2,
                "max": dish.get("maxServingScaledX2", 6) / 2,
                "step": dish.get("stepServingScaledX2", 1) / 2,
            },
            "ingredientsComplete": bool(recipe),
            "ingredientBasis": "raw",
            "recipeSource": dish.get("code") or str(dish["id"]),
        }

    def raw_plan(self, session, plan_id):
        data = self.call(
            self.optimizer,
            "GET",
            "api/v1/users/me/meal-plans/" + numeric_id(plan_id),
            headers=self.headers(session),
        )
        self.check_owner(session, data)
        return data

    @staticmethod
    def check_owner(session, plan):
        if str(plan.get("userId")) != str(session.service_id):
            raise HTTPException(404, "Không tìm thấy thực đơn thuộc tài khoản này.")

    def plan(self, session, raw):
        self.check_owner(session, raw)
        meta = self.state.get(session.account["id"], "plan:" + str(raw["planId"]), {})
        items = []
        for slot, entries in (raw.get("mealsBySlot") or {}).items():
            if slot not in SLOTS:
                raise HTTPException(502, "Backend trả loại bữa chưa được hỗ trợ.")
            for item in entries:
                if item.get("status") == "SKIPPED":
                    continue
                items.append(
                    {
                        "id": str(item["itemId"]),
                        "foodId": str(item["dishId"]),
                        "meal": SLOTS[slot],
                        "servings": numeric(item.get("servingMultiplier")),
                        "locked": bool(item.get("isLocked")),
                        # Java item nutrients ALREADY include servingMultiplier.
                        "nutrition": {k: numeric(item.get(v)) for k, v in NUTRIENTS.items()},
                    }
                )
        return {
            "id": str(raw["planId"]),
            "date": raw["planDate"],
            "profileVersion": meta.get("profileVersion", 0),
            "version": raw["version"] + 1 if isinstance(raw.get("version"), int) else revision(raw),
            "items": items,
            "solverStatus": raw["solverStatus"],
            "dataMode": "api",
            "target": numeric(raw["targetCaloriesKcal"]),
            "notes": [
                *(raw.get("medicalWarnings") or []),
                "Kết quả solver chưa kèm xác nhận đầy đủ mọi ràng buộc cá nhân.",
            ],
            "createdAt": meta.get("createdAt", ""),
            "validationPassed": bool(raw.get("validationPassed")),
            "changeSignature": raw.get("changeSignature"),
        }

    def workspace(self, session):
        profile = self.profile(session)
        raw_plans = self.pages(self.optimizer, "api/v1/users/me/meal-plans", session)
        plans = [self.plan(session, p) for p in raw_plans]
        dishes = self.pages(self.catalog, "api/v1/dishes", session)
        ids = {str(d["id"]) for d in dishes} | {i["foodId"] for p in plans for i in p["items"]}
        # Read detail, not the catalog's list projection with an empty recipe.
        with ThreadPoolExecutor(max_workers=6) as executor:
            foods = list(executor.map(lambda i: self.food(self.dish(session, i)), sorted(ids)))
        prefs = self.call(
            self.catalog,
            "GET",
            "api/v1/users/me/food-preferences",
            headers=self.headers(session),
        )
        completed = [
            str(p["planId"]) + ":" + str(i["itemId"])
            for p in raw_plans
            for entries in (p.get("mealsBySlot") or {}).values()
            for i in entries
            if i.get("status") == "COMPLETED"
        ]
        try:
            capabilities = self.call(
                self.optimizer, "GET", "api/v1/internal/optimizer/capabilities"
            )
        except HTTPException:
            capabilities = {}
        return {
            "profile": profile,
            "plans": plans,
            "foods": foods,
            "favorites": [str(d["id"]) for d in prefs.get("favoriteDishes") or []],
            "checkedShopping": self.state.get(session.account["id"], "checkedShopping", []),
            "checkIns": self.state.get(session.account["id"], "checkIns", []),
            "conversations": [],
            "completedMeals": completed,
            "capabilities": {
                "generate": True,
                "swap": capabilities.get("validatedSwap") is True
                and capabilities.get("planVersions") is True,
                "favoriteRemoval": False,
                "cookingTime": False,
                "atomicVersions": capabilities.get("planVersions") is True,
                "reason": "Backend cần bổ sung hợp đồng sinh/đổi có kiểm tra phiên bản, giữ thực đơn cũ và áp dụng đủ bộ lọc.",
            },
        }

    def generate(self, session, body):
        profile = self.profile(session)
        if profile["version"] != body.profileVersion:
            raise HTTPException(409, "Hồ sơ đã thay đổi. Hãy tải lại.")
        if (
            not profile["confirmed"]
            or profile["age"] < 18
            or profile["pregnant"]
            or profile["specialDiet"]
        ):
            raise HTTPException(422, "Cần hồ sơ đã xác nhận và thuộc phạm vi hỗ trợ.")
        if not body.snacks or body.maxMinutes or body.excludeRepeat:
            raise HTTPException(
                422,
                "Backend hiện hỗ trợ bốn bữa; chưa hỗ trợ lọc thời gian hoặc tùy chọn tránh lặp từ giao diện.",
            )
        excluded_dishes = []
        if profile["excludedFoods"]:
            try:
                capabilities = self.call(
                    self.optimizer, "GET", "api/v1/internal/optimizer/capabilities"
                )
            except HTTPException as error:
                if error.status_code != 404:
                    raise
                raise HTTPException(
                    503,
                    "Meal Optimizer đang chạy bản chưa hỗ trợ bộ lọc không ăn. Hãy khởi động lại service sau khi cập nhật code.",
                ) from None
            if (
                not isinstance(capabilities, dict)
                or capabilities.get("excludedDishIds") is not True
            ):
                raise HTTPException(
                    503,
                    "Meal Optimizer chưa xác nhận hỗ trợ bộ lọc không ăn. Chưa gửi yêu cầu sinh.",
                )
            listing = self.pages(self.catalog, "api/v1/dishes", session)
            with ThreadPoolExecutor(max_workers=6) as executor:
                details = list(executor.map(lambda d: self.dish(session, d["id"]), listing))
            excluded_dishes = resolve_excluded_dishes(profile["excludedFoods"], details)
        allergies = {
            "Hải sản": "ALLERGEN_SEAFOOD",
            "Trứng": "ALLERGEN_EGG",
            "Sữa": "ALLERGEN_DAIRY",
            "Đậu nành": "ALLERGEN_SOY",
            "Đậu phộng": "ALLERGEN_PEANUT",
        }
        tags = []
        for allergy in profile["allergies"]:
            tag = allergies.get(allergy, allergy)
            if tag not in set(allergies.values()):
                raise HTTPException(
                    422,
                    f"Backend chưa có mã dị ứng tương ứng: {allergy}. Không bỏ qua điều kiện này.",
                )
            tags.append(tag)
        target = body.target
        payload = {
            "planDate": body.date.isoformat(),
            "targetCaloriesKcal": target,
            "targetNetCarbG": round(target * 0.55 / 4, 1),
            "targetProteinG": round(target * 0.175 / 4, 1),
            "targetFatG": round(target * 0.275 / 9, 1),
            "patientContraindications": tags,
            "templateCode": "STANDARD_4_MEALS",
            "enableRandomPerturbation": True,
            "excludedDishIds": excluded_dishes,
        }
        # Guard the dangerous overwrite in the current Java implementation.
        # All BFF instances serialize on PostgreSQL; direct Java writes must be
        # restricted to the internal network until Java itself has versioning.
        with self.state.operation(session.account["id"]):
            existing = self.pages(self.optimizer, "api/v1/users/me/meal-plans", session)
            if any(p["planDate"] == body.date.isoformat() for p in existing):
                raise HTTPException(
                    409,
                    "Đã có thực đơn ngày này. Backend chưa hỗ trợ sinh lại có bảo toàn dữ liệu; thực đơn cũ được giữ nguyên.",
                )
            raw = self.call(
                self.optimizer,
                "POST",
                "api/v1/users/me/meal-plans/generate-daily",
                headers=self.headers(session),
                json=payload,
            )
            self.check_owner(session, raw)
            if any(
                int(item["dishId"]) in excluded_dishes
                for rows in (raw.get("mealsBySlot") or {}).values()
                for item in rows
            ):
                raise HTTPException(
                    502,
                    "Backend trả món nằm trong danh sách không ăn. Kết quả không được chấp nhận; cần kiểm tra lại bộ lọc backend.",
                )
            if raw["solverStatus"] not in {"OPTIMAL", "FEASIBLE"}:
                raise HTTPException(
                    422,
                    "Solver chưa trả phương án sử dụng được. Không hiển thị kết quả như thực đơn thành công.",
                )
            self.state.put(
                session.account["id"],
                "plan:" + str(raw["planId"]),
                {
                    "profileVersion": body.profileVersion,
                    "createdAt": datetime.now(UTC).isoformat(),
                },
            )
            return self.plan(session, raw)

    def snapshot(self, session, plan_id=None):
        if not plan_id:
            # Never silently use the first/historical plan when today's is absent.
            today = date.today().isoformat()
            plans = self.pages(self.optimizer, "api/v1/users/me/meal-plans", session)
            choices = [p for p in plans if p["planDate"] == today]
            if not choices:
                raise HTTPException(404, "Chưa có thực đơn hôm nay. Hãy chọn thực đơn cần hỏi.")
            raw = max(choices, key=lambda p: int(p["planId"]))
        else:
            raw = self.raw_plan(session, plan_id)
        plan = self.plan(session, raw)
        profile = self.profile(session)
        if not plan["items"] or raw["solverStatus"] not in {"OPTIMAL", "FEASIBLE"}:
            raise HTTPException(422, "Thực đơn chưa có kết quả solver sử dụng được.")
        items = []
        for item in plan["items"]:
            dish = self.dish(session, item["foodId"])
            recipe = dish.get("recipeBreakdown") or []
            items.append(
                {
                    "id": item["id"],
                    "recipeId": item["foodId"],
                    "recipeVersion": str(revision(dish)),
                    "name": next(
                        i["dishNameVi"]
                        for rows in raw["mealsBySlot"].values()
                        for i in rows
                        if str(i["itemId"]) == item["id"]
                    ),
                    "mealType": {"snack": "SNACK"}.get(item["meal"], item["meal"].upper()),
                    "portionId": item["id"],
                    "amount": item["servings"],
                    "unit": "serving",
                    "state": "unknown",
                    "nutritionBasis": "raw_ingredients_estimate",
                    "nutrients": {
                        camel(k): item["nutrition"][v] for k, v in MEAL_NUTRIENTS.items()
                    },
                    "ingredients": [
                        {"id": str(i["ingredientId"]), "name": i["ingredientNameVi"]}
                        for i in recipe
                    ],
                    "ingredientsComplete": bool(recipe),
                    "sourceRefs": [
                        "Food Catalog: " + (dish.get("code") or str(dish["id"])),
                        "Meal Optimizer: plan " + plan["id"],
                    ],
                }
            )
        # Zero/unknown ranges are not invented from the optimizer's point target.
        snapshot = {
            "dataMode": "http",
            "profile": {
                "profileVersion": profile["version"] or 1,
                "age": profile["age"] or None,
                "gender": profile["gender"] or None,
                "height": profile["height"] or None,
                "weight": profile["weight"] or None,
                "activityLevel": profile["activity"],
                "goal": profile["goal"],
                "allergies": profile["allergies"],
                "restrictedIngredients": profile["excludedFoods"],
                "scopeStatus": "unknown",
                "restrictionsResolved": False,
            },
            "plan": {
                "id": plan["id"],
                "version": plan["version"],
                "profileVersion": plan["profileVersion"] or 1,
                "catalogVersion": "java-catalog-unversioned",
                "date": plan["date"],
                "solverStatus": plan["solverStatus"],
                "validationPassed": False,
                "limitations": [
                    "Backend chưa cung cấp bằng chứng kiểm tra đầy đủ và phiên bản catalog.",
                    "Nguyên liệu theo catalog hiện tại; chưa có phiên bản công thức tại lúc sinh thực đơn.",
                ],
                "target": {
                    "version": str(plan["version"]),
                    "sourceRefs": ["Meal Optimizer targetCaloriesKcal"],
                    "bounds": {},
                    "pointTargets": {"energy_kcal": plan["target"]},
                },
                "items": items,
                "totals": {
                    camel(key): float(
                        sum(
                            (Decimal(str(i["nutrients"][camel(key)])) for i in items),
                            Decimal(0),
                        )
                    )
                    for key in MEAL_NUTRIENTS
                },
            },
        }
        return snapshot

    def close(self):
        with self.lock:
            for session in self.sessions.values():
                session.client.close()
            self.sessions.clear()
        self.catalog.close()
        self.optimizer.close()

    def checked_change(self, session, plan_id, body, *, preview):
        with self.state.operation(session.account["id"]):
            raw = self.raw_plan(session, plan_id)
            if not isinstance(raw.get("version"), int):
                raise HTTPException(
                    503, "Bộ đổi món trên máy chủ cần được cập nhật và khởi động lại."
                )
            if raw["version"] + 1 != body.baseVersion:
                raise HTTPException(409, "Thực đơn đã thay đổi. Hãy tải lại trước khi đổi món.")
            profile = self.profile(session)
            if (
                profile["version"] != body.profileVersion
                or self.plan(session, raw)["profileVersion"] != profile["version"]
            ):
                raise HTTPException(
                    409,
                    "Hồ sơ đã thay đổi từ lúc tạo thực đơn. Cần cập nhật thực đơn theo hồ sơ mới.",
                )
            if (
                not profile["confirmed"]
                or profile["pregnant"]
                or profile["specialDiet"]
                or profile["age"] < 18
            ):
                raise HTTPException(422, "Hồ sơ chưa xác nhận hoặc nằm ngoài phạm vi đổi món.")
            details = []
            if profile["excludedFoods"]:
                listing = self.pages(self.catalog, "api/v1/dishes", session)
                with ThreadPoolExecutor(max_workers=6) as executor:
                    details = list(executor.map(lambda d: self.dish(session, d["id"]), listing))
            exclusions = resolve_excluded_dishes(profile["excludedFoods"], details)
            known = {
                "Hải sản": "ALLERGEN_SEAFOOD",
                "Trứng": "ALLERGEN_EGG",
                "Sữa": "ALLERGEN_DAIRY",
                "Đậu nành": "ALLERGEN_SOY",
                "Đậu phộng": "ALLERGEN_PEANUT",
            }
            tags = [known.get(a, a) for a in profile["allergies"]]
            if any(t not in known.values() for t in tags):
                raise HTTPException(422, "Chưa ánh xạ đủ dị ứng để kiểm tra thay đổi.")
            scaled = body.servings * 2
            if not scaled.is_integer():
                raise HTTPException(422, "Khẩu phần cần theo bước nửa suất của danh mục.")
            if not preview and not body.previewSignature:
                raise HTTPException(422, "Cần xem trước phương án trước khi xác nhận.")
            payload = {
                "expectedVersion": raw["version"],
                "itemId": int(numeric_id(body.itemId)),
                "newDishId": int(numeric_id(body.foodId)),
                "newServingScaledX2": int(scaled),
                "excludedDishIds": exclusions,
                "contraindications": tags,
                "previewSignature": body.previewSignature,
            }
            result = self.call(
                self.optimizer,
                "POST",
                f"api/v1/users/me/meal-plans/{numeric_id(plan_id)}/change-{'preview' if preview else 'apply'}",
                headers=self.headers(session),
                json=payload,
            )
            self.check_owner(session, result)
            if result.get("validationPassed") is not True:
                raise HTTPException(502, "Máy chủ chưa xác nhận kết quả kiểm tra thay đổi.")
            return self.plan(session, result)


def create_team_router(team):
    router = APIRouter(prefix="/api")

    def session(request: Request):
        return team.resolve_token(request.cookies.get(COOKIE, ""))

    session_dependency = Depends(session)

    @router.post("/auth/login")
    @router.post("/auth/register")
    def login(body: Credentials, request: Request, response: Response):
        team.limiter.check("login:" + (request.client.host if request.client else "unknown"))
        token, user = team.login(body, register=request.url.path.endswith("/register"))
        old = request.cookies.get(COOKIE)
        with team.lock:
            previous = team.sessions.pop(old, None)
            if previous:
                with previous.lock:
                    previous.client.close()
        response.set_cookie(
            COOKIE,
            token,
            httponly=True,
            samesite="strict",
            secure=team.settings.app_env == "production",
            max_age=team.settings.team_session_seconds,
            path="/",
        )
        return {"user": user, "accessToken": token}

    @router.post("/auth/logout", status_code=204)
    def logout(request: Request):
        with team.lock:
            previous = team.sessions.pop(request.cookies.get(COOKIE), None)
            if previous:
                with previous.lock:
                    previous.client.close()
        response = Response(status_code=204)
        response.delete_cookie(COOKIE, path="/")
        return response

    @router.get("/workspace")
    def workspace(current=session_dependency):
        return team.workspace(current)

    @router.put("/me/profile")
    def profile(body: UIProfile, current=session_dependency):
        with team.state.operation(current.account["id"]):
            result = team.save_profile(current, body)
        return result

    @router.post("/meal-plans/generate")
    def generate(body: Generate, current=session_dependency):
        return team.generate(current, body)

    @router.put("/meal-plans/{plan_id}")
    def unsupported(plan_id: str, current=session_dependency):
        team.raw_plan(current, plan_id)
        raise HTTPException(
            503,
            "Backend chưa hỗ trợ thay đổi có kiểm tra ràng buộc và phiên bản. Thực đơn được giữ nguyên.",
        )

    @router.post("/meal-plans/{plan_id}/swap-preview")
    def preview_swap(plan_id: str, body: MealChange, current=session_dependency):
        return team.checked_change(current, plan_id, body, preview=True)

    @router.post("/meal-plans/{plan_id}/swap")
    def apply_swap(plan_id: str, body: MealChange, current=session_dependency):
        return team.checked_change(current, plan_id, body, preview=False)

    @router.patch("/meal-plans/{plan_id}/items/{item_id}/lock")
    def lock(plan_id: str, item_id: str, body: LockItem, current=session_dependency):
        raw = team.raw_plan(current, plan_id)
        if team.plan(current, raw)["version"] != body.baseVersion:
            raise HTTPException(409, "Thực đơn đã thay đổi. Hãy tải lại.")
        result = team.call(
            team.optimizer,
            "PATCH",
            f"api/v1/users/me/meal-plans/{numeric_id(plan_id)}/items/{numeric_id(item_id)}/lock",
            headers=team.headers(current),
            json={"isLocked": body.locked},
        )
        return team.plan(current, result)

    @router.delete("/meal-plans/{plan_id}", status_code=204)
    def delete_plan(plan_id: str, current=session_dependency):
        team.raw_plan(current, plan_id)
        team.call(
            team.optimizer,
            "DELETE",
            "api/v1/users/me/meal-plans/" + numeric_id(plan_id),
            headers=team.headers(current),
        )
        return Response(status_code=204)

    @router.put("/me/meal-logs", status_code=204)
    def meal_log(body: MealLog, current=session_dependency):
        parts = body.key.split(":")
        if len(parts) != 2:
            raise HTTPException(422, "Mã thực đơn/món không hợp lệ.")
        plan_id, item_id = map(numeric_id, parts)
        team.raw_plan(current, plan_id)
        team.call(
            team.optimizer,
            "PATCH",
            f"api/v1/users/me/meal-plans/{plan_id}/items/{item_id}/status",
            headers=team.headers(current),
            json={"status": "COMPLETED" if body.completed else "PLANNED"},
        )
        return Response(status_code=204)

    @router.put("/me/favorites/{dish_id}", status_code=204)
    def favorite(dish_id: str, current=session_dependency):
        team.call(
            team.catalog,
            "POST",
            f"api/v1/users/me/dishes/{numeric_id(dish_id)}/favorite",
            headers=team.headers(current),
        )
        return Response(status_code=204)

    @router.delete("/me/favorites/{dish_id}")
    def unfavorite(dish_id: str, current=session_dependency):
        raise HTTPException(503, "Food Catalog chưa có API bỏ yêu thích.")

    @router.put("/me/shopping-list", status_code=204)
    def shopping(body: Shopping, current=session_dependency):
        team.state.put(current.account["id"], "checkedShopping", sorted(set(body.checkedIds)))
        return Response(status_code=204)

    @router.post("/me/check-ins")
    def check_in(body: CheckIn, current=session_dependency):
        entry = body.model_dump(mode="json")
        team.state.check_in(current.account["id"], entry)
        return entry

    @router.delete("/me/check-ins/{entry_id}", status_code=204)
    def delete_check_in(entry_id: UUID, current=session_dependency):
        team.state.check_in(current.account["id"], delete_id=str(entry_id))
        return Response(status_code=204)

    return router
