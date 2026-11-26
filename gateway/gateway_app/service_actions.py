"""Allowlisted browser access to the Catalog and Optimizer controllers."""

import re
from contextlib import nullcontext
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import ValidationError

from gateway_app.integration import COOKIE, MealChange


PLANS = "users/me/meal-plans"
DIAGNOSTICS = "internal/optimizer"

# Each entry declares the upstream path, method and accepted query parameters.
CATALOG = (
    ("GET", "dishes", "role slot giLevel keyword page size"),
    ("GET", "dishes/{id}", ""),
    ("POST", "users/me/dishes/{id}/favorite", ""),
    ("POST", "users/me/dishes/{id}/dislike", ""),
    ("GET", "users/me/food-preferences", ""),
    ("GET", "dishes/{id}/calculate-serving", "multiplier"),
    ("POST", "dishes/{id}/safety-check", ""),
    ("GET", "dishes/{id}/alternatives", "mealSlot"),
    ("GET", "dishes/compare", "dish1 dish2"),
    ("POST", "users/me/custom-dishes", ""),
    ("POST", "internal/dishes/candidates", ""),
    ("GET", "internal/dishes/{id}/solver-dto", "activeOnly"),
    ("POST", "internal/dishes/batch", ""),
    ("POST", "admin/ingredients", ""),
    ("PUT", "admin/ingredients/{id}", ""),
    ("GET", "admin/ingredients", "group giLevel keyword page size"),
    ("DELETE", "admin/ingredients/{id}", ""),
    ("GET", "admin/yield-factors", ""),
    ("POST", "admin/yield-factors", ""),
    ("PATCH", "admin/dishes/{id}/status", ""),
    ("PATCH", "admin/dishes/{id}/popularity", ""),
    ("PUT", "admin/dishes/{id}/serving-rules", ""),
    ("PUT", "admin/dishes/{id}/medical-tags", ""),
    ("POST", "admin/ingredients/bulk-import", ""),
    ("POST", "admin/dishes/simulate-nutrition", ""),
    ("POST", "admin/dishes", ""),
    ("PUT", "admin/dishes/{id}", ""),
    ("POST", "admin/ingredients/{id}/recalculate-affected-dishes", ""),
    ("POST", "admin/diagnostics/solver-coverage", ""),
)
OPTIMIZER = (
    ("GET", PLANS, "page size"),
    ("GET", PLANS + "/{id}", ""),
    ("DELETE", PLANS + "/{id}", ""),
    ("PATCH", PLANS + "/{id}/items/{itemId}/status", ""),
    ("PATCH", PLANS + "/{id}/items/{itemId}/lock", ""),
    ("POST", PLANS + "/{id}/rate", ""),
    ("GET", PLANS + "/shopping-list", "fromDate toDate"),
    ("PUT", PLANS + "/{id}/items/{itemId}/manual-replace", ""),
    ("GET", PLANS + "/analytics", "days"),
    ("POST", PLANS + "/generate-from-profile", ""),
    ("POST", PLANS + "/generate-daily", ""),
    ("POST", PLANS + "/{id}/swap-dish", ""),
    ("POST", PLANS + "/{id}/rebalance-remaining", ""),
    ("POST", PLANS + "/generate-weekly", ""),
    ("POST", PLANS + "/{id}/change-preview", ""),
    ("POST", PLANS + "/{id}/change-apply", ""),
    ("GET", DIAGNOSTICS + "/capabilities", ""),
    ("GET", DIAGNOSTICS + "/users/me/recent-dishes", "days"),
    ("POST", DIAGNOSTICS + "/feasibility-check", ""),
    ("GET", "admin/optimizer/profiles", ""),
    ("POST", "admin/optimizer/profiles", ""),
    ("PUT", "admin/optimizer/profiles/{id}", ""),
    ("PATCH", "admin/optimizer/profiles/{id}/activate", ""),
    ("GET", "admin/optimizer/meal-templates", "templateCode"),
    ("PUT", "admin/optimizer/meal-templates/{id}", ""),
    ("GET", "admin/optimizer/audit-logs", "page size"),
    ("GET", "admin/optimizer/metrics/summary", ""),
    ("POST", "admin/optimizer/curated-plans", ""),
    ("GET", "admin/optimizer/curated-plans", ""),
    ("POST", "admin/optimizer/dry-run", ""),
    ("POST", "admin/optimizer/benchmark-profiles", ""),
    ("POST", "admin/optimizer/diagnostics/explain-infeasible", ""),
)


def compile_actions(actions):
    return [
        (method, template, re.compile(re.sub(
            r"\\\{(\w+)\\\}", r"(?P<\1>[1-9][0-9]{0,18})", re.escape(template)
        )), query.split())
        for method, template, query in actions
    ]


