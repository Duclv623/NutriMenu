from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )
    app_env: str = "development"
    team_user_url: str = Field(default="http://127.0.0.1:8083", validation_alias="USER_SERVICE_URL")
    team_catalog_url: str = Field(
        default="http://127.0.0.1:8081", validation_alias="FOOD_CATALOG_URL"
    )
    team_optimizer_url: str = Field(
        default="http://127.0.0.1:8082", validation_alias="MEAL_OPTIMIZER_URL"
    )
    chatbot_url: str = "http://127.0.0.1:8000"
    team_session_seconds: int = Field(
        default=28800, ge=300, le=86400, validation_alias="SESSION_SECONDS"
    )
    meal_api_timeout: float = Field(default=8, ge=1, le=30, validation_alias="UPSTREAM_TIMEOUT")
    postgres_dsn: SecretStr = SecretStr("")
    postgres_schema: str = Field(default="gateway", pattern=r"^[a-z_][a-z0-9_]{0,62}$")
    legacy_schema: str = Field(default="chatbot", pattern=r"^[a-z_][a-z0-9_]{0,62}$")
    import_legacy_state: bool = False
    gateway_service_key: SecretStr = SecretStr("")
    public_origins: str = (
        "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8080,http://localhost:8080"
    )

    @model_validator(mode="after")
    def validate_urls(self):
        if self.app_env not in {"development", "production"}:
            raise ValueError("APP_ENV must be development or production")
        for name in (
            "team_user_url",
            "team_catalog_url",
            "team_optimizer_url",
            "chatbot_url",
        ):
            url = urlparse(getattr(self, name))
            if (
                url.scheme not in {"http", "https"}
                or not url.netloc
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.path not in {"", "/"}
            ):
                raise ValueError(f"Invalid service origin: {name}")
            if self.app_env == "production" and url.scheme != "https":
                raise ValueError("Production upstreams require TLS")
        if len(self.gateway_service_key.get_secret_value()) < 32:
            raise ValueError("Set a random GATEWAY_SERVICE_KEY with at least 32 characters")
        if self.app_env == "production" and any(
            not value.strip().startswith("https://") for value in self.public_origins.split(",")
        ):
            raise ValueError("Production PUBLIC_ORIGINS must use HTTPS")
        return self
