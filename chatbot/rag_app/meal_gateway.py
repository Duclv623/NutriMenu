"""Explicit disabled/mock/HTTP meal integration; never falls back to fake meals."""

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
from pydantic import ValidationError

from rag_app.config import ROOT, Settings
from rag_app.meal_models import (
    MealPlan,
    MealSnapshot,
    NutritionProfile,
    PlanItem,
    SwapProposal,
    SwapRequest,
    sum_nutrients,
)

ERRORS = {
    "INTEGRATION_REQUIRED": (503, "Dịch vụ hồ sơ/thực đơn chưa được kết nối."),
    "AUTH_REQUIRED": (401, "Cần đăng nhập qua backend nhóm để đọc hồ sơ/thực đơn thật."),
    "NOT_FOUND": (404, "Không tìm thấy thực đơn hoặc đề xuất thuộc tài khoản này."),
    "STALE_PLAN": (409, "Thực đơn hoặc hồ sơ đã thay đổi. Hãy tải lại và đề xuất đổi món mới."),
    "PROFILE_INCOMPLETE": (422, "Cần xác nhận phạm vi hỗ trợ, dị ứng và danh sách loại trừ trước khi đổi món."),
    "OUT_OF_SCOPE": (422, "Hồ sơ nằm ngoài phạm vi sinh/đổi thực đơn của hệ thống."),
    "DATA_INCOMPLETE": (422, "Chưa đủ dữ liệu hoặc kết quả kiểm tra để chấp nhận phương án này."),
    "NO_FEASIBLE_PLAN": (422, "Chưa có phương án đổi món đáp ứng các điều kiện hiện tại. Thực đơn cũ được giữ nguyên."),
    "SOLVER_UNRESOLVED": (503, "Bộ giải chưa xác định được phương án; chưa thể kết luận không có nghiệm."),
    "MODEL_INVALID": (503, "Dịch vụ tối ưu báo mô hình chưa hợp lệ."),
    "PROPOSAL_EXPIRED": (409, "Đề xuất đã hết hạn hoặc đã áp dụng. Hãy tạo đề xuất mới."),
    "PROPOSAL_CANCELLED": (409, "Phương án này đã dừng trong cuộc trò chuyện. Hãy cập nhật hồ sơ nếu cần rồi tạo phương án mới."),
    "SERVICE_UNAVAILABLE": (503, "Dịch vụ thực đơn chưa phản hồi hợp lệ. Không thay bằng dữ liệu mẫu."),
}


class MealServiceError(Exception):
    def __init__(self, code):
        self.code = code if isinstance(code, str) and code in ERRORS else "SERVICE_UNAVAILABLE"
        self.status_code, self.message = ERRORS[self.code]
        super().__init__(self.message)


def require_editable(snapshot):
    profile, plan = snapshot.profile, snapshot.plan
    if profile.scope_status == "out_of_scope" or profile.age is not None and profile.age < 18:
        raise MealServiceError("OUT_OF_SCOPE")
    if profile.scope_status != "eligible" or profile.allergies is None or profile.restricted_ingredients is None or not profile.restrictions_resolved:
        raise MealServiceError("PROFILE_INCOMPLETE")
    if profile.profile_version != plan.profile_version:
        raise MealServiceError("STALE_PLAN")


def check_plan(plan, profile, *, mock=False):
    """Additional contract checks, not a replacement for TV2's full validator."""
    errors = []
    if plan.solver_status in {"INFEASIBLE", "UNKNOWN", "MODEL_INVALID"}:
        return [plan.solver_status]
    if not mock and plan.solver_status not in {"OPTIMAL", "FEASIBLE"}:
        errors.append("solver_status")
    if not plan.validation_passed:
        errors.append("backend_validation")
    if not {"BREAKFAST", "LUNCH", "DINNER"}.issubset({item.meal_type for item in plan.items}):
        errors.append("main_meals")
    excluded = set(profile.excluded_ingredient_ids)
    for item in plan.items:
        if not item.ingredients_complete:
            errors.append("ingredients_incomplete")
        if excluded.intersection(i.id for i in item.ingredients):
            errors.append("excluded_ingredient")
        if not mock and (item.nutrition_basis != "as_consumed" or item.state == "unknown"):
            errors.append("nutrition_basis")
        if any(getattr(item.nutrients, key) is None for key in ("energy_kcal", "carbohydrate_g", "protein_g", "fat_g")):
            errors.append("core_nutrients")
    for key, bounds in plan.target.bounds.items():
        value = getattr(plan.totals, key)
        if value is None or not in_range(Decimal(str(value)), bounds):
            errors.append(key)
    energy = plan.totals.energy_kcal
    for key, bounds in plan.target.energy_percent.items():
        value = getattr(plan.totals, key)
        if energy is None or energy <= 0 or value is None:
            errors.append(key + "_percent")
        else:
            percent = Decimal(str(value)) * (9 if key == "fat_g" else 4) * 100 / Decimal(str(energy))
            if not in_range(percent, bounds):
                errors.append(key + "_percent")
    return list(dict.fromkeys(errors))


