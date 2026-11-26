import re
import secrets
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from gateway_app.config import GatewaySettings
from gateway_app.database import GatewayDatabase
from gateway_app.integration import COOKIE, TeamIntegration, create_team_router
from gateway_app.service_actions import create_service_actions_router


def internal_session(team, request):
    expected = team.settings.gateway_service_key.get_secret_value()
    supplied = request.headers.get("x-gateway-key", "")
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(403, "Yêu cầu nội bộ không hợp lệ.")
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Thiếu phiên đã xác thực.")
    return team.resolve_token(auth[7:])


def create_app(settings=None, *, integration=None):
    settings = settings or GatewaySettings()
    team = integration or TeamIntegration(settings, GatewayDatabase(settings))
    proxy = httpx.AsyncClient(
        base_url=settings.chatbot_url.rstrip("/") + "/",
        timeout=95,
        trust_env=False,
        follow_redirects=False,
    )

    @asynccontextmanager
    async def lifespan(app):
        yield
        team.close()
        await proxy.aclose()

    app = FastAPI(title="NutriGuide API Gateway", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.integration = team
    app.include_router(create_team_router(team))
    app.include_router(create_service_actions_router(team))

    @app.middleware("http")
    async def origin_and_headers(request, call_next):
        origin = request.headers.get("origin")
        allowed = {value.strip() for value in settings.public_origins.split(",")}
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and origin
            and origin not in allowed
        ):
            return JSONResponse({"detail": "Origin không được phép."}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/api/health")
    def health():
        # Liveness only; does not claim all Java/DB dependencies are ready.
        return {"service": "gateway", "status": "UP", "check": "liveness"}

    def internal(request: Request):
        return internal_session(team, request)

    internal_dependency = Depends(internal)

    @app.get("/api/internal/identity")
    def identity(current=internal_dependency):
        return {"owner": "user:" + current.account["id"]}

    @app.get("/api/internal/me/meal-context")
    def meal_context(planId: str | None = None, current=internal_dependency):
        return team.snapshot(current, planId)

    @app.post("/api/internal/me/meal-plans/swap-preview")
    @app.post("/api/internal/me/meal-plans/apply-swap")
    def unsupported_edit(current=internal_dependency):
        raise HTTPException(
            503,
            detail={
                "code": "INTEGRATION_REQUIRED",
                "message": "Backend chưa có hợp đồng đổi món nguyên tử có validator.",
            },
        )

    @app.api_route(
        "/api/chatbot/{path:path}", methods=["GET", "POST", "DELETE"], include_in_schema=False
    )
    async def chatbot(path: str, request: Request):
        patterns = {
            "GET": r"(?:status|meal-context|sessions(?:/[0-9a-fA-F-]{36})?|(?:documents|foods|supplements)(?:/[\w.:-]+(?:/(?:pdf|preview|original))?)?)",
            "POST": r"(?:chat|feedback|meal-plans/apply-swap)",
            "DELETE": r"sessions/[0-9a-fA-F-]{36}",
        }
        if not re.fullmatch(patterns[request.method], path):
            raise HTTPException(404, "Không có API chatbot này.")
        token = request.cookies.get(COOKIE, "")
        if path != "status":
            await run_in_threadpool(team.resolve_token, token)
        body = await request.body()
        if len(body) > 65536:
            raise HTTPException(413, "Yêu cầu quá lớn.")
        headers = {
            "Accept": request.headers.get("accept", "application/json"),
            "Content-Type": request.headers.get("content-type", "application/json"),
            "X-Gateway-Key": settings.gateway_service_key.get_secret_value(),
            "Authorization": "Bearer " + token,
            "Origin": settings.chatbot_url.rstrip("/"),
        }
        try:
            upstream = await proxy.request(
                request.method,
                "api/" + path,
                params=request.query_params,
                headers=headers,
                content=body,
            )
        except httpx.HTTPError:
            raise HTTPException(
                503, "Chatbot chưa phản hồi. Không sử dụng câu trả lời mẫu."
            ) from None
        preserved = {
            k: v
            for k, v in upstream.headers.items()
            if k.lower() in {"content-type", "content-disposition", "retry-after", "x-request-id"}
        }
        return Response(upstream.content, status_code=upstream.status_code, headers=preserved)

    return app
