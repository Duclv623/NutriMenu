from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from rag_app.config import Settings
from rag_app.main import create_app


@pytest.fixture
def secured(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    path = tmp_path / "test-public-key.pem"
    path.write_bytes(public)
    cfg = Settings(
        app_env="production",
        jwt_public_key_path=path,
        jwt_issuer="tv1-test",
        jwt_audience="rag-test",
        storage_dir=tmp_path,
        openai_api_key="",
        _env_file=None,
    )
    return cfg, key


def token(key, **overrides):
    now = datetime.now(UTC)
    claims = {
        "sub": "member-3",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "iss": "tv1-test",
        "aud": "rag-test",
        **overrides,
    }
    return jwt.encode(claims, key, algorithm="RS256")


def test_production_requires_verified_jwt(secured):
    cfg, key = secured
    with TestClient(create_app(cfg)) as client:
        assert client.get("/api/sessions").status_code == 401
        assert (
            client.get("/api/sessions", headers={"Authorization": "Bearer bogus"}).status_code
            == 401
        )
        good = {"Authorization": "Bearer " + token(key)}
        assert client.get("/api/sessions", headers=good).status_code == 200
        result = client.post("/api/chat", headers=good, json={"message": "xin chào"})
        # Verified authentication reaches the service, which still requires a key.
        assert result.status_code == 503
        assert "datn_owner" not in result.cookies


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "other"},
        {"iss": "other"},
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
        {"sub": ""},
    ],
)
def test_invalid_jwt_rejected(secured, overrides):
    cfg, key = secured
    with TestClient(create_app(cfg)) as client:
        assert (
            client.get(
                "/api/sessions", headers={"Authorization": "Bearer " + token(key, **overrides)}
            ).status_code
            == 401
        )


def test_wrong_signature_rejected(secured):
    cfg, _ = secured
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with TestClient(create_app(cfg)) as client:
        assert (
            client.get(
                "/api/sessions", headers={"Authorization": "Bearer " + token(other)}
            ).status_code
            == 401
        )
