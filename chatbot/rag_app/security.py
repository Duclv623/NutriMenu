import secrets
import threading
import time
from collections import deque
from uuid import UUID, uuid4

import httpx
import jwt
from fastapi import HTTPException, Request, Response

from rag_app.config import Settings


def identity(request: Request, response: Response, settings: Settings) -> str:
    if settings.gateway_auth_url:
        supplied = request.headers.get('x-gateway-key', '')
        expected = settings.gateway_service_key.get_secret_value()
        authorization = request.headers.get('authorization', '')
        if not supplied or not secrets.compare_digest(supplied, expected) or not authorization.startswith('Bearer '):
            raise HTTPException(401, 'Cần đăng nhập qua API Gateway.')
        try:
            with httpx.Client(timeout=settings.meal_api_timeout, trust_env=False, follow_redirects=False) as client:
                result = client.get(settings.gateway_auth_url,
                                    headers={'Authorization': authorization, 'X-Gateway-Key': expected})
            if result.status_code in {401, 403}:
                raise HTTPException(401, 'Phiên đăng nhập đã hết hạn.')
            if result.status_code != 200:
                raise HTTPException(503, 'Dịch vụ xác thực chưa sẵn sàng.')
            owner = result.json()['owner']
            if not isinstance(owner, str) or not owner.startswith('user:'):
                raise ValueError('Invalid owner')
            UUID(owner[5:])
            request.state.gateway_authorization = authorization
            return owner
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise HTTPException(503, 'Không xác minh được danh tính từ API Gateway.') from None
    if settings.app_env == "production":
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Cần Bearer JWT của User Service")
        try:
            payload = jwt.decode(
                authorization[7:],
                settings.jwt_public_key_path.read_text(encoding="utf-8"),
                algorithms=["RS256"],
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
            subject = payload["sub"]
            if not isinstance(subject, str) or not subject or len(subject) > 200:
                raise ValueError("sub không hợp lệ")
            return "jwt:" + subject
        except (jwt.PyJWTError, ValueError, OSError) as error:
            raise HTTPException(401, "JWT không hợp lệ hoặc hết hạn") from error
    # Anonymous development only. Never enable this on a public server.
    value = request.cookies.get("datn_owner", "")
    try:
        UUID(value)
    except ValueError:
        value = str(uuid4())
        response.set_cookie("datn_owner", value, httponly=True, samesite="strict", max_age=604800)
    return "dev:" + value


class RateLimiter:
    def __init__(self, per_minute: int):
        self.limit = per_minute
        self.events: dict[str, deque] = {}
        self.lock = threading.Lock()

    def check(self, key: str, now: float | None = None):
        now = time.monotonic() if now is None else now
        with self.lock:
            # Bound memory even if many anonymous clients arrive.
            self.events = {k: v for k, v in self.events.items() if v and v[-1] > now - 60}
            if key not in self.events and len(self.events) >= 10000:
                raise HTTPException(429, "Máy chủ bận; thử lại sau", headers={"Retry-After": "60"})
            events = self.events.setdefault(key, deque())
            while events and events[0] <= now - 60:
                events.popleft()
            if len(events) >= self.limit:
                raise HTTPException(
                    429, "Quá nhiều câu hỏi; thử lại sau", headers={"Retry-After": "60"}
                )
            events.append(now)