def in_range(value, bounds):
    return (bounds.minimum is None or value >= Decimal(str(bounds.minimum))) and (
        bounds.maximum is None or value <= Decimal(str(bounds.maximum)))


def validate_proposal(snapshot, request, proposal):
    require_editable(snapshot)
    before, after = snapshot.plan, proposal.plan
    if (request.plan_id != before.id or request.base_version != before.version
            or proposal.plan_id != before.id or proposal.base_version != before.version
            or proposal.profile_version != snapshot.profile.profile_version
            or proposal.changed_item_id != request.item_id or after.id != before.id
            or after.version != before.version + 1 or after.profile_version != before.profile_version
            or after.date != before.date or after.catalog_version != before.catalog_version
            or after.target != before.target or proposal.expires_at <= time.time()
            or proposal.data_mode != snapshot.data_mode):
        raise MealServiceError("STALE_PLAN")
    old = {item.id: item for item in before.items}
    new = {item.id: item for item in after.items}
    if request.item_id not in old or old.keys() != new.keys():
        raise MealServiceError("DATA_INCOMPLETE")
    if old[request.item_id].meal_type != new[request.item_id].meal_type or any(
            old[key] != new[key] for key in old if key != request.item_id):
        raise MealServiceError("DATA_INCOMPLETE")
    if check_plan(after, snapshot.profile, mock=snapshot.data_mode == "mock"):
        raise MealServiceError("DATA_INCOMPLETE")


class DisabledMealGateway:
    mode = "disabled"

    def status(self):
        return {"mode": self.mode, "configured": False, "connected": False}

    def snapshot(self, owner, authorization=None, plan_id=None):
        raise MealServiceError("INTEGRATION_REQUIRED")

    def preview(self, owner, request, authorization=None):
        raise MealServiceError("INTEGRATION_REQUIRED")

    def apply(self, owner, request, authorization=None):
        raise MealServiceError("INTEGRATION_REQUIRED")

    def close(self):
        pass


