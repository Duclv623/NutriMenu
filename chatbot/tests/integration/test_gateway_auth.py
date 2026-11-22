from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from rag_app.config import Settings
from rag_app.security import identity

KEY = "test-only-gateway-key-with-more-than-32-characters"


def config():
    return Settings(
        _env_file=None,
        gateway_auth_url="http://gateway.test/api/internal/identity",
        gateway_service_key=KEY,
    )


def request(key=KEY):
    return Request(
        {
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer opaque-session"),
                (b"x-gateway-key", key.encode()),
            ],
        }
    )


def mock_identity(monkeypatch, status, payload):
    original = httpx.Client

    def handler(req):
        assert req.headers["x-gateway-key"] == KEY
        assert req.headers["authorization"] == "Bearer opaque-session"
        return httpx.Response(status, json=payload)

    monkeypatch.setattr(
        "rag_app.security.httpx.Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )


def test_identity_is_resolved_by_gateway_not_client_user_header(monkeypatch):
    owner = "user:" + str(uuid4())
    mock_identity(monkeypatch, 200, {"owner": owner})
    req = request()
    assert identity(req, Response(), config()) == owner
    assert req.state.gateway_authorization == "Bearer opaque-session"


def test_client_cannot_forge_gateway_identity():
    with pytest.raises(HTTPException) as error:
        identity(request("forged-key"), Response(), config())
    assert error.value.status_code == 401


def test_revoked_gateway_session_is_denied(monkeypatch):
    mock_identity(monkeypatch, 401, {"detail": "expired"})
    with pytest.raises(HTTPException) as error:
        identity(request(), Response(), config())
    assert error.value.status_code == 401


def test_unavailable_auth_does_not_fall_back_to_anonymous_owner(monkeypatch):
    mock_identity(monkeypatch, 503, {})
    with pytest.raises(HTTPException) as error:
        identity(request(), Response(), config())
    assert error.value.status_code == 503