ACTIONS = {"catalog": compile_actions(CATALOG), "optimizer": compile_actions(OPTIMIZER)}
GENERATE = {"generate-daily", "generate-weekly", "generate-from-profile"}
MEAL_EDITS = {"manual-replace", "swap-dish", "rebalance-remaining"}


def object_body(payload):
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise HTTPException(422, "Dữ liệu yêu cầu phải là một đối tượng JSON.")
    return payload


def plan_date(value):
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() == value:
            return parsed
    except (TypeError, ValueError):
        pass
    raise HTTPException(422, "Nhập ngày theo định dạng YYYY-MM-DD.")


def merge_filter(body, key, additions, value_type):
    values = body.get(key, [])
    if not isinstance(values, list) or any(type(value) is not value_type for value in values):
        raise HTTPException(422, f"Danh sách {key} không hợp lệ.")
    body[key] = list(dict.fromkeys([*values, *additions]))


def optimizer_generation(team, session, action, payload, headers):
    body = object_body(payload).copy()
    profile_version = body.pop("profileVersion", None)
    profile = team.profile(session)
    team.require_meal_profile(profile, profile_version)
    tags = team.allergy_tags(profile)
    exclusions = team.catalog_exclusions(session, profile)
    if action == "generate-weekly":
        start = plan_date(body.get("startDate"))
        try:
            dates = {(start + timedelta(days=offset)).isoformat() for offset in range(7)}
        except OverflowError:
            raise HTTPException(422, "Ngày bắt đầu nằm ngoài phạm vi hỗ trợ.") from None
        daily = object_body(body.get("dailyTargetTemplate")).copy()
        daily["planDate"] = start.isoformat()
        merge_filter(daily, "patientContraindications", tags, str)
        merge_filter(daily, "excludedDishIds", exclusions, int)
        body["dailyTargetTemplate"] = daily
    else:
        dates = {plan_date(body.get("planDate")).isoformat()}
        if action == "generate-from-profile":
            if profile["gender"] not in {"male", "female"}:
                raise HTTPException(422, "Công thức của Optimizer hiện cần giới tính Nam hoặc Nữ trong hồ sơ.")
            activity = {
                "sedentary": "LIGHT", "light": "LIGHT", "moderate": "MODERATE",
                "active": "HEAVY", "very_active": "HEAVY",
            }
            body.update(
                gender=profile["gender"].upper(),
                heightMeters=float(profile["height"]) / 100,
                actualWeightKg=profile["weight"],
                activityLevel=activity[profile["activity"]],
            )
            merge_filter(body, "additionalAllergens", tags, str)
        else:
            merge_filter(body, "patientContraindications", tags, str)
        merge_filter(body, "excludedDishIds", exclusions, int)
    if exclusions:
        caps = team.call(team.optimizer, "GET", "api/v1/" + DIAGNOSTICS + "/capabilities")
        if not isinstance(caps, dict) or caps.get("profilePolicyActions") is not True:
            raise HTTPException(503, "Cần cập nhật Meal Optimizer để áp dụng danh sách không ăn.")
    team.ensure_empty_plan_dates(session, dates)
    result = team.call(team.optimizer, "POST", "api/v1/" + PLANS + "/" + action,
                       headers=headers, json=body)
    plans = result if action == "generate-weekly" else [
        result["optimalMealPlan"] if action == "generate-from-profile" else result
    ]
    for plan in plans:
        team.check_owner(session, plan)
        if any(item["dishId"] in exclusions for rows in plan["mealsBySlot"].values() for item in rows):
            raise HTTPException(502, "Optimizer trả về món nằm trong danh sách không ăn.")
        if action == "generate-weekly" and plan["solverStatus"] not in {"OPTIMAL", "FEASIBLE"}:
            continue  # Weekly returns a result for each day, including days without a solution.
        team.remember_plan(session, plan, profile_version)
    return result


def checked_change(team, session, plan_id, payload, preview):
    try:
        body = MealChange.model_validate(payload)
    except ValidationError as error:
        raise HTTPException(422, "Cần chọn món, khẩu phần và phiên bản thực đơn hợp lệ.") from error
    return team.checked_change(session, plan_id, body, preview=preview)