class MockMealGateway(DisabledMealGateway):
    """Per-owner volatile fixtures. This does NOT run CP-SAT or model cooking."""
    mode = "mock"

    def __init__(self, dataset="mathematical"):
        self.named_demo = dataset == "named"
        if self.named_demo:
            from rag_app.demo_menu import named_demo_fixture
            self.fixture = named_demo_fixture()
        else:
            self.fixture = json.loads((ROOT / "data/fixtures/meal_demo.json").read_text(encoding="utf-8"))
        self.states = {}
        self.proposals = {}
        self.lock = threading.RLock()

    def status(self):
        return {"mode": self.mode, "configured": True, "connected": False}

    def _prune(self):
        now = time.time()
        self.states = {key: value for key, value in self.states.items() if now - value[0] < 1800}
        self.proposals = {key: value for key, value in self.proposals.items() if value[1].expires_at > now}

    def snapshot(self, owner, authorization=None, plan_id=None):
        with self.lock:
            self._prune()
            if owner not in self.states:
                if plan_id:
                    raise MealServiceError("NOT_FOUND")
                if len(self.states) >= 200:
                    del self.states[min(self.states, key=lambda key: self.states[key][0])]
                profile = NutritionProfile.model_validate(self.fixture["profile"])
                items = [PlanItem.model_validate(row) for row in self.fixture["items"]]
                plan = MealPlan(
                    id=str(uuid4()), version=1, profile_version=profile.profile_version,
                    catalog_version="named-demo-v1" if self.named_demo else "fictional-v1", date=datetime.now(timezone(timedelta(hours=7))).date(),
                    solver_status="NOT_RUN", validation_passed=not self.named_demo,
                    checked_constraints=["Cộng số dinh dưỡng của các phần ăn mẫu; chưa kiểm tra phù hợp cá nhân" if self.named_demo else "Kiểm số học dữ liệu mẫu; không chạy CP-SAT"],
                    limitations=[self.fixture["notice"]] if self.named_demo else [self.fixture["notice"], "Chưa có dữ liệu xơ, natri và cơ sở sống/chín thực tế."],
                    target=self.fixture["target"], items=items, totals=sum_nutrients(items),
                )
                self.states[owner] = (time.time(), MealSnapshot(data_mode="mock", profile=profile, plan=plan))
            value = self.states[owner][1]
            if plan_id and value.plan.id != plan_id:
                raise MealServiceError("NOT_FOUND")
            return value.model_copy(deep=True)

    def update_profile(self, owner, body):
        with self.lock:
            snapshot = self.snapshot(owner)
            if body.base_version != snapshot.profile.profile_version:
                raise MealServiceError("STALE_PLAN")
            values = body.profile.model_dump(by_alias=False)
            # Client cannot assert backend eligibility or resolve arbitrary real allergies.
            values.update(profile_version=snapshot.profile.profile_version + 1,
                          scope_status="out_of_scope" if body.profile.age is not None and body.profile.age < 18 else body.profile.scope_status if body.profile.age else "unknown",
                          restrictions_resolved=body.profile.allergies == [] and body.profile.restricted_ingredients == [],
                          excluded_ingredient_ids=[])
            profile = NutritionProfile.model_validate(values)
            value = snapshot.model_copy(update={"profile": profile})
            if self.named_demo:
                # This fixed illustrative menu is not recalculated or prescribed for the profile.
                value = value.model_copy(update={"plan": snapshot.plan.model_copy(update={
                    "profile_version": profile.profile_version, "version": snapshot.plan.version + 1})})
            self.states[owner] = (time.time(), value)
            self.proposals = {key: row for key, row in self.proposals.items() if row[0] != owner}
            return value.model_copy(deep=True)

    def refresh_demo_plan(self, owner):
        with self.lock:
            snapshot = self.snapshot(owner)
            profile = snapshot.profile
            if profile.scope_status != "eligible":
                raise MealServiceError("OUT_OF_SCOPE")
            if not profile.restrictions_resolved:
                raise MealServiceError("PROFILE_INCOMPLETE")
            if check_plan(snapshot.plan, profile, mock=True):
                raise MealServiceError("DATA_INCOMPLETE")
            plan = snapshot.plan.model_copy(update={"profile_version": profile.profile_version, "version": snapshot.plan.version + 1})
            value = snapshot.model_copy(update={"plan": plan})
            self.states[owner] = (time.time(), value)
            return value.model_copy(deep=True)

    def preview(self, owner, request, authorization=None):
        with self.lock:
            snapshot = self.snapshot(owner, plan_id=request.plan_id)
            require_editable(snapshot)
            if request.base_version != snapshot.plan.version:
                raise MealServiceError("STALE_PLAN")
            original = next((item for item in snapshot.plan.items if item.id == request.item_id), None)
            if original is None:
                raise MealServiceError("NOT_FOUND")
            alternatives = [PlanItem.model_validate(row) for row in self.fixture["alternatives"]]
            # Explicit demo IDs can request the infeasible example D. No free-form
            # ingredient changes are claimed: the UI labels fixed demo candidates.
            desired = next((item.recipe_id for item in alternatives if item.recipe_id.lower() in request.instruction.lower()), None)
            for replacement in alternatives:
                if replacement.meal_type != original.meal_type or replacement.recipe_id == original.recipe_id or desired and desired != replacement.recipe_id:
                    continue
                replacement = replacement.model_copy(update={"id": original.id})
                items = [replacement if item.id == original.id else item for item in snapshot.plan.items]
                values = snapshot.plan.model_dump(by_alias=False)
                values.update(version=snapshot.plan.version + 1, items=items, totals=sum_nutrients(items))
                plan = MealPlan.model_validate(values)
                if check_plan(plan, snapshot.profile, mock=True):
                    continue
                proposal = SwapProposal(
                    id=uuid4(), plan_id=plan.id, base_version=request.base_version,
                    profile_version=snapshot.profile.profile_version, changed_item_id=original.id,
                    expires_at=time.time() + 300, data_mode="mock", plan=plan,
                )
                validate_proposal(snapshot, request, proposal)
                if len(self.proposals) >= 500:
                    del self.proposals[min(self.proposals, key=lambda key: self.proposals[key][1].expires_at)]
                self.proposals[str(proposal.id)] = (owner, proposal.model_copy(deep=True))
                return proposal
            raise MealServiceError("NO_FEASIBLE_PLAN")

    def apply(self, owner, request, authorization=None):
        with self.lock:
            entry = self.proposals.get(str(request.proposal_id))
            if entry is None or entry[0] != owner:
                raise MealServiceError("NOT_FOUND")
            proposal = entry[1]
            if proposal.expires_at <= time.time():
                raise MealServiceError("PROPOSAL_EXPIRED")
            if request.plan_id != proposal.plan_id or request.base_version != proposal.base_version:
                raise MealServiceError("STALE_PLAN")
            snapshot = self.snapshot(owner, plan_id=request.plan_id)
            validate_proposal(snapshot, SwapRequest(
                plan_id=request.plan_id, base_version=request.base_version,
                item_id=proposal.changed_item_id, instruction="Apply previously reviewed proposal"), proposal)
            value = snapshot.model_copy(update={"plan": proposal.plan.model_copy(deep=True)})
            self.states[owner] = (time.time(), value)
            del self.proposals[str(request.proposal_id)]
            return value.model_copy(deep=True)