def create_service_actions_router(team):
    router = APIRouter(prefix="/api/service-actions")

    def session(request: Request):
        return team.resolve_token(request.cookies.get(COOKIE, ""))

    current_user = Depends(session)

    @router.get("/access")
    def access(current=current_user):
        return {"role": team.user(current)["role"]}

    @router.get("/recipe-ingredients")
    def recipe_ingredients(keyword: str = "", page: int = 0, current=current_user):
        result = team.call(
            team.catalog, "GET", "api/v1/admin/ingredients",
            headers=team.headers(current), params={"keyword": keyword, "page": page, "size": 20},
        )
        return {
            "content": [{"id": item["id"], "nameVi": item["nameVi"]} for item in result["content"]],
            "last": result["last"],
        }

    @router.api_route("/{service}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def dispatch(service: str, path: str, request: Request,
                 payload: Annotated[Any, Body()] = None, current=current_user):
        for method, template, pattern, allowed_query in ACTIONS.get(service, ()):
            match = pattern.fullmatch(path)
            if method == request.method and match:
                break
        else:
            raise HTTPException(404, "Không tìm thấy thao tác này.")
        if template.startswith("admin/") and current.account.get("role") != "ADMIN":
            raise HTTPException(403, "Cần tài khoản quản trị.")

        query = {key: request.query_params[key] for key in allowed_query if key in request.query_params}
        headers = team.headers(current)
        params = match.groupdict()
        action = template.rsplit("/", 1)[-1]
        if template == DIAGNOSTICS + "/users/me/recent-dishes":
            path = f"{DIAGNOSTICS}/users/{current.service_id}/recent-dishes"
        if template == "internal/dishes/{id}/solver-dto":
            query["userId"] = current.service_id
        if template in (PLANS + "/{id}/change-preview", PLANS + "/{id}/change-apply"):
            return checked_change(team, current, params["id"], payload, action == "change-preview")

        write_plan = service == "optimizer" and template.startswith(PLANS + "/") and method != "GET"
        lock = team.state.operation(current.account["id"]) if write_plan else nullcontext()
        with lock:
            if write_plan and action in GENERATE:
                return optimizer_generation(team, current, action, payload, headers)
            if write_plan:
                plan = team.raw_plan(current, params["id"])
                if action in MEAL_EDITS:
                    payload = object_body(payload).copy()
                    profile = team.profile(current)
                    team.require_meal_profile(profile, payload.pop("profileVersion", None))
                    if team.plan(current, plan)["profileVersion"] != profile["version"]:
                        raise HTTPException(409, "Thực đơn được tạo với phiên bản hồ sơ khác.")
                    if not isinstance(plan.get("version"), int) or payload.pop("baseVersion", None) != plan["version"] + 1:
                        raise HTTPException(409, "Thực đơn đã thay đổi. Hãy tải lại trước khi chỉnh sửa.")
                    caps = team.call(team.optimizer, "GET", "api/v1/" + DIAGNOSTICS + "/capabilities")
                    if not isinstance(caps, dict) or caps.get("profilePolicyActions") is not True:
                        raise HTTPException(503, "Cần cập nhật Meal Optimizer để áp dụng bộ lọc hồ sơ.")
                    payload["policy"] = {
                        "expectedVersion": plan["version"],
                        "contraindications": team.allergy_tags(profile),
                        "excludedDishIds": team.catalog_exclusions(current, profile),
                    }
            if template in {"dishes/{id}/safety-check", "internal/dishes/candidates",
                            DIAGNOSTICS + "/feasibility-check"}:
                payload = object_body(payload).copy()
                profile = team.profile(current)
                exclusions = team.catalog_exclusions(current, profile)
                tags = team.allergy_tags(profile)
                if action == "candidates":
                    payload["userId"] = current.service_id
                    merge_filter(payload, "excludedMedicalTags", tags, str)
                    merge_filter(payload, "excludedRecentDishIds", exclusions, int)
                else:
                    merge_filter(payload, "patientContraindications", tags, str)
                    if action == "feasibility-check":
                        merge_filter(payload, "excludedDishIds", exclusions, int)
            else:
                exclusions = []
            client = team.catalog if service == "catalog" else team.optimizer
            options = {"headers": headers, "params": query}
            if payload is not None and method in {"POST", "PUT", "PATCH"}:
                options["json"] = payload
            if action == "shopping-list":
                start, end = plan_date(query.get("fromDate")), plan_date(query.get("toDate"))
                if start > end:
                    raise HTTPException(422, "Ngày kết thúc phải từ ngày bắt đầu trở đi.")
                options["timeout"] = 55
            if action in {"benchmark-profiles", "solver-coverage"}:
                options["timeout"] = 55
            result = team.call(client, method, "api/v1/" + path, **options)
            if template == "dishes/{id}/safety-check" and int(params["id"]) in exclusions:
                result["isSafeForPatient"] = False
                result["detailedWarnings"].append("Món hoặc nguyên liệu nằm trong danh sách không ăn của hồ sơ.")
            if service == "optimizer" and template in {PLANS + "/{id}", PLANS} and method == "GET":
                for plan in result["content"] if template == PLANS else [result]:
                    team.check_owner(current, plan)
            if write_plan and result is not None:
                team.check_owner(current, result)
            return Response(status_code=204) if result is None else result

    return router