class HttpMealGateway(DisabledMealGateway):
    mode = "http"

    def __init__(self, settings, transport=None):
        self.client = httpx.Client(
            base_url=settings.meal_api_base_url.rstrip("/") + "/", timeout=settings.meal_api_timeout,
            follow_redirects=False, trust_env=False, transport=transport,
        )
        self.last_success = 0

    def status(self):
        return {"mode": self.mode, "configured": True, "connected": time.monotonic() - self.last_success < 60 if self.last_success else False}

    def _request(self, method, path, authorization, model, **kwargs):
        if not authorization or not authorization.startswith("Bearer ") or not authorization[7:].strip() or "\n" in authorization or "\r" in authorization:
            raise MealServiceError("AUTH_REQUIRED")
        try:
            response = self.client.request(method, path, headers={"Authorization": authorization}, **kwargs)
            if response.status_code >= 300:
                code = {401: "AUTH_REQUIRED", 403: "NOT_FOUND", 404: "NOT_FOUND", 409: "STALE_PLAN"}.get(response.status_code, "SERVICE_UNAVAILABLE")
                if response.status_code in {409, 422}:
                    try:
                        code = response.json().get("code", code)
                    except (ValueError, AttributeError):
                        pass
                raise MealServiceError(code)
            value = model.model_validate(response.json())
            if value.data_mode != "http":
                raise MealServiceError("SERVICE_UNAVAILABLE")
            if isinstance(value, MealSnapshot) and value.plan.solver_status not in {"OPTIMAL", "FEASIBLE"}:
                raise MealServiceError({"INFEASIBLE": "NO_FEASIBLE_PLAN", "UNKNOWN": "SOLVER_UNRESOLVED", "MODEL_INVALID": "MODEL_INVALID"}.get(value.plan.solver_status, "DATA_INCOMPLETE"))
            self.last_success = time.monotonic()
            return value
        except (httpx.HTTPError, ValueError, ValidationError) as error:
            raise MealServiceError("SERVICE_UNAVAILABLE") from error

    def snapshot(self, owner, authorization=None, plan_id=None):
        return self._request("GET", "me/meal-context", authorization, MealSnapshot,
                             params={"planId": plan_id} if plan_id else {})

    def preview(self, owner, request, authorization=None):
        snapshot = self.snapshot(owner, authorization, request.plan_id)
        require_editable(snapshot)
        if snapshot.plan.version != request.base_version:
            raise MealServiceError("STALE_PLAN")
        proposal = self._request("POST", "me/meal-plans/swap-preview", authorization, SwapProposal,
                                 json=request.model_dump(mode="json"))
        validate_proposal(snapshot, request, proposal)
        return proposal

    def apply(self, owner, request, authorization=None):
        # The upstream owns proposals and must atomically revalidate profile,
        # plan version, ownership and expiry before committing (no POST retries).
        before = self.snapshot(owner, authorization, request.plan_id)
        require_editable(before)
        if before.plan.version != request.base_version:
            raise MealServiceError("STALE_PLAN")
        result = self._request("POST", "me/meal-plans/apply-swap", authorization, MealSnapshot,
                               json=request.model_dump(mode="json"))
        if result.plan.id != request.plan_id or result.plan.version != request.base_version + 1 or result.profile.profile_version != before.profile.profile_version or result.plan.profile_version != result.profile.profile_version or check_plan(result.plan, result.profile):
            raise MealServiceError("SERVICE_UNAVAILABLE")
        return result

    def close(self):
        self.client.close()


def create_meal_gateway(settings: Settings):
    if settings.meal_service_mode == "mock":
        return MockMealGateway(settings.meal_demo_dataset)
    if settings.meal_service_mode == "http":
        return HttpMealGateway(settings)
    return DisabledMealGateway()
